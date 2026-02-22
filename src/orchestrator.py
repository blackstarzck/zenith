"""
메인 오케스트레이터.
데이터 수집 → 지표 계산 → 전략 판단 → 주문 실행 → 기록/알림의
전체 매매 루프를 통합 관리합니다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date

from src.config import AppConfig
from src.collector.data_collector import UpbitCollector
from src.strategy.indicators import compute_snapshot
from src.strategy.engine import MeanReversionEngine, Signal
from src.executor.order_executor import OrderExecutor
from src.risk.manager import RiskManager
from src.storage.client import StorageClient
from src.notifier.kakao import KakaoNotifier

logger = logging.getLogger(__name__)

# 가격 스냅샷 저장 간격 (틱 수 기준, 10초 루프 × 18 = 약 3분)
_SNAPSHOT_INTERVAL = 18


class Orchestrator:
    """트레이딩 봇 오케스트레이터.

    하나의 메인 루프에서 모든 모듈을 조율합니다:
    1. 거래 대금 상위 종목 추출
    2. 종목별 OHLCV 수집 + 지표 계산
    3. 보유 종목 청산 조건 평가
    4. 미보유 종목 진입 조건 평가
    5. 주문 실행 + DB 기록 + 카카오 알림
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config

        # 모듈 초기화
        self._collector = UpbitCollector(config.upbit)
        self._strategy = MeanReversionEngine(config.strategy)
        self._executor = OrderExecutor(self._collector.upbit, config.risk)
        self._storage = StorageClient(config.supabase)
        self._notifier = KakaoNotifier(config.kakao, storage=self._storage)
        self._risk: RiskManager | None = None  # 잔고 확인 후 초기화

        self._running = False
        self._loop_count = 0
        self._today: date = date.today()

    # ── 메인 루프 ────────────────────────────────────────────

    def run(self) -> None:
        """봇 메인 루프를 시작합니다."""
        logger.info("=== Zenith 트레이딩 봇 시작 ===")

        # 초기 잔고로 리스크 매니저 초기화
        try:
            initial_balance = self._get_total_balance_krw()
            self._risk = RiskManager(self._config.risk, initial_balance)
            logger.info("초기 자산: %.0f KRW", initial_balance)
            krw = self._collector.get_krw_balance()
            self._storage.upsert_bot_state(
                initial_balance=initial_balance,
                current_balance=initial_balance,
                krw_balance=krw,
            )
            # 업비트 실제 보유 종목을 RiskManager에 동기화
            self._sync_existing_positions()
            # 봇 재시작 시 BB 이탈 상태 복구 (캔들 역산)
            self._recover_bb_states()
            # 시작 즉시 오늘의 일일 통계 기록 (대시보드 자산 성장 곡선용)
            self._storage.upsert_daily_stats(
                stats_date=self._today,
                total_balance=initial_balance,
                net_profit=0.0,
                drawdown=0.0,
            )
        except Exception as e:
            logger.critical("초기화 실패: %s", e)
            asyncio.run(self._notifier.notify_error(f"봇 초기화 실패: {e}"))
            return

        self._running = True

        while self._running:
            try:
                self._tick()
            except KeyboardInterrupt:
                logger.info("사용자 종료 요청")
                self._running = False
            except Exception as e:
                logger.exception("메인 루프 오류")
                asyncio.run(self._notifier.notify_error(f"메인 루프 오류: {e}"))

            if self._running:
                time.sleep(self._config.loop_interval_sec)

        logger.info("=== Zenith 트레이딩 봇 종료 ===")

    def stop(self) -> None:
        """봇을 안전하게 중지합니다."""
        self._running = False

    # ── 단일 틱 (1회 루프) ───────────────────────────────────

    def _tick(self) -> None:
        """1회 매매 사이클을 실행합니다."""
        self._loop_count += 1
        self._check_daily_reset()

        if self._risk.is_daily_stopped:
            if self._loop_count % 60 == 1:  # 10분에 1번만 로그
                logger.info("일일 손실 한도 초과 — 대기 중")
            return

        # 1. 감시 종목 추출 (10분마다 갱신)
        if self._loop_count % 60 == 1:
            self._target_symbols = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )
            # 상위 종목 변경 → bot_state 갱신
            self._storage.upsert_bot_state(top_symbols=self._target_symbols)
            if not self._target_symbols:
                logger.warning("감시 대상 종목 없음")
                return

        if not hasattr(self, "_target_symbols") or not self._target_symbols:
            self._target_symbols = self._collector.get_top_volume_symbols(
                self._config.strategy.top_volume_count
            )
            self._storage.upsert_bot_state(top_symbols=self._target_symbols)

        # 2. 보유 종목 청산 평가
        self._evaluate_exits()

        # 3. 미보유 종목 진입 평가
        self._evaluate_entries()

        # 4. 보유 종목 가격 스냅샷 저장 (약 3분 간격)
        if self._loop_count == 1 or self._loop_count % _SNAPSHOT_INTERVAL == 0:
            self._save_price_snapshots()

        # 4-1. 오늘의 일일 통계 주기적 갱신 (자산 성장 곡선용)
        if self._loop_count == 1 or self._loop_count % _SNAPSHOT_INTERVAL == 0:
            try:
                balance = self._get_total_balance_krw()
                self._storage.upsert_daily_stats(
                    stats_date=self._today,
                    total_balance=balance,
                    net_profit=self._risk.daily_realized_pnl,
                    drawdown=0.0,
                )
            except Exception as e:
                logger.error("오늘 일일 통계 갱신 실패: %s", e)
            # 4-2. 잔고 스냅샷 저장 (시간별 자산 성장 곡선용)
            try:
                self._storage.insert_balance_snapshot(balance)
            except Exception as e:
                logger.error("잔고 스냅샷 저장 실패: %s", e)

        # 5. 주기적 일일 리포트 (매 시간)
        if self._loop_count % 360 == 0:
            self._send_daily_report()

    # ── 청산 평가 ────────────────────────────────────────────

    def _evaluate_exits(self) -> None:
        """보유 종목의 청산 조건을 평가합니다."""
        positions = self._risk.get_all_positions()
        if not positions:
            return

        for symbol, pos in positions.items():
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
                    self._execute_sell_all(symbol, pos, signal.reason, label="손절 매도")
                elif signal.signal == Signal.SELL_ALL:
                    self._execute_sell_all(symbol, pos, signal.reason, label="2차 익절")
                elif signal.signal == Signal.SELL_HALF:
                    self._execute_sell_half(symbol, pos, signal.reason)

                # Rate limit 방어
                time.sleep(0.2)

            except Exception as e:
                logger.error("청산 평가 오류 [%s]: %s", symbol, e)

    # ── 진입 평가 ────────────────────────────────────────────

    def _evaluate_entries(self) -> None:
        """미보유 종목의 진입 조건을 평가합니다."""
        current_balance = self._get_total_balance_krw()
        krw = self._collector.get_krw_balance()
        self._storage.upsert_bot_state(current_balance=current_balance, krw_balance=krw)

        for symbol in self._target_symbols:
            # 체결 실패 쿨다운 확인
            if self._executor.is_on_cooldown(symbol):
                continue

            can_enter, reason = self._risk.can_enter(symbol, current_balance)
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

                signal = self._strategy.evaluate_entry(
                    symbol, snapshot, df["close"],
                )

                if signal.signal == Signal.BUY:
                    self._execute_buy(symbol, signal, current_balance)
                elif signal.signal == Signal.MARKET_PAUSE:
                    logger.info("[%s] %s", symbol, signal.reason)

                time.sleep(0.2)

            except Exception as e:
                logger.error("진입 평가 오류 [%s]: %s", symbol, e)

    # ── 가격 스냅샷 저장 ─────────────────────────────────────

    def _save_price_snapshots(self) -> None:
        """보유 종목의 가격 · 손절선 · 익절선 스냅샷을 DB에 저장합니다."""
        positions = self._risk.get_all_positions()
        if not positions:
            return

        params = self._config.strategy

        for symbol, pos in positions.items():
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
                    bb_period=params.bb_period,
                    bb_std_dev=params.bb_std_dev,
                    rsi_period=params.rsi_period,
                    atr_period=params.atr_period,
                )

                price = snapshot.current_price
                stop_loss = pos.entry_price - (snapshot.atr * params.atr_stop_multiplier)
                take_profit = snapshot.bb.upper

                self._storage.insert_price_snapshot(
                    symbol=symbol,
                    price=price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

                time.sleep(0.1)

            except Exception as e:
                logger.error("가격 스냅샷 저장 오류 [%s]: %s", symbol, e)

    # ── 주문 실행 ────────────────────────────────────────────

    def _execute_buy(self, symbol: str, signal, current_balance: float) -> None:
        """매수 주문을 실행합니다."""
        amount = self._risk.calc_position_size(current_balance)
        if amount <= 0:
            logger.info("[%s] 투입 가능 금액 부족", symbol)
            return

        logger.info(
            "[매수 진입] %s | 사유: %s | 금액: %.0f KRW",
            symbol, signal.reason, amount,
        )

        result = self._executor.buy_market(symbol, amount)
        if not result.success:
            logger.error("[매수 실패] %s: %s", symbol, result.error)
            return

        # 포지션 등록
        self._risk.add_position(
            symbol=symbol,
            entry_price=result.price,
            volume=result.volume,
            amount=result.amount,
        )

        # DB 기록
        self._storage.insert_trade(
            symbol=symbol,
            side="bid",
            price=result.price,
            volume=result.volume,
            amount=result.amount,
            fee=result.fee,
        )

    def _execute_sell_half(self, symbol: str, pos, reason: str) -> None:
        """1차 분할 익절 (50%)을 실행합니다.

        반값이 최소 주문금액(5,000 KRW) 미달 시 전량 매도로 전환합니다.
        전량도 미달이면 더스트(dust)로 판단하여 포지션을 정리합니다.
        """
        # 실제 보유량 조회 (업비트 잔고 기준)
        actual_volume = self._collector.get_balance(symbol)
        if actual_volume <= 0:
            self._risk.mark_half_sold(symbol)
            return

        current_price = self._collector.get_current_price(symbol) or pos.entry_price
        half_volume = actual_volume * 0.5
        half_amount = half_volume * current_price
        full_amount = actual_volume * current_price
        min_order = self._config.risk.min_order_amount_krw

        if half_amount < min_order:
            if full_amount >= min_order:
                # 반값 미달 → 전량 매도로 전환
                logger.info(
                    "[1차 익절 → 전량 전환] %s | 반값 %.0f < 최소 %d KRW | 사유: %s",
                    symbol, half_amount, min_order, reason,
                )
                self._execute_sell_all(symbol, pos, f"{reason} (소액 전량 전환)")
            else:
                # 전량도 미달 → 더스트 처리
                logger.warning(
                    "[더스트 정리] %s | 보유액 %.0f KRW < 최소 %d KRW → 포지션 제거",
                    symbol, full_amount, min_order,
                )
                self._risk.remove_position(symbol)
                self._strategy.reset_tracking(symbol)
            return

        logger.info("[1차 익절] %s | 사유: %s", symbol, reason)

        result = self._executor.sell_half(symbol, actual_volume)
        if not result.success:
            logger.error("[1차 익절 실패] %s: %s", symbol, result.error)
            return

        self._risk.mark_half_sold(symbol)

        # 실현 손익 계산
        pnl = result.amount - (pos.entry_price * result.volume) - result.fee
        pnl_pct = ((result.price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0
        self._risk.record_realized_pnl(pnl)

        remaining = actual_volume - result.volume
        self._storage.insert_trade(
            symbol=symbol, side="ask",
            price=result.price, volume=result.volume,
            amount=result.amount, fee=result.fee,
            pnl=pnl,
            remaining_volume=remaining if remaining > 0 else None,
        )

        asyncio.run(
            self._notifier.notify_pnl(symbol, result.price, pnl, pnl_pct, reason)
        )

    def _execute_sell_all(self, symbol: str, pos, reason: str, label: str = "전량 매도") -> None:
        """전량 매도를 실행합니다."""
        # 실제 보유량 조회 (1차 익절 후 잔량 반영)
        actual_volume = self._collector.get_balance(symbol)
        if actual_volume <= 0:
            self._risk.remove_position(symbol)
            self._strategy.reset_tracking(symbol)
            return

        logger.info("[%s] %s | 사유: %s", label, symbol, reason)

        result = self._executor.sell_all(symbol, actual_volume)
        if not result.success:
            logger.error("[%s 실패] %s: %s", label, symbol, result.error)
            return

        # 실현 손익 계산
        pnl = result.amount - (pos.entry_price * result.volume) - result.fee
        pnl_pct = ((result.price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0
        self._risk.record_realized_pnl(pnl)

        self._risk.remove_position(symbol)
        self._strategy.reset_tracking(symbol)

        self._storage.insert_trade(
            symbol=symbol, side="ask",
            price=result.price, volume=result.volume,
            amount=result.amount, fee=result.fee,
            pnl=pnl,
            remaining_volume=0.0,
        )

        asyncio.run(
            self._notifier.notify_pnl(symbol, result.price, pnl, pnl_pct, reason)
        )

        # 일일 손실 한도 초과 알림
        if self._risk.is_daily_stopped:
            asyncio.run(
                self._notifier.notify_daily_stop(self._risk.daily_realized_pnl)
            )

    # ── 유틸리티 ─────────────────────────────────────────────

    def _sync_existing_positions(self) -> None:
        """업비트 실제 보유 종목을 RiskManager에 동기화합니다.

        봇이 직접 매수하지 않은(외부 매수) 종목도 포지션 관리 및
        프론트엔드 거래내역에 표시되도록 합성 매수 기록을 삽입합니다.
        중복 방지: DB에 해당 종목의 bid 거래가 이미 있으면 스킵합니다.
        """
        balances = self._collector.get_balances()
        synced = 0
        for b in balances:
            currency = b.get("currency", "")
            if currency == "KRW":
                continue
            balance = float(b.get("balance", 0))
            avg_price = float(b.get("avg_buy_price", 0))
            if balance <= 0 or avg_price <= 0:
                continue
            symbol = f"KRW-{currency}"
            if self._risk.get_position(symbol):
                continue
            amount = balance * avg_price
            self._risk.add_position(
                symbol=symbol,
                entry_price=avg_price,
                volume=balance,
                amount=amount,
            )
            # 거래내역에 합성 매수 기록 삽입 (중복 방지)
            existing = self._storage.get_trades(symbol=symbol, limit=1)
            if not existing:
                self._storage.insert_trade(
                    symbol=symbol,
                    side="bid",
                    price=avg_price,
                    volume=balance,
                    amount=amount,
                    fee=0.0,
                )
            synced += 1
            logger.info(
                "[포지션 동기화] %s | 수량: %f | 평단: %.2f KRW",
                symbol, balance, avg_price,
            )
        if synced:
            logger.info("기존 보유 종목 %d개 동기화 완료", synced)

    def _recover_bb_states(self) -> None:
        """봇 재시작 시 감시 종목의 BB 이탈 상태를 캔들 데이터로 복구합니다."""
        tickers = self._collector.get_top_volume_symbols(
            self._config.strategy.top_volume_count
        )
        params = self._config.strategy
        recovered = 0
        for symbol in tickers:
            try:
                df = self._collector.get_ohlcv(
                    symbol,
                    interval=self._config.candle_interval,
                    count=self._config.candle_count,
                )
                if df.empty:
                    continue
                self._strategy.recover_bb_state(
                    symbol, df["close"], params.bb_period, params.bb_std_dev,
                )
                recovered += 1
                time.sleep(0.1)
            except Exception as e:
                logger.error("BB 상태 복구 오류 [%s]: %s", symbol, e)
        if recovered:
            logger.info("BB 이탈 상태 복구 완료: %d개 종목", recovered)

    def _get_total_balance_krw(self) -> float:
        """전체 자산을 KRW 기준으로 환산합니다."""
        krw = self._collector.get_krw_balance()
        total = krw

        balances = self._collector.get_balances()
        for b in balances:
            currency = b.get("currency", "")
            if currency == "KRW":
                continue
            balance = float(b.get("balance", 0))
            avg_price = float(b.get("avg_buy_price", 0))
            if balance > 0 and avg_price > 0:
                # 현재가로 환산 시도
                symbol = f"KRW-{currency}"
                current = self._collector.get_current_price(symbol)
                if current:
                    total += balance * current
                else:
                    total += balance * avg_price

        return total

    def _check_daily_reset(self) -> None:
        """날짜가 바뀌면 일일 상태를 갱신합니다."""
        today = date.today()
        if today != self._today:
            self._today = today
            # 전일 일일 통계 저장
            try:
                balance = self._get_total_balance_krw()
                self._storage.upsert_daily_stats(
                    stats_date=self._today,
                    total_balance=balance,
                    net_profit=self._risk.daily_realized_pnl,
                    drawdown=0.0,  # TODO: MDD 계산 추가
                )
                self._risk.update_initial_balance(balance)
            except Exception as e:
                logger.error("일일 통계 저장 실패: %s", e)

            # 오래된 가격 스냅샷 정리 (7일 초과)
            try:
                self._storage.cleanup_old_snapshots(days=7)
            except Exception as e:
                logger.error("가격 스냅샷 정리 실패: %s", e)
            # 오래된 잔고 스냅샷 정리 (7일 초과)
            try:
                self._storage.cleanup_old_balance_snapshots(days=7)
            except Exception as e:
                logger.error("잔고 스냅샷 정리 실패: %s", e)

    def _send_daily_report(self) -> None:
        """일일 리포트를 전송합니다."""
        try:
            balance = self._get_total_balance_krw()
            pnl = self._risk.daily_realized_pnl
            pnl_pct = (pnl / (balance - pnl) * 100) if (balance - pnl) > 0 else 0
            trades = self._storage.get_trades(limit=100)
            today_trades = [
                t for t in trades
                if t.get("created_at", "").startswith(str(self._today))
            ]
            asyncio.run(
                self._notifier.notify_daily_report(
                    balance, pnl, pnl_pct, len(today_trades)
                )
            )
        except Exception as e:
            logger.error("일일 리포트 전송 실패: %s", e)
