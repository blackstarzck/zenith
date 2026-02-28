"""
주문 실행 엔진.
매수/매도 주문을 집행하고, 미체결 주문을 관리합니다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import pyupbit

from src.config import RiskParams

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """주문 실행 결과."""
    success: bool
    order_id: str | None = None
    symbol: str = ""
    side: str = ""        # "bid" (매수) / "ask" (매도)
    price: float = 0.0
    volume: float = 0.0
    amount: float = 0.0   # 총 거래 금액
    fee: float = 0.0
    error: str = ""


class OrderExecutor:
    """주문 실행기.

    - 시장가 매수/매도 실행
    - 분할 매도 (절반/전량)
    - 미체결 주문 타임아웃 관리
    - 체결 실패 쿨다운 (동일 종목 재시도 방지)
    """

    # 동일 종목 체결 실패 시 재시도 금지 기간 (초)
    _COOLDOWN_SEC = 1800  # 30분

    def __init__(self, upbit: pyupbit.Upbit, risk_params: RiskParams) -> None:
        self._upbit = upbit
        self._risk_params = risk_params
        # 체결 실패 종목별 타임스탬프 (쿨다운 추적)
        self._failed_symbols: dict[str, float] = {}

    # ── 쿨다운 관리 ───────────────────────────────────────────

    def is_on_cooldown(self, symbol: str) -> bool:
        """해당 종목이 체결 실패 쿨다운 중인지 확인합니다."""
        if symbol not in self._failed_symbols:
            return False
        elapsed = time.time() - self._failed_symbols[symbol]
        if elapsed >= self._COOLDOWN_SEC:
            del self._failed_symbols[symbol]
            return False
        return True

    def _record_failure(self, symbol: str) -> None:
        """체결 실패를 기록합니다 (쿨다운 시작)."""
        self._failed_symbols[symbol] = time.time()
        remaining = self._COOLDOWN_SEC
        logger.info("[쿨다운 시작] %s: %d초간 재시도 금지", symbol, remaining)

    # ── 매수 ─────────────────────────────────────────────────

    def buy_market(self, symbol: str, amount_krw: float) -> OrderResult:
        """시장가 매수를 실행합니다.

        Args:
            symbol: 마켓 코드 (예: "KRW-BTC")
            amount_krw: 투입 금액 (KRW)

        Returns:
            OrderResult
        """
        # 쿨다운 확인
        if self.is_on_cooldown(symbol):
            remaining = int(self._COOLDOWN_SEC - (time.time() - self._failed_symbols[symbol]))
            return OrderResult(
                success=False, symbol=symbol, side="bid",
                error=f"체결 실패 쿨다운 중 (잔여 {remaining}초)",
            )

        if amount_krw < self._risk_params.min_order_amount_krw:
            return OrderResult(
                success=False,
                symbol=symbol,
                side="bid",
                error=f"최소 주문 금액 미달: {amount_krw:,.0f} < {self._risk_params.min_order_amount_krw:,}",
            )

        try:
            result = self._upbit.buy_market_order(symbol, amount_krw)
            if result is None:
                return OrderResult(
                    success=False, symbol=symbol, side="bid",
                    error="주문 응답 없음",
                )

            if "error" in result:
                err_msg = result["error"].get("message", str(result["error"]))
                return OrderResult(
                    success=False, symbol=symbol, side="bid",
                    error=err_msg,
                )

            order_id = result.get("uuid", "")
            logger.info("매수 주문 접수: %s | %.0f KRW | ID: %s", symbol, amount_krw, order_id)

            # 체결 확인 대기
            filled = self._wait_for_fill(order_id)
            if filled:
                return self._build_order_result(order_id, symbol, "bid")

            # 타임아웃 시 취소 + 쿨다운 기록
            self._cancel_order(order_id)
            self._record_failure(symbol)
            return OrderResult(
                success=False, symbol=symbol, side="bid",
                order_id=order_id,
                error=f"체결 타임아웃 ({self._risk_params.unfilled_timeout_sec}초)",
            )

        except Exception as e:
            logger.exception("매수 주문 실패: %s", symbol)
            return OrderResult(
                success=False, symbol=symbol, side="bid",
                error=str(e),
            )

    # ── 매도 ─────────────────────────────────────────────────

    def sell_market(self, symbol: str, volume: float) -> OrderResult:
        """시장가 매도를 실행합니다.

        Args:
            symbol: 마켓 코드
            volume: 매도 수량

        Returns:
            OrderResult
        """
        if volume <= 0:
            return OrderResult(
                success=False, symbol=symbol, side="ask",
                error=f"매도 수량 부적절: {volume}",
            )

        try:
            result = self._upbit.sell_market_order(symbol, volume)
            if result is None:
                return OrderResult(
                    success=False, symbol=symbol, side="ask",
                    error="주문 응답 없음",
                )

            if "error" in result:
                err_msg = result["error"].get("message", str(result["error"]))
                return OrderResult(
                    success=False, symbol=symbol, side="ask",
                    error=err_msg,
                )

            order_id = result.get("uuid", "")
            logger.info("매도 주문 접수: %s | 수량 %f | ID: %s", symbol, volume, order_id)

            filled = self._wait_for_fill(order_id)
            if filled:
                return self._build_order_result(order_id, symbol, "ask")

            self._cancel_order(order_id)
            return OrderResult(
                success=False, symbol=symbol, side="ask",
                order_id=order_id,
                error=f"체결 타임아웃 ({self._risk_params.unfilled_timeout_sec}초)",
            )

        except Exception as e:
            logger.exception("매도 주문 실패: %s", symbol)
            return OrderResult(
                success=False, symbol=symbol, side="ask",
                error=str(e),
            )

    def sell_half(self, symbol: str, total_volume: float) -> OrderResult:
        """보유 수량의 50%를 시장가 매도합니다."""
        half_volume = total_volume * 0.5
        return self.sell_market(symbol, half_volume)

    def sell_all(self, symbol: str, total_volume: float) -> OrderResult:
        """보유 수량 전량을 시장가 매도합니다."""
        return self.sell_market(symbol, total_volume)

    # ── 미체결 관리 ──────────────────────────────────────────

    def _wait_for_fill(self, order_id: str) -> bool:
        """주문 체결을 대기합니다.

        Args:
            order_id: 주문 UUID

        Returns:
            체결 여부
        """
        timeout = self._risk_params.unfilled_timeout_sec
        elapsed = 0
        poll_interval = 2  # 2초마다 확인

        while elapsed < timeout:
            try:
                order = self._upbit.get_order(order_id)
                if order and order.get("state") == "done":
                    return True
                if order and order.get("state") == "cancel":
                    # 시장가 주문은 즉시 체결 후 잔여분이 취소 처리될 수 있음
                    # executed_volume > 0 이면 (부분)체결 성공으로 간주
                    executed_vol = float(order.get("executed_volume", 0))
                    if executed_vol > 0:
                        logger.info("주문 %s: cancel 상태이나 체결량 %f 존재 → 성공 처리", order_id, executed_vol)
                        return True
                    # 체결량 0으로 취소됨 → 즉시 실패 (대기하지 않음)
                    logger.warning("주문 %s: 체결 없이 즉시 취소됨", order_id)
                    return False

            except Exception:
                logger.warning("주문 상태 확인 실패: %s", order_id)

            time.sleep(poll_interval)
            elapsed += poll_interval

        return False

    def _cancel_order(self, order_id: str) -> bool:
        """미체결 주문을 취소합니다."""
        try:
            result = self._upbit.cancel_order(order_id)
            if result and "error" not in result:
                logger.info("주문 취소 완료: %s", order_id)
                return True
            logger.warning("주문 취소 실패: %s | %s", order_id, result)
            return False
        except Exception:
            logger.exception("주문 취소 중 오류: %s", order_id)
            return False

    def _build_order_result(
        self, order_id: str, symbol: str, side: str,
    ) -> OrderResult:
        """체결 완료된 주문의 상세 결과를 조립합니다."""
        try:
            order = self._upbit.get_order(order_id)
            if not order:
                logger.error("체결 결과 조회 실패 (응답 없음): %s", order_id)
                return OrderResult(
                    success=False, order_id=order_id,
                    symbol=symbol, side=side,
                    error="체결 상세 조회 실패 (응답 없음)",
                )

            # 체결 정보 집계
            trades = order.get("trades", [])
            total_volume = sum(float(t.get("volume", 0)) for t in trades)
            total_amount = sum(float(t.get("funds", 0)) for t in trades)
            avg_price = total_amount / total_volume if total_volume > 0 else 0
            fee = float(order.get("paid_fee", 0))

            return OrderResult(
                success=True,
                order_id=order_id,
                symbol=symbol,
                side=side,
                price=avg_price,
                volume=total_volume,
                amount=total_amount,
                fee=fee,
            )
        except Exception:
            logger.exception("체결 결과 조회 실패: %s", order_id)
            return OrderResult(
                success=False, order_id=order_id,
                symbol=symbol, side=side,
                error="체결 상세 조회 중 예외 발생",
            )
