"""
워크포워드 최적화 파이프라인.
과거 데이터를 훈련/테스트 윈도우로 분할하여 과적합을 방지하면서
최적 파라미터를 탐색합니다.

원리:
    1. 전체 데이터를 rolling window로 분할 (train 70% / test 30%)
    2. 각 train 구간에서 그리드 서치로 최적 파라미터 선택
    3. 해당 파라미터를 test 구간에 적용하여 Out-of-Sample 성능 측정
    4. 모든 윈도우의 OOS 결과를 종합하여 과적합 비율 산출

사용법:
    config = WalkForwardConfig(
        param_grid={"atr_stop_multiplier": [1.5, 2.0, 2.5]},
        n_windows=5,
    )
    pipeline = WalkForwardPipeline(config)
    report = pipeline.run(df, symbol="KRW-BTC")
    print(pipeline.summary(report))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.grid_search import GridSearchConfig, GridSearchRunner
from src.config import RiskParams, StrategyParams

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    """워크포워드 최적화 설정."""

    # 탐색할 파라미터 그리드
    param_grid: dict[str, list[Any]]

    # 훈련/테스트 비율 (0.0~1.0, 훈련 구간 비율)
    train_ratio: float = 0.7

    # 롤링 윈도우 수 (최소 2)
    n_windows: int = 5

    # 윈도우 간 겹침 비율 (0.0 = 겹침 없음, 0.5 = 50% 겹침)
    overlap_ratio: float = 0.0

    # 백테스트 설정
    initial_balance: float = 1_000_000
    risk_params: RiskParams | None = None

    # 그리드 서치 병렬 워커 수
    max_workers: int | None = None

    # 랭킹 기준 지표
    ranking_metric: str = "sharpe_ratio"

    # 과적합 판정 기준 (train 대비 test 성능 비율이 이 값 미만이면 과적합)
    overfit_threshold: float = 0.5


@dataclass
class WindowSplit:
    """단일 윈도우의 훈련/테스트 분할 정보."""

    window_id: int
    train_start: int  # iloc 인덱스
    train_end: int
    test_start: int
    test_end: int
    train_size: int
    test_size: int


@dataclass
class WindowResult:
    """단일 윈도우의 최적화 결과."""

    window_id: int
    split: WindowSplit

    # 훈련 구간 최적 파라미터
    best_params: dict[str, Any]

    # 훈련 구간 최적 결과 (In-Sample)
    train_result: BacktestResult

    # 테스트 구간 결과 (Out-of-Sample)
    test_result: BacktestResult

    # 과적합 비율 (test_metric / train_metric)
    efficiency_ratio: float

    # 과적합 여부
    is_overfit: bool


@dataclass
class WalkForwardReport:
    """워크포워드 최적화 종합 보고서."""

    # 개별 윈도우 결과
    window_results: list[WindowResult]

    # 종합 지표
    avg_train_sharpe: float = 0.0
    avg_test_sharpe: float = 0.0
    avg_train_return: float = 0.0
    avg_test_return: float = 0.0
    avg_efficiency_ratio: float = 0.0
    overfit_count: int = 0
    total_windows: int = 0

    # 가장 많이 선택된 파라미터 (안정적 파라미터 식별)
    most_selected_params: dict[str, Any] = field(default_factory=dict)


class WalkForwardPipeline:
    """워크포워드 최적화 파이프라인.

    과거 데이터를 여러 개의 훈련/테스트 윈도우로 분할하고,
    각 훈련 구간에서 그리드 서치로 찾은 최적 파라미터를
    테스트 구간에서 검증하여 과적합을 탐지합니다.

    사용법:
        config = WalkForwardConfig(
            param_grid={"atr_stop_multiplier": [1.5, 2.0, 2.5]},
            n_windows=5,
        )
        pipeline = WalkForwardPipeline(config)
        report = pipeline.run(df, symbol="KRW-BTC")
        print(pipeline.summary(report))
    """

    # 백테스트 최소 캔들 수
    _MIN_CANDLES = 50

    def __init__(self, config: WalkForwardConfig) -> None:
        if config.n_windows < 2:
            raise ValueError(f"윈도우 수는 최소 2개: {config.n_windows}")
        if not (0.3 <= config.train_ratio <= 0.9):
            raise ValueError(
                f"train_ratio는 0.3~0.9 범위: {config.train_ratio}"
            )
        if not config.param_grid:
            raise ValueError("param_grid가 비어 있습니다.")
        self._config = config

    # ── 공개 API ────────────────────────────────────────────────

    def run(
        self,
        df: pd.DataFrame,
        symbol: str = "KRW-BTC",
    ) -> WalkForwardReport:
        """워크포워드 최적화를 실행합니다."""
        splits = self._generate_splits(len(df))

        logger.info(
            "워크포워드 최적화 시작: %d개 윈도우, train_ratio=%.0f%%",
            len(splits),
            self._config.train_ratio * 100,
        )

        window_results: list[WindowResult] = []

        for split in splits:
            logger.info(
                "윈도우 %d/%d 처리 중 (train: %d~%d, test: %d~%d)",
                split.window_id,
                len(splits),
                split.train_start,
                split.train_end,
                split.test_start,
                split.test_end,
            )

            result = self._run_window(df, split, symbol)
            if result is not None:
                window_results.append(result)
                logger.info(
                    "윈도우 %d 완료: 효율비=%.2f%s",
                    split.window_id,
                    result.efficiency_ratio,
                    " (과적합)" if result.is_overfit else "",
                )

        return self._build_report(window_results)

    def summary(self, report: WalkForwardReport) -> str:
        """워크포워드 보고서를 포맷된 문자열로 반환합니다."""
        if not report.window_results:
            return "결과 없음."

        lines: list[str] = []
        lines.append("")
        lines.append("=" * 95)
        lines.append("  워크포워드 최적화 보고서")
        lines.append("=" * 95)

        # 종합 지표
        lines.append(f"  윈도우 수:         {report.total_windows}")
        lines.append(
            f"  과적합 윈도우:     {report.overfit_count}/{report.total_windows}"
        )
        lines.append(f"  평균 효율비:       {report.avg_efficiency_ratio:.2f}")
        lines.append("")
        lines.append(
            f"  평균 Train Sharpe: {report.avg_train_sharpe:.3f}  |  "
            f"평균 Test Sharpe: {report.avg_test_sharpe:.3f}"
        )
        lines.append(
            f"  평균 Train 수익률: {report.avg_train_return:+.2f}%  |  "
            f"평균 Test 수익률: {report.avg_test_return:+.2f}%"
        )
        lines.append("-" * 95)

        # 개별 윈도우 결과
        lines.append(
            f"  {'윈도우':>6}  {'Train Sharpe':>12}  {'Test Sharpe':>11}  "
            f"{'Train 수익률':>12}  {'Test 수익률':>11}  {'효율비':>6}  {'상태':>6}"
        )
        lines.append("-" * 95)

        for wr in report.window_results:
            status = "과적합" if wr.is_overfit else "정상"
            lines.append(
                f"  {wr.window_id:>6}  "
                f"{wr.train_result.sharpe_ratio:>12.3f}  "
                f"{wr.test_result.sharpe_ratio:>11.3f}  "
                f"{wr.train_result.total_return_pct:>+12.2f}  "
                f"{wr.test_result.total_return_pct:>+11.2f}  "
                f"{wr.efficiency_ratio:>6.2f}  "
                f"{status:>6}"
            )

        lines.append("-" * 95)

        # 안정적 파라미터
        if report.most_selected_params:
            lines.append("")
            lines.append("  가장 안정적인 파라미터 (최빈값):")
            for k, v in sorted(report.most_selected_params.items()):
                lines.append(f"    {k}: {v}")

        lines.append("=" * 95)

        # 판정
        lines.append("")
        overfit_pct = (
            (report.overfit_count / report.total_windows * 100)
            if report.total_windows > 0
            else 0
        )
        if overfit_pct <= 20:
            lines.append(
                f"  ✓ 과적합 판정: 안전 (과적합 윈도우 {overfit_pct:.0f}% ≤ 20%)"
            )
        elif overfit_pct <= 50:
            lines.append(
                f"  △ 과적합 판정: 주의 (과적합 윈도우 {overfit_pct:.0f}%)"
            )
        else:
            lines.append(
                f"  ✗ 과적합 판정: 위험 (과적합 윈도우 {overfit_pct:.0f}% > 50%)"
            )

        lines.append("")
        return "\n".join(lines)

    # ── 내부 ────────────────────────────────────────────────────

    def _generate_splits(self, total_rows: int) -> list[WindowSplit]:
        """롤링 윈도우 분할을 생성합니다."""
        cfg = self._config
        n_windows = cfg.n_windows

        # 단일 윈도우 크기 계산
        if cfg.overlap_ratio > 0:
            step = int(
                total_rows
                / (n_windows + (1 - cfg.overlap_ratio) * (n_windows - 1))
            )
        else:
            step = total_rows // n_windows

        window_size = int(step / (1 - cfg.overlap_ratio)) if cfg.overlap_ratio > 0 else step

        # 최소 크기 보장
        min_window = int(self._MIN_CANDLES / cfg.train_ratio) + 10
        if window_size < min_window:
            window_size = min_window

        splits: list[WindowSplit] = []
        window_id = 1

        start = 0
        while start + window_size <= total_rows and window_id <= n_windows:
            end = start + window_size
            train_end_idx = start + int(window_size * cfg.train_ratio)

            train_size = train_end_idx - start
            test_size = end - train_end_idx

            # 최소 캔들 수 확인
            if train_size >= self._MIN_CANDLES and test_size >= 10:
                splits.append(
                    WindowSplit(
                        window_id=window_id,
                        train_start=start,
                        train_end=train_end_idx,
                        test_start=train_end_idx,
                        test_end=end,
                        train_size=train_size,
                        test_size=test_size,
                    )
                )
                window_id += 1

            if cfg.overlap_ratio > 0:
                start += int(window_size * (1 - cfg.overlap_ratio))
            else:
                start = end

        return splits

    def _run_window(
        self,
        df: pd.DataFrame,
        split: WindowSplit,
        symbol: str,
    ) -> WindowResult | None:
        """단일 윈도우에 대해 훈련 + 테스트를 실행합니다."""
        cfg = self._config

        train_df = df.iloc[split.train_start : split.train_end].copy()
        test_df = df.iloc[split.test_start : split.test_end].copy()

        if len(train_df) < self._MIN_CANDLES:
            logger.warning(
                "윈도우 %d: 훈련 데이터 부족 (%d개 < %d)",
                split.window_id,
                len(train_df),
                self._MIN_CANDLES,
            )
            return None

        if len(test_df) < 10:
            logger.warning(
                "윈도우 %d: 테스트 데이터 부족 (%d개)",
                split.window_id,
                len(test_df),
            )
            return None

        # 1. 훈련 구간에서 그리드 서치
        grid_config = GridSearchConfig(
            param_grid=cfg.param_grid,
            initial_balance=cfg.initial_balance,
            risk_params=cfg.risk_params,
            max_workers=cfg.max_workers,
            ranking_metric=cfg.ranking_metric,
        )
        runner = GridSearchRunner(grid_config)

        try:
            grid_results = runner.run(train_df, symbol=symbol)
        except Exception as exc:
            logger.warning(
                "윈도우 %d: 그리드 서치 실패: %s", split.window_id, exc,
            )
            return None

        if not grid_results:
            logger.warning("윈도우 %d: 그리드 서치 결과 없음", split.window_id)
            return None

        # 최적 파라미터
        best = grid_results[0]
        best_params = best.params
        train_result = best.backtest_result

        # 2. 테스트 구간에서 OOS 검증
        try:
            from dataclasses import replace

            strategy_params = replace(StrategyParams(), **best_params)
            test_engine = BacktestEngine(
                initial_balance=cfg.initial_balance,
                strategy_params=strategy_params,
                risk_params=cfg.risk_params,
            )
            test_result = test_engine.run(test_df, symbol=symbol, verbose=False)
        except Exception as exc:
            logger.warning(
                "윈도우 %d: OOS 백테스트 실패: %s", split.window_id, exc,
            )
            return None

        # 3. 효율비 계산
        metric = cfg.ranking_metric
        train_metric = getattr(train_result, metric)
        test_metric = getattr(test_result, metric)

        if abs(train_metric) > 1e-9:
            efficiency = test_metric / train_metric
        else:
            efficiency = 0.0 if abs(test_metric) < 1e-9 else 1.0

        is_overfit = efficiency < cfg.overfit_threshold

        return WindowResult(
            window_id=split.window_id,
            split=split,
            best_params=best_params,
            train_result=train_result,
            test_result=test_result,
            efficiency_ratio=efficiency,
            is_overfit=is_overfit,
        )

    def _build_report(
        self,
        window_results: list[WindowResult],
    ) -> WalkForwardReport:
        """종합 보고서를 생성합니다."""
        if not window_results:
            return WalkForwardReport(window_results=[])

        n = len(window_results)

        avg_train_sharpe = sum(
            wr.train_result.sharpe_ratio for wr in window_results
        ) / n
        avg_test_sharpe = sum(
            wr.test_result.sharpe_ratio for wr in window_results
        ) / n
        avg_train_return = sum(
            wr.train_result.total_return_pct for wr in window_results
        ) / n
        avg_test_return = sum(
            wr.test_result.total_return_pct for wr in window_results
        ) / n
        avg_efficiency = sum(
            wr.efficiency_ratio for wr in window_results
        ) / n
        overfit_count = sum(1 for wr in window_results if wr.is_overfit)

        # 가장 많이 선택된 파라미터 (최빈값)
        param_counts: dict[str, dict[str, int]] = {}
        for wr in window_results:
            for k, v in wr.best_params.items():
                if k not in param_counts:
                    param_counts[k] = {}
                v_str = str(v)
                param_counts[k][v_str] = param_counts[k].get(v_str, 0) + 1

        most_selected: dict[str, Any] = {}
        for k, counts in param_counts.items():
            best_val_str = max(counts, key=counts.get)  # type: ignore[arg-type]
            # 원래 타입으로 복원 시도
            for wr in window_results:
                if k in wr.best_params and str(wr.best_params[k]) == best_val_str:
                    most_selected[k] = wr.best_params[k]
                    break

        return WalkForwardReport(
            window_results=window_results,
            avg_train_sharpe=avg_train_sharpe,
            avg_test_sharpe=avg_test_sharpe,
            avg_train_return=avg_train_return,
            avg_test_return=avg_test_return,
            avg_efficiency_ratio=avg_efficiency,
            overfit_count=overfit_count,
            total_windows=n,
            most_selected_params=most_selected,
        )


# ── 편의 함수 ────────────────────────────────────────────────────


def run_walk_forward(
    df: pd.DataFrame,
    param_grid: dict[str, list[Any]],
    symbol: str = "KRW-BTC",
    n_windows: int = 5,
    train_ratio: float = 0.7,
    initial_balance: float = 1_000_000,
    ranking_metric: str = "sharpe_ratio",
) -> WalkForwardReport:
    """워크포워드 최적화를 실행하는 편의 함수.

    Args:
        df: OHLCV DataFrame (open, high, low, close, volume).
        param_grid: 탐색할 파라미터 그리드.
        symbol: 마켓 코드.
        n_windows: 롤링 윈도우 수.
        train_ratio: 훈련 구간 비율 (0.3~0.9).
        initial_balance: 초기 자산 (KRW).
        ranking_metric: 결과 정렬 기준 지표.

    Returns:
        WalkForwardReport 종합 보고서.
    """
    config = WalkForwardConfig(
        param_grid=param_grid,
        train_ratio=train_ratio,
        n_windows=n_windows,
        initial_balance=initial_balance,
        ranking_metric=ranking_metric,
    )
    pipeline = WalkForwardPipeline(config)
    return pipeline.run(df, symbol=symbol)


if __name__ == "__main__":
    import pyupbit

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    symbol = "KRW-BTC"
    print(f"[WalkForward] {symbol} 과거 데이터 수집 중...")
    df = pyupbit.get_ohlcv(symbol, interval="minute15", count=200)

    if df is None or len(df) < 50:
        print("[ERROR] 데이터 부족. 네트워크 연결을 확인하세요.")
    else:
        grid = {
            "atr_stop_multiplier": [1.5, 2.0, 2.5, 3.0],
            "bb_std_dev": [1.8, 2.0, 2.2],
            "rsi_oversold": [25, 30, 35],
        }

        print(f"[WalkForward] {len(df)}개 캔들 수집 완료. 워크포워드 실행...")
        report = run_walk_forward(
            df, grid, symbol=symbol, n_windows=3, train_ratio=0.7,
        )

        pipeline = WalkForwardPipeline(
            WalkForwardConfig(param_grid=grid, n_windows=3)
        )
        print(pipeline.summary(report))
