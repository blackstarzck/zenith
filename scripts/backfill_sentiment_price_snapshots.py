"""
과거 감성 뉴스 구간의 price_snapshots 백필 스크립트.

목적:
- sentiment_insights 레코드의 뉴스 생성 시각 ~ 검증 종료 시각 구간을 업비트 1분봉으로 조회
- 누락된 분봉 close 값을 price_snapshots에 채워 차트 렌더링 가능 상태로 보정

주의:
- 기본은 dry-run 권장
- 같은 symbol+분(minute) 시점이 이미 있으면 중복 삽입하지 않음
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.storage.client import StorageClient
from src.strategy.sentiment_verifier import parse_iso_datetime, select_symbol

logger = logging.getLogger("sentiment-snapshot-backfill")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="감성 뉴스 구간 price_snapshots 백필")
    parser.add_argument("--days", type=int, default=180, help="조회 기간(일), 기본 180")
    parser.add_argument("--limit", type=int, default=5000, help="최대 처리 뉴스 건수, 기본 5000")
    parser.add_argument("--sleep-sec", type=float, default=0.08, help="API 호출 간 대기(초), 기본 0.08")
    parser.add_argument("--news-id", action="append", default=[], help="특정 news_id만 처리 (복수 지정 가능)")
    parser.add_argument("--dry-run", action="store_true", help="DB 삽입 없이 예상 결과만 출력")
    return parser.parse_args()


def _to_upbit_to_string(dt_utc: datetime) -> str:
    """Upbit candles `to` 파라미터용 UTC ISO 문자열."""
    return dt_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iter_ohlcv_close_points(
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    sleep_sec: float,
) -> list[tuple[datetime, float]]:
    """업비트 1분봉 close 포인트를 [start, end] 범위로 반환합니다."""
    if end_utc <= start_utc:
        return []

    endpoint = "https://api.upbit.com/v1/candles/minutes/1"
    timeout = httpx.Timeout(8.0, connect=4.0)
    points: dict[datetime, float] = {}
    remain_minutes = int((end_utc - start_utc).total_seconds() // 60)
    count = max(5, min(200, remain_minutes + 2))
    params = {
        "market": symbol,
        "to": _to_upbit_to_string(end_utc),
        "count": count,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(endpoint, params=params)
        resp.raise_for_status()
        candles = resp.json() or []
    time.sleep(sleep_sec)

    for c in candles:
        ts_utc = parse_iso_datetime(c.get("candle_date_time_utc"))
        if ts_utc is None:
            continue
        ts_utc = ts_utc.replace(second=0, microsecond=0)
        close = float(c.get("trade_price") or 0.0)
        if start_utc <= ts_utc <= end_utc and close > 0:
            points[ts_utc] = close

    return sorted(points.items(), key=lambda x: x[0])


def _fetch_existing_minutes(storage: StorageClient, symbol: str, start_utc: datetime, end_utc: datetime) -> set[datetime]:
    try:
        result = (
            storage._client.table("price_snapshots")
            .select("created_at")
            .eq("symbol", symbol)
            .gte("created_at", start_utc.isoformat())
            .lte("created_at", end_utc.isoformat())
            .execute()
        )
        rows = result.data or []
    except Exception:
        logger.exception("기존 스냅샷 조회 실패: %s", symbol)
        return set()

    existing: set[datetime] = set()
    for row in rows:
        ts = parse_iso_datetime(row.get("created_at"))
        if ts is None:
            continue
        existing.add(ts.replace(second=0, microsecond=0))
    return existing


def _insert_rows(storage: StorageClient, rows: list[dict], batch_size: int = 500) -> int:
    inserted = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        try:
            storage._client.table("price_snapshots").insert(chunk).execute()
            inserted += len(chunk)
        except Exception:
            logger.exception("price_snapshots 배치 삽입 실패: chunk=%d", len(chunk))
    return inserted


def run() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    config = load_config()
    storage = StorageClient(config.supabase)

    news_ids = [str(v).strip() for v in args.news_id if str(v).strip()]
    targets = storage.get_sentiment_insights_for_backfill(
        limit=args.limit,
        days=args.days,
        include_verified=True,
        news_ids=news_ids,
    )

    if not targets:
        logger.info("백필 대상 뉴스가 없습니다.")
        return 0

    logger.info("백필 대상 %d건 (news_id_filter=%d)", len(targets), len(news_ids))

    processed = 0
    skipped = 0
    inserted_total = 0

    for row in targets:
        news_id = str(row.get("news_id") or "")
        symbol = select_symbol(row.get("currencies") or [])
        if not news_id or not symbol:
            skipped += 1
            continue

        created_at = parse_iso_datetime(row.get("created_at"))
        if created_at is None:
            skipped += 1
            continue

        start_utc = created_at.replace(second=0, microsecond=0)
        end_utc = parse_iso_datetime(row.get("verification_window_end_at"))
        if end_utc is None:
            end_utc = parse_iso_datetime(row.get("evaluated_at"))
        if end_utc is None:
            horizon = int(row.get("verification_horizon_min") or config.sentiment.verification_horizon_minutes)
            end_utc = start_utc + timedelta(minutes=max(horizon, 1))
        end_utc = end_utc.replace(second=0, microsecond=0)

        if end_utc <= start_utc:
            skipped += 1
            continue

        points = _iter_ohlcv_close_points(
            symbol,
            start_utc,
            end_utc,
            sleep_sec=args.sleep_sec,
        )
        if not points:
            logger.info("스킵 %s | %s | 분봉 조회 결과 없음", news_id[:16], symbol)
            skipped += 1
            continue

        existing = _fetch_existing_minutes(storage, symbol, start_utc, end_utc)
        to_insert = [
            {
                "symbol": symbol,
                "price": price,
                "created_at": ts.isoformat(),
            }
            for ts, price in points
            if ts not in existing
        ]

        if args.dry_run:
            logger.info(
                "DRY %s | %s | 구간 %s~%s | 조회 %d점 | 신규 %d점",
                news_id[:16],
                symbol,
                start_utc.isoformat(),
                end_utc.isoformat(),
                len(points),
                len(to_insert),
            )
            processed += 1
            continue

        inserted = _insert_rows(storage, to_insert)
        inserted_total += inserted
        processed += 1

        logger.info(
            "완료 %s | %s | 구간 %s~%s | 조회 %d점 | 삽입 %d점",
            news_id[:16],
            symbol,
            start_utc.isoformat(),
            end_utc.isoformat(),
            len(points),
            inserted,
        )

    logger.info(
        "요약: 처리 %d건, 스킵 %d건, 삽입 스냅샷 %d건, 모드=%s",
        processed,
        skipped,
        inserted_total,
        "dry-run" if args.dry_run else "apply",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
