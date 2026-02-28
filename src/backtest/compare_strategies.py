"""
전략 설정 비교 백테스트 스크립트.

동일한 과거 데이터에 대해 서로 다른 진입 전략 설정(AND-게이트 vs 스코어링)을
비교 실행하여, 각 설정의 수익성·안정성 지표를 나란히 출력합니다.

사용법:
    python -m src.backtest.compare_strategies
    python -m src.backtest.compare_strategies --symbol KRW-ETH --count 500
    python -m src.backtest.compare_strategies --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace

import pandas as pd

from src.backtest.engine import BacktestEngine, BacktestResult, print_backtest_report
from src.config import StrategyParams

logger = logging.getLogger(__name__)


# ── 비교 대상 전략 설정 ──────────────────────────────────────────────

STRATEGY_CONFIGS: list[tuple[str, StrategyParams]] = [
    (
        "A: AND-게이트 근사",
        replace(
            StrategyParams(),
            entry_score_threshold=100.0,
            w_volatility=1.0,
            w_ma_trend=1.0,
            w_adx=1.0,
            w_bb_recovery=1.0,
            w_rsi_slope=1.0,
            w_rsi_level=1.0,
        ),
    ),
    (
        "B: 기본값 (보수적)",
        replace(
            StrategyParams(),
            entry_score_threshold=85.0,
            w_volatility=1.0,
            w_ma_trend=1.0,
            w_adx=1.0,
            w_bb_recovery=1.0,
            w_rsi_slope=1.0,
            w_rsi_level=1.0,
        ),
    ),
    (
        "C: 균형",
        replace(
            StrategyParams(),
            entry_score_threshold=70.0,
            w_volatility=1.0,
            w_ma_trend=1.0,
            w_adx=1.0,
            w_bb_recovery=1.0,
            w_rsi_slope=1.0,
            w_rsi_level=1.0,
        ),
    ),
    (
        "D: 공격적",
        replace(
            StrategyParams(),
            entry_score_threshold=55.0,
            bb_period=15,
            bb_std_dev=1.5,
            rsi_period=10,
            rsi_oversold=35.0,
            atr_period=10,
            atr_stop_multiplier=2.0,
            top_volume_count=15,
            w_volatility=0.5,
            w_ma_trend=0.5,
            w_adx=0.5,
            w_bb_recovery=1.0,
            w_rsi_slope=1.0,
            w_rsi_level=1.0,
        ),
    ),
]


# ── 비교 결과 타입 ───────────────────────────────────────────────────

ComparisonRow = dict[str, str | float | int]


# ── 핵심 비교 함수 ───────────────────────────────────────────────────

def compare_strategies(
    df: pd.DataFrame,
    symbol: str = "KRW-BTC",
    initial_balance: float = 1_000_000,
) -> list[tuple[str, BacktestResult]]:
    """여러 전략 설정으로 백테스트를 실행하고 결과 목록을 반환합니다.

    Args:
        df: OHLCV DataFrame (open, high, low, close, volume). 인덱스는 datetime.
        symbol: 마켓 코드
        initial_balance: 초기 자산 (KRW)

    Returns:
        (설정 이름, BacktestResult) 튜플 목록
    """
    results: list[tuple[str, BacktestResult]] = []

    for name, params in STRATEGY_CONFIGS:
        logger.info("[비교 백테스트] '%s' 설정 실행 중...", name)
        engine = BacktestEngine(
            initial_balance=initial_balance,
            strategy_params=params,
        )
        try:
            result = engine.run(df, symbol=symbol, verbose=False)
            results.append((name, result))
            logger.info(
                "[비교 백테스트] '%s' 완료 — 거래 %d건, 수익률 %+.2f%%",
                name, result.total_trades, result.total_return_pct,
            )
        except Exception:
            logger.exception("[비교 백테스트] '%s' 설정 실행 실패", name)

    return results


# ── 비교 테이블 출력 ─────────────────────────────────────────────────

def _format_comparison_table(results: list[tuple[str, BacktestResult]]) -> str:
    """비교 결과를 포맷된 테이블 문자열로 생성합니다."""
    if not results:
        return "  (비교 결과 없음)\n"

    # 컬럼 정의: (헤더, 포맷 함수)
    columns: list[tuple[str, callable]] = [
        ("설정",        lambda name, _r: name),
        ("거래수",      lambda _n, r: f"{r.total_trades}"),
        ("승률(%)",     lambda _n, r: f"{r.win_rate:.1f}"),
        ("수익률(%)",   lambda _n, r: f"{r.total_return_pct:+.2f}"),
        ("MDD(%)",      lambda _n, r: f"{r.max_drawdown_pct:.2f}"),
        ("샤프비율",    lambda _n, r: f"{r.sharpe_ratio:.2f}"),
        ("손익비",      lambda _n, r: f"{r.profit_loss_ratio:.2f}"),
    ]

    # 각 컬럼 최대 너비 계산 (헤더 + 데이터)
    col_widths: list[int] = []
    for header, fmt_fn in columns:
        max_w = len(header)
        for name, result in results:
            val = fmt_fn(name, result)
            max_w = max(max_w, len(val))
        # 최소 여유 2칸
        col_widths.append(max_w + 2)

    # 구분선
    separator = "+" + "+".join("-" * w for w in col_widths) + "+"

    # 헤더 행
    header_row = "|" + "|".join(
        f" {header:<{col_widths[i] - 2}} " if i == 0
        else f" {header:>{col_widths[i] - 2}} "
        for i, (header, _) in enumerate(columns)
    ) + "|"

    # 데이터 행들
    data_rows: list[str] = []
    for name, result in results:
        row = "|" + "|".join(
            f" {fmt_fn(name, result):<{col_widths[i] - 2}} " if i == 0
            else f" {fmt_fn(name, result):>{col_widths[i] - 2}} "
            for i, (_, fmt_fn) in enumerate(columns)
        ) + "|"
        data_rows.append(row)

    lines = [separator, header_row, separator] + data_rows + [separator]
    return "\n".join(lines)


def print_comparison_table(results: list[tuple[str, BacktestResult]]) -> None:
    """비교 결과를 콘솔에 출력합니다."""
    if not results:
        print("\n  비교할 결과가 없습니다.")
        return

    # 기본 정보 (첫 번째 결과 기준)
    first_result = results[0][1]
    print("\n" + "=" * 72)
    print("  전략 설정 비교 백테스트 결과")
    print("=" * 72)
    print(f"  심볼: {first_result.symbol}")
    print(f"  기간: {first_result.start_date} ~ {first_result.end_date}")
    print(f"  초기 자산: {first_result.initial_balance:,.0f} KRW")
    print("-" * 72)
    print()

    # 비교 테이블
    print(_format_comparison_table(results))
    print()

    # 최고 성과 요약
    best_return = max(results, key=lambda x: x[1].total_return_pct)
    best_sharpe = max(results, key=lambda x: x[1].sharpe_ratio)
    lowest_mdd = min(results, key=lambda x: x[1].max_drawdown_pct)
    most_trades = max(results, key=lambda x: x[1].total_trades)

    print("  ── 최고 성과 요약 ──")
    print(f"  최고 수익률: {best_return[0]} ({best_return[1].total_return_pct:+.2f}%)")
    print(f"  최고 샤프:   {best_sharpe[0]} ({best_sharpe[1].sharpe_ratio:.2f})")
    print(f"  최저 MDD:    {lowest_mdd[0]} ({lowest_mdd[1].max_drawdown_pct:.2f}%)")
    print(f"  최다 거래:   {most_trades[0]} ({most_trades[1].total_trades}건)")
    print("=" * 72)
    print()


# ── 메인 실행 ────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱합니다."""
    parser = argparse.ArgumentParser(
        description="전략 설정 비교 백테스트 - AND-게이트 vs 스코어링 시스템",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="KRW-BTC",
        help="마켓 코드 (기본값: KRW-BTC)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=500,
        help="수집할 캔들 수 (기본값: 500)",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="minute15",
        help="캔들 간격 (기본값: minute15)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="각 설정별 상세 리포트 출력",
    )
    return parser.parse_args()


