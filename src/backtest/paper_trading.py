"""
모의 투자(Paper Trading) 모듈.
실제 업비트 시세를 실시간으로 받아오되, 주문은 가상으로 처리합니다.
네트워크 지연과 슬리피지가 수익률에 미치는 영향을 확인합니다.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from src.config import AppConfig, RiskParams
from src.collector.data_collector import UpbitCollector
from src.strategy.indicators import compute_snapshot
from src.strategy.engine import MeanReversionEngine, Signal
from src.risk.manager import RiskManager
from src.executor.order_executor import OrderResult

logger = logging.getLogger(__name__)

# 모의 수수료율 (업비트 동일)
PAPER_FEE_RATE = 0.0005
# 모의 슬리피지 (시장가 주문 시 평균 0.02% 불리하게 체결)
PAPER_SLIPPAGE_RATE = 0.0002


@dataclass
class PaperPosition:
    """모의 포지션."""
    symbol: str
    entry_price: float
    volume: float
    amount: float
    has_sold_half: bool = False
    entry_time: str = ""


@dataclass
class PaperTrade:
    """모의 거래 기록."""
    trade_id: str
    symbol: str
    side: str            # 'bid' | 'ask'
    price: float
    volume: float
    amount: float
    fee: float
    slippage: float      # 슬리피지 금액
    timestamp: str
    reason: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class PaperTradingStats:
    """모의 투자 세션 통계."""
    session_start: str
    session_end: str = ""
    initial_balance: float = 0.0
    final_balance: float = 0.0
    total_return_pct: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    max_drawdown_pct: float = 0.0
    trades: list[PaperTrade] = field(default_factory=list)


class PaperOrderExecutor:
    """모의 주문 실행기.

    실제 OrderExecutor와 동일한 인터페이스를 제공하되,
    실제 주문 대신 가상으로 체결 처리합니다.
    """

    def __init__(
        self,
        collector: UpbitCollector,
        risk_params: RiskParams,
        slippage_rate: float = PAPER_SLIPPAGE_RATE,
    ) -> None:
        self._collector = collector
        self._risk_params = risk_params
        self._slippage_rate = slippage_rate

    def buy_market(self, symbol: str, amount_krw: float) -> OrderResult:
        """모의 시장가 매수."""
        if amount_krw < self._risk_params.min_order_amount_krw:
            return OrderResult(
                success=False, symbol=symbol, side="bid",
                error=f"최소 주문 금액 미달: {amount_krw:,.0f}",
            )

        current_price = self._collector.get_current_price(symbol)
        if current_price is None:
            return OrderResult(
                success=False, symbol=symbol, side="bid",
                error="현재가 조회 실패",
            )

        # 슬리피지 적용 (매수 시 불리 = 높은 가격)
        slippage = current_price * self._slippage_rate
        fill_price = current_price + slippage

        fee = amount_krw * PAPER_FEE_RATE
        actual_amount = amount_krw - fee
        volume = actual_amount / fill_price

        order_id = f"paper-{uuid.uuid4().hex[:8]}"

        logger.info(
            "[PAPER 매수] %s | %.0f KRW @ %.2f (슬리피지: +%.2f) | ID: %s",
            symbol, amount_krw, fill_price, slippage, order_id,
        )

        return OrderResult(
            success=True,
            order_id=order_id,
            symbol=symbol,
            side="bid",
            price=fill_price,
            volume=volume,
            amount=amount_krw,
            fee=fee,
        )

    def sell_market(self, symbol: str, volume: float) -> OrderResult:
        """모의 시장가 매도."""
        if volume <= 0:
            return OrderResult(
                success=False, symbol=symbol, side="ask",
                error=f"매도 수량 부적절: {volume}",
            )

        current_price = self._collector.get_current_price(symbol)
        if current_price is None:
            return OrderResult(
                success=False, symbol=symbol, side="ask",
                error="현재가 조회 실패",
            )

        # 슬리피지 적용 (매도 시 불리 = 낮은 가격)
        slippage = current_price * self._slippage_rate
        fill_price = current_price - slippage

        amount = volume * fill_price
        fee = amount * PAPER_FEE_RATE

        order_id = f"paper-{uuid.uuid4().hex[:8]}"

        logger.info(
            "[PAPER 매도] %s | 수량 %f @ %.2f (슬리피지: -%.2f) | ID: %s",
            symbol, volume, fill_price, slippage, order_id,
        )

        return OrderResult(
            success=True,
            order_id=order_id,
            symbol=symbol,
            side="ask",
            price=fill_price,
            volume=volume,
            amount=amount,
            fee=fee,
        )

    def sell_half(self, symbol: str, total_volume: float) -> OrderResult:
        """보유 수량의 50% 모의 매도."""
        return self.sell_market(symbol, total_volume * 0.5)

    def sell_all(self, symbol: str, total_volume: float) -> OrderResult:
        """전량 모의 매도."""
        return self.sell_market(symbol, total_volume)


class PaperTradingBot:
    """모의 투자 봇.

    실제 Orchestrator와 동일한 로직을 사용하되:
    - 실제 시세 데이터 사용 (UpbitCollector)
    - 가상 주문 처리 (PaperOrderExecutor)
    - 가상 잔고 관리
    - DB/알림 비활성화

    사용법:
        config = load_config()
        bot = PaperTradingBot(config, initial_balance=1_000_000)
        bot.run(max_iterations=100)
        stats = bot.get_stats()
    """

    def __init__(
        self,
        config: AppConfig,
        initial_balance: float = 1_000_000,
    ) -> None:
        self._config = config
        self._initial_balance = initial_balance
        self._balance = initial_balance

        # 실제 데이터 수집기
        self._collector = UpbitCollector(config.upbit)
        # 가상 주문 실행기
        self._executor = PaperOrderExecutor(self._collector, config.risk)
        # 전략 엔진
        self._strategy = MeanReversionEngine(config.strategy)
        # 리스크 매니저
        self._risk = RiskManager(config.risk, initial_balance)

        # 상태
        self._positions: dict[str, PaperPosition] = {}
        self._trades: list[PaperTrade] = []
        self._running = False
        self._loop_count = 0
        self._target_symbols: list[str] = []
        self._peak_equity = initial_balance
        self._max_drawdown_pct = 0.0
        self._session_start = datetime.now().isoformat()

    def run(self, max_iterations: int = 0) -> PaperTradingStats:
        """모의 투자를 실행합니다.

        Args:
            max_iterations: 최대 반복 횟수 (0이면 무한)

        Returns:
            PaperTradingStats 결과
        """
        logger.info("=== Paper Trading 시작 (초기 자산: %.0f KRW) ===", self._initial_balance)
        self._running = True

        while self._running:
            try:
                self._tick()
                self._loop_count += 1

                if max_iterations > 0 and self._loop_count >= max_iterations:
                    logger.info("최대 반복 횟수 도달 (%d회)", max_iterations)
                    self._running = False
                    break

            except KeyboardInterrupt:
                logger.info("사용자 종료 요청")
                self._running = False
            except Exception as e:
                logger.exception("Paper Trading 루프 오류: %s", e)

            if self._running:
                time.sleep(self._config.loop_interval_sec)

        return self.get_stats()

    def stop(self) -> None:
        """봇을 안전하게 중지합니다."""
        self._running = False

    def get_stats(self) -> PaperTradingStats:
        """현재까지의 통계를 반환합니다."""
        equity = self._get_equity()
        total_return = ((equity - self._initial_balance) / self._initial_balance) * 100

        sell_trades = [t for t in self._trades if t.side == "ask"]
        winning = [t for t in sell_trades if t.pnl > 0]
        losing = [t for t in sell_trades if t.pnl <= 0]
        win_rate = (len(winning) / len(sell_trades) * 100) if sell_trades else 0

        return PaperTradingStats(
            session_start=self._session_start,
            session_end=datetime.now().isoformat(),
            initial_balance=self._initial_balance,
            final_balance=equity,
            total_return_pct=total_return,
            total_trades=len(self._trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            total_fees=sum(t.fee for t in self._trades),
            total_slippage=sum(t.slippage for t in self._trades),
            max_drawdown_pct=self._max_drawdown_pct,
            trades=list(self._trades),
        )

    # ── 내부 로직 ────────────────────────────────────────────

    def _tick(self) -> None:
        """1회 매매 사이클."""
        if self._risk.is_daily_stopped:
            if self._loop_count % 60 == 0:
                logger.info("[PAPER] 일일 손실 한도 초과 — 대기 중")
            return

        # 감시 종목 갱신 (10분마다)
        if self._loop_count % 60 == 0 or not self._target_symbols:
            self._target_symbols = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )

        if not self._target_symbols:
            return

        # MDD 업데이트
        equity = self._get_equity()
        if equity > self._peak_equity:
            self._peak_equity = equity
        dd_pct = ((self._peak_equity - equity) / self._peak_equity * 100) if self._peak_equity > 0 else 0
        if dd_pct > self._max_drawdown_pct:
            self._max_drawdown_pct = dd_pct

        # 청산 평가
        self._evaluate_exits()
        # 진입 평가
        self._evaluate_entries()

    def _evaluate_exits(self) -> None:
        """보유 포지션 청산 평가."""
        for symbol in list(self._positions.keys()):
            pos = self._positions[symbol]
            try:
                df = self._collector.get_ohlcv(
                    symbol,
                    interval=self._config.candle_interval,
                    count=self._config.candle_count,
                )
                if df.empty:
                    continue

                snapshot = compute_snapshot(
                    df,
                    bb_period=self._config.strategy.bb_period,
                    bb_std_dev=self._config.strategy.bb_std_dev,
                    rsi_period=self._config.strategy.rsi_period,
                    atr_period=self._config.strategy.atr_period,
                )

                signal = self._strategy.evaluate_exit(
                    symbol, snapshot, pos.entry_price, pos.has_sold_half,
                )

                if signal.signal == Signal.STOP_LOSS:
                    self._paper_sell_all(symbol, signal.reason)
                elif signal.signal == Signal.SELL_ALL:
                    self._paper_sell_all(symbol, signal.reason)
                elif signal.signal == Signal.SELL_HALF and not pos.has_sold_half:
                    self._paper_sell_half(symbol, signal.reason)

                time.sleep(0.2)
            except Exception as e:
                logger.error("[PAPER] 청산 평가 오류 [%s]: %s", symbol, e)

    def _evaluate_entries(self) -> None:
        """미보유 종목 진입 평가."""
        for symbol in self._target_symbols:
            if symbol in self._positions:
                continue

            can_enter, _ = self._risk.can_enter(symbol, self._balance)
            if not can_enter:
                continue

            try:
                df = self._collector.get_ohlcv(
                    symbol,
                    interval=self._config.candle_interval,
                    count=self._config.candle_count,
                )
                if df.empty:
                    continue

                snapshot = compute_snapshot(
                    df,
                    bb_period=self._config.strategy.bb_period,
                    bb_std_dev=self._config.strategy.bb_std_dev,
                    rsi_period=self._config.strategy.rsi_period,
                    atr_period=self._config.strategy.atr_period,
                )

                signal = self._strategy.evaluate_entry(symbol, snapshot, df["close"])

                if signal.signal == Signal.BUY:
                    self._paper_buy(symbol, signal.reason)

                time.sleep(0.2)
            except Exception as e:
                logger.error("[PAPER] 진입 평가 오류 [%s]: %s", symbol, e)

    def _paper_buy(self, symbol: str, reason: str) -> None:
        """모의 매수."""
        amount = self._risk.calc_position_size(self._balance)
        if amount <= 0:
            return

        result = self._executor.buy_market(symbol, amount)
        if not result.success:
            logger.warning("[PAPER] 매수 실패 %s: %s", symbol, result.error)
            return

        # 가상 잔고 차감
        self._balance -= result.amount

        # 포지션 등록
        pos = PaperPosition(
            symbol=symbol,
            entry_price=result.price,
            volume=result.volume,
            amount=result.amount - result.fee,
            entry_time=datetime.now().isoformat(),
        )
        self._positions[symbol] = pos
        self._risk.add_position(symbol, result.price, result.volume, result.amount)

        # 거래 기록
        slippage = result.price * PAPER_SLIPPAGE_RATE * result.volume
        self._trades.append(PaperTrade(
            trade_id=result.order_id or "",
            symbol=symbol, side="bid",
            price=result.price, volume=result.volume,
            amount=result.amount, fee=result.fee,
            slippage=slippage,
            timestamp=datetime.now().isoformat(),
            reason=reason,
        ))

        logger.info(
            "[PAPER 매수] %s @ %.2f | 금액: %.0f KRW | 사유: %s",
            symbol, result.price, result.amount, reason,
        )

    def _paper_sell_half(self, symbol: str, reason: str) -> None:
        """모의 1차 분할 익절."""
        pos = self._positions.get(symbol)
        if not pos:
            return

        result = self._executor.sell_half(symbol, pos.volume)
        if not result.success:
            return

        # 가상 잔고 가산
        net_amount = result.amount - result.fee
        self._balance += net_amount

        # 손익 계산
        cost = pos.entry_price * result.volume
        pnl = net_amount - cost
        pnl_pct = ((result.price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0

        self._risk.record_realized_pnl(pnl)
        self._risk.mark_half_sold(symbol)
        pos.volume -= result.volume
        pos.has_sold_half = True

        slippage = result.price * PAPER_SLIPPAGE_RATE * result.volume
        self._trades.append(PaperTrade(
            trade_id=result.order_id or "",
            symbol=symbol, side="ask",
            price=result.price, volume=result.volume,
            amount=result.amount, fee=result.fee,
            slippage=slippage,
            timestamp=datetime.now().isoformat(),
            reason=reason, pnl=pnl, pnl_pct=pnl_pct,
        ))

        logger.info(
            "[PAPER 1차익절] %s @ %.2f | PnL: %+.0f (%.2f%%) | 사유: %s",
            symbol, result.price, pnl, pnl_pct, reason,
        )

    def _paper_sell_all(self, symbol: str, reason: str) -> None:
        """모의 전량 매도."""
        pos = self._positions.get(symbol)
        if not pos:
            return

        result = self._executor.sell_all(symbol, pos.volume)
        if not result.success:
            return

        net_amount = result.amount - result.fee
        self._balance += net_amount

        cost = pos.entry_price * result.volume
        pnl = net_amount - cost
        pnl_pct = ((result.price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0

        self._risk.record_realized_pnl(pnl)
        self._risk.remove_position(symbol)
        self._strategy.reset_tracking(symbol)
        del self._positions[symbol]

        slippage = result.price * PAPER_SLIPPAGE_RATE * result.volume
        self._trades.append(PaperTrade(
            trade_id=result.order_id or "",
            symbol=symbol, side="ask",
            price=result.price, volume=result.volume,
            amount=result.amount, fee=result.fee,
            slippage=slippage,
            timestamp=datetime.now().isoformat(),
            reason=reason, pnl=pnl, pnl_pct=pnl_pct,
        ))

        logger.info(
            "[PAPER 전량매도] %s @ %.2f | PnL: %+.0f (%.2f%%) | 사유: %s",
            symbol, result.price, pnl, pnl_pct, reason,
        )

    def _get_equity(self) -> float:
        """현재 총 자산 (KRW 잔고 + 포지션 평가액)."""
        equity = self._balance
        for symbol, pos in self._positions.items():
            price = self._collector.get_current_price(symbol)
            if price:
                equity += pos.volume * price
            else:
                equity += pos.volume * pos.entry_price
        return equity


def print_paper_trading_report(stats: PaperTradingStats) -> None:
    """모의 투자 결과를 콘솔에 출력합니다."""
    print("\n" + "=" * 60)
    print("  모의 투자 (Paper Trading) 결과")
    print("=" * 60)
    print(f"  기간: {stats.session_start[:19]} ~ {stats.session_end[:19]}")
    print(f"  초기 자산: {stats.initial_balance:,.0f} KRW")
    print(f"  최종 자산: {stats.final_balance:,.0f} KRW")
    print("-" * 60)
    print(f"  총 수익률:    {stats.total_return_pct:+.2f}%")
    print(f"  총 거래:      {stats.total_trades}건")
    print(f"  수익/손실:    {stats.winning_trades}W / {stats.losing_trades}L")
    print(f"  승률:         {stats.win_rate:.1f}%")
    print("-" * 60)
    print(f"  총 수수료:    {stats.total_fees:,.0f} KRW")
    print(f"  총 슬리피지:  {stats.total_slippage:,.0f} KRW")
    print(f"  최대 낙폭:    {stats.max_drawdown_pct:.2f}%")
    print("=" * 60)

    # 성공 기준 판정
    net_return = stats.total_return_pct
    if net_return > 0:
        print("  ✓ 수수료 제외 양의 수익률 기준 통과")
    else:
        print(f"  ✗ 수수료 제외 양의 수익률 기준 미달 ({net_return:+.2f}%)")
    print()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    from src.config import load_config

    config = load_config()

    if not config.upbit.access_key or not config.upbit.secret_key:
        print("[ERROR] UPBIT API 키가 .env에 설정되지 않았습니다.")
        sys.exit(1)

    print("=" * 60)
    print("  Zenith Paper Trading (모의 투자)")
    print("  실시간 시세 + 가상 주문")
    print("  Ctrl+C로 종료")
    print("=" * 60)

    bot = PaperTradingBot(config)

    try:
        bot.run()
    except KeyboardInterrupt:
        bot.stop()
        stats = bot.get_stats()
        print_paper_trading_report(stats)
