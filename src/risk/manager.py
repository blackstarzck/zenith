"""
리스크 관리 모듈.
포지션 사이징, 동시 보유 제한, 일일 손실 한도를 관리합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from src.config import RiskParams

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """보유 포지션 정보."""
    symbol: str
    entry_price: float
    volume: float
    amount: float         # 진입 총액 (KRW)
    has_sold_half: bool = False  # 1차 분할 익절 완료 여부


class RiskManager:
    """리스크 관리자.

    역할:
    - 신규 진입 가능 여부 판단
    - 포지션 사이징 (종목당 최대 20%)
    - 일일 손실 한도 모니터링
    - 동시 보유 종목 수 제한
    """

    def __init__(self, params: RiskParams, initial_balance: float) -> None:
        self._params = params
        self._initial_balance = initial_balance   # 당일 시작 자산
        self._daily_realized_pnl: float = 0.0     # 당일 실현 손익
        self._positions: dict[str, Position] = {}  # symbol → Position
        self._today: date = date.today()
        self._is_daily_stopped: bool = False       # 일일 손실 한도 초과 여부

    # ── 진입 판단 ────────────────────────────────────────────

    def can_enter(self, symbol: str, current_balance: float) -> tuple[bool, str]:
        """신규 진입이 가능한지 판단합니다.

        Returns:
            (가능 여부, 사유)
        """
        self._check_daily_reset()

        if self._is_daily_stopped:
            return False, "일일 손실 한도 초과로 매매 중단"

        if symbol in self._positions:
            return False, f"{symbol} 이미 보유 중"

        if len(self._positions) >= self._params.max_concurrent_positions:
            return False, f"동시 보유 한도 도달 ({self._params.max_concurrent_positions}종목)"

        return True, "진입 가능"

    def calc_position_size(self, current_balance: float) -> float:
        """신규 진입 시 투입 금액을 계산합니다 (KRW).

        전체 자산의 max_position_ratio(20%) 이하로 제한.
        """
        max_amount = current_balance * self._params.max_position_ratio

        # 최소 주문 금액 확인
        if max_amount < self._params.min_order_amount_krw:
            return 0.0

        return max_amount

    # ── 포지션 관리 ──────────────────────────────────────────

    def add_position(
        self,
        symbol: str,
        entry_price: float,
        volume: float,
        amount: float,
    ) -> None:
        """포지션을 등록합니다."""
        self._positions[symbol] = Position(
            symbol=symbol,
            entry_price=entry_price,
            volume=volume,
            amount=amount,
        )
        logger.info(
            "포지션 추가: %s @ %.2f KRW (수량: %f)",
            symbol, entry_price, volume,
        )

    def remove_position(self, symbol: str) -> Position | None:
        """포지션을 제거하고 반환합니다."""
        pos = self._positions.pop(symbol, None)
        if pos:
            logger.info("포지션 제거: %s", symbol)
        return pos

    def get_position(self, symbol: str) -> Position | None:
        """포지션을 조회합니다."""
        return self._positions.get(symbol)

    def get_all_positions(self) -> dict[str, Position]:
        """모든 포지션을 반환합니다."""
        return dict(self._positions)

    def mark_half_sold(self, symbol: str) -> None:
        """1차 분할 익절 완료를 표시합니다."""
        if symbol in self._positions:
            self._positions[symbol].has_sold_half = True

    # ── 손익 관리 ────────────────────────────────────────────

    def record_realized_pnl(self, pnl: float) -> None:
        """실현 손익을 기록하고 일일 한도를 확인합니다."""
        self._daily_realized_pnl += pnl
        logger.info(
            "실현 손익: %+.0f KRW (당일 누적: %+.0f KRW)",
            pnl, self._daily_realized_pnl,
        )

        # 일일 손실 한도 확인
        loss_limit = self._initial_balance * self._params.daily_loss_limit_ratio
        if self._daily_realized_pnl < -loss_limit:
            self._is_daily_stopped = True
            logger.critical(
                "일일 손실 한도 초과! 누적 손실: %+.0f KRW > 한도: -%.0f KRW. 매매 중단.",
                self._daily_realized_pnl, loss_limit,
            )

    @property
    def is_daily_stopped(self) -> bool:
        """일일 매매 중단 상태인지 반환합니다."""
        return self._is_daily_stopped

    @property
    def daily_realized_pnl(self) -> float:
        """당일 실현 손익을 반환합니다."""
        return self._daily_realized_pnl

    # ── 내부 유틸 ────────────────────────────────────────────

    def _check_daily_reset(self) -> None:
        """날짜가 바뀌면 일일 카운터를 초기화합니다."""
        today = date.today()
        if today != self._today:
            logger.info("새 거래일 시작. 일일 카운터 초기화.")
            self._today = today
            self._daily_realized_pnl = 0.0
            self._is_daily_stopped = False

    def update_initial_balance(self, balance: float) -> None:
        """당일 시작 자산을 갱신합니다 (새 거래일 시작 시 호출)."""
        self._initial_balance = balance
