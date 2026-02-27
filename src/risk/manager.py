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

    def calc_position_size(self, current_balance: float,
                           recent_sell_trades: list[dict] | None = None) -> float:
        """포지션 크기(KRW)를 계산합니다.

        켈리 공식 기반 동적 사이징: 최근 매도 거래 통계로 최적 비중 산출.
        데이터 부족(< kelly_min_trades) 시 기존 고정비율(max_position_ratio) 폴백.

        Args:
            current_balance: 현재 가용 잔고 (KRW)
            recent_sell_trades: 최근 매도 거래 목록 (각 dict에 'pnl' 키 필수). None이면 고정비율.

        Returns:
            float: 투입 금액 (KRW). 0.0이면 진입 차단.
        """
        fixed_size = current_balance * self._params.max_position_ratio

        # 최소 주문 금액 확인
        if fixed_size < self._params.min_order_amount_krw:
            return 0.0

        # 폴백 조건: 데이터 없음 또는 부족
        if not recent_sell_trades or len(recent_sell_trades) < self._params.kelly_min_trades:
            logger.debug('[Kelly 폴백] 매도 거래 %d건 < 최소 %d건, 고정비율 %.0f%% 사용',
                         len(recent_sell_trades) if recent_sell_trades else 0,
                         self._params.kelly_min_trades,
                         self._params.max_position_ratio * 100)
            return fixed_size

        # 승률/손익비 계산
        wins = [t['pnl'] for t in recent_sell_trades if t.get('pnl', 0) > 0]
        losses = [t['pnl'] for t in recent_sell_trades if t.get('pnl', 0) < 0]

        # 엣지 케이스: 손실 없음 (전승) → 고정비율 사용 (과신 방지)
        if not losses:
            logger.info('[Kelly 폴백] 손실 거래 0건 (전승), 고정비율 사용')
            return fixed_size

        # 엣지 케이스: 승리 없음 (전패) → 진입 차단
        if not wins:
            logger.warning('[Kelly 차단] 승리 거래 0건 (전패), 진입 차단')
            return 0.0

        total = len(wins) + len(losses)
        win_rate = len(wins) / total
        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))

        if avg_loss == 0:
            return fixed_size  # 0으로 나누기 방지
        win_loss_ratio = avg_win / avg_loss

        # 켈리 공식: f* = p - (1-p)/b
        kelly_f = win_rate - ((1 - win_rate) / win_loss_ratio)

        # Half-Kelly 적용
        optimal_f = kelly_f * self._params.kelly_multiplier

        # 켈리 ≤ 0 → 기대값 음수, 진입 차단
        if optimal_f <= 0:
            logger.warning('[Kelly 차단] 기대값 음수 (Kelly=%.4f), 진입 차단', kelly_f)
            return 0.0

        # max_position_ratio로 캡핑
        capped_f = min(optimal_f, self._params.max_position_ratio)
        kelly_size = current_balance * capped_f

        # 최소 주문 금액 확인
        if kelly_size < self._params.min_order_amount_krw:
            return 0.0

        logger.info('[Kelly 사이징] 승률: %.1f%%, 손익비: %.2f, Kelly: %.1f%% → %.0f KRW',
                    win_rate * 100, win_loss_ratio, capped_f * 100, kelly_size)

        return kelly_size

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

    def reset_daily(self, new_initial_balance: float) -> None:
        """새 거래일 시작 시 일일 카운터를 초기화하고 시작 자산을 갱신합니다.

        Orchestrator._check_daily_reset()에서 전일 stats 확정 후 호출됩니다.
        """
        logger.info("새 거래일 시작. 일일 카운터 초기화.")
        self._today = date.today()
        self._daily_realized_pnl = 0.0
        self._is_daily_stopped = False
        self._initial_balance = new_initial_balance
