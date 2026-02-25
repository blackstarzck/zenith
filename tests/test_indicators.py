"""
기술 지표 계산 모듈 유닛 테스트.
"""

import pytest
import pandas as pd
import numpy as np

from src.strategy.indicators import (
    calc_bollinger_bands,
    calc_rsi,
    calc_atr,
    calc_volatility_ratio,
    calc_rsi_slope,
    compute_snapshot,
    BollingerBands,
)


# ── 테스트 데이터 생성 헬퍼 ──────────────────────────────────

def make_closes(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def make_ohlcv_df(n: int = 200, base_price: float = 50000.0) -> pd.DataFrame:
    """랜덤 OHLCV DataFrame 생성."""
    np.random.seed(42)
    returns = np.random.normal(0, 0.02, n)
    prices = base_price * np.cumprod(1 + returns)

    highs = prices * (1 + np.abs(np.random.normal(0, 0.005, n)))
    lows = prices * (1 - np.abs(np.random.normal(0, 0.005, n)))

    return pd.DataFrame({
        "open": prices * (1 + np.random.normal(0, 0.001, n)),
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": np.random.uniform(100, 10000, n),
    })


# ── Bollinger Bands ──────────────────────────────────────────

class TestBollingerBands:
    def test_basic_calculation(self):
        closes = make_closes([float(i) for i in range(1, 25)])
        bb = calc_bollinger_bands(closes, period=20, std_dev=2.0)

        assert isinstance(bb, BollingerBands)
        assert bb.lower < bb.middle < bb.upper
        assert bb.bandwidth > 0

    def test_middle_is_sma(self):
        closes = make_closes([float(i) for i in range(1, 25)])
        bb = calc_bollinger_bands(closes, period=20, std_dev=2.0)

        expected_sma = closes.iloc[-20:].mean()
        assert abs(bb.middle - expected_sma) < 1e-10

    def test_band_width_increases_with_std_dev(self):
        closes = make_closes([float(i) for i in range(1, 25)])
        bb1 = calc_bollinger_bands(closes, period=20, std_dev=1.0)
        bb2 = calc_bollinger_bands(closes, period=20, std_dev=2.0)
        bb3 = calc_bollinger_bands(closes, period=20, std_dev=3.0)

        assert bb1.bandwidth < bb2.bandwidth < bb3.bandwidth

    def test_constant_prices_zero_width(self):
        closes = make_closes([100.0] * 25)
        bb = calc_bollinger_bands(closes, period=20, std_dev=2.0)

        assert bb.upper == bb.middle == bb.lower == 100.0
        assert bb.bandwidth == 0.0

    def test_insufficient_data_raises(self):
        closes = make_closes([1.0] * 10)
        with pytest.raises(ValueError, match="데이터 부족"):
            calc_bollinger_bands(closes, period=20)


# ── RSI ──────────────────────────────────────────────────────

class TestRSI:
    def test_all_gains_returns_near_100(self):
        """연속 상승 시 RSI ≈ 100."""
        closes = make_closes([100 + i * 2 for i in range(20)])
        rsi = calc_rsi(closes, period=14)
        assert rsi > 95.0

    def test_all_losses_returns_near_0(self):
        """연속 하락 시 RSI ≈ 0."""
        closes = make_closes([200 - i * 2 for i in range(20)])
        rsi = calc_rsi(closes, period=14)
        assert rsi < 5.0

    def test_rsi_range(self):
        """RSI는 항상 0~100 사이."""
        df = make_ohlcv_df(100)
        rsi = calc_rsi(df["close"], period=14)
        assert 0.0 <= rsi <= 100.0

    def test_mixed_movement_moderate(self):
        """혼합 움직임 시 RSI는 30~70 범위."""
        np.random.seed(123)
        prices = 50000 + np.cumsum(np.random.normal(0, 100, 50))
        closes = make_closes(prices.tolist())
        rsi = calc_rsi(closes, period=14)
        assert 20.0 <= rsi <= 80.0

    def test_insufficient_data_raises(self):
        closes = make_closes([1.0] * 10)
        with pytest.raises(ValueError, match="데이터 부족"):
            calc_rsi(closes, period=14)


# ── ATR ──────────────────────────────────────────────────────

class TestATR:
    def test_positive_atr(self):
        df = make_ohlcv_df(50)
        atr = calc_atr(df["high"], df["low"], df["close"], period=14)
        assert atr > 0

    def test_zero_volatility(self):
        """변동이 없으면 ATR ≈ 0."""
        n = 20
        flat = pd.Series([100.0] * n)
        atr = calc_atr(flat, flat, flat, period=14)
        assert atr < 1e-10

    def test_higher_volatility_higher_atr(self):
        """변동성이 높을수록 ATR이 큼."""
        n = 50
        np.random.seed(42)

        # 저변동성
        low_vol = pd.DataFrame({
            "high": 100 + np.random.uniform(0, 1, n),
            "low": 100 - np.random.uniform(0, 1, n),
            "close": 100 + np.random.normal(0, 0.5, n),
        })

        # 고변동성
        high_vol = pd.DataFrame({
            "high": 100 + np.random.uniform(0, 10, n),
            "low": 100 - np.random.uniform(0, 10, n),
            "close": 100 + np.random.normal(0, 5, n),
        })

        atr_low = calc_atr(low_vol["high"], low_vol["low"], low_vol["close"], period=14)
        atr_high = calc_atr(high_vol["high"], high_vol["low"], high_vol["close"], period=14)

        assert atr_high > atr_low

    def test_insufficient_data_raises(self):
        short = pd.Series([1.0] * 10)
        with pytest.raises(ValueError, match="데이터 부족"):
            calc_atr(short, short, short, period=14)


# ── Volatility Ratio ─────────────────────────────────────────

class TestVolatilityRatio:
    def test_stable_market_near_one(self):
        """안정적인 시장에서 변동성 비율 ≈ 1.0."""
        np.random.seed(42)
        prices = 50000 + np.cumsum(np.random.normal(0, 50, 2000))
        closes = make_closes(prices.tolist())
        ratio = calc_volatility_ratio(closes, short_window=96, long_window=1920)
        assert 0.5 < ratio < 2.0

    def test_insufficient_data_returns_default(self):
        """데이터 부족 시 기본값 999.0 반환 (진입 차단)."""
        closes = make_closes([100.0] * 50)
        ratio = calc_volatility_ratio(closes, short_window=96, long_window=1920)
        assert ratio == 999.0


# ── RSI Slope ────────────────────────────────────────────────

class TestRSISlope:
    def test_rising_rsi_positive_slope(self):
        """RSI가 상승하면 기울기 > 0."""
        # 하락 후 반등 패턴
        prices = [100 - i * 2 for i in range(15)] + [70 + i * 3 for i in range(10)]
        closes = make_closes(prices)
        slope = calc_rsi_slope(closes, period=14, lookback=3)
        assert slope > 0

    def test_insufficient_data_returns_zero(self):
        closes = make_closes([100.0] * 5)
        slope = calc_rsi_slope(closes, period=14, lookback=3)
        assert slope == 0.0


# ── Compute Snapshot ─────────────────────────────────────────

class TestComputeSnapshot:
    def test_snapshot_has_all_fields(self):
        df = make_ohlcv_df(200)
        snap = compute_snapshot(df)

        assert snap.bb is not None
        assert 0 <= snap.rsi <= 100
        assert snap.atr > 0
        assert snap.current_price > 0
        assert snap.volatility_ratio > 0

    def test_current_price_matches_last_close(self):
        df = make_ohlcv_df(200)
        snap = compute_snapshot(df)
        assert snap.current_price == float(df["close"].iloc[-1])
