"""
과거 감성 분석 데이터 백필 스크립트.

목적:
- 기존 sentiment_insights 레코드 중 검증값이 비어 있는 데이터를
  뉴스 시점/검증 시점 분봉 가격으로 보정하여 채운다.
- 갱신된 날짜의 sentiment_performance_daily 집계를 재생성한다.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.storage.client import StorageClient
from src.strategy.sentiment_verifier import (
    parse_iso_datetime,
    select_symbol,
    get_price_near,
    get_window_metrics,
    evaluate_decision,
    build_verification_explanation,
    build_analysis_insight,
)

logger = logging.getLogger("sentiment-backfill")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="감성 검증 과거 데이터 백필")
    parser.add_argument("--days", type=int, default=30, help="조회 기간(일), 기본 30")
    parser.add_argument("--limit", type=int, default=1000, help="최대 처리 건수, 기본 1000")
    parser.add_argument("--sleep-sec", type=float, default=0.12, help="API 호출 간 대기초, 기본 0.12")
    parser.add_argument(
        "--include-verified",
        action="store_true",
        help="이미 검증된 데이터도 다시 계산하여 덮어씁니다.",
    )
    parser.add_argument(
        "--news-id",
        action="append",
        default=[],
        help="특정 news_id만 처리합니다. 여러 번 지정 가능",
    )
    parser.add_argument(
        "--reassign-horizon-ab",
        action="store_true",
        help="기존 verification_horizon_min을 무시하고 현재 A/B 규칙(단기/장기)으로 재할당합니다.",
    )
    parser.add_argument("--dry-run", action="store_true", help="DB 업데이트 없이 로그만 출력")
    return parser.parse_args()


def pick_horizon_minutes(row: dict, config, use_ab: bool) -> int:
    if not use_ab:
        return int(row.get("verification_horizon_min") or config.sentiment.verification_horizon_minutes)

    decision = str(row.get("decision") or "WAIT").upper()
    confidence = float(row.get("confidence") or 0.0)
    if decision in {"BUY", "SELL"} and confidence >= float(config.sentiment.horizon_ab_confidence_threshold):
        return int(config.sentiment.verification_horizon_short_minutes)
    return int(config.sentiment.verification_horizon_long_minutes)


def run() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    config = load_config()
    storage = StorageClient(config.supabase)

    news_ids = [str(n).strip() for n in args.news_id if str(n).strip()]
    targets = storage.get_sentiment_insights_for_backfill(
        limit=args.limit,
        days=args.days,
        include_verified=bool(args.include_verified),
        news_ids=news_ids,
    )
    if not targets:
        logger.info("백필 대상이 없습니다.")
        return 0

    logger.info(
        "백필 대상 %d건 (include_verified=%s, news_id_filter=%d)",
        len(targets),
        args.include_verified,
        len(news_ids),
    )

    now_utc = datetime.now(timezone.utc)
    affected_dates: set[date] = set()
    success = 0
    skipped = 0
    hold_threshold = abs(config.sentiment.hold_neutral_threshold_pct)

    for row in targets:
        news_id = str(row.get("news_id") or "")
        if not news_id:
            skipped += 1
            continue

        created_at = parse_iso_datetime(row.get("created_at"))
        if not created_at:
            if not args.dry_run:
                storage.update_sentiment_pending_reason(news_id, "생성 시각 파싱 실패")
            skipped += 1
            continue

        horizon = pick_horizon_minutes(row, config, args.reassign_horizon_ab)
        due_at = created_at + timedelta(minutes=max(horizon, 1))
        if due_at > now_utc:
            skipped += 1
            continue

        decision = str(row.get("decision") or "WAIT").upper()
        symbol = select_symbol(row.get("currencies") or [])
        if not symbol:
            if not args.dry_run:
                storage.update_sentiment_pending_reason(news_id, "검증 심볼 없음")
            skipped += 1
            continue

        # 과거 저장 baseline_price 품질 이슈를 피하기 위해
        # 뉴스 시각 기준가를 우선 재조회하고, 실패 시 저장값으로 폴백합니다.
        baseline = get_price_near(symbol, created_at)
        time.sleep(args.sleep_sec)
        if baseline is None or float(baseline) <= 0:
            stored_baseline = row.get("baseline_price")
            baseline = stored_baseline
        if baseline is None or float(baseline) <= 0:
            if not args.dry_run:
                storage.update_sentiment_pending_reason(news_id, "기준가 백필 실패")
            skipped += 1
            continue

        metrics = get_window_metrics(symbol, created_at, due_at)
        time.sleep(args.sleep_sec)
        if metrics is None:
            if not args.dry_run:
                storage.update_sentiment_pending_reason(news_id, "검증 구간 가격 데이터 부족")
            skipped += 1
            continue

        change_pct = ((metrics.close_price / float(baseline)) - 1.0) * 100.0
        verification_result, direction_match = evaluate_decision(
            decision=decision,
            change_pct=change_pct,
            hold_threshold_pct=hold_threshold,
            directional_neutral_band_pct=config.sentiment.directional_neutral_band_pct,
        )
        explanation = build_verification_explanation(metrics)
        insight = build_analysis_insight(
            decision=decision,
            confidence=row.get("confidence"),
            metrics=metrics,
            verification_result=verification_result,
        )

        logger.info(
            "백필 %s | %s | horizon=%d분 | %.4f%% | %s",
            news_id[:16], symbol, horizon, change_pct, verification_result
        )

        if not args.dry_run:
            ok = storage.finalize_sentiment_verification(
                news_id=news_id,
                actual_price_change=change_pct,
                evaluation_price=metrics.close_price,
                verification_result=verification_result,
                direction_match=direction_match,
                baseline_price=float(baseline),
                verification_window_start_at=metrics.window_start_at,
                verification_window_end_at=metrics.window_end_at,
                window_open_price=metrics.open_price,
                window_close_price=metrics.close_price,
                window_high_price=metrics.high_price,
                window_low_price=metrics.low_price,
                window_return_pct=metrics.return_pct,
                window_max_rise_pct=metrics.max_rise_pct,
                window_max_drop_pct=metrics.max_drop_pct,
                verification_explanation=explanation,
                analysis_insight=insight,
                evaluated_at=now_utc,
                verification_horizon_min=horizon,
                pending_reason=None,
            )
            if ok:
                success += 1
                affected_dates.add(created_at.date())
            else:
                skipped += 1
        else:
            success += 1
            affected_dates.add(created_at.date())

    if not args.dry_run:
        for target_date in sorted(affected_dates):
            storage.rebuild_sentiment_performance_daily(target_date)

    logger.info("완료: 성공 %d건, 스킵 %d건, 영향 날짜 %d일", success, skipped, len(affected_dates))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
