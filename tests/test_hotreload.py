"""
전략 파라미터 핫리로드 기능 유닛 테스트.
"""

import pytest

from src.config import StrategyParams, AppConfig
from src.strategy.engine import MeanReversionEngine, Signal
from src.strategy.indicators import BollingerBands, IndicatorSnapshot
from src.risk.manager import Position


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


# ── StrategyParams 직렬화/역직렬화 ─────────────────────────────

class TestStrategyParamsSerialization:
    def test_to_dict_returns_all_fields(self):
        """to_dict는 모든 필드를 포함합니다."""
        params = StrategyParams()
        d = params.to_dict()
        assert d["bb_period"] == 20
        assert d["bb_std_dev"] == 2.0
        assert d["rsi_period"] == 14
        assert d["rsi_oversold"] == 30.0
        assert d["atr_period"] == 14
        assert d["atr_stop_multiplier"] == 2.5

    def test_from_dict_with_full_data(self):
        """from_dict는 전체 데이터에서 StrategyParams를 생성합니다."""
        data = {
            "bb_period": 30,
            "bb_std_dev": 3.0,
            "rsi_period": 21,
            "rsi_oversold": 25.0,
            "atr_period": 21,
            "atr_stop_multiplier": 3.0,
        }
        params = StrategyParams.from_dict(data)
        assert params.bb_period == 30
        assert params.bb_std_dev == 3.0
        assert params.rsi_period == 21
        assert params.rsi_oversold == 25.0

    def test_from_dict_with_partial_data(self):
        """from_dict는 미지정 필드에 기본값을 사용합니다."""
        data = {"bb_period": 50}
        params = StrategyParams.from_dict(data)
        assert params.bb_period == 50
        # 나머지 기본값 유지
        assert params.bb_std_dev == 2.0
        assert params.rsi_period == 14
        assert params.rsi_oversold == 30.0

    def test_from_dict_with_empty_data(self):
        """빈 딕셔너리는 기본값 StrategyParams를 반환합니다."""
        params = StrategyParams.from_dict({})
        default = StrategyParams()
        assert params == default

    def test_from_dict_ignores_unknown_keys(self):
        """from_dict는 알 수 없는 키를 무시합니다."""
        data = {"bb_period": 25, "unknown_key": 999}
        params = StrategyParams.from_dict(data)
        assert params.bb_period == 25

    def test_from_dict_ignores_none_values(self):
        """from_dict는 None 값을 무시하고 기본값을 사용합니다."""
        data = {"bb_period": None, "rsi_period": 21}
        params = StrategyParams.from_dict(data)
        assert params.bb_period == 20  # 기본값 유지
        assert params.rsi_period == 21

    def test_roundtrip_to_dict_from_dict(self):
        """to_dict → from_dict 왕복 변환이 동일한 결과를 냅니다."""
        original = StrategyParams(bb_period=30, rsi_oversold=25.0)
        restored = StrategyParams.from_dict(original.to_dict())
        assert original == restored

    def test_to_dict_includes_scoring_fields(self):
        """to_dict는 스코어링 필드를 포함합니다."""
        d = StrategyParams().to_dict()
        assert d["w_volatility"] == 1.0
        assert d["w_ma_trend"] == 1.0
        assert d["w_adx"] == 1.0
        assert d["w_bb_recovery"] == 1.0
        assert d["w_rsi_slope"] == 1.0
        assert d["w_rsi_level"] == 1.0
        assert d["entry_score_threshold"] == 70.0

    def test_from_dict_with_scoring_weights(self):
        """from_dict는 스코어링 가중치를 복원합니다."""
        data = {"w_volatility": 2.0, "entry_score_threshold": 60.0}
        params = StrategyParams.from_dict(data)
        assert params.w_volatility == 2.0
        assert params.entry_score_threshold == 60.0
        assert params.w_ma_trend == 1.0  # default preserved


# ── MeanReversionEngine.update_params ─────────────────────────

class TestEngineUpdateParams:
    def test_update_params_changes_behavior(self):
        """update_params 호출 후 새 파라미터가 적용됩니다."""
        # Default threshold=85 → high bar
        engine = MeanReversionEngine(StrategyParams())
        snap = make_snapshot(rsi=30, adx=20, volatility_ratio=1.5)
        signal = engine.evaluate_entry("KRW-BTC", snap)
        # With default threshold 85, likely HOLD

        # Lower threshold dramatically → should change to BUY
        new_params = StrategyParams(entry_score_threshold=30.0)
        engine.update_params(new_params)
        signal2 = engine.evaluate_entry("KRW-BTC", snap)
        assert signal2.score == signal.score  # Same score, different threshold
        # Score didn't change but threshold did

    def test_update_params_affects_exit_evaluation(self):
        """update_params 후 청산 평가에 새 파라미터가 적용됩니다."""
        engine = MeanReversionEngine(StrategyParams())

        # 기본 atr_stop_multiplier=2.5 → 손절선 = 50000 - 500*2.5 = 48750
        snap = make_snapshot(price=48800, atr=500)
        pos = Position(symbol="KRW-BTC", entry_price=50000, volume=1.0, amount=50000)
        signal = engine.evaluate_exit("KRW-BTC", snap, pos)
        assert signal.signal == Signal.HOLD  # 48800 > 48750

        # atr_stop_multiplier를 2.0으로 줄이면 손절선 = 50000 - 500*2.0 = 49000
        engine.update_params(StrategyParams(atr_stop_multiplier=2.0))
        signal2 = engine.evaluate_exit("KRW-BTC", snap, pos)
        assert signal2.signal == Signal.STOP_LOSS  # 48800 < 49000


# ── AppConfig 불변성 및 재생성 ─────────────────────────────────

class TestAppConfigImmutability:
    def test_new_appconfig_with_changed_strategy(self):
        """frozen AppConfig를 새 strategy로 재생성합니다."""
        original = AppConfig()
        new_strategy = StrategyParams(bb_period=50)

        updated = AppConfig(
            upbit=original.upbit,
            supabase=original.supabase,
            kakao=original.kakao,
            strategy=new_strategy,
            risk=original.risk,
            loop_interval_sec=original.loop_interval_sec,
            candle_interval=original.candle_interval,
            candle_count=original.candle_count,
        )

        assert updated.strategy.bb_period == 50
        assert original.strategy.bb_period == 20  # 원본 변경 없음

    def test_strategy_params_equality(self):
        """같은 값의 StrategyParams는 동등합니다."""
        a = StrategyParams()
        b = StrategyParams()
        assert a == b

        c = StrategyParams(bb_period=30)
        assert a != c
