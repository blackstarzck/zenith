"""
백테스팅 엔진.
과거 OHLCV 데이터를 기반으로 평균 회귀 전략의 수익성과 안정성을 검증합니다.

검증 지표:
- 승률 (Win Rate)
- 손익비 (Profit/Loss Ratio)
- 최대 낙폭 (MDD: Maximum Drawdown)
- 총 수익률
- 거래 횟수
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.config import StrategyParams, RiskParams
from src.strategy.indicators import compute_snapshot
from src.strategy.engine import MeanReversionEngine, Signal

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """백테스트 개별 거래 기록."""
    symbol: str
    side: str               # 'buy' | 'sell'
    price: float
    volume: float
    amount: float
    fee: float
    timestamp: str
    reason: str = ""
    pnl: float = 0.0        # 매도 시 실현 손익
    pnl_pct: float = 0.0    # 매도 시 수익률 (%)


@dataclass
class BacktestPosition:
    """백테스트 보유 포지션."""
    symbol: str
    entry_price: float
    volume: float
    amount: float
    has_sold_half: bool = False


@dataclass
class BacktestResult:
    """백테스트 결과 요약."""
    # 기본 정보
    symbol: str
    start_date: str
    end_date: str
    initial_balance: float
    final_balance: float

    # 수익 지표
    total_return_pct: float       # 총 수익률 (%)
    annualized_return_pct: float  # 연환산 수익률 (%)

    # 거래 지표
    total_trades: int             # 총 거래 횟수 (매수+매도)
    winning_trades: int           # 수익 거래
    losing_trades: int            # 손실 거래
    win_rate: float               # 승률 (%)
    profit_loss_ratio: float      # 손익비 (평균 수익 / 평균 손실)

    # 리스크 지표
    max_drawdown_pct: float       # 최대 낙폭 (%)
    max_drawdown_amount: float    # 최대 낙폭 (KRW)
    sharpe_ratio: float           # 샤프 비율 (연환산)

    # 상세 기록
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)


# 업비트 수수료율 (0.05%)
UPBIT_FEE_RATE = 0.0005


class BacktestEngine:
    """과거 데이터 시뮬레이션 백테스팅 엔진.

    사용법:
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df, symbol="KRW-BTC")
        print(f"승률: {result.win_rate:.1f}%, MDD: {result.max_drawdown_pct:.2f}%")
    """

    def __init__(
        self,
        initial_balance: float = 1_000_000,
        strategy_params: StrategyParams | None = None,
        risk_params: RiskParams | None = None,
    ) -> None:
        self._initial_balance = initial_balance
        self._strategy_params = strategy_params or StrategyParams()
        self._risk_params = risk_params or RiskParams()

    def run(
        self,
        df: pd.DataFrame,
        symbol: str = "KRW-BTC",
        verbose: bool = False,
    ) -> BacktestResult:
        """백테스팅을 실행합니다.

        Args:
            df: OHLCV DataFrame (open, high, low, close, volume).
                인덱스는 datetime이어야 합니다.
            symbol: 마켓 코드
            verbose: 상세 로그 출력 여부

        Returns:
            BacktestResult 요약 및 거래 기록
        """
        if len(df) < 50:
            raise ValueError(f"데이터 부족: {len(df)}개 < 최소 50개 캔들 필요")

        # 컬럼 정규화
        df = self._normalize_columns(df)

        strategy = MeanReversionEngine(self._strategy_params)
        params = self._strategy_params

        balance = self._initial_balance
        position: BacktestPosition | None = None
        trades: list[BacktestTrade] = []
        equity_curve: list[dict] = []
        peak_equity = balance

        # 지표 계산에 필요한 최소 윈도우
        min_window = max(params.bb_period, params.rsi_period, params.atr_period) + 5

        for i in range(min_window, len(df)):
            # 현재 시점까지의 데이터 슬라이스
            window = df.iloc[:i + 1]
            timestamp = str(window.index[-1])
            current_price = float(window["close"].iloc[-1])

            try:
                snapshot = compute_snapshot(
                    window,
                    bb_period=params.bb_period,
                    bb_std_dev=params.bb_std_dev,
                    rsi_period=params.rsi_period,
                    atr_period=params.atr_period,
                    vol_short_window=params.vol_short_window,
                    vol_long_window=params.vol_long_window,
                    adx_period=params.adx_period,
                )
            except (ValueError, Exception):
                continue

            # 현재 자산 평가
            equity = balance
            if position is not None:
                equity += position.volume * current_price

            # 고점 갱신 및 equity curve 기록
            if equity > peak_equity:
                peak_equity = equity

            equity_curve.append({
                "timestamp": timestamp,
                "equity": equity,
                "balance": balance,
                "drawdown_pct": ((peak_equity - equity) / peak_equity * 100)
                if peak_equity > 0 else 0.0,
            })

            # ── 보유 중: 청산 평가 ──
            if position is not None:
                signal = strategy.evaluate_exit(
                    symbol, snapshot,
                    position.entry_price,
                    position.has_sold_half,
                )

                if signal.signal == Signal.STOP_LOSS:
                    # 전량 손절
                    sell_amount = position.volume * current_price
                    fee = sell_amount * UPBIT_FEE_RATE
                    pnl = sell_amount - position.amount - fee
                    pnl_pct = (pnl / position.amount * 100) if position.amount > 0 else 0

                    trades.append(BacktestTrade(
                        symbol=symbol, side="sell",
                        price=current_price, volume=position.volume,
                        amount=sell_amount, fee=fee,
                        timestamp=timestamp, reason=signal.reason,
                        pnl=pnl, pnl_pct=pnl_pct,
                    ))

                    balance += sell_amount - fee
                    position = None

                    if verbose:
                        logger.info("[손절] %s @ %.2f | PnL: %+.0f (%.2f%%)",
                                    symbol, current_price, pnl, pnl_pct)

                elif signal.signal == Signal.SELL_ALL:
                    sell_amount = position.volume * current_price
                    fee = sell_amount * UPBIT_FEE_RATE
                    pnl = sell_amount - position.amount - fee
                    pnl_pct = (pnl / position.amount * 100) if position.amount > 0 else 0

                    trades.append(BacktestTrade(
                        symbol=symbol, side="sell",
                        price=current_price, volume=position.volume,
                        amount=sell_amount, fee=fee,
                        timestamp=timestamp, reason=signal.reason,
                        pnl=pnl, pnl_pct=pnl_pct,
                    ))

                    balance += sell_amount - fee
                    position = None

                    if verbose:
                        logger.info("[전량매도] %s @ %.2f | PnL: %+.0f (%.2f%%)",
                                    symbol, current_price, pnl, pnl_pct)

                elif signal.signal == Signal.SELL_HALF and not position.has_sold_half:
                    half_volume = position.volume * params.take_profit_ratio_1st
                    sell_amount = half_volume * current_price
                    fee = sell_amount * UPBIT_FEE_RATE
                    pnl = sell_amount - (position.entry_price * half_volume) - fee
                    pnl_pct = ((current_price / position.entry_price) - 1) * 100

                    trades.append(BacktestTrade(
                        symbol=symbol, side="sell",
                        price=current_price, volume=half_volume,
                        amount=sell_amount, fee=fee,
                        timestamp=timestamp, reason=signal.reason,
                        pnl=pnl, pnl_pct=pnl_pct,
                    ))

                    balance += sell_amount - fee
                    position.volume -= half_volume
                    position.has_sold_half = True

                    if verbose:
                        logger.info("[1차익절] %s @ %.2f | PnL: %+.0f (%.2f%%)",
                                    symbol, current_price, pnl, pnl_pct)

            # ── 미보유: 진입 평가 ──
            elif position is None:
                signal = strategy.evaluate_entry(
                    symbol, snapshot, window["close"],
                )

                if signal.signal == Signal.BUY:
                    # 포지션 사이징
                    invest = min(
                        balance * self._risk_params.max_position_ratio,
                        balance,
                    )
                    if invest < self._risk_params.min_order_amount_krw:
                        continue

                    fee = invest * UPBIT_FEE_RATE
                    actual_invest = invest - fee
                    volume = actual_invest / current_price

                    trades.append(BacktestTrade(
                        symbol=symbol, side="buy",
                        price=current_price, volume=volume,
                        amount=invest, fee=fee,
                        timestamp=timestamp, reason=signal.reason,
                    ))

                    balance -= invest
                    position = BacktestPosition(
                        symbol=symbol,
                        entry_price=current_price,
                        volume=volume,
                        amount=actual_invest,
                    )

                    if verbose:
                        logger.info("[매수] %s @ %.2f | 금액: %.0f KRW",
                                    symbol, current_price, invest)

        # ── 마지막 포지션 강제 청산 ──
        if position is not None:
            last_price = float(df["close"].iloc[-1])
            sell_amount = position.volume * last_price
            fee = sell_amount * UPBIT_FEE_RATE
            pnl = sell_amount - position.amount - fee
            pnl_pct = (pnl / position.amount * 100) if position.amount > 0 else 0

            trades.append(BacktestTrade(
                symbol=symbol, side="sell",
                price=last_price, volume=position.volume,
                amount=sell_amount, fee=fee,
                timestamp=str(df.index[-1]),
                reason="백테스트 종료 — 강제 청산",
                pnl=pnl, pnl_pct=pnl_pct,
            ))
            balance += sell_amount - fee

        # ── 결과 계산 ──
        return self._compute_result(
            symbol=symbol,
            df=df,
            initial_balance=self._initial_balance,
            final_balance=balance,
            trades=trades,
            equity_curve=equity_curve,
        )

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """DataFrame 컬럼명을 소문자로 정규화합니다."""
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"필수 컬럼 누락: {missing}")
        return df

    def _compute_result(
        self,
        symbol: str,
        df: pd.DataFrame,
        initial_balance: float,
        final_balance: float,
        trades: list[BacktestTrade],
        equity_curve: list[dict],
    ) -> BacktestResult:
        """백테스트 결과를 집계합니다."""
        # 수익률
        total_return_pct = ((final_balance - initial_balance) / initial_balance) * 100

        # 기간 (일)
        start_date = str(df.index[0])
        end_date = str(df.index[-1])
        try:
            days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
        except Exception:
            days = len(df)
        days = max(days, 1)

        # 연환산 수익률
        annualized = ((final_balance / initial_balance) ** (365 / days) - 1) * 100

        # 승/패 분류 (매도 기록만)
        sell_trades = [t for t in trades if t.side == "sell"]
        winning = [t for t in sell_trades if t.pnl > 0]
        losing = [t for t in sell_trades if t.pnl <= 0]

        win_rate = (len(winning) / len(sell_trades) * 100) if sell_trades else 0.0

        avg_win = np.mean([t.pnl for t in winning]) if winning else 0.0
        avg_loss = abs(np.mean([t.pnl for t in losing])) if losing else 1.0
        pl_ratio = float(avg_win / avg_loss) if avg_loss > 0 else 0.0

        # MDD
        max_dd_pct = 0.0
        max_dd_amount = 0.0
        if equity_curve:
            equities = [e["equity"] for e in equity_curve]
            peak = equities[0]
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = peak - eq
                dd_pct = (dd / peak * 100) if peak > 0 else 0
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct
                    max_dd_amount = dd

        # 샤프 비율 (일간 수익률 기반)
        sharpe = 0.0
        if len(equity_curve) > 1:
            equities = np.array([e["equity"] for e in equity_curve])
            daily_returns = np.diff(equities) / equities[:-1]
            if daily_returns.std() > 0:
                sharpe = float(
                    (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
                )

        return BacktestResult(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return_pct=total_return_pct,
            annualized_return_pct=annualized,
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            profit_loss_ratio=pl_ratio,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_amount=max_dd_amount,
            sharpe_ratio=sharpe,
            trades=trades,
            equity_curve=equity_curve,
        )


def run_backtest_from_csv(
    csv_path: str,
    symbol: str = "KRW-BTC",
    initial_balance: float = 1_000_000,
    strategy_params: StrategyParams | None = None,
    verbose: bool = False,
) -> BacktestResult:
    """CSV 파일로부터 백테스트를 실행하는 편의 함수.

    CSV 형식: datetime, open, high, low, close, volume
    """
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    engine = BacktestEngine(
        initial_balance=initial_balance,
        strategy_params=strategy_params,
    )
    return engine.run(df, symbol=symbol, verbose=verbose)


def print_backtest_report(result: BacktestResult) -> None:
    """백테스트 결과를 콘솔에 출력합니다."""
    print("\n" + "=" * 60)
    print(f"  백테스트 결과: {result.symbol}")
    print("=" * 60)
    print(f"  기간: {result.start_date} ~ {result.end_date}")
    print(f"  초기 자산: {result.initial_balance:,.0f} KRW")
    print(f"  최종 자산: {result.final_balance:,.0f} KRW")
    print("-" * 60)
    print(f"  총 수익률:     {result.total_return_pct:+.2f}%")
    print(f"  연환산 수익률: {result.annualized_return_pct:+.2f}%")
    print(f"  샤프 비율:     {result.sharpe_ratio:.2f}")
    print("-" * 60)
    print(f"  총 거래:       {result.total_trades}건")
    print(f"  수익 거래:     {result.winning_trades}건")
    print(f"  손실 거래:     {result.losing_trades}건")
    print(f"  승률:          {result.win_rate:.1f}%")
    print(f"  손익비:        {result.profit_loss_ratio:.2f}")
    print("-" * 60)
    print(f"  최대 낙폭(MDD): {result.max_drawdown_pct:.2f}% ({result.max_drawdown_amount:,.0f} KRW)")
    print("=" * 60)

    # MDD 10% 이내 기준 판정
    if result.max_drawdown_pct <= 10:
        print("  ✓ MDD 기준 통과 (≤ 10%)")
    else:
        print(f"  ✗ MDD 기준 미달 ({result.max_drawdown_pct:.2f}% > 10%)")

    # 양의 수익률 기준
    if result.total_return_pct > 0:
        print("  ✓ 양의 수익률 기준 통과")
    else:
        print("  ✗ 양의 수익률 기준 미달")

    print()


if __name__ == "__main__":
    import pyupbit

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    symbol = "KRW-BTC"
    print(f"[Backtest] {symbol} 과거 데이터 수집 중...")
    df = pyupbit.get_ohlcv(symbol, interval="minute15", count=200)

    if df is None or len(df) < 50:
        print("[ERROR] 데이터 부족. 네트워크 연결을 확인하세요.")
    else:
        print(f"[Backtest] {len(df)}개 캔들 수집 완료. 백테스트 실행...")
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df, symbol=symbol, verbose=True)
        print_backtest_report(result)
