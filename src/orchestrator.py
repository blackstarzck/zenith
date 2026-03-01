"""
메인 오케스트레이터.
데이터 수집 → 지표 계산 → 전략 판단 → 주문 실행 → 기록/알림의
전체 매매 루프를 통합 관리합니다.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

from src.config import AppConfig, StrategyParams
from src.collector.data_collector import UpbitCollector
from src.strategy.indicators import compute_snapshot, calc_ma_trend, calc_rsi_slope, calc_bb_status
from src.strategy.engine import MeanReversionEngine, Signal
from src.executor.order_executor import OrderExecutor
from src.risk.manager import RiskManager
from src.storage.client import StorageClient
from src.notifier.kakao import KakaoNotifier
from src.report.generator import generate_daily_report
from src.strategy.regime import classify_regime, MarketRegime
from src.collector.news_collector import NewsCollector
from src.strategy.sentiment import SentimentAnalyzer

logger = logging.getLogger(__name__)

# 가격 스냅샷 저장 간격 (틱 수 기준, 10초 루프 × 18 = 약 3분)
_SNAPSHOT_INTERVAL = 18

# 전략 파라미터 핫리로드 간격 (틱 수 기준, 10초 루프 × 6 = 약 1분)
_PARAM_RELOAD_INTERVAL = 6


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
        self._daily_report_sent: bool = False  # 당일 08:00 리포트 발송 여부
        self._consecutive_errors: int = 0     # 연속 에러 횟수 (지수 백오프용)
        self._max_backoff_sec: int = 300          # 최대 백오프 5분
        self._current_regime: str = "ranging"  # 현재 시장 레짐

        # 감성 분석 모듈 (API 키가 설정된 경우에만 활성화)
        self._sentiment_enabled = bool(config.sentiment.groq_api_key and config.sentiment.cryptopanic_api_key)
        if self._sentiment_enabled:
            self._news_collector = NewsCollector(config.sentiment)
            self._sentiment_analyzer = SentimentAnalyzer(config.sentiment)
            self._seen_news_ids: set[str] = set()
            logger.info("뉴스 감성 분석 모듈 활성화")
        else:
            logger.info("감성 분석 비활성화 — GROQ_API_KEY 또는 CRYPTOPANIC_API_KEY 미설정")

    # ── 안전한 알림 래퍼 ───────────────────────────────────

    def _safe_notify(self, method: str, *args, **kwargs) -> None:
        """알림 전송을 안전하게 실행합니다.

        알림 실패가 메인 루프를 죽이지 않도록 모든 예외를 삼킵니다.
        """
        try:
            func = getattr(self._notifier, method, None)
            if func:
                func(*args, **kwargs)
        except Exception:
            logger.warning("알림 전송 실패 (%s) — 무시하고 계속합니다.", method)

    # ── 메인 루프 ────────────────────────────────────────────

    def run(self) -> None:
        """봇 메인 루프를 시작합니다."""
        logger.info("=== Zenith 트레이딩 봇 시작 ===")

        # 초기 잔고로 리스크 매니저 초기화
        try:
            initial_balance = self._get_total_balance_krw()
            # 네트워크 장애로 초기 잔고가 0이면 시작 불가
            if initial_balance <= 0:
                logger.critical('초기 자산 조회 실패: 잔고 0 — 네트워크 상태를 확인하세요')
                self._safe_notify('notify_error', '봇 초기화 실패: 잔고 0 (네트워크 확인 필요)')
                return
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
            # 시작 즉시 오늘의 일일 통계 기록 (대시보드 자산 성장 곡선용)
            self._storage.upsert_daily_stats(
                stats_date=self._today,
                total_balance=initial_balance,
                net_profit=0.0,
                drawdown=0.0,
            )
        except Exception as e:
            logger.critical("초기화 실패: %s", e)
            self._safe_notify("notify_error", f"봇 초기화 실패: {e}")
            return

        self._running = True
        self._storage.upsert_bot_state(is_active=True)

        try:
            while self._running:
                try:
                    self._tick()
                    # 성공 시 연속 에러 카운터 초기화
                    if self._consecutive_errors > 0:
                        logger.info("연속 에러 %d회 후 복구 완료", self._consecutive_errors)
                        self._consecutive_errors = 0
                    time.sleep(self._config.loop_interval_sec)
                except KeyboardInterrupt:
                    logger.info("사용자 종료 요청")
                    self._running = False
                except Exception:
                    self._consecutive_errors += 1
                    logger.exception(
                        "메인 루프 오류 (연속 %d회)", self._consecutive_errors
                    )
                    # 최초 1회만 알림 (연속 에러 시 알림 폭탄 방지)
                    if self._consecutive_errors == 1:
                        self._safe_notify("notify_error", "메인 루프 오류 발생 — 로그를 확인하세요.")
                    # 지수 백오프 (10s, 20s, 40s, ... 최대 300s)
                    backoff = min(
                        self._config.loop_interval_sec * (2 ** self._consecutive_errors),
                        self._max_backoff_sec,
                    )
                    logger.info("백오프 대기: %d초", backoff)
                    time.sleep(backoff)
        finally:
            # 리소스 정리 (HTTP 클라이언트 등)
            self._storage.upsert_bot_state(is_active=False)
            self._notifier.close()
            logger.info("=== Zenith 트레이딩 봇 종료 ===")

    def stop(self) -> None:
        """봇을 안전하게 중지합니다."""
        self._running = False
        self._storage.upsert_bot_state(is_active=False)

    # ── 단일 틱 (1회 루프) ───────────────────────────────────

    def _tick(self) -> None:
        """1회 매매 사이클을 실행합니다."""
        self._loop_count += 1
        self._check_daily_reset()

        # 0. 전략 파라미터 핫리로드 (약 1분마다)
        if self._loop_count % _PARAM_RELOAD_INTERVAL == 0:
            self._reload_strategy_params()

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

        # 1.5. 시장 레짐 감지 (10분마다, 종목 목록 갱신과 동일 주기)
        if self._loop_count % 60 == 1:
            self._update_market_regime()
        # 1.6. 켈리 비중 업데이트 (10분마다, 레짐과 오프셋)
        if self._loop_count % 60 == 2:
            self._update_kelly_fraction()
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
                balance = 0.0  # 아래 스냅샷 저장에서 사용할 폴백 값
            # 4-2. 잔고 스냅샷 저장 (시간별 자산 성장 곡선용)
            if balance > 0:
                try:
                    self._storage.insert_balance_snapshot(balance)
                except Exception as e:
                    logger.error("잔고 스냅샷 저장 실패: %s", e)

        # 4-3. 뉴스 감성 분석 (약 5분 간격)
        if self._sentiment_enabled and self._loop_count % self._config.sentiment.poll_interval_ticks == 0:
            self._run_sentiment_cycle()

        # 5. 일일 리포트 (매일 08:00 1회 발송)
        if not self._daily_report_sent and datetime.now().hour >= 8:
            self._send_daily_report()
            self._daily_report_sent = True

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
                    vol_short_window=self._config.strategy.vol_short_window,
                    vol_long_window=self._config.strategy.vol_long_window,
                    adx_period=self._config.strategy.adx_period,
                )

                # 트레일링 고점 업데이트 (evaluate_exit 호출 전)
                self._risk.update_trailing_high(symbol, snapshot.current_price)

                # Position 객체 직접 전달
                signal = self._strategy.evaluate_exit(symbol, snapshot, pos)

                if signal.signal == Signal.STOP_LOSS:
                    self._execute_sell_all(symbol, pos, signal.reason, label="손절 매도")
                elif signal.signal == Signal.SELL_ALL:
                    self._execute_sell_all(symbol, pos, signal.reason, label="2차 익절")
                elif signal.signal == Signal.SELL_HALF:
                    self._execute_sell_half(symbol, pos, signal.reason)

                # Rate limit 방어
                time.sleep(0.2)

            except ValueError as e:
                logger.debug("청산 평가 건너뜀 [%s]: %s", symbol, e)
            except Exception as e:
                logger.error("청산 평가 오류 [%s]: %s", symbol, e)

    # ── 진입 평가 ────────────────────────────────────────────

    def _evaluate_entries(self) -> None:
        """미보유 종목의 진입 조건을 평가합니다."""
        # 레짐 기반 threshold offset 계산 (하이브리드 필터)
        regime_offset = 0.0
        if self._current_regime == "trending":
            regime_offset = self._config.strategy.regime_trending_offset
        elif self._current_regime == "volatile":
            regime_offset = self._config.strategy.regime_volatile_offset

        if regime_offset > 0 and self._loop_count % 60 == 1:
            logger.info(
                "[레짐 오프셋] 시장 레짐 '%s' — 진입 임계치 +%.0f 적용 중",
                self._current_regime, regime_offset,
            )

        try:
            current_balance = self._get_total_balance_krw()
            krw = self._collector.get_krw_balance()
        except Exception as e:
            logger.error("잔고 조회 실패 — 진입 평가 건너뜀: %s", e)
            return
        # 네트워크 장애로 잔고가 0으로 조회되면 DB에 기록하지 않음 (대시보드 0 표시 방지)
        if current_balance > 0 or krw > 0:
            self._storage.upsert_bot_state(current_balance=current_balance, krw_balance=krw)

        symbol_indicators: dict[str, dict] = {}

        for symbol in self._target_symbols:
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
                    vol_short_window=self._config.strategy.vol_short_window,
                    vol_long_window=self._config.strategy.vol_long_window,
                    adx_period=self._config.strategy.adx_period,
                )

                closes = df["close"]

                # ── 프론트엔드 표시용: 4가지 진입 게이트 지표 수집 ──
                # 1) 변동성 비율
                vol = round(snapshot.volatility_ratio, 2)

                # 2) 추세 (MA20 > MA50)
                trend = calc_ma_trend(closes, short_period=self._config.strategy.ma_short_period, long_period=self._config.strategy.ma_long_period)
                # True/False/None → "up"/"down"/"unknown"
                trend_str = "up" if trend is True else ("down" if trend is False else "unknown")

                # 3) BB 이탈 상태 — 캔들 데이터에서 직접 계산 (stateless)
                bb_str = calc_bb_status(
                    closes,
                    bb_period=self._config.strategy.bb_period,
                    bb_std_dev=self._config.strategy.bb_std_dev,
                    lookback=20,
                )

                # 4) RSI 값 + 기울기
                rsi_val = round(snapshot.rsi, 1)
                rsi_slope = round(
                    calc_rsi_slope(closes, self._config.strategy.rsi_period, lookback=self._config.strategy.rsi_slope_lookback),
                    2,
                )

                symbol_indicators[symbol] = {
                    "vol": vol,
                    "trend": trend_str,
                    "bb": bb_str,
                    "rsi": rsi_val,
                    "rsi_slope": rsi_slope,
                    "adx": round(snapshot.adx, 1),
                }

                # 체결 실패 쿨다운 확인
                if self._executor.is_on_cooldown(symbol):
                    time.sleep(0.2)
                    continue

                can_enter, reason = self._risk.can_enter(symbol, current_balance)
                if not can_enter:
                    time.sleep(0.2)
                    continue

                signal = self._strategy.evaluate_entry(
                    symbol, snapshot, closes,
                    threshold_offset=regime_offset,
                )

                if signal.signal == Signal.BUY:
                    self._execute_buy(symbol, signal, current_balance)
                elif signal.signal == Signal.MARKET_PAUSE:
                    logger.info("[%s] %s", symbol, signal.reason)

                time.sleep(0.2)

            except ValueError as e:
                logger.debug("진입 평가 건너뜀 [%s]: %s", symbol, e)
            except Exception as e:
                logger.error("진입 평가 오류 [%s]: %s", symbol, e)

        # 지표 데이터를 bot_state에 저장
        if symbol_indicators:
            self._storage.upsert_bot_state(symbol_volatilities=symbol_indicators)

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
                    vol_short_window=params.vol_short_window,
                    vol_long_window=params.vol_long_window,
                    adx_period=params.adx_period,
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
        # 켈리 기반 사이징
        recent_trades = self._storage.get_recent_sell_trades(limit=100)
        amount = self._risk.calc_position_size(current_balance, recent_trades)
        if amount <= 0:
            logger.info("[%s] 투입 가능 금액 부족 (Kelly 차단 또는 잔고 부족)", symbol)
            return

        # 슬리피지 체크
        slippage_bps = self._collector.estimate_slippage(symbol, 'buy', amount)
        if slippage_bps > self._risk._params.slippage_threshold_bps:
            logger.info(
                '[슬리피지 초과] %s | 예상: %.1f bps > 한도: %.1f bps, 진입 거부',
                symbol, slippage_bps, self._risk._params.slippage_threshold_bps,
            )
            return

        logger.info(
            "[매수 진입] %s | 사유: %s | 금액: %.0f KRW | 슬리피지: %.1f bps",
            symbol, signal.reason, amount, slippage_bps,
        )

        result = self._executor.buy_market(symbol, amount)
        if not result.success:
            logger.error("[매수 실패] %s: %s", symbol, result.error)
            return

        # 체결 결과 검증 (팬텀 포지션 방지)
        if result.price <= 0 or result.volume <= 0:
            logger.critical(
                "[매수 체결 결과 이상] %s | price=%.2f, volume=%f — 포지션 등록 차단. "
                "업비트 잔고를 수동 확인하세요.",
                symbol, result.price, result.volume,
            )
            self._safe_notify(
                "notify_error",
                f"[긴급] {symbol} 매수 체결되었으나 결과 조회 실패. 업비트 잔고를 확인하세요.",
            )
            return

        # 포지션 등록
        self._risk.add_position(
            symbol=symbol,
            entry_price=result.price,
            volume=result.volume,
            amount=result.amount,
            entry_fee=result.fee,
        )

        # DB 기록 (슬리피지 포함)
        self._storage.insert_trade(
            symbol=symbol,
            side="bid",
            price=result.price,
            volume=result.volume,
            amount=result.amount,
            fee=result.fee,
            reason=signal.reason,
            slippage=slippage_bps,
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
        sell_ratio = self._config.strategy.take_profit_sell_ratio
        half_volume = actual_volume * sell_ratio
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
            return

        logger.info("[1차 익절] %s | 사유: %s", symbol, reason)

        result = self._executor.sell_half(symbol, actual_volume, ratio=self._config.strategy.take_profit_sell_ratio)
        if not result.success:
            logger.error("[1차 익절 실패] %s: %s", symbol, result.error)
            return

        self._risk.mark_half_sold(symbol, current_price=result.price)

        # 실현 손익 계산 (매수 수수료 비례 배분 포함)
        buy_fee_share = pos.entry_fee * (result.volume / pos.volume) if pos.volume > 0 else 0.0
        pnl = result.amount - (pos.entry_price * result.volume) - result.fee - buy_fee_share
        pnl_pct = ((result.price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0
        self._risk.record_realized_pnl(pnl)

        remaining = actual_volume - result.volume
        self._storage.insert_trade(
            symbol=symbol, side="ask",
            price=result.price, volume=result.volume,
            amount=result.amount, fee=result.fee,
            pnl=pnl,
            remaining_volume=remaining if remaining > 0 else None,
            reason=reason,
        )

        self._safe_notify("notify_pnl", symbol, result.price, pnl, pnl_pct, reason)

    def _execute_sell_all(self, symbol: str, pos, reason: str, label: str = "전량 매도") -> None:
        """전량 매도를 실행합니다."""
        # 실제 보유량 조회 (1차 익절 후 잔량 반영)
        actual_volume = self._collector.get_balance(symbol)
        if actual_volume <= 0:
            self._risk.remove_position(symbol)
            return

        logger.info("[%s] %s | 사유: %s", label, symbol, reason)

        result = self._executor.sell_all(symbol, actual_volume)
        if not result.success:
            logger.error("[%s 실패] %s: %s", label, symbol, result.error)
            return

        # 실현 손익 계산 (매수 수수료 비례 배분 포함)
        buy_fee_share = pos.entry_fee * (result.volume / pos.volume) if pos.volume > 0 else 0.0
        pnl = result.amount - (pos.entry_price * result.volume) - result.fee - buy_fee_share
        pnl_pct = ((result.price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0
        self._risk.record_realized_pnl(pnl)

        self._risk.remove_position(symbol)

        self._storage.insert_trade(
            symbol=symbol, side="ask",
            price=result.price, volume=result.volume,
            amount=result.amount, fee=result.fee,
            pnl=pnl,
            remaining_volume=0.0,
            reason=reason,
        )

        self._safe_notify("notify_pnl", symbol, result.price, pnl, pnl_pct, reason)

        # 일일 손실 한도 초과 알림
        if self._risk.is_daily_stopped:
            self._safe_notify("notify_daily_stop", self._risk.daily_realized_pnl)

    # ── 시장 레짐 감지 ─────────────────────────────────────

    def _update_market_regime(self) -> None:
        """BTC-KRW 데이터로 시장 레짐을 판단하고 bot_state에 저장합니다."""
        try:
            df = self._collector.get_ohlcv(
                "KRW-BTC",
                interval=self._config.candle_interval,
                count=self._config.candle_count,
            )
            if df.empty:
                logger.warning("BTC-KRW OHLCV 데이터 없음 — 레짐 판단 건너뜀")
                return

            params = self._config.strategy
            result = classify_regime(
                df,
                adx_trending_threshold=params.regime_adx_trending_threshold,
                vol_overload_ratio=params.regime_vol_overload_ratio,
                adx_period=params.adx_period,
                vol_short_window=params.vol_short_window,
                vol_long_window=params.vol_long_window,
                ma_short_period=params.ma_short_period,
                ma_long_period=params.ma_long_period,
                lookback_candles=params.regime_lookback_candles,
            )

            new_regime = result.regime.value
            if new_regime != self._current_regime:
                logger.info(
                    "[레짐 변경] %s → %s | ADX=%.1f, Vol=%.2f | 사유: %s",
                    self._current_regime, new_regime,
                    result.adx, result.volatility_ratio, result.reason,
                )
                self._current_regime = new_regime

            self._storage.upsert_bot_state(market_regime=self._current_regime)

        except Exception:
            logger.warning("시장 레짐 판단 실패 — 기존 레짐 유지 (%s)", self._current_regime)

    def _update_kelly_fraction(self) -> None:
        """켈리 비중을 계산하여 bot_state에 업데이트합니다."""
        try:
            recent_trades = self._storage.get_recent_sell_trades(limit=100)
            if not recent_trades or len(recent_trades) < self._risk._params.kelly_min_trades:
                kelly_f = None  # 데이터 부족
            else:
                wins = [t['pnl'] for t in recent_trades if t.get('pnl', 0) > 0]
                losses = [t['pnl'] for t in recent_trades if t.get('pnl', 0) < 0]
                if not losses or not wins:
                    kelly_f = None
                else:
                    total = len(wins) + len(losses)
                    win_rate = len(wins) / total
                    avg_win = sum(wins) / len(wins)
                    avg_loss = abs(sum(losses) / len(losses))
                    if avg_loss == 0:
                        kelly_f = None
                    else:
                        raw_kelly = win_rate - ((1 - win_rate) / (avg_win / avg_loss))
                        kelly_f = min(raw_kelly * self._risk._params.kelly_multiplier,
                                      self._risk._params.max_position_ratio)
                        if kelly_f <= 0:
                            kelly_f = 0.0
            self._storage.upsert_bot_state(kelly_fraction=kelly_f)
        except Exception as e:
            logger.warning('[Kelly 업데이트 실패] %s', e)
    # ── 전략 파라미터 핫리로드 ─────────────────────────────────

    def _reload_strategy_params(self) -> None:
        """DB에서 전략 파라미터를 읽어 엔진에 반영합니다.

        프론트엔드에서 bot_state.strategy_params에 저장한 값을
        약 1분 간격으로 폴링하여 MeanReversionEngine에 핫리로드합니다.
        DB에 값이 없으면 (None) 아무 것도 하지 않습니다.
        """
        try:
            saved = self._storage.get_strategy_params()
            if saved is None:
                return
            new_params = StrategyParams.from_dict(saved)
            if new_params != self._config.strategy:
                self._config = AppConfig(
                    upbit=self._config.upbit,
                    supabase=self._config.supabase,
                    kakao=self._config.kakao,
                    strategy=new_params,
                    risk=self._config.risk,
                    sentiment=self._config.sentiment,
                    loop_interval_sec=self._config.loop_interval_sec,
                    candle_interval=self._config.candle_interval,
                    candle_count=self._config.candle_count,
                )
                self._strategy.update_params(new_params)
                logger.info("전략 파라미터 핫리로드 완료: %s", saved)
        except Exception:
            logger.warning("전략 파라미터 핫리로드 실패 — 기존 값 유지")
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
                    reason="포지션 동기화 (봇 재시작)",
                )
            synced += 1
            logger.info(
                "[포지션 동기화] %s | 수량: %f | 평단: %.2f KRW",
                symbol, balance, avg_price,
            )
        if synced:
            logger.info("기존 보유 종목 %d개 동기화 완료", synced)

    def _get_total_balance_krw(self) -> float:
        """전체 자산을 KRW 기준으로 환산합니다.

        네트워크 오류 시에도 봇이 죽지 않도록 개별 API 호출을 보호합니다.
        """
        try:
            krw = self._collector.get_krw_balance()
        except Exception as e:
            logger.error("KRW 잔고 조회 실패: %s", e)
            krw = 0.0

        total = krw

        try:
            balances = self._collector.get_balances()
        except Exception as e:
            logger.error("전체 잔고 조회 실패: %s", e)
            return total

        for b in balances:
            currency = b.get("currency", "")
            if currency == "KRW":
                continue
            balance = float(b.get("balance", 0))
            avg_price = float(b.get("avg_buy_price", 0))
            if balance > 0 and avg_price > 0:
                # 현재가로 환산 시도
                symbol = f"KRW-{currency}"
                try:
                    current = self._collector.get_current_price(symbol)
                except Exception:
                    current = None
                if current:
                    total += balance * current
                else:
                    total += balance * avg_price

        return total

    def _check_daily_reset(self) -> None:
        """날짜가 바뀌면 전일 stats를 확정하고 새 거래일을 초기화합니다."""
        today = date.today()
        if today != self._today:
            try:
                balance = self._get_total_balance_krw()

                # 네트워크 장애로 잔고가 0으로 조회되면 stats/리포트 기록 건너뜀
                if balance > 0:
                    # 1) 전일 최종 stats 확정 (self._today는 아직 어제)
                    self._storage.upsert_daily_stats(
                        stats_date=self._today,
                        total_balance=balance,
                        net_profit=self._risk.daily_realized_pnl,
                        drawdown=0.0,  # TODO: MDD 계산 추가
                    )

                    # 1-1) 일일 분석 리포트 생성 (날짜 전환 전에 실행)
                    try:
                        generate_daily_report(
                            storage=self._storage,
                            report_date=self._today,
                            total_balance=balance,
                            net_profit=self._risk.daily_realized_pnl,
                            initial_balance=self._risk._initial_balance,
                        )
                        logger.info("일일 분석 리포트 생성 완료: %s", self._today)
                    except Exception as e:
                        logger.error("일일 분석 리포트 생성 실패: %s", e)
                else:
                    logger.warning("네트워크 장애 추정: 잔고 0 조회 — 전일 통계/리포트 기록 건너뜀")

                # 2) 날짜 전환 + 리스크 매니저 리셋 (PnL 0, 초기 잔고 갱신)
                self._today = today
                if balance > 0:
                    self._risk.reset_daily(balance)
                self._daily_report_sent = False

                # 3) 금일 stats 초기 행 삽입 (net_profit=0) — 잔고 유효할 때만
                if balance > 0:
                    self._storage.upsert_daily_stats(
                        stats_date=self._today,
                        total_balance=balance,
                        net_profit=0.0,
                        drawdown=0.0,
                    )
            except Exception as e:
                logger.error("일일 통계 저장/리셋 실패: %s", e)
                # 날짜 전환은 반드시 수행 (다음 틱에서 무한 반복 방지)
                self._today = today
                self._daily_report_sent = False

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

            # 오래된 감성 분석 결과 정리 (7일 초과)
            if self._sentiment_enabled:
                try:
                    self._storage.cleanup_old_sentiment_insights(days=7)
                except Exception as e:
                    logger.error("감성 분석 결과 정리 실패: %s", e)

    def _run_sentiment_cycle(self) -> None:
        """뉴스 수집 → 감성 분석 → DB 저장 사이클을 실행합니다."""
        try:
            news_list = self._news_collector.fetch_latest_news(self._seen_news_ids)
            if not news_list:
                return

            analyzed = 0
            for news in news_list:
                try:
                    analysis = self._sentiment_analyzer.analyze(
                        title=news["title"],
                        source=news["source"],
                        currencies=news["currencies"],
                    )

                    insight = {
                        "news_id": news["news_id"],
                        "title": news["title"],
                        "source": news["source"],
                        "url": news["url"],
                        "currencies": news["currencies"],
                        **analysis,
                    }

                    self._storage.insert_sentiment_insight(insight)
                    self._seen_news_ids.add(news["news_id"])
                    analyzed += 1

                    time.sleep(1.0)  # Gemini rate limit 방어

                except Exception as e:
                    logger.error("감성 분석 실패 [%s]: %s", news.get("title", "?")[:30], e)

            if analyzed:
                logger.info("[감성 분석] %d건 뉴스 분석 완료", analyzed)

        except Exception:
            logger.warning("감성 분석 사이클 실패 — 다음 주기에 재시도")

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
            self._safe_notify(
                "notify_daily_report",
                balance, pnl, pnl_pct, len(today_trades),
            )
        except Exception as e:
            logger.error("일일 리포트 전송 실패: %s", e)
