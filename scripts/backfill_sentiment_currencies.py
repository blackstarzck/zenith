"""
과거 sentiment_insights 코인 목록 보정 스크립트.

기능:
1) 뉴스 제목 기반으로 currencies를 재추론해 DB를 보정
2) 옵션(--reanalyze)으로 보정된 currencies 기준 AI 감성 분석값까지 재계산

기본 동작:
- 과거 레코드 중 "fallback 패턴(모든 뉴스가 동일 코인 목록)" 행만 대상으로 안전하게 보정
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collector.news_collector import NewsCollector
from src.config import load_config
from src.storage.client import StorageClient
from src.strategy.sentiment import SentimentAnalyzer

logger = logging.getLogger("sentiment-currency-backfill")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="과거 감성 데이터 코인 목록 보정")
    parser.add_argument("--limit", type=int, default=2000, help="조회/처리 최대 건수 (기본 2000)")
    parser.add_argument(
        "--only-fallback",
        action="store_true",
        default=True,
        help="fallback 패턴 레코드만 처리 (기본값: true)",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="모든 레코드를 대상으로 코인 재추론 (only-fallback 무시)",
    )
    parser.add_argument(
        "--reanalyze",
        action="store_true",
        help="코인 보정 후 AI 감성 분석값도 재계산하여 업데이트",
    )
    parser.add_argument("--dry-run", action="store_true", help="DB 반영 없이 변경 예정만 출력")
    parser.add_argument("--news-id", action="append", default=[], help="특정 news_id만 처리 (여러 번 지정 가능)")
    parser.add_argument("--reanalyze-retries", type=int, default=2, help="AI 재분석 재시도 횟수 (기본 2)")
    parser.add_argument("--reanalyze-sleep-sec", type=float, default=1.2, help="재시도 간 대기 초 (기본 1.2)")
    return parser.parse_args()


def _normalize_currencies(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        result = [str(v).upper().replace("KRW-", "").strip() for v in value if str(v).strip()]
        return result
    if isinstance(value, str):
        return [v.strip().upper().replace("KRW-", "") for v in value.split(",") if v.strip()]
    return []


def _is_fallback_like(row_currencies: list[str], target_currencies: list[str]) -> bool:
    if not row_currencies:
        return True
    return row_currencies == target_currencies


def _is_analysis_failed(analysis: dict[str, Any]) -> bool:
    if not analysis:
        return True
    return (
        str(analysis.get("reasoning_chain") or "").strip() == "분석 실패"
        and str(analysis.get("decision") or "").upper() == "WAIT"
        and float(analysis.get("confidence") or 0.0) == 0.0
    )


def run() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    config = load_config()
    storage = StorageClient(config.supabase)
    collector = NewsCollector(config.sentiment)
    analyzer = SentimentAnalyzer(config.sentiment) if args.reanalyze else None

    rows = storage.get_recent_sentiment_insights(limit=args.limit)
    if not rows:
        logger.info("백필 대상 레코드가 없습니다.")
        return 0

    only_news_ids = {str(n).strip() for n in args.news_id if str(n).strip()}
    target_currencies = [c.strip().upper() for c in config.sentiment.target_currencies.split(",") if c.strip()]
    processed = 0
    changed = 0
    skipped = 0

    for row in rows:
        news_id = str(row.get("news_id") or "")
        title = str(row.get("title") or "").strip()
        source = str(row.get("source") or "CryptoPanic")
        if not news_id or not title:
            skipped += 1
            continue

        if only_news_ids and news_id not in only_news_ids:
            skipped += 1
            continue

        existing = _normalize_currencies(row.get("currencies"))
        if not args.force_all and args.only_fallback and not _is_fallback_like(existing, target_currencies):
            skipped += 1
            continue

        inferred = collector.infer_currencies(title=title, result=None)
        if inferred == existing and not args.reanalyze:
            skipped += 1
            continue

        processed += 1
        logger.info(
            "[코인 보정] %s | 기존=%s -> 신규=%s",
            news_id[:16],
            ",".join(existing) if existing else "-",
            ",".join(inferred),
        )

        if args.dry_run:
            changed += 1
            continue

        update_data: dict[str, Any] = {"currencies": inferred}

        if analyzer is not None:
            analysis: dict[str, Any] = {}
            for attempt in range(args.reanalyze_retries + 1):
                analysis = analyzer.analyze(title=title, source=source, currencies=inferred)
                if not _is_analysis_failed(analysis):
                    break
                if attempt < args.reanalyze_retries:
                    wait = args.reanalyze_sleep_sec * (attempt + 1)
                    logger.warning("[재분석 재시도] %s | %d/%d | %.1fs 대기", news_id[:16], attempt + 1, args.reanalyze_retries, wait)
                    time.sleep(wait)

            if _is_analysis_failed(analysis):
                logger.warning("[재분석 실패 보존] %s | 기존 분석값 유지", news_id[:16])
            else:
                update_data.update(
                    {
                        "sentiment_score": analysis.get("sentiment_score", row.get("sentiment_score", 0.0)),
                        "sentiment_label": analysis.get("sentiment_label", row.get("sentiment_label", "neutral")),
                        "decision": analysis.get("decision", row.get("decision", "WAIT")),
                        "confidence": analysis.get("confidence", row.get("confidence", 0.0)),
                        "reasoning_chain": analysis.get("reasoning_chain", row.get("reasoning_chain")),
                        "keywords": analysis.get("keywords", row.get("keywords", [])),
                        "positive_factors": analysis.get("positive_factors", row.get("positive_factors", [])),
                        "negative_factors": analysis.get("negative_factors", row.get("negative_factors", [])),
                        "pending_reason": analysis.get("pending_reason", row.get("pending_reason")),
                    }
                )

        try:
            result = (
                storage._client.table("sentiment_insights")
                .update(update_data)
                .eq("news_id", news_id)
                .execute()
            )
            if result.data:
                changed += 1
            else:
                skipped += 1
        except Exception:
            logger.exception("코인 보정 업데이트 실패: %s", news_id)
            skipped += 1

    logger.info(
        "완료 | 처리=%d건, 변경=%d건, 스킵=%d건, 모드=%s%s",
        processed,
        changed,
        skipped,
        "dry-run" if args.dry_run else "apply",
        " + reanalyze" if args.reanalyze else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
    only_news_ids = {n.strip() for n in args.news_id if str(n).strip()}
