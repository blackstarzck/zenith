from src.collector.news_collector import NewsCollector
from src.config import SentimentConfig


def make_collector(target: str = "BTC,ETH,XRP,SOL,DOGE,ADA") -> NewsCollector:
    cfg = SentimentConfig(
        groq_api_key="",
        cryptopanic_api_key="dummy",
        target_currencies=target,
    )
    return NewsCollector(cfg)


def test_extract_currencies_from_title_market_symbol() -> None:
    collector = make_collector()
    title = "고래 지갑 이동 급증, KRW-SOL 5% 급등"
    assert collector._extract_currencies_from_title(title) == ["SOL"]


def test_extract_currencies_from_title_alias_and_ticker() -> None:
    collector = make_collector()
    title = "비트코인 약세 후 ETH 반등 시도"
    assert collector._extract_currencies_from_title(title) == ["BTC", "ETH"]


def test_extract_currencies_from_result_prefers_list() -> None:
    collector = make_collector()
    result = {"currencies": [{"code": "xrp"}, {"symbol": "krw-ada"}]}
    assert collector._extract_currencies_from_result(result) == ["XRP", "ADA"]


def test_infer_currencies_title_then_no_fallback() -> None:
    collector = make_collector("BTC,ETH")
    assert collector.infer_currencies(title="이더리움 네트워크 수수료 급락", result=None) == ["ETH"]
    assert collector.infer_currencies(title="거시 지표 불확실성 확대", result=None) == []
