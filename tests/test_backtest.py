"""백테스팅 엔진 유닛 테스트."""

import unittest
import numpy as np
import pandas as pd

from src.backtest.engine import (
    BacktestEngine,
    BacktestResult,
    BacktestTrade,
    UPBIT_FEE_RATE,
)
from src.config import StrategyParams, RiskParams


def _make_ohlcv(n: int = 200, base_price: float = 50000.0, seed: int = 42) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="15min")
    prices = [base_price]
    for _ in range(n - 1):
        change = rng.normal(0, base_price * 0.005)
        prices.append(max(prices[-1] + change, base_price * 0.5))

    closes = np.array(prices)
    highs = closes * (1 + rng.uniform(0, 0.01, n))
    lows = closes * (1 - rng.uniform(0, 0.01, n))
    opens = closes + rng.normal(0, base_price * 0.002, n)
    volumes = rng.uniform(100, 10000, n)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }, index=dates)


def _make_trending_down(n: int = 200, base_price: float = 50000.0) -> pd.DataFrame:
    """하락 추세 OHLCV 생성 (BB 하단 이탈 → 복귀 시나리오 유도)."""
    rng = np.random.RandomState(99)
    dates = pd.date_range("2024-01-01", periods=n, freq="15min")

    prices = []
    price = base_price
    for i in range(n):
        if i < 80:
            # 안정기
            price += rng.normal(0, price * 0.002)
        elif i < 120:
            # 급락 (BB 하단 이탈)
            price -= abs(rng.normal(price * 0.008, price * 0.003))
        else:
            # 반등 (복귀)
            price += abs(rng.normal(price * 0.004, price * 0.002))
        prices.append(max(price, 1000))

    closes = np.array(prices)
    highs = closes * 1.005
    lows = closes * 0.995
    opens = closes * (1 + rng.normal(0, 0.001, n))
    volumes = rng.uniform(100, 10000, n)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }, index=dates)


class TestBacktestEngineBasic(unittest.TestCase):
    """BacktestEngine 기본 동작 테스트."""

    def test_returns_backtest_result(self):
        df = _make_ohlcv()
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df, symbol="KRW-TEST")
        self.assertIsInstance(result, BacktestResult)

    def test_result_has_required_fields(self):
        df = _make_ohlcv()
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df, symbol="KRW-TEST")

        self.assertEqual(result.symbol, "KRW-TEST")
        self.assertEqual(result.initial_balance, 1_000_000)
        self.assertGreater(result.final_balance, 0)
        self.assertIsInstance(result.total_return_pct, float)
        self.assertIsInstance(result.win_rate, float)
        self.assertIsInstance(result.max_drawdown_pct, float)
        self.assertIsInstance(result.profit_loss_ratio, float)
        self.assertIsInstance(result.sharpe_ratio, float)

    def test_equity_curve_populated(self):
        df = _make_ohlcv()
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df, symbol="KRW-TEST")
        self.assertGreater(len(result.equity_curve), 0)

    def test_equity_curve_has_required_keys(self):
        df = _make_ohlcv()
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df, symbol="KRW-TEST")
        if result.equity_curve:
            entry = result.equity_curve[0]
            self.assertIn("timestamp", entry)
            self.assertIn("equity", entry)
            self.assertIn("balance", entry)
            self.assertIn("drawdown_pct", entry)

    def test_insufficient_data_raises(self):
        df = _make_ohlcv(n=20)
        engine = BacktestEngine()
        with self.assertRaises(ValueError):
            engine.run(df)

    def test_dates_match_dataframe(self):
        df = _make_ohlcv()
        engine = BacktestEngine()
        result = engine.run(df)
        self.assertIn("2024-01-01", result.start_date)


class TestBacktestEngineMetrics(unittest.TestCase):
    """백테스트 지표 계산 테스트."""

    def test_win_rate_between_0_and_100(self):
        df = _make_ohlcv(n=500, seed=123)
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df)
        self.assertGreaterEqual(result.win_rate, 0)
        self.assertLessEqual(result.win_rate, 100)

    def test_mdd_non_negative(self):
        df = _make_ohlcv()
        engine = BacktestEngine()
        result = engine.run(df)
        self.assertGreaterEqual(result.max_drawdown_pct, 0)

    def test_total_return_matches_balance(self):
        df = _make_ohlcv()
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df)
        expected_return = ((result.final_balance - 1_000_000) / 1_000_000) * 100
        self.assertAlmostEqual(result.total_return_pct, expected_return, places=4)

    def test_no_trades_means_zero_win_rate(self):
        """거래가 없으면 승률 0%."""
        # 매우 짧은 안정적 데이터 → 진입 조건 미충족 기대
        df = _make_ohlcv(n=60, base_price=50000, seed=1)
        engine = BacktestEngine()
        result = engine.run(df)
        if result.total_trades == 0:
            self.assertEqual(result.win_rate, 0)

    def test_trades_are_paired(self):
        """매수와 매도가 쌍으로 이루어져야 함."""
        df = _make_trending_down(n=300)
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df)
        buys = [t for t in result.trades if t.side == "buy"]
        sells = [t for t in result.trades if t.side == "sell"]
        # 매수 수 <= 매도 수 (마지막 강제 청산 포함)
        self.assertLessEqual(len(buys), len(sells) + 1)


class TestBacktestEngineCustomParams(unittest.TestCase):
    """커스텀 파라미터 테스트."""

    def test_custom_strategy_params(self):
        params = StrategyParams(
            bb_period=15,
            bb_std_dev=1.5,
            rsi_period=10,
            rsi_oversold=25.0,
        )
        df = _make_ohlcv(n=200)
        engine = BacktestEngine(strategy_params=params)
        result = engine.run(df)
        self.assertIsInstance(result, BacktestResult)

    def test_custom_risk_params(self):
        risk = RiskParams(
            max_position_ratio=0.10,
            min_order_amount_krw=1000,
        )
        df = _make_ohlcv(n=200)
        engine = BacktestEngine(risk_params=risk)
        result = engine.run(df)
        self.assertIsInstance(result, BacktestResult)

    def test_different_initial_balance(self):
        df = _make_ohlcv()
        engine = BacktestEngine(initial_balance=10_000_000)
        result = engine.run(df)
        self.assertEqual(result.initial_balance, 10_000_000)

    def test_fee_is_applied(self):
        """수수료가 0이 아닌지 확인."""
        df = _make_trending_down(n=300)
        engine = BacktestEngine(initial_balance=1_000_000)
        result = engine.run(df)
        if result.trades:
            fees = [t.fee for t in result.trades]
            total_fee = sum(fees)
            self.assertGreater(total_fee, 0)


class TestBacktestColumnNormalization(unittest.TestCase):
    """컬럼 정규화 테스트."""

    def test_uppercase_columns_work(self):
        df = _make_ohlcv()
        df.columns = [c.upper() for c in df.columns]
        engine = BacktestEngine()
        result = engine.run(df)
        self.assertIsInstance(result, BacktestResult)

    def test_missing_column_raises(self):
        df = _make_ohlcv()
        df = df.drop(columns=["close"])
        engine = BacktestEngine()
        with self.assertRaises(ValueError):
            engine.run(df)


if __name__ == "__main__":
    unittest.main()
