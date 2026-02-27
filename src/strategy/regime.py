"""
시장 레짐(Regime) 감지 모듈.
BTC-KRW를 시장 대표 지표로 사용하여 현재 시장이
추세장(trending), 횡보장(ranging), 변동성 폭발(volatile) 중
어느 상태인지 분류합니다.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from src.strategy.indicators import calc_adx, calc_volatility_ratio, calc_ma_trend

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """시장 레짐 유형."""
    TRENDING = "trending"      # 강한 추세 — 평균 회귀 부적합
    RANGING = "ranging"        # 횡보 — 평균 회귀 최적
    VOLATILE = "volatile"      # 변동성 폭발 — 매매 중단


@dataclass(frozen=True)
class RegimeResult:
    """레짐 분류 결과."""
    regime: MarketRegime
    adx: float
    volatility_ratio: float
    ma_trend: bool | None  # True=상승, False=하락, None=데이터 부족
    reason: str


def _classify_single_point(
    df: pd.DataFrame,
    end_idx: int,
    adx_trending_threshold: float,
    vol_overload_ratio: float,
    adx_period: int,
    vol_short_window: int,
    vol_long_window: int,
) -> MarketRegime:
    """특정 시점까지의 데이터로 레짐을 분류합니다 (내부용).

    Args:
        df: 전체 OHLCV DataFrame
        end_idx: 사용할 데이터 끝 인덱스 (exclusive)
        adx_trending_threshold: ADX 추세 임계값
        vol_overload_ratio: 변동성 과부하 임계값
        adx_period: ADX 계산 기간
        vol_short_window: 변동성 단기 윈도우
        vol_long_window: 변동성 장기 윈도우

    Returns:
        해당 시점의 MarketRegime
    """
    sub_df = df.iloc[:end_idx]
    closes = sub_df["close"]
    highs = sub_df["high"]
    lows = sub_df["low"]

    # 1순위: 변동성 폭발
    vol_ratio = calc_volatility_ratio(closes, vol_short_window, vol_long_window)
    if vol_ratio >= vol_overload_ratio:
        return MarketRegime.VOLATILE

    # 2순위: 추세장
    try:
        adx = calc_adx(highs, lows, closes, adx_period)
    except ValueError:
        adx = 0.0

    if adx >= adx_trending_threshold:
        return MarketRegime.TRENDING

    # 3순위: 횡보장 (기본)
    return MarketRegime.RANGING


def classify_regime(
    df: pd.DataFrame,
    adx_trending_threshold: float = 25.0,
    vol_overload_ratio: float = 2.0,
    adx_period: int = 14,
    vol_short_window: int = 16,
    vol_long_window: int = 192,
    ma_short_period: int = 20,
    ma_long_period: int = 50,
    lookback_candles: int = 3,
) -> RegimeResult:
    """OHLCV DataFrame으로부터 시장 레짐을 분류합니다.

    분류 우선순위:
    1. volatile: 변동성 비율 >= vol_overload_ratio
    2. trending: ADX >= adx_trending_threshold
    3. ranging: 위 조건 미충족

    히스테리시스: lookback_candles 개수만큼 과거 캔들에서도 분류하여
    다수결로 최종 레짐을 결정합니다 (잦은 전환 방지).

    Args:
        df: BTC-KRW의 OHLCV DataFrame (open, high, low, close, volume)
        adx_trending_threshold: ADX가 이 값 이상이면 추세장
        vol_overload_ratio: 변동성 비율이 이 값 이상이면 변동성 폭발
        adx_period: ADX 계산 기간
        vol_short_window: 변동성 단기 윈도우
        vol_long_window: 변동성 장기 윈도우
        ma_short_period: MA 단기 기간
        ma_long_period: MA 장기 기간
        lookback_candles: 히스테리시스 룩백 캔들 수

    Returns:
        RegimeResult
    """
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]

    # 현재 시점 지표 계산 (결과 객체에 포함)
    vol_ratio = calc_volatility_ratio(closes, vol_short_window, vol_long_window)
    ma_trend = calc_ma_trend(closes, ma_short_period, ma_long_period)

    try:
        adx = calc_adx(highs, lows, closes, adx_period)
    except ValueError:
        adx = 0.0

    # 히스테리시스: 현재 시점 + lookback 캔들에서 각각 레짐 분류 → 다수결
    votes: list[MarketRegime] = []
    total_len = len(df)

    for offset in range(lookback_candles + 1):
        end_idx = total_len - offset
        if end_idx < vol_long_window:
            # 데이터 부족 시 더 이상 과거로 가지 않음
            break
        regime = _classify_single_point(
            df, end_idx,
            adx_trending_threshold, vol_overload_ratio,
            adx_period, vol_short_window, vol_long_window,
        )
        votes.append(regime)

    if not votes:
        # 데이터가 전혀 부족한 경우 → 보수적으로 ranging (정상 매매 허용)
        return RegimeResult(
            regime=MarketRegime.RANGING,
            adx=adx,
            volatility_ratio=vol_ratio,
            ma_trend=ma_trend,
            reason="데이터 부족 — 기본값 ranging",
        )

    # 다수결 (동점 시 현재 시점(votes[0]) 우선)
    counter = Counter(votes)
    most_common = counter.most_common()
    top_count = most_common[0][1]

    candidates = [regime for regime, count in most_common if count == top_count]
    if votes[0] in candidates:
        final_regime = votes[0]
    else:
        final_regime = candidates[0]

    # 사유 생성 (로깅용)
    vote_summary = ", ".join(f"{r.value}:{c}" for r, c in most_common)
    reason = f"ADX={adx:.1f}, Vol={vol_ratio:.2f}, 투표=[{vote_summary}]"

    return RegimeResult(
        regime=final_regime,
        adx=adx,
        volatility_ratio=vol_ratio,
        ma_trend=ma_trend,
        reason=reason,
    )
