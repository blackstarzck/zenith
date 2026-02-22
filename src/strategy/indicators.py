"""
기술 지표 계산 모듈.
볼린저 밴드, RSI, ATR 등 전략에 필요한 기술 지표를 계산합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BollingerBands:
    """볼린저 밴드 계산 결과."""
    upper: float
    middle: float
    lower: float
    bandwidth: float  # (상단 - 하단) / 중앙


@dataclass
class IndicatorSnapshot:
    """특정 시점의 모든 지표 스냅샷."""
    bb: BollingerBands
    rsi: float
    atr: float
    current_price: float
    volatility_ratio: float  # 현재 변동성 / 20일 평균 변동성


def calc_bollinger_bands(
    closes: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> BollingerBands:
    """볼린저 밴드를 계산합니다.

    Args:
        closes: 종가 시리즈
        period: 이동평균 기간 (기본 20)
        std_dev: 표준편차 배수 (기본 2.0)

    Returns:
        BollingerBands(upper, middle, lower, bandwidth)
    """
    if len(closes) < period:
        raise ValueError(f"데이터 부족: {len(closes)}개 < 필요 {period}개")

    sma = closes.rolling(window=period).mean().iloc[-1]
    std = closes.rolling(window=period).std().iloc[-1]

    upper = sma + std_dev * std
    lower = sma - std_dev * std
    bandwidth = (upper - lower) / sma if sma != 0 else 0.0

    return BollingerBands(
        upper=float(upper),
        middle=float(sma),
        lower=float(lower),
        bandwidth=float(bandwidth),
    )


def calc_rsi(closes: pd.Series, period: int = 14) -> float:
    """RSI(상대강도지수)를 계산합니다.

    Wilder's smoothing 방식을 사용합니다.

    Args:
        closes: 종가 시리즈
        period: RSI 기간 (기본 14)

    Returns:
        0~100 사이의 RSI 값
    """
    if len(closes) < period + 1:
        raise ValueError(f"데이터 부족: {len(closes)}개 < 필요 {period + 1}개")

    delta = closes.diff()
    gains = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)

    # Wilder's EMA (alpha = 1/period)
    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().iloc[-1]
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().iloc[-1]

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return float(rsi)


def calc_atr(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 14,
) -> float:
    """ATR(평균 진폭)을 계산합니다.

    Args:
        highs: 고가 시리즈
        lows: 저가 시리즈
        closes: 종가 시리즈
        period: ATR 기간 (기본 14)

    Returns:
        ATR 값
    """
    if len(closes) < period + 1:
        raise ValueError(f"데이터 부족: {len(closes)}개 < 필요 {period + 1}개")

    prev_close = closes.shift(1)

    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().iloc[-1]

    return float(atr)


def calc_volatility_ratio(
    closes: pd.Series,
    short_window: int = 16,    # 4시간 (15분봉 기준 16개)
    long_window: int = 192,    # ~2일 (15분봉 기준 192개, 200개 수집 범위 내)
) -> float:
    """변동성 과부하 비율을 계산합니다.

    최근 단기 변동성 / 장기 평균 변동성.
    이 값이 2.0 이상이면 시장이 비정상적으로 변동성이 높은 상태.

    Args:
        closes: 종가 시리즈
        short_window: 단기 변동성 윈도우 (기본 16 = 4h in 15min candles)
        long_window: 장기 변동성 윈도우 (기본 192 = ~2일)

    Returns:
        변동성 비율 (> 2.0이면 과부하)
    """
    if len(closes) < long_window:
        # 데이터 부족 시 보수적으로 진입 차단
        logger.debug("변동성 계산 데이터 부족 (%d/%d), 기본값 999.0 반환 (진입 차단)", len(closes), long_window)
        return 999.0

    returns = closes.pct_change().dropna()
    short_vol = returns.iloc[-short_window:].std()
    long_vol = returns.iloc[-long_window:].std()

    if long_vol == 0:
        return 1.0

    return float(short_vol / long_vol)


def calc_ma_trend(
    closes: pd.Series,
    short_period: int = 20,
    long_period: int = 50,
) -> bool | None:
    """이동평균선 추세를 확인합니다.

    MA(short) > MA(long)이면 상승 추세로 판단합니다.

    Args:
        closes: 종가 시리즈
        short_period: 단기 이동평균 기간 (기본 20)
        long_period: 장기 이동평균 기간 (기본 50)

    Returns:
        True=상승추세, False=하락추세, None=데이터 부족
    """
    if len(closes) < long_period:
        logger.debug("MA 추세 계산 데이터 부족 (%d/%d)", len(closes), long_period)
        return None

    ma_short = closes.rolling(window=short_period).mean().iloc[-1]
    ma_long = closes.rolling(window=long_period).mean().iloc[-1]

    return float(ma_short) > float(ma_long)


def calc_rsi_slope(closes: pd.Series, period: int = 14, lookback: int = 3) -> float:
    """RSI의 최근 기울기를 계산합니다.

    RSI가 과매도 구간에서 '고개를 들며 상승하는지' 확인하는 데 사용합니다.

    Args:
        closes: 종가 시리즈
        period: RSI 기간
        lookback: 기울기 계산 기간 (최근 N개 캔들)

    Returns:
        양수면 상승 전환, 음수면 하락 지속
    """
    if len(closes) < period + lookback + 1:
        return 0.0

    rsi_values = []
    for i in range(lookback + 1):
        end_idx = len(closes) - i
        sub = closes.iloc[:end_idx]
        rsi_values.append(calc_rsi(sub, period))

    rsi_values.reverse()  # 시간순 정렬
    # 최근 값 - 이전 값의 평균
    slope = (rsi_values[-1] - rsi_values[0]) / lookback
    return float(slope)


def compute_snapshot(
    df: pd.DataFrame,
    bb_period: int = 20,
    bb_std_dev: float = 2.0,
    rsi_period: int = 14,
    atr_period: int = 14,
) -> IndicatorSnapshot:
    """OHLCV DataFrame으로부터 전체 지표 스냅샷을 생성합니다.

    Args:
        df: open, high, low, close, volume 컬럼이 있는 DataFrame
        bb_period: 볼린저 밴드 기간
        bb_std_dev: 볼린저 밴드 표준편차 배수
        rsi_period: RSI 기간
        atr_period: ATR 기간

    Returns:
        IndicatorSnapshot
    """
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]
    current_price = float(closes.iloc[-1])

    bb = calc_bollinger_bands(closes, bb_period, bb_std_dev)
    rsi = calc_rsi(closes, rsi_period)
    atr = calc_atr(highs, lows, closes, atr_period)
    vol_ratio = calc_volatility_ratio(closes)

    return IndicatorSnapshot(
        bb=bb,
        rsi=rsi,
        atr=atr,
        current_price=current_price,
        volatility_ratio=vol_ratio,
    )