def main() -> None:
    """비교 백테스트 메인 진입점."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args = _parse_args()
    symbol = args.symbol
    count = args.count
    interval = args.interval
    verbose = args.verbose

    # ── 데이터 수집 ──
    print(f"\n[비교 백테스트] {symbol} 과거 데이터 수집 중... (간격: {interval}, {count}개)")

    try:
        import pyupbit
        df = pyupbit.get_ohlcv(symbol, interval=interval, count=count)
    except ImportError:
        logger.error("pyupbit 패키지가 설치되지 않았습니다. pip install pyupbit")
        sys.exit(1)
    except Exception:
        logger.exception("데이터 수집 중 오류 발생")
        sys.exit(1)

    if df is None or len(df) < 50:
        print(f"[ERROR] 데이터 부족 ({0 if df is None else len(df)}개). "
              "네트워크 연결을 확인하세요.")
        sys.exit(1)

    print(f"[비교 백테스트] {len(df)}개 캔들 수집 완료. 비교 실행 시작...\n")

    # ── 비교 실행 ──
    results = compare_strategies(df, symbol=symbol, initial_balance=1_000_000)

    if not results:
        print("[ERROR] 모든 전략 설정이 실패했습니다.")
        sys.exit(1)

    # ── 결과 출력 ──
    print_comparison_table(results)

    # --verbose 시 각 설정별 상세 리포트
    if verbose:
        for name, result in results:
            print(f"\n{'─' * 60}")
            print(f"  상세 리포트: {name}")
            print(f"{'─' * 60}")
            print_backtest_report(result)


if __name__ == "__main__":
    main()
