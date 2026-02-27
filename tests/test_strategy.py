"""
평균 회귀 전략 엔진 유닛 테스트.
"""

import pytest

from src.config import StrategyParams
from src.strategy.engine import MeanReversionEngine, Signal, TradeSignal
from src.strategy.indicators import BollingerBands, IndicatorSnapshot


# ── 헬퍼 ─────────────────────────────────────────────────────

def make_snapshot(
    price: float = 50000,
    bb_upper: float = 52000,
    bb_middle: float = 50000,
    bb_lower: float = 48000,
    rsi: float = 50.0,
    atr: float = 500.0,
    volatility_ratio: float = 1.0,
    adx: float = 15.0,
) -> IndicatorSnapshot:
    return IndicatorSnapshot(
        bb=BollingerBands(
            upper=bb_upper,
            middle=bb_middle,
            lower=bb_lower,
            bandwidth=(bb_upper - bb_lower) / bb_middle,
        ),
        rsi=rsi,
        atr=atr,
        current_price=price,
        volatility_ratio=volatility_ratio,
        adx=adx,
    )


def make_engine(params: StrategyParams | None = None) -> MeanReversionEngine:
    return MeanReversionEngine(params or StrategyParams())


# ── 진입 조건 테스트 ─────────────────────────────────────────

class TestEntrySignals:
    def test_volatility_overload_pauses_trading(self):
        """변동성 과부하 시 MARKET_PAUSE."""
        engine = make_engine()
        snap = make_snapshot(volatility_ratio=2.5)
        signal = engine.evaluate_entry("KRW-BTC", snap)

        assert signal.signal == Signal.MARKET_PAUSE
        assert "변동성 과부하" in signal.reason

    def test_no_bb_breakout_history_hold(self):
        """BB 하단 이탈 이력 없으면 HOLD."""
        engine = make_engine()
        snap = make_snapshot(price=49000, bb_lower=48000)
        signal = engine.evaluate_entry("KRW-BTC", snap)

        assert signal.signal == Signal.HOLD
        assert "이탈 이력 없음" in signal.reason

    def test_currently_below_bb_lower_hold(self):
        """BB 하단 이탈 중이면 복귀 대기."""
        engine = make_engine()
        snap = make_snapshot(price=47000, bb_lower=48000)
        signal = engine.evaluate_entry("KRW-BTC", snap)

        assert signal.signal == Signal.HOLD
        assert "이탈 중" in signal.reason

    def test_bb_recovery_with_rsi_oversold_triggers_buy(self):
        """BB 하단 이탈 후 복귀 + RSI 과매도 → 매수 신호."""
        engine = make_engine()

        # 1단계: 하단 이탈 기록
        snap_below = make_snapshot(price=47000, bb_lower=48000, rsi=25)
        engine.evaluate_entry("KRW-BTC", snap_below)

        # 2단계: 밴드 안으로 복귀 + RSI 과매도
        snap_recovered = make_snapshot(price=48500, bb_lower=48000, rsi=28)
        signal = engine.evaluate_entry("KRW-BTC", snap_recovered)

        assert signal.signal == Signal.BUY
        assert signal.stop_loss_price is not None
        assert signal.target_price_1 is not None  # BB 중앙선
        assert signal.target_price_2 is not None  # BB 상단선

    def test_bb_recovery_but_rsi_too_high_hold(self):
        """BB 복귀했지만 RSI가 과매도 구간이 아니면 HOLD."""
        engine = make_engine()

        # 하단 이탈 기록
        snap_below = make_snapshot(price=47000, bb_lower=48000)
        engine.evaluate_entry("KRW-BTC", snap_below)

        # 복귀했지만 RSI 높음
        snap_recovered = make_snapshot(price=48500, bb_lower=48000, rsi=55)
        signal = engine.evaluate_entry("KRW-BTC", snap_recovered)

        assert signal.signal == Signal.HOLD
        assert "과매도 구간 아님" in signal.reason

    def test_different_symbols_tracked_independently(self):
        """종목별 BB 이탈 상태는 독립적으로 추적."""
        engine = make_engine()

        # BTC 하단 이탈
        engine.evaluate_entry("KRW-BTC", make_snapshot(price=47000, bb_lower=48000))

        # ETH는 이탈 이력 없음
        signal_eth = engine.evaluate_entry(
            "KRW-ETH",
            make_snapshot(price=3500, bb_lower=3000),
        )
        assert signal_eth.signal == Signal.HOLD
        assert "이탈 이력 없음" in signal_eth.reason

    def test_reset_tracking_clears_state(self):
        """reset_tracking 호출 시 상태 초기화."""
        engine = make_engine()

        # 하단 이탈 기록
        engine.evaluate_entry("KRW-BTC", make_snapshot(price=47000, bb_lower=48000))
        engine.reset_tracking("KRW-BTC")

        # 복귀해도 이력이 없으므로 HOLD
        signal = engine.evaluate_entry(
            "KRW-BTC",
            make_snapshot(price=48500, bb_lower=48000, rsi=25),
        )
        assert signal.signal == Signal.HOLD

    def test_adx_strong_trend_blocks_entry(self):
        """ADX가 추세 임계치 초과 시 평균 회귀 진입 차단."""
        engine = make_engine()

        # 하단 이탈 기록
        engine.evaluate_entry("KRW-BTC", make_snapshot(price=47000, bb_lower=48000))

        # 복귀 + RSI 과매도이지만 ADX가 높음 (강한 추세)
        snap = make_snapshot(price=48500, bb_lower=48000, rsi=25, adx=30.0)
        signal = engine.evaluate_entry("KRW-BTC", snap)

        assert signal.signal == Signal.HOLD
        assert "ADX" in signal.reason

    def test_adx_weak_trend_allows_entry(self):
        """ADX가 낮으면 (횡보) 평균 회귀 진입 허용."""
        engine = make_engine()

        # 하단 이탈 기록
        engine.evaluate_entry("KRW-BTC", make_snapshot(price=47000, bb_lower=48000))

        # 복귀 + RSI 과매도 + ADX 낮음 (횡보장)
        snap = make_snapshot(price=48500, bb_lower=48000, rsi=25, adx=15.0)
        signal = engine.evaluate_entry("KRW-BTC", snap)

        assert signal.signal == Signal.BUY

