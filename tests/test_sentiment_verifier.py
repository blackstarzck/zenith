from datetime import datetime, timedelta, timezone

from src.strategy.sentiment_verifier import (
    VerificationMetrics,
    build_analysis_insight,
    evaluate_decision,
)


def make_metrics(
    return_pct: float = 1.2,
    max_rise_pct: float = 2.4,
    max_drop_pct: float = -0.8,
    minutes_to_peak: int = 7,
    minutes_to_trough: int = 3,
) -> VerificationMetrics:
    start = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)
    return VerificationMetrics(
        window_start_at=start,
        window_end_at=end,
        open_price=100.0,
        close_price=101.2,
        high_price=102.4,
        low_price=99.2,
        return_pct=return_pct,
        max_rise_pct=max_rise_pct,
        max_drop_pct=max_drop_pct,
        volatility_pct=3.2,
        peak_at=start + timedelta(minutes=minutes_to_peak),
        trough_at=start + timedelta(minutes=minutes_to_trough),
        minutes_to_peak=minutes_to_peak,
        minutes_to_trough=minutes_to_trough,
    )


def test_buy_insight_contains_surge_timing() -> None:
    text = build_analysis_insight(
        decision="BUY",
        confidence=82,
        metrics=make_metrics(),
        verification_result="correct",
    )
    assert "BUY" in text
    assert "7분" in text
    assert "+2.40%" in text


def test_sell_insight_contains_drop_timing() -> None:
    text = build_analysis_insight(
        decision="SELL",
        confidence=78,
        metrics=make_metrics(return_pct=-1.1, max_rise_pct=0.6, max_drop_pct=-2.0, minutes_to_peak=4, minutes_to_trough=9),
        verification_result="correct",
    )
    assert "SELL" in text
    assert "9분" in text
    assert "-2.00%" in text


def test_evaluate_decision_returns_neutral_in_small_move_band() -> None:
    result, direction = evaluate_decision(
        decision="BUY",
        change_pct=0.04,
        hold_threshold_pct=0.3,
        directional_neutral_band_pct=0.15,
    )
    assert result == "neutral"
    assert direction is None
