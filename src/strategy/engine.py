"""
평균 회귀 전략 엔진.
볼린저 밴드 + RSI + ATR 기반으로 진입/청산 신호를 생성합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto

from src.strategy.indicators import (
    IndicatorSnapshot,
    calc_bollinger_bands,
    calc_bb_status,
    calc_ma_trend,
    calc_rsi_slope,
)
from src.config import StrategyParams

logger = logging.getLogger(__name__)


class Signal(Enum):
    """매매 신호."""
    HOLD = auto()          # 대기
    BUY = auto()           # 매수 진입
    SELL_HALF = auto()     # 1차 분할 익절 (50%)
    SELL_ALL = auto()      # 2차 전량 매도
    STOP_LOSS = auto()     # 동적 손절
    MARKET_PAUSE = auto()  # 변동성 과부하로 매매 중단


@dataclass
class TradeSignal:
    """매매 신호 상세 정보."""
    signal: Signal
    symbol: str
    reason: str
    price: float
    stop_loss_price: float | None = None
    target_price_1: float | None = None  # 1차 목표가 (BB 중앙선)
    target_price_2: float | None = None  # 2차 목표가 (BB 상단선)
    score: float | None = None           # 스코어링 합산 점수 (0~100)


class MeanReversionEngine:
    """변동성 조절형 평균 회귀 전략 엔진."""

    def __init__(self, params: StrategyParams) -> None:
        self._params = params

    def update_params(self, params: StrategyParams) -> None:
        """전략 파라미터를 핫리로드합니다."""
        self._params = params

    def evaluate_entry(
        self,
        symbol: str,
        snapshot: IndicatorSnapshot,
        closes_series: "pd.Series | None" = None,
    ) -> TradeSignal:
        """매수 진입 조건을 스코어링 방식으로 평가합니다.

        각 필터가 0~100 점수를 반환하고, 가중합산 점수가
        entry_score_threshold 이상이면 BUY 신호를 생성합니다.

        Args:
            symbol: 마켓 코드
            snapshot: 현재 지표 스냅샷
            closes_series: RSI 기울기/BB 상태 계산용 종가 시리즈 (선택)

        Returns:
            TradeSignal (score 필드 포함)
        """
        price = snapshot.current_price
        bb = snapshot.bb
        params = self._params

        # ── 개별 필터 스코어 계산 ──
        scores = {
            "Vol": (params.w_volatility, self._score_volatility(snapshot.volatility_ratio)),
            "MA": (params.w_ma_trend, self._score_ma_trend(closes_series, params)),
            "ADX": (params.w_adx, self._score_adx(snapshot.adx)),
            "BB": (params.w_bb_recovery, self._score_bb_recovery(closes_series, params)),
            "RSI↗": (params.w_rsi_slope, self._score_rsi_slope(closes_series, params)),
            "RSI": (params.w_rsi_level, self._score_rsi_level(snapshot.rsi)),
        }

        # ── 정규화 가중합산 ──
        total_weight = sum(w for w, _ in scores.values())
        if total_weight == 0:
            return TradeSignal(
                signal=Signal.HOLD,
                symbol=symbol,
                reason="모든 스코어링 가중치가 0 — 진입 불가",
                price=price,
                score=0.0,
            )

        total_score = sum(w * s for w, s in scores.values()) / total_weight

        # ── 스코어 breakdown 문자열 ──
        breakdown = " ".join(f"{name}:{s:.0f}" for name, (_, s) in scores.items())
        reason_str = f"스코어 {total_score:.1f} ({breakdown})"

        # ── 임계치 비교 ──
        if total_score >= params.entry_score_threshold:
            stop_loss = price - (snapshot.atr * params.atr_stop_multiplier)
            return TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                reason=f"{reason_str} ≥ {params.entry_score_threshold:.1f}",
                price=price,
                stop_loss_price=stop_loss,
                target_price_1=bb.middle,
                target_price_2=bb.upper,
                score=total_score,
            )

        return TradeSignal(
            signal=Signal.HOLD,
            symbol=symbol,
            reason=f"{reason_str} < {params.entry_score_threshold:.1f}",
            price=price,
            score=total_score,
        )

    # ── 스코어링 헬퍼 메서드 ──────────────────────────────────

    def _score_volatility(self, vol_ratio: float) -> float:
        """변동성 스코어. 낮은 변동성 = 높은 점수."""
        # vol_ratio ≤ 1.0 → 100, vol_ratio ≥ 3.0 → 0, 선형 보간
        return max(0.0, min(100.0, (3.0 - vol_ratio) / 2.0 * 100.0))

    def _score_ma_trend(self, closes_series, params: StrategyParams) -> float:
        """MA 추세 스코어. 상승추세 = 100, 하락추세 = 0."""
        if closes_series is None or len(closes_series) < params.ma_long_period:
            return 50.0  # 데이터 부족 시 중립
        is_uptrend = calc_ma_trend(closes_series, params.ma_short_period, params.ma_long_period)
        if is_uptrend is None:
            return 50.0
        return 100.0 if is_uptrend else 0.0

    def _score_adx(self, adx: float) -> float:
        """ADX 스코어. 낮은 ADX(횡보) = 높은 점수 (평균회귀에 유리)."""
        # adx ≤ 15 → 100, adx ≥ 40 → 0, 선형 보간
        return max(0.0, min(100.0, (40.0 - adx) / 25.0 * 100.0))

    def _score_bb_recovery(self, closes_series, params: StrategyParams) -> float:
        """BB 복귀 스코어. 무상태, calc_bb_status() 사용."""
        if closes_series is None or len(closes_series) < params.bb_period + 20:
            return 0.0  # 데이터 부족 시 불리
        status = calc_bb_status(closes_series, params.bb_period, params.bb_std_dev)
        if status == "recovered":
            return 100.0
        elif status == "below":
            return 30.0  # 이탈 중 — 부분 점수 (반등 가능성)
        else:  # "none"
            return 0.0

    def _score_rsi_slope(self, closes_series, params: StrategyParams) -> float:
        """RSI 기울기 스코어. 양의 기울기(상승전환) = 높은 점수."""
        if closes_series is None or len(closes_series) <= 20:
            return 50.0  # 데이터 부족 시 중립
        slope = calc_rsi_slope(closes_series, params.rsi_period, lookback=params.rsi_slope_lookback)
        # slope ≤ 0 → 0, slope ≥ 3.0 → 100, 선형 보간
        return max(0.0, min(100.0, slope / 3.0 * 100.0))

    def _score_rsi_level(self, rsi: float) -> float:
        """RSI 수준 스코어. 낮은 RSI(과매도) = 높은 점수."""
        # rsi ≤ 20 → 100, rsi ≥ 45 → 0, 선형 보간
        return max(0.0, min(100.0, (45.0 - rsi) / 25.0 * 100.0))

    def evaluate_exit(
        self,
        symbol: str,
        snapshot: IndicatorSnapshot,
        entry_price: float,
        has_sold_half: bool = False,
    ) -> TradeSignal:
        """청산 조건을 평가합니다.

        청산 조건:
        1. 동적 손절: 가격 < 진입가 - ATR * 2.5
        2. 1차 익절: 가격 ≥ BB 중앙선 & 수익률 ≥ 0.3% → 50% 매도
        3. 2차 익절: 가격 ≥ BB 상단선 → 나머지 전량 매도

        Args:
            symbol: 마켓 코드
            snapshot: 현재 지표 스냅샷
            entry_price: 진입 가격
            has_sold_half: 1차 분할 매도 완료 여부

        Returns:
            TradeSignal
        """
        price = snapshot.current_price
        bb = snapshot.bb
        params = self._params

        # ── 동적 손절 (ATR 기반) ──
        stop_loss_price = entry_price - (snapshot.atr * params.atr_stop_multiplier)
        if price <= stop_loss_price:
            return TradeSignal(
                signal=Signal.STOP_LOSS,
                symbol=symbol,
                reason=f"동적 손절 발동 (가격 {price:,.2f} ≤ 손절선 {stop_loss_price:,.2f})",
                price=price,
                stop_loss_price=stop_loss_price,
            )

        # ── 수익률 계산 (수수료 반영 익절 필터) ──
        profit_pct = (price - entry_price) / entry_price if entry_price > 0 else 0.0

        # ── 2차 익절: BB 상단선 도달 ──
        if price >= bb.upper:
            return TradeSignal(
                signal=Signal.SELL_ALL,
                symbol=symbol,
                reason=f"BB 상단선 도달 (가격 {price:,.2f} ≥ 상단 {bb.upper:,.2f})",
                price=price,
                target_price_2=bb.upper,
            )

        # ── 1차 익절: BB 중앙선 도달 + 최소 수익률 확보 ──
        if not has_sold_half and price >= bb.middle:
            if profit_pct < params.min_profit_margin:
                return TradeSignal(
                    signal=Signal.HOLD,
                    symbol=symbol,
                    reason=(
                        f"BB 중앙선 도달이나 수익률 부족 "
                        f"({profit_pct:.2%} < {params.min_profit_margin:.2%})"
                    ),
                    price=price,
                    stop_loss_price=stop_loss_price,
                )
            return TradeSignal(
                signal=Signal.SELL_HALF,
                symbol=symbol,
                reason=f"1차 익절 - BB 중앙선 도달 (가격 {price:,.2f} ≥ 중앙 {bb.middle:,.2f}, 수익 {profit_pct:.2%})",
                price=price,
                target_price_1=bb.middle,
            )

        # ── 청산 조건 미충족 ──
        return TradeSignal(
            signal=Signal.HOLD,
            symbol=symbol,
            reason=f"보유 유지 (가격 {price:,.2f}, 손절선 {stop_loss_price:,.2f})",
            price=price,
            stop_loss_price=stop_loss_price,
        )

