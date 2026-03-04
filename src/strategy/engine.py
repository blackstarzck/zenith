"""
평균 회귀 전략 엔진.
볼린저 밴드 + RSI + ATR 기반으로 진입/청산 신호를 생성합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import pandas as pd
    from src.risk.manager import Position

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
        regime: str = "ranging",
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
            "BB": (params.w_bb_recovery, self._score_bb_recovery(closes_series, params, rsi=snapshot.rsi, adx=snapshot.adx, current_price=price)),
            "RSI↗": (params.w_rsi_slope, self._score_rsi_slope(closes_series, params)),
            "RSI": (params.w_rsi_level, self._score_rsi_level(snapshot.rsi)),
        }

        # Falling Knife Guard: RSI < 15 시 RSI↗ 기울기 스코어 감쇠 (×0.6)
        # 극저 RSI에서의 일시적 반등 기울기는 신뢰도가 낮음
        if snapshot.rsi < 15.0:
            w, s = scores["RSI↗"]
            scores["RSI↗"] = (w, s * 0.6)


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
        # ── 레짐별 절대 임계값 조회 ──
        effective_threshold = params.get_entry_threshold(regime)

        if total_score >= effective_threshold:
            stop_loss = price - (snapshot.atr * params.get_atr_multiplier(regime))
            return TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                reason=f"{reason_str} ≥ {effective_threshold:.1f} (레짐: {regime})",
                price=price,
                stop_loss_price=stop_loss,
                target_price_1=bb.middle,
                target_price_2=bb.upper,
                score=total_score,
            )

        return TradeSignal(
            signal=Signal.HOLD,
            symbol=symbol,
            reason=f"{reason_str} < {effective_threshold:.1f}",
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

    def _score_bb_recovery(self, closes_series, params: StrategyParams, rsi: float = 50.0, adx: float = 20.0, current_price: float = 0.0) -> float:
        """BB 복귀 스코어. 3단계 추세 컨텍스트 평가.

        - RSI < 15 (극단적 과매도) → 30점 (떨어지는 칼날 방어)
        - MA20 < MA50 (하락 추세) → 30점 (데드캣 바운스 방어)
        - ADX > 25 & 가격 < MA50 (추세 의심) → 40점
        - 그 외 → 100점 (정상 평균회귀)
        """
        if closes_series is None or len(closes_series) < params.bb_period + 20:
            return 0.0  # 데이터 부족 시 불리
        status = calc_bb_status(closes_series, params.bb_period, params.bb_std_dev)
        if status == "recovered":
            # 1단계: Falling Knife Guard — 극단적 과매도에서 반등 신호 신뢰도 하향
            if rsi < 15.0:
                return 30.0
            # 2단계: MA 데드크로스 — 확정적 하락 추세
            ma_trend = calc_ma_trend(closes_series, params.ma_short_period, params.ma_long_period)
            if ma_trend is False:
                return 30.0
            # 3단계: 추세 의심 구간 — ADX > 25이면서 가격이 MA50 아래
            if adx > 25.0 and current_price > 0:
                ma50 = closes_series.rolling(window=params.ma_long_period).mean().iloc[-1]
                if current_price < ma50:
                    return 40.0
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
        position: "Position",
        regime: str = "ranging",
    ) -> TradeSignal:
        """청산 조건을 스코어링 방식으로 평가합니다.

        우선순위:
        1. [하드 룰] 동적 손절 (ATR 기반) — 무조건 발동
        2. [하드 룰] BB 상단 도달 익절 — 가격 ≥ BB 상단 + 최소 수익 마진 충족 시 즉시 매도
        3. [하드 룰] 트레일링 스탑 (1차 익절 후 활성)
        4. [스코어링] 익절 조건 가중합산 평가

        Args:
            symbol: 마켓 코드
            snapshot: 현재 지표 스냅샷
            position: 포지션 정보 (진입가, 분할매도 여부, 트레일링 고점)

        Returns:
            TradeSignal (score 필드 포함)
        """
        price = snapshot.current_price
        bb = snapshot.bb
        params = self._params
        entry_price = position.entry_price
        has_sold_half = position.has_sold_half
        profit_pct = (price - entry_price) / entry_price if entry_price > 0 else 0.0
        effective_exit_threshold = self._effective_exit_threshold(regime)
        adaptive_profit_margin = self._adaptive_min_profit_margin(entry_price, snapshot.atr)

        # ── [하드 룰 1] 동적 손절 (ATR 기반) ──
        stop_loss_price = entry_price - (snapshot.atr * params.get_atr_multiplier(regime))
        if price <= stop_loss_price:
            return TradeSignal(
                signal=Signal.STOP_LOSS,
                symbol=symbol,
                reason=f"동적 손절 발동 (가격 {price:,.2f} ≤ 손절선 {stop_loss_price:,.2f})",
                price=price,
                stop_loss_price=stop_loss_price,
            )

        # ── [하드 룰 2] BB 상단 도달 익절 ──
        # 가격이 BB 상단 이상이고 최소 수익 마진을 충족하면 즉시 매도
        if price >= bb.upper and profit_pct >= params.min_profit_margin:
            signal_type = Signal.SELL_ALL if has_sold_half else Signal.SELL_HALF
            return TradeSignal(
                signal=signal_type,
                symbol=symbol,
                reason=(
                    f"BB 상단 도달 익절 "
                    f"(가격 {price:,.2f} ≥ BB상단 {bb.upper:,.2f}, 수익 {profit_pct:.2%})"
                ),
                price=price,
                stop_loss_price=stop_loss_price,
                target_price_1=bb.middle if not has_sold_half else None,
                target_price_2=bb.upper,
            )
        # ── [하드 룰 3] 트레일링 스탑 (1차 익절 후 활성) ──
        if has_sold_half and position.trailing_high > 0:
            trailing_multiplier = self._trailing_stop_multiplier(regime, profit_pct)
            trailing_stop = position.trailing_high - (snapshot.atr * trailing_multiplier)
            # 잔량은 본전+최소마진 이상에서 정리되도록 보호선을 추가
            break_even_floor = entry_price * (1.0 + max(params.min_profit_margin, 0.001))
            trailing_stop = max(trailing_stop, break_even_floor)
            if price <= trailing_stop:
                return TradeSignal(
                    signal=Signal.SELL_ALL,
                    symbol=symbol,
                    reason=(
                        f"트레일링 스탑 발동 "
                        f"(고점 {position.trailing_high:,.2f} → 현재 {price:,.2f} ≤ {trailing_stop:,.2f}, "
                        f"배수 {trailing_multiplier:.2f})"
                    ),
                    price=price,
                    stop_loss_price=trailing_stop,
                )

        # ── [1차 익절 후] 스코어링 매도 비활성화 — 트레일링 스탑만 작동 ──
        # SIGN 분석(2026-03-01)에서 도출: 스코어링이 트레일링보다 항상 먼저 발동하여
        # 트레일링 스탑이 사문화됨. 1차 익절 후에는 하드 룰만으로 2차 매도 결정.
        if has_sold_half:
            return TradeSignal(
                signal=Signal.HOLD,
                symbol=symbol,
                reason=f"1차 익절 완료 — 트레일링 스탑 대기 중 (스코어링 매도 비활성)",
                price=price,
                stop_loss_price=stop_loss_price,
            )

        # ── [스코어링] 익절 조건 평가 ──
        scores = {
            "RSI↑": (params.w_exit_rsi_level, self._score_exit_rsi_level(snapshot.rsi)),
            "BB↑": (params.w_exit_bb_position, self._score_exit_bb_position(price, bb)),
            "수익": (params.w_exit_profit_pct, self._score_exit_profit(price, entry_price)),
            "ADX": (params.w_exit_adx_trend, self._score_exit_adx(snapshot.adx)),
        }

        total_weight = sum(w for w, _ in scores.values())
        if total_weight == 0:
            return TradeSignal(
                signal=Signal.HOLD,
                symbol=symbol,
                reason="모든 매도 스코어링 가중치가 0 — 청산 불가",
                price=price,
                stop_loss_price=stop_loss_price,
                score=0.0,
            )

        total_score = sum(w * s for w, s in scores.values()) / total_weight

        # ── 스코어 breakdown 문자열 ──
        breakdown = " ".join(f"{name}:{s:.0f}" for name, (_, s) in scores.items())
        reason_str = f"청산 스코어 {total_score:.1f} ({breakdown})"

        # ── 임계치 비교 ──
        if total_score >= effective_exit_threshold:
            # 최소 수익 마진 확인 (1차 익절 시에만)
            if not has_sold_half and profit_pct < adaptive_profit_margin:
                return TradeSignal(
                    signal=Signal.HOLD,
                    symbol=symbol,
                    reason=(
                        f"{reason_str} ≥ {effective_exit_threshold:.1f} 이나 수익률 부족 "
                        f"({profit_pct:.2%} < {adaptive_profit_margin:.2%})"
                    ),
                    price=price,
                    stop_loss_price=stop_loss_price,
                    score=total_score,
                )

            # 1차 익절은 '평균 복귀 확인(BB 중앙선 도달)' 또는
            # '적응형 마진 대비 충분한 초과수익'일 때만 허용해 조기 청산을 억제
            if not has_sold_half:
                reached_bb_middle = price >= bb.middle
                strong_profit = profit_pct >= (adaptive_profit_margin * 1.8)
                if not reached_bb_middle and not strong_profit:
                    return TradeSignal(
                        signal=Signal.HOLD,
                        symbol=symbol,
                        reason=(
                            f"{reason_str} ≥ {effective_exit_threshold:.1f} 이나 익절 품질 게이트 미통과 "
                            f"(중앙선 미도달, {profit_pct:.2%} < {adaptive_profit_margin * 1.8:.2%})"
                        ),
                        price=price,
                        stop_loss_price=stop_loss_price,
                        score=total_score,
                    )

            signal_type = Signal.SELL_ALL if has_sold_half else Signal.SELL_HALF
            return TradeSignal(
                signal=signal_type,
                symbol=symbol,
                reason=f"{reason_str} ≥ {effective_exit_threshold:.1f}",
                price=price,
                stop_loss_price=stop_loss_price,
                target_price_1=bb.middle if not has_sold_half else None,
                target_price_2=bb.upper,
                score=total_score,
            )

        return TradeSignal(
            signal=Signal.HOLD,
            symbol=symbol,
            reason=f"{reason_str} < {effective_exit_threshold:.1f}",
            price=price,
            stop_loss_price=stop_loss_price,
            score=total_score,
        )

    # ── 매도 스코어링 헬퍼 메서드 ──────────────────────────────

    def _effective_exit_threshold(self, regime: str) -> float:
        """레짐별 청산 임계치를 계산합니다.

        - 추세장/변동성장에서는 조기 익절을 줄이기 위해 임계치를 상향
        - 횡보장은 기본 임계치를 사용
        """
        base = self._params.exit_score_threshold
        if regime == "trending":
            return min(95.0, base + 4.0)
        if regime == "volatile":
            return min(95.0, base + 2.0)
        return base

    def _adaptive_min_profit_margin(self, entry_price: float, atr: float) -> float:
        """ATR 기반 적응형 최소 익절 마진을 계산합니다.

        시장 호흡(ATR)이 큰 구간에서는 최소 익절 마진을 자동 상향해
        노이즈성 조기 청산을 줄이고 손익비를 개선합니다.
        """
        if entry_price <= 0:
            return self._params.min_profit_margin
        atr_ratio = max(0.0, atr / entry_price)
        atr_based_margin = min(0.012, max(0.003, atr_ratio * 0.8))
        return max(self._params.min_profit_margin, atr_based_margin)

    def _trailing_stop_multiplier(self, regime: str, profit_pct: float) -> float:
        """잔량 청산용 트레일링 배수를 상황에 맞게 조정합니다."""
        mult = self._params.trailing_stop_atr_multiplier

        if regime == "trending":
            mult += 0.4  # 추세장: 너무 빠른 청산 방지
        elif regime == "volatile":
            mult += 0.2
        elif regime == "ranging":
            mult -= 0.1  # 횡보장: 수익 보호를 위해 조금 타이트하게

        # 이익이 충분히 누적될수록 스탑을 당겨 수익 잠금 강화
        if profit_pct >= 0.05:
            mult -= 0.5
        elif profit_pct >= 0.03:
            mult -= 0.3
        elif profit_pct < 0.01:
            mult += 0.2

        return max(1.2, min(3.5, mult))

    def _score_exit_rsi_level(self, rsi: float) -> float:
        """RSI 과매수 스코어. 높은 RSI = 높은 청산 점수."""
        # rsi ≤ 40 → 0, rsi ≥ 70 → 100, 선형 보간
        return max(0.0, min(100.0, (rsi - 40.0) / 30.0 * 100.0))

    def _score_exit_bb_position(self, price: float, bb) -> float:
        """BB 포지션 스코어. 상단 접근/초과 = 높은 청산 점수."""
        if bb.upper == bb.lower:
            return 50.0
        # lower → 0, upper → 100, 초과 시 100 캡
        position = (price - bb.lower) / (bb.upper - bb.lower)
        return max(0.0, min(100.0, position * 100.0))

    def _score_exit_profit(self, price: float, entry_price: float) -> float:
        """수익률 스코어. 수익 클수록 높은 청산 점수."""
        if entry_price <= 0:
            return 0.0
        profit_pct = ((price / entry_price) - 1.0) * 100.0  # %
        # 0% → 0, 3% → 100, 선형 보간
        return max(0.0, min(100.0, profit_pct / 3.0 * 100.0))

    def _score_exit_adx(self, adx: float) -> float:
        """ADX 추세 강도 스코어. 강한 추세 = 높은 청산 점수 (추세 전환 경고)."""
        # adx ≤ 20 → 0, adx ≥ 40 → 100, 선형 보간
        return max(0.0, min(100.0, (adx - 20.0) / 20.0 * 100.0))

