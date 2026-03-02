from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pyupbit

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class VerificationMetrics:
    window_start_at: datetime
    window_end_at: datetime
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    return_pct: float
    max_rise_pct: float
    max_drop_pct: float
    volatility_pct: float
    peak_at: datetime
    trough_at: datetime
    minutes_to_peak: int
    minutes_to_trough: int


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def select_symbol(currencies: list[str] | None) -> str | None:
    if not currencies:
        return None
    for item in currencies:
        symbol = str(item).upper().strip()
        if not symbol:
            continue
        if symbol.startswith("KRW-"):
            base = symbol.split("-", 1)[1].strip()
            if base:
                return f"KRW-{base}"
            continue
        return f"KRW-{symbol}"
    return None


def get_price_near(symbol: str, target_utc: datetime) -> float | None:
    """target 시각 직전 1분봉 종가를 조회합니다."""
    try:
        target_kst = target_utc.astimezone(KST)
        to_str = target_kst.strftime("%Y-%m-%d %H:%M:%S")
        df = pyupbit.get_ohlcv(symbol, interval="minute1", to=to_str, count=1)
        if df is None or df.empty:
            return None
        value = float(df["close"].iloc[-1])
        return value if value > 0 else None
    except Exception:
        return None


def _to_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=KST).astimezone(timezone.utc)
    return ts.astimezone(timezone.utc)


