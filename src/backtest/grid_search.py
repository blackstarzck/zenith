"""
그리드 서치 러너.
전략 파라미터 조합을 체계적으로 평가하여 최적 조합을 탐색합니다.

사용법:
    grid = {"atr_stop_multiplier": [1.5, 2.0, 2.5], "rsi_oversold": [25, 30, 35]}
    results = run_grid_search(df, grid, symbol="KRW-BTC")
    runner = GridSearchRunner(GridSearchConfig(param_grid=grid))
    print(runner.summary(results))
"""

from __future__ import annotations

import itertools
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field, replace, fields
from typing import Any

import pandas as pd

from src.backtest.engine import BacktestEngine, BacktestResult
from src.config import RiskParams, StrategyParams

logger = logging.getLogger(__name__)

# 랭킹 시 오름차순 정렬이 필요한 지표 (낮을수록 좋은 값)
_ASCENDING_METRICS = {"max_drawdown_pct", "max_drawdown_amount"}

# BacktestResult에서 랭킹 가능한 숫자 필드
_RANKABLE_FIELDS: set[str] = {
    f.name
    for f in fields(BacktestResult)
    if f.type in ("float", "int")
    and f.name not in ("initial_balance", "final_balance")
}


@dataclass
class GridSearchConfig:
    """그리드 서치 설정."""

    param_grid: dict[str, list[Any]]
    initial_balance: float = 1_000_000
    risk_params: RiskParams | None = None
    max_workers: int | None = None  # None → os.cpu_count()
    ranking_metric: str = "sharpe_ratio"


@dataclass
class GridSearchResult:
    """개별 파라미터 조합의 백테스트 결과."""

    params: dict[str, Any]
    backtest_result: BacktestResult
    rank: int = 0


# ── 모듈 레벨 워커 (ProcessPoolExecutor pickle 호환) ──────────────


def _run_single_backtest(
    params_dict: dict[str, Any],
    df: pd.DataFrame,
    symbol: str,
    initial_balance: float,
    risk_params: RiskParams | None,
) -> GridSearchResult | None:
    """단일 파라미터 조합에 대해 백테스트를 실행합니다.

    ProcessPoolExecutor에서 pickle 가능하도록 모듈 레벨에 정의합니다.
    """
    try:
        strategy_params = replace(StrategyParams(), **params_dict)
        engine = BacktestEngine(
            initial_balance=initial_balance,
            strategy_params=strategy_params,
            risk_params=risk_params,
        )
        result = engine.run(df, symbol=symbol, verbose=False)
        return GridSearchResult(params=params_dict, backtest_result=result)
    except Exception as exc:
        logger.warning(
            "파라미터 조합 실패 %s: %s", params_dict, exc,
        )
        return None