# ── 청산 조건 테스트 ─────────────────────────────────────────

class TestExitSignals:
    def test_stop_loss_triggers(self):
        """가격이 ATR 기반 손절선 이하면 STOP_LOSS."""
        engine = make_engine()
        snap = make_snapshot(price=47000, atr=500)
        # 진입가 50000, 손절선 = 50000 - 500 * 2.5 = 48750
        signal = engine.evaluate_exit("KRW-BTC", snap, entry_price=50000)

        assert signal.signal == Signal.STOP_LOSS
        assert "동적 손절" in signal.reason

    def test_bb_upper_triggers_sell_all(self):
        """가격이 BB 상단선에 도달하면 SELL_ALL."""
        engine = make_engine()
        snap = make_snapshot(price=52500, bb_upper=52000, atr=500)
        signal = engine.evaluate_exit("KRW-BTC", snap, entry_price=50000)

        assert signal.signal == Signal.SELL_ALL

    def test_bb_middle_triggers_sell_half_first_time(self):
        """BB 중앙선 도달 + 아직 1차 익절 안했으면 SELL_HALF."""
        engine = make_engine()
        snap = make_snapshot(price=50500, bb_middle=50000, atr=500)
        signal = engine.evaluate_exit(
            "KRW-BTC", snap, entry_price=48000, has_sold_half=False,
        )

        assert signal.signal == Signal.SELL_HALF

    def test_bb_middle_already_sold_half_hold(self):
        """1차 익절 이미 완료 시, 중앙선에서 HOLD."""
        engine = make_engine()
        snap = make_snapshot(price=50500, bb_middle=50000, atr=500)
        signal = engine.evaluate_exit(
            "KRW-BTC", snap, entry_price=48000, has_sold_half=True,
        )

        assert signal.signal == Signal.HOLD

    def test_stop_loss_priority_over_take_profit(self):
        """손절 조건이 익절보다 우선."""
        engine = make_engine()
        # 가격이 BB 상단 위이지만 손절선 이하 (비현실적이지만 우선순위 테스트)
        snap = make_snapshot(price=44000, bb_upper=45000, atr=500)
        signal = engine.evaluate_exit("KRW-BTC", snap, entry_price=50000)

        assert signal.signal == Signal.STOP_LOSS

    def test_hold_when_no_exit_condition(self):
        """청산 조건 미충족 시 HOLD."""
        engine = make_engine()
        snap = make_snapshot(price=49500, bb_middle=50000, bb_upper=52000, atr=500)
        signal = engine.evaluate_exit("KRW-BTC", snap, entry_price=49000)

        assert signal.signal == Signal.HOLD
        assert signal.stop_loss_price is not None