def get_window_metrics(symbol: str, start_utc: datetime, end_utc: datetime) -> VerificationMetrics | None:
    """검증 구간의 분봉 지표를 계산합니다."""
    if end_utc <= start_utc:
        return None

    minutes = int((end_utc - start_utc).total_seconds() // 60)
    count = max(5, min(200, minutes + 3))
    try:
        to_str = end_utc.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
        df = pyupbit.get_ohlcv(symbol, interval="minute1", to=to_str, count=count)
        if df is None or df.empty:
            return None

        open_price = float(df["open"].iloc[0])
        close_price = float(df["close"].iloc[-1])
        high_price = float(df["high"].max())
        low_price = float(df["low"].min())
        if open_price <= 0:
            return None

        peak_idx = df["high"].idxmax()
        trough_idx = df["low"].idxmin()
        peak_at = _to_utc(peak_idx.to_pydatetime())
        trough_at = _to_utc(trough_idx.to_pydatetime())

        return_pct = ((close_price / open_price) - 1.0) * 100.0
        max_rise_pct = ((high_price / open_price) - 1.0) * 100.0
        max_drop_pct = ((low_price / open_price) - 1.0) * 100.0
        volatility_pct = ((high_price - low_price) / open_price) * 100.0
        minutes_to_peak = max(0, int((peak_at - start_utc).total_seconds() // 60))
        minutes_to_trough = max(0, int((trough_at - start_utc).total_seconds() // 60))

        return VerificationMetrics(
            window_start_at=start_utc,
            window_end_at=end_utc,
            open_price=open_price,
            close_price=close_price,
            high_price=high_price,
            low_price=low_price,
            return_pct=return_pct,
            max_rise_pct=max_rise_pct,
            max_drop_pct=max_drop_pct,
            volatility_pct=volatility_pct,
            peak_at=peak_at,
            trough_at=trough_at,
            minutes_to_peak=minutes_to_peak,
            minutes_to_trough=minutes_to_trough,
        )
    except Exception:
        return None


def evaluate_decision(
    decision: str,
    change_pct: float,
    hold_threshold_pct: float,
    directional_neutral_band_pct: float = 0.0,
) -> tuple[str, bool | None]:
    verification_result = "incorrect"
    direction_match: bool | None = None

    if decision == "BUY":
        if abs(change_pct) <= abs(directional_neutral_band_pct):
            verification_result = "neutral"
        else:
            direction_match = change_pct > 0
            verification_result = "correct" if direction_match else "incorrect"
    elif decision == "SELL":
        if abs(change_pct) <= abs(directional_neutral_band_pct):
            verification_result = "neutral"
        else:
            direction_match = change_pct < 0
            verification_result = "correct" if direction_match else "incorrect"
    elif decision in {"HOLD", "WAIT"}:
        verification_result = "correct" if abs(change_pct) <= hold_threshold_pct else "incorrect"

    return verification_result, direction_match


def build_verification_explanation(metrics: VerificationMetrics) -> str:
    """검증 구간 설명 문장을 생성합니다."""
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    start_dt = metrics.window_start_at.astimezone(KST)
    end_dt = metrics.window_end_at.astimezone(KST)

    start_txt = (
        f"{start_dt.month}월 {start_dt.day}일 {weekdays[start_dt.weekday()]}요일 "
        f"{start_dt.hour:02d}시 {start_dt.minute:02d}분"
    )
    end_txt = (
        f"{end_dt.month}월 {end_dt.day}일 {weekdays[end_dt.weekday()]}요일 "
        f"{end_dt.hour:02d}시 {end_dt.minute:02d}분"
    )

    is_same_day_label = (
        start_dt.month == end_dt.month
        and start_dt.day == end_dt.day
        and start_dt.weekday() == end_dt.weekday()
    )
    period_txt = start_txt if is_same_day_label else f"{start_txt}~{end_txt}"

    trend = "상승" if metrics.return_pct > 0 else "하락" if metrics.return_pct < 0 else "횡보"
    return (
        f"{period_txt} 구간 {trend} 흐름. "
        f"시가 {metrics.open_price:,.0f}원 → 종가 {metrics.close_price:,.0f}원({metrics.return_pct:+.3f}%), "
        f"고가 {metrics.high_price:,.0f}원({metrics.max_rise_pct:+.3f}%, +{metrics.minutes_to_peak}분), "
        f"저가 {metrics.low_price:,.0f}원({metrics.max_drop_pct:+.3f}%, +{metrics.minutes_to_trough}분), "
        f"변동폭 {metrics.volatility_pct:.3f}%."
    )


def build_analysis_insight(
    *,
    decision: str,
    confidence: float | None,
    metrics: VerificationMetrics,
    verification_result: str,
) -> str:
    """검증 결과를 기반으로 AI 차트 분석 인사이트 문장을 생성합니다."""
    conf = float(confidence or 0.0)
    decision = str(decision or "WAIT").upper()

    if decision == "BUY":
        if verification_result == "neutral":
            return (
                f"AI는 BUY였지만 종료 수익률이 {metrics.return_pct:+.2f}%로 중립 밴드 안에 머물렀습니다. "
                f"발행 후 {metrics.minutes_to_peak}분 내 최대 {metrics.max_rise_pct:+.2f}% 반등과 "
                f"{metrics.minutes_to_trough}분 내 {metrics.max_drop_pct:+.2f}% 되돌림이 교차해 "
                f"명확한 방향성이 약한 구간으로 해석됩니다."
            )
        if verification_result == "correct":
            return (
                f"AI가 BUY를 제시한 뒤 {metrics.minutes_to_peak}분 내 최대 {metrics.max_rise_pct:+.2f}%까지 급등했고, "
                f"검증 종료 시점 수익률은 {metrics.return_pct:+.2f}%입니다. "
                f"신뢰도 {conf:.0f}점 기준으로 보면 진입 타이밍 적중 케이스입니다."
            )
        return (
            f"AI는 BUY였지만 발행 후 {metrics.minutes_to_trough}분 내 최대 {metrics.max_drop_pct:+.2f}% 하락이 먼저 발생했고, "
            f"종료 수익률도 {metrics.return_pct:+.2f}%로 마감했습니다. "
            f"신뢰도 {conf:.0f}점 대비 방향 오판 가능성이 높은 케이스입니다."
        )

    if decision == "SELL":
        if verification_result == "neutral":
            return (
                f"AI는 SELL이었지만 종료 수익률이 {metrics.return_pct:+.2f}%로 중립 밴드 안에 머물렀습니다. "
                f"구간 내 하락/반등이 혼재해 하방 신호의 우위가 크지 않았던 케이스입니다."
            )
        if verification_result == "correct":
            return (
                f"AI가 SELL을 제시한 뒤 {metrics.minutes_to_trough}분 내 최대 {metrics.max_drop_pct:+.2f}%까지 하락해 "
                f"하방 방향성이 확인됐습니다. 종료 시점 수익률은 {metrics.return_pct:+.2f}%입니다."
            )
        return (
            f"AI는 SELL이었지만 발행 후 {metrics.minutes_to_peak}분 내 최대 {metrics.max_rise_pct:+.2f}% 급등이 나타났고, "
            f"종료 수익률도 {metrics.return_pct:+.2f}%입니다. 숏/회피 판단 관점에서 미스 신호입니다."
        )

    # HOLD / WAIT
    if verification_result == "correct":
        return (
            f"AI가 {decision}로 관망한 뒤 구간 변동폭은 {metrics.volatility_pct:.2f}% 수준이었고 "
            f"종료 수익률은 {metrics.return_pct:+.2f}%입니다. 급격한 추세 전환 없이 중립 흐름에 가까웠습니다."
        )

    return (
        f"AI가 {decision}로 관망했지만 발행 후 {metrics.minutes_to_peak}분 내 +{metrics.max_rise_pct:.2f}% "
        f"또는 {metrics.minutes_to_trough}분 내 {metrics.max_drop_pct:+.2f}% 수준의 유의미한 변동이 발생했습니다. "
        f"관망 기준 재조정이 필요한 케이스입니다."
    )