class GridSearchRunner:
    """전략 파라미터 그리드 서치 러너.

    사용법:
        config = GridSearchConfig(
            param_grid={"atr_stop_multiplier": [1.5, 2.0, 2.5]},
            ranking_metric="sharpe_ratio",
        )
        runner = GridSearchRunner(config)
        results = runner.run(df, symbol="KRW-BTC")
        print(runner.summary(results))
    """

    def __init__(self, config: GridSearchConfig) -> None:
        if config.ranking_metric not in _RANKABLE_FIELDS:
            raise ValueError(
                f"유효하지 않은 랭킹 지표: '{config.ranking_metric}'. "
                f"사용 가능: {sorted(_RANKABLE_FIELDS)}"
            )
        self._config = config

    # ── 공개 API ────────────────────────────────────────────────

    def run(
        self,
        df: pd.DataFrame,
        symbol: str = "KRW-BTC",
    ) -> list[GridSearchResult]:
        """모든 파라미터 조합을 실행하고 결과를 랭킹순으로 반환합니다."""
        combinations = self._build_combinations()
        if not combinations:
            logger.info("파라미터 조합이 없습니다.")
            return []

        total = len(combinations)
        logger.info(
            "그리드 서치 시작: %d개 조합, 지표=%s",
            total,
            self._config.ranking_metric,
        )

        start = time.perf_counter()
        results = self._execute_parallel(combinations, df, symbol)
        elapsed = time.perf_counter() - start

        logger.info(
            "그리드 서치 완료: %d/%d 성공 (%.1f초)",
            len(results),
            total,
            elapsed,
        )

        return self._rank(results)

    def summary(
        self,
        results: list[GridSearchResult],
        top_n: int = 10,
    ) -> str:
        """상위 N개 결과를 포맷된 문자열로 반환합니다."""
        if not results:
            return "결과 없음."

        top = results[:top_n]
        metric = self._config.ranking_metric

        lines: list[str] = []
        lines.append("")
        lines.append("=" * 90)
        lines.append(f"  그리드 서치 결과 (상위 {len(top)}개, 정렬 기준: {metric})")
        lines.append("=" * 90)

        # 헤더
        lines.append(
            f"  {'순위':>4}  {'파라미터':<36}  "
            f"{'Sharpe':>7}  {'승률(%)':>7}  {'MDD(%)':>7}  {'수익률(%)':>8}"
        )
        lines.append("-" * 90)

        for r in top:
            params_str = ", ".join(
                f"{k}={v}" for k, v in sorted(r.params.items())
            )
            if len(params_str) > 34:
                params_str = params_str[:31] + "..."
            br = r.backtest_result
            lines.append(
                f"  {r.rank:>4}  {params_str:<36}  "
                f"{br.sharpe_ratio:>7.2f}  {br.win_rate:>7.1f}  "
                f"{br.max_drawdown_pct:>7.2f}  {br.total_return_pct:>+8.2f}"
            )

        lines.append("=" * 90)
        lines.append("")
        return "\n".join(lines)

    # ── 내부 ────────────────────────────────────────────────────

    def _build_combinations(self) -> list[dict[str, Any]]:
        """param_grid로부터 모든 파라미터 조합을 생성합니다."""
        grid = self._config.param_grid
        if not grid:
            return []

        # StrategyParams에 존재하는 필드인지 검증
        valid_fields = {f.name for f in fields(StrategyParams)}
        for key in grid:
            if key not in valid_fields:
                raise ValueError(
                    f"StrategyParams에 없는 파라미터: '{key}'. "
                    f"사용 가능: {sorted(valid_fields)}"
                )

        keys = list(grid.keys())
        values = list(grid.values())

        return [
            dict(zip(keys, combo))
            for combo in itertools.product(*values)
        ]

    def _execute_parallel(
        self,
        combinations: list[dict[str, Any]],
        df: pd.DataFrame,
        symbol: str,
    ) -> list[GridSearchResult]:
        """ProcessPoolExecutor를 사용하여 병렬로 백테스트를 실행합니다."""
        max_workers = self._config.max_workers or os.cpu_count() or 1
        cfg = self._config
        results: list[GridSearchResult] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _run_single_backtest,
                    combo,
                    df,
                    symbol,
                    cfg.initial_balance,
                    cfg.risk_params,
                ): combo
                for combo in combinations
            }

            for future in as_completed(futures):
                combo = futures[future]
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)
                except Exception as exc:
                    logger.warning("워커 예외 %s: %s", combo, exc)

        return results

    def _rank(
        self,
        results: list[GridSearchResult],
    ) -> list[GridSearchResult]:
        """결과를 랭킹 지표 기준으로 정렬하고 순위를 매깁니다."""
        metric = self._config.ranking_metric
        ascending = metric in _ASCENDING_METRICS

        results.sort(
            key=lambda r: getattr(r.backtest_result, metric),
            reverse=not ascending,
        )

        for i, r in enumerate(results, start=1):
            r.rank = i

        return results


# ── 편의 함수 ────────────────────────────────────────────────────


def run_grid_search(
    df: pd.DataFrame,
    param_grid: dict[str, list[Any]],
    symbol: str = "KRW-BTC",
    initial_balance: float = 1_000_000,
    ranking_metric: str = "sharpe_ratio",
) -> list[GridSearchResult]:
    """그리드 서치를 실행하는 편의 함수.

    Args:
        df: OHLCV DataFrame (open, high, low, close, volume).
        param_grid: 탐색할 파라미터 그리드.
        symbol: 마켓 코드.
        initial_balance: 초기 자산 (KRW).
        ranking_metric: 결과 정렬 기준 지표.

    Returns:
        랭킹순으로 정렬된 GridSearchResult 리스트.
    """
    config = GridSearchConfig(
        param_grid=param_grid,
        initial_balance=initial_balance,
        ranking_metric=ranking_metric,
    )
    runner = GridSearchRunner(config)
    return runner.run(df, symbol=symbol)


if __name__ == "__main__":
    import pyupbit

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    symbol = "KRW-BTC"
    print(f"[GridSearch] {symbol} 과거 데이터 수집 중...")
    df = pyupbit.get_ohlcv(symbol, interval="minute15", count=200)

    if df is None or len(df) < 50:
        print("[ERROR] 데이터 부족. 네트워크 연결을 확인하세요.")
    else:
        grid = {
            "atr_stop_multiplier": [1.5, 2.0, 2.5, 3.0],
            "bb_std_dev": [1.8, 2.0, 2.2],
            "rsi_oversold": [25, 28, 30, 33],
        }

        print(f"[GridSearch] {len(df)}개 캔들 수집 완료. 그리드 서치 실행...")
        results = run_grid_search(df, grid, symbol=symbol)

        runner = GridSearchRunner(GridSearchConfig(param_grid=grid))
        print(runner.summary(results))
