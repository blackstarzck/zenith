"""
리스크 관리 모듈 유닛 테스트.
"""

import pytest
from unittest.mock import patch
from datetime import date

from src.config import RiskParams
from src.risk.manager import RiskManager, Position


# ── 헬퍼 ─────────────────────────────────────────────────────

def make_risk_manager(
    initial_balance: float = 10_000_000,
    params: RiskParams | None = None,
) -> RiskManager:
    return RiskManager(params or RiskParams(), initial_balance)


# ── 진입 판단 ────────────────────────────────────────────────

class TestCanEnter:
    def test_can_enter_empty_portfolio(self):
        rm = make_risk_manager()
        can, reason = rm.can_enter("KRW-BTC", 10_000_000)

        assert can is True
        assert "진입 가능" in reason

    def test_cannot_enter_duplicate_symbol(self):
        rm = make_risk_manager()
        rm.add_position("KRW-BTC", 50000, 0.1, 5000)
        can, reason = rm.can_enter("KRW-BTC", 10_000_000)

        assert can is False
        assert "이미 보유" in reason

    def test_cannot_enter_max_positions(self):
        rm = make_risk_manager()
        for i in range(5):
            rm.add_position(f"KRW-COIN{i}", 1000, 1.0, 1000)

        can, reason = rm.can_enter("KRW-NEW", 10_000_000)
        assert can is False
        assert "동시 보유 한도" in reason

    def test_cannot_enter_when_daily_stopped(self):
        rm = make_risk_manager(initial_balance=1_000_000)
        # 일일 손실 5% = 50,000 KRW 초과
        rm.record_realized_pnl(-60_000)

        can, reason = rm.can_enter("KRW-BTC", 1_000_000)
        assert can is False
        assert "일일 손실 한도" in reason


# ── 포지션 사이징 ────────────────────────────────────────────

class TestPositionSizing:
    def test_max_20_percent(self):
        rm = make_risk_manager(initial_balance=10_000_000)
        amount = rm.calc_position_size(10_000_000)

        assert amount == 2_000_000  # 10M * 20%

    def test_below_minimum_returns_zero(self):
        rm = make_risk_manager(initial_balance=10_000)
        amount = rm.calc_position_size(10_000)

        # 10000 * 0.2 = 2000 < 5000 (최소 주문 금액)
        assert amount == 0.0

    def test_custom_ratio(self):
        params = RiskParams(max_position_ratio=0.10)
        rm = make_risk_manager(initial_balance=10_000_000, params=params)
        amount = rm.calc_position_size(10_000_000)

        assert amount == 1_000_000


# ── 포지션 관리 ──────────────────────────────────────────────

class TestPositionManagement:
    def test_add_and_get_position(self):
        rm = make_risk_manager()
        rm.add_position("KRW-BTC", 50000, 0.1, 5000)

        pos = rm.get_position("KRW-BTC")
        assert pos is not None
        assert pos.symbol == "KRW-BTC"
        assert pos.entry_price == 50000
        assert pos.volume == 0.1
        assert pos.has_sold_half is False

    def test_remove_position(self):
        rm = make_risk_manager()
        rm.add_position("KRW-BTC", 50000, 0.1, 5000)

        removed = rm.remove_position("KRW-BTC")
        assert removed is not None
        assert rm.get_position("KRW-BTC") is None

    def test_remove_nonexistent_returns_none(self):
        rm = make_risk_manager()
        assert rm.remove_position("KRW-NONE") is None

    def test_mark_half_sold(self):
        rm = make_risk_manager()
        rm.add_position("KRW-BTC", 50000, 0.1, 5000)
        rm.mark_half_sold("KRW-BTC")

        pos = rm.get_position("KRW-BTC")
        assert pos.has_sold_half is True

    def test_get_all_positions(self):
        rm = make_risk_manager()
        rm.add_position("KRW-BTC", 50000, 0.1, 5000)
        rm.add_position("KRW-ETH", 3000, 1.0, 3000)

        all_pos = rm.get_all_positions()
        assert len(all_pos) == 2
        assert "KRW-BTC" in all_pos
        assert "KRW-ETH" in all_pos


# ── 손익 관리 ────────────────────────────────────────────────

class TestPnLManagement:
    def test_record_profit(self):
        rm = make_risk_manager()
        rm.record_realized_pnl(100_000)
        assert rm.daily_realized_pnl == 100_000

    def test_cumulative_pnl(self):
        rm = make_risk_manager()
        rm.record_realized_pnl(50_000)
        rm.record_realized_pnl(-20_000)
        rm.record_realized_pnl(30_000)
        assert rm.daily_realized_pnl == 60_000

    def test_daily_stop_triggered(self):
        rm = make_risk_manager(initial_balance=1_000_000)
        assert rm.is_daily_stopped is False

        # 5% of 1M = 50,000 KRW
        rm.record_realized_pnl(-30_000)
        assert rm.is_daily_stopped is False

        rm.record_realized_pnl(-25_000)  # 누적 -55,000 > -50,000
        assert rm.is_daily_stopped is True

    def test_daily_reset_clears_stop(self):
        rm = make_risk_manager(initial_balance=1_000_000)
        rm.record_realized_pnl(-60_000)
        assert rm.is_daily_stopped is True

        # 날짜가 바뀌면 초기화
        tomorrow = date(2099, 12, 31)
        with patch("src.risk.manager.date") as mock_date:
            mock_date.today.return_value = tomorrow
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            rm._check_daily_reset()

        assert rm.is_daily_stopped is False
        assert rm.daily_realized_pnl == 0.0


# ── 초기 잔고 갱신 ───────────────────────────────────────────

class TestBalanceUpdate:
    def test_update_initial_balance(self):
        rm = make_risk_manager(initial_balance=1_000_000)
        rm.update_initial_balance(2_000_000)

        # 새 기준으로 5% = 100,000
        rm.record_realized_pnl(-90_000)
        assert rm.is_daily_stopped is False

        rm.record_realized_pnl(-20_000)  # 누적 -110,000 > -100,000
        assert rm.is_daily_stopped is True
