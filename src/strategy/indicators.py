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
    adx: float  # ADX 추세 강도 (0~100)


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


def calc_bb_status(
    closes: pd.Series,
    bb_period: int = 20,
    bb_std_dev: float = 2.0,
    lookback: int = 20,
) -> str:
    """캔들 데이터에서 BB 하단 이탈/복귀 상태를 직접 판별합니다.

    인메모리 상태(_was_below_lower)에 의존하지 않고,
    최근 lookback 캔들을 역순 스캔하여 BB 하단 이탈 이력을 확인합니다.

    Args:
        closes: 종가 시리즈
        bb_period: 볼린저 밴드 기간
        bb_std_dev: 볼린저 밴드 표준편차 배수
        lookback: 이탈 이력 검색 범위 (최근 N개 캔들)

    Returns:
        "below"     — 현재 가격이 BB 하단 아래
        "recovered" — 최근 lookback 캔들 내에서 하단 이탈 후 복귀 완료
        "none"      — 이탈 이력 없음
    """
    min_required = bb_period + lookback
    if len(closes) < min_required:
        return "none"

    current_price = float(closes.iloc[-1])

    # 현재 BB 하단
    sma_now = closes.rolling(window=bb_period).mean().iloc[-1]
    std_now = closes.rolling(window=bb_period).std().iloc[-1]
    lower_now = float(sma_now - bb_std_dev * std_now)

    # 현재 가격이 BB 하단 아래면 → "below"
    if current_price < lower_now:
        return "below"

    # 최근 lookback 캔들에서 BB 하단 이탈 이력 확인
    # 각 캔들 시점의 BB lower를 rolling으로 한번에 계산
    sma_series = closes.rolling(window=bb_period).mean()
    std_series = closes.rolling(window=bb_period).std()
    lower_series = sma_series - bb_std_dev * std_series

    # 최근 lookback 캔들 (현재 캔들 제외)에서 종가가 BB 하단 아래였던 적이 있는지
    for i in range(2, lookback + 1):
        idx = len(closes) - i
        if idx < bb_period:
            break
        close_val = float(closes.iloc[idx])
        lower_val = float(lower_series.iloc[idx])
        if close_val < lower_val:
            return "recovered"

    return "none"

def calc_adx(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 14,
) -> float:
    """ADX(Average Directional Index)를 계산합니다.

    추세 강도를 측정합니다. 값이 25 이상이면 강한 추세, 20 이하면 횡보.

    Args:
        highs: 고가 시리즈
        lows: 저가 시리즈
        closes: 종가 시리즈
        period: ADX 기간 (기본 14)

    Returns:
        0~100 사이의 ADX 값
    """
    min_required = period * 2 + 1
    if len(closes) < min_required:
        raise ValueError(f"데이터 부족: {len(closes)}개 < 필요 {min_required}개")

    # Directional Movement 계산
    high_diff = highs.diff()
    low_diff = -lows.diff()

    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)

    # True Range 계산
    prev_close = closes.shift(1)
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's EMA (alpha = 1/period) 로 스무딩
    alpha = 1.0 / period
    smoothed_tr = true_range.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    smoothed_plus_dm = plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    smoothed_minus_dm = minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    # +DI, -DI 계산
    plus_di = (smoothed_plus_dm / smoothed_tr) * 100
    minus_di = (smoothed_minus_dm / smoothed_tr) * 100

    # DX 계산
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = (di_diff / di_sum.replace(0, np.nan)) * 100
    dx = dx.fillna(0.0)

    # ADX = DX의 Wilder's EMA
    adx = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    return float(adx.iloc[-1])



def compute_snapshot(
    df: pd.DataFrame,
    bb_period: int = 20,
    bb_std_dev: float = 2.0,
    rsi_period: int = 14,
    atr_period: int = 14,
    vol_short_window: int = 16,
    vol_long_window: int = 192,
    adx_period: int = 14,
) -> IndicatorSnapshot:
    """OHLCV DataFrame으로부터 전체 지표 스냅샷을 생성합니다.

    Args:
        df: open, high, low, close, volume 컬럼이 있는 DataFrame
        bb_period: 볼린저 밴드 기간
        bb_std_dev: 볼린저 밴드 표준편차 배수
        rsi_period: RSI 기간
        atr_period: ATR 기간
        vol_short_window: 변동성 비율 단기 윈도우
        vol_long_window: 변동성 비율 장기 윈도우
        adx_period: ADX 기간

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
    vol_ratio = calc_volatility_ratio(closes, vol_short_window, vol_long_window)

    # ADX 계산 (데이터 부족 시 0.0 — 필터 비활성화 효과)
    try:
        adx = calc_adx(highs, lows, closes, adx_period)
    except ValueError:
        adx = 0.0

    return IndicatorSnapshot(
        bb=bb,
        rsi=rsi,
        atr=atr,
        current_price=current_price,
        volatility_ratio=vol_ratio,
        adx=adx,
    )
