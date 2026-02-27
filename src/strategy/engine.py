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


class MeanReversionEngine:
    """변동성 조절형 평균 회귀 전략 엔진."""

    def __init__(self, params: StrategyParams) -> None:
        self._params = params
        # 종목별 이전 캔들의 BB 하단 이탈 여부 추적
        self._was_below_lower: dict[str, bool] = {}

    def update_params(self, params: StrategyParams) -> None:
        """전략 파라미터를 핫리로드합니다 (BB 추적 상태는 보존)."""
        self._params = params

    def evaluate_entry(
        self,
        symbol: str,
        snapshot: IndicatorSnapshot,
        closes_series: "pd.Series | None" = None,
    ) -> TradeSignal:
        """매수 진입 조건을 평가합니다.

        진입 조건 (모두 충족 시):
        1. 변동성 과부하가 아닐 것 (volatility_ratio < 2.0)
        2. 추세 필터: MA20 > MA50 (상승 추세)
        3. 가격이 BB 하단을 뚫고 내려갔다가 다시 밴드 안으로 복귀
        4. RSI가 35 이하에서 상승 전환 중

        Args:
            symbol: 마켓 코드
            snapshot: 현재 지표 스냅샷
            closes_series: RSI 기울기 계산용 종가 시리즈 (선택)

        Returns:
            TradeSignal
        """
        price = snapshot.current_price
        bb = snapshot.bb
        rsi = snapshot.rsi
        params = self._params

        # ── 1단계: 변동성 과부하 필터 ──
        if snapshot.volatility_ratio >= params.volatility_overload_ratio:
            return TradeSignal(
                signal=Signal.MARKET_PAUSE,
                symbol=symbol,
                reason=f"변동성 과부하 ({snapshot.volatility_ratio:.2f}x ≥ {params.volatility_overload_ratio}x)",
                price=price,
            )

        # ── 1.5단계: 추세 필터 (MA 단기 > MA 장기) ──
        if closes_series is not None and len(closes_series) >= params.ma_long_period:
            is_uptrend = calc_ma_trend(closes_series, short_period=params.ma_short_period, long_period=params.ma_long_period)
            if is_uptrend is False:
                return TradeSignal(
                    signal=Signal.HOLD,
                    symbol=symbol,
                    reason=f"하락 추세 (MA{params.ma_short_period} < MA{params.ma_long_period}) — 진입 보류",
                    price=price,
                )

        # ── 1.75단계: ADX 추세 강도 필터 ──
        if snapshot.adx > params.adx_trend_threshold:
            return TradeSignal(
                signal=Signal.HOLD,
                symbol=symbol,
                reason=f"강한 추세 감지 (ADX={snapshot.adx:.1f} > {params.adx_trend_threshold}) — 평균 회귀 부적합",
                price=price,
            )

        # ── 2단계: BB 하단 이탈 후 복귀 확인 ──
        was_below = self._was_below_lower.get(symbol, False)
        currently_below = price < bb.lower

        if currently_below:
            # 현재 하단 이탈 중 → 다음 캔들에서 복귀 확인
            self._was_below_lower[symbol] = True
            return TradeSignal(
                signal=Signal.HOLD,
                symbol=symbol,
                reason=f"BB 하단 이탈 중 (가격 {price:,.2f} < 하단 {bb.lower:,.2f}), 복귀 대기",
                price=price,
            )

        if not was_below:
            # 이전에 하단을 이탈한 적 없음 → 진입 조건 미충족
            return TradeSignal(
                signal=Signal.HOLD,
                symbol=symbol,
                reason="BB 하단 이탈 이력 없음",
                price=price,
            )

        # BB 하단 이탈 후 복귀 완료! → 이력 초기화
        self._was_below_lower[symbol] = False

        # ── 3단계: RSI 확증 ──
        rsi_rising = True  # 기본값
        if closes_series is not None and len(closes_series) > 20:
            rsi_slope = calc_rsi_slope(closes_series, params.rsi_period, lookback=params.rsi_slope_lookback)
            rsi_rising = rsi_slope > 0

        if not rsi_rising:
            return TradeSignal(
                signal=Signal.HOLD,
                symbol=symbol,
                reason=f"RSI 상승 전환 미확인 (RSI={rsi:.1f})",
                price=price,
            )

        if rsi > params.rsi_oversold + params.rsi_entry_ceiling_offset:
            # RSI가 상한을 초과하면 과매도 구간이 아님
            return TradeSignal(
                signal=Signal.HOLD,
                symbol=symbol,
                reason=f"RSI 과매도 구간 아님 (RSI={rsi:.1f})",
                price=price,
            )

        # ── 모든 조건 충족: 매수 신호 ──
        stop_loss = price - (snapshot.atr * params.atr_stop_multiplier)

        return TradeSignal(
            signal=Signal.BUY,
            symbol=symbol,
            reason=f"BB 복귀 + RSI 과매도 상승전환 (RSI={rsi:.1f})",
            price=price,
            stop_loss_price=stop_loss,
            target_price_1=bb.middle,
            target_price_2=bb.upper,
        )

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

    def recover_bb_state(
        self,
        symbol: str,
        closes: "pd.Series",
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
    ) -> None:
        """봇 재시작 시 캔들 데이터로 BB 이탈 상태를 복구합니다.

        직전 캔들이 BB 하단 아래였으면 _was_below_lower를 True로 설정합니다.

        Args:
            symbol: 마켓 코드
            closes: 종가 시리즈
            bb_period: 볼린저 밴드 기간
            bb_std_dev: 볼린저 밴드 표준편차 배수
        """
        if len(closes) < bb_period + 1:
            return

        # 직전 캔들까지의 데이터로 BB를 계산하여 그 시점의 상태를 복원
        prev_closes = closes.iloc[:-1]
        try:
            bb = calc_bollinger_bands(prev_closes, bb_period, bb_std_dev)
            prev_close = float(prev_closes.iloc[-1])

            if prev_close < bb.lower:
                self._was_below_lower[symbol] = True
                logger.info(
                    "[BB 상태 복구] %s: 이전 캔들 BB 하단 이탈 확인 (%.2f < %.2f)",
                    symbol, prev_close, bb.lower,
                )
            else:
                self._was_below_lower[symbol] = False
        except ValueError:
            # 데이터 부족 등
            pass

    def reset_tracking(self, symbol: str) -> None:
        """종목의 BB 이탈 추적 상태를 초기화합니다."""
        self._was_below_lower.pop(symbol, None)
