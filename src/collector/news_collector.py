from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from src.config import SentimentConfig

logger = logging.getLogger(__name__)


class NewsCollector:
    """CryptoPanic Developer API v2 뉴스 수집기."""

    def __init__(self, config: SentimentConfig) -> None:
        """
        뉴스 수집기를 초기화합니다.

        Args:
            config: 감성 분석 설정 (API 키, 대상 코인 등 포함)
        """
        self._api_key = config.cryptopanic_api_key
        self._currencies = config.target_currencies
        self._max_news = config.max_news_per_poll
        self._timeout = config.api_timeout_sec
        self._endpoint = "https://cryptopanic.com/api/developer/v2/posts/"

    def fetch_latest_news(self, seen_ids: set[str]) -> list[dict[str, Any]]:
        """
        최신 뉴스를 수집합니다.

        Args:
            seen_ids: 이미 처리된 뉴스 ID 집합 (중복 방지용)

        Returns:
            수집된 뉴스 목록 (최대 max_news_per_poll 개)
        """
        if not self._api_key:
            logger.warning("CryptoPanic API 키가 설정되지 않았습니다.")
            return []

        params = {
            "auth_token": self._api_key,
            "currencies": self._currencies,
            "regions": "ko",
        }

        try:
            time.sleep(0.5)  # Rate limiting 방어
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(self._endpoint, params=params)
                response.raise_for_status()
                data = response.json()

            results = data.get("results", [])
            news_list: list[dict[str, Any]] = []

            for result in results:
                title = result.get("title", "")
                created_at = result.get("created_at", result.get("published_at", ""))

                # v2 API는 id 필드를 제공하지 않음 → title+created_at 해시로 고유 ID 생성
                raw_id = f"{title}:{created_at}"
                news_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]

                if not title or news_id in seen_ids:
                    continue

                # v2 API는 source/url/currencies 필드를 제공하지 않음
                # currencies는 요청 파라미터에서 가져옴
                news_item = {
                    "news_id": news_id,
                    "title": title,
                    "source": "CryptoPanic",
                    "url": "",
                    "currencies": [c.strip() for c in self._currencies.split(",") if c.strip()],
                    "created_at": created_at,
                }
                news_list.append(news_item)

                if len(news_list) >= self._max_news:
                    break

            time.sleep(0.5)  # Rate limiting 방어
            return news_list

        except Exception as e:
            logger.warning("뉴스 수집 실패: %s", e)
            return []
