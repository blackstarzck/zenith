from src.collector.cross_exchange_collector import CrossExchangeCollector
from src.config import BinanceConfig, FxConfig


def make_collector() -> CrossExchangeCollector:
    return CrossExchangeCollector(
        binance_config=BinanceConfig(),
        fx_config=FxConfig(),
    )


def test_to_binance_symbol_converts_market_code() -> None:
    collector = make_collector()
    assert collector._to_binance_symbol("KRW-BTC") == "BTCUSDT"
    collector.close()


def test_calculate_dislocation_pct_returns_positive_for_kimchi_premium() -> None:
    pct = CrossExchangeCollector.calculate_dislocation_pct(
        upbit_price=101_000.0,
        foreign_price_krw=100_000.0,
    )
    assert pct is not None
    assert round(pct, 2) == 1.0


def test_calculate_dislocation_pct_returns_none_for_invalid_foreign_price() -> None:
    assert CrossExchangeCollector.calculate_dislocation_pct(100_000.0, 0.0) is None

