from src.config import SentimentConfig
from src.strategy.sentiment import SentimentAnalyzer


def make_analyzer() -> SentimentAnalyzer:
    cfg = SentimentConfig(
        groq_api_key="dummy",
        cryptopanic_api_key="dummy",
        verification_horizon_short_minutes=12,
        verification_horizon_long_minutes=36,
        horizon_ab_confidence_threshold=75.0,
        directional_decision_min_confidence=75.0,
        directional_decision_min_abs_score=0.35,
    )
    return SentimentAnalyzer(cfg)


def test_directional_gate_blocks_low_confidence() -> None:
    analyzer = make_analyzer()
    result = analyzer._normalize_result(
        {
            "sentiment_score": 0.6,
            "sentiment_label": "bullish",
            "decision": "BUY",
            "confidence": 70,
        }
    )
    assert result["decision"] == "WAIT"
    assert "게이트 미통과" in str(result["pending_reason"])
    assert result["verification_horizon_min"] == 36


def test_directional_gate_allows_high_confidence_and_short_horizon() -> None:
    analyzer = make_analyzer()
    result = analyzer._normalize_result(
        {
            "sentiment_score": -0.5,
            "sentiment_label": "bearish",
            "decision": "SELL",
            "confidence": 90,
        }
    )
    assert result["decision"] == "SELL"
    assert result["verification_horizon_min"] == 12


def test_no_symbol_forces_wait() -> None:
    analyzer = make_analyzer()
    result = analyzer._normalize_result(
        {
            "sentiment_score": 0.9,
            "sentiment_label": "bullish",
            "decision": "BUY",
            "confidence": 99,
        },
        no_symbol=True,
    )
    assert result["decision"] == "WAIT"
    assert result["pending_reason"] == "코인 식별 실패"
    assert result["verification_horizon_min"] == 36
