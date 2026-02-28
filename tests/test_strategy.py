"""
평균 회귀 전략 엔진 유닛 테스트.
"""

import pytest
import pandas as pd

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
    def test_high_volatility_lowers_score(self):
        """높은 변동성은 Vol 스코어를 0으로 만든다."""
        engine = make_engine(StrategyParams(entry_score_threshold=95.0))
        snap = make_snapshot(volatility_ratio=3.0, rsi=20, adx=15)
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert signal.score is not None
        assert "Vol:0" in signal.reason

    def test_high_adx_lowers_score(self):
        """높은 ADX(강한 추세)는 ADX 스코어를 0으로 만든다."""
        engine = make_engine(StrategyParams(entry_score_threshold=95.0))
        snap = make_snapshot(adx=40.0)
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert "ADX:0" in signal.reason

    def test_low_adx_raises_score(self):
        """낮은 ADX(횡보)는 ADX 스코어를 100으로 만든다."""
        engine = make_engine(StrategyParams(entry_score_threshold=95.0))
        snap = make_snapshot(adx=15.0)
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert "ADX:100" in signal.reason

    def test_high_rsi_lowers_score(self):
        """높은 RSI는 RSI 스코어를 0으로 만든다."""
        engine = make_engine(StrategyParams(entry_score_threshold=95.0))
        snap = make_snapshot(rsi=55.0)
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert "RSI:0" in signal.reason

    def test_favorable_conditions_trigger_buy(self):
        """모든 조건이 유리하면 높은 스코어로 BUY."""
        # Without closes_series: BB=0, RSI slope=50 (neutral), MA=50 (neutral)
        # Vol: (3-0.5)/2*100=125→100, MA:50, ADX:(40-10)/25*100=120→100,
        # BB:0, RSI↗:50, RSI:(45-20)/25*100=100
        # weighted avg = (100+50+100+0+50+100)/6 = 66.7
        params = StrategyParams(entry_score_threshold=50.0)
        engine = make_engine(params)
        snap = make_snapshot(price=48500, rsi=20, adx=10, volatility_ratio=0.5)
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert signal.signal == Signal.BUY
        assert signal.score >= 50.0
        assert signal.stop_loss_price is not None
        assert signal.target_price_1 is not None
        assert signal.target_price_2 is not None

    def test_score_always_in_0_100_range(self):
        """스코어는 항상 0~100 범위."""
        engine = make_engine()
        # Extreme values
        snap = make_snapshot(volatility_ratio=10.0, rsi=99, adx=99)
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert signal.score is not None
        assert 0 <= signal.score <= 100

    def test_weight_zero_excludes_filter(self):
        """가중치 0인 필터는 결과에 영향 없음."""
        # All weights 0 except RSI level
        params = StrategyParams(
            w_volatility=0, w_ma_trend=0, w_adx=0,
            w_bb_recovery=0, w_rsi_slope=0, w_rsi_level=1.0,
            entry_score_threshold=50.0,
        )
        engine = make_engine(params)
        snap = make_snapshot(rsi=20)  # RSI score = (45-20)/25*100 = 100
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert signal.signal == Signal.BUY
        assert signal.score == 100.0  # Only RSI level matters

    def test_all_weights_zero_returns_hold(self):
        """모든 가중치 0이면 HOLD."""
        params = StrategyParams(
            w_volatility=0, w_ma_trend=0, w_adx=0,
            w_bb_recovery=0, w_rsi_slope=0, w_rsi_level=0,
        )
        engine = make_engine(params)
        snap = make_snapshot(rsi=20, adx=10, volatility_ratio=0.5)
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert signal.signal == Signal.HOLD
        assert signal.score == 0.0

    def test_threshold_boundary(self):
        """임계치 정확히 일치 시 BUY."""
        # Only RSI level active, RSI=20 → score=100
        params = StrategyParams(
            w_volatility=0, w_ma_trend=0, w_adx=0,
            w_bb_recovery=0, w_rsi_slope=0, w_rsi_level=1.0,
            entry_score_threshold=100.0,
        )
        engine = make_engine(params)
        snap = make_snapshot(rsi=20)  # score exactly 100
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert signal.signal == Signal.BUY

    def test_score_field_populated(self):
        """TradeSignal.score 필드가 채워짐."""
        engine = make_engine()
        snap = make_snapshot()
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert signal.score is not None
        assert isinstance(signal.score, float)

    def test_reason_contains_score_breakdown(self):
        """reason 문자열에 스코어 내역 포함."""
        engine = make_engine()
        snap = make_snapshot()
        signal = engine.evaluate_entry("KRW-BTC", snap)
        assert "스코어" in signal.reason
        assert "Vol:" in signal.reason
        assert "MA:" in signal.reason
        assert "ADX:" in signal.reason
        assert "BB:" in signal.reason
        assert "RSI↗:" in signal.reason
        assert "RSI:" in signal.reason

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
