from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from src.config import SentimentConfig

logger = logging.getLogger(__name__)


class NewsCollector:
    """CryptoPanic API v1 뉴스 수집기."""

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
        self._endpoint = "https://cryptopanic.com/api/v1/posts/"

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
            "kind": "news",
            "regions": "ko,en",
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
                news_id = str(result.get("id", ""))
                if not news_id or news_id in seen_ids:
                    continue

                source_data = result.get("source", {})
                source_title = source_data.get("title", "Unknown") if isinstance(source_data, dict) else "Unknown"
                
                currencies_data = result.get("currencies", [])
                currencies = [c.get("code", "") for c in currencies_data if isinstance(c, dict) and "code" in c]

                news_item = {
                    "news_id": news_id,
                    "title": result.get("title", ""),
                    "source": source_title,
                    "url": result.get("url", ""),
                    "currencies": currencies,
                    "created_at": result.get("created_at", ""),
                }
                news_list.append(news_item)

                if len(news_list) >= self._max_news:
                    break

            time.sleep(0.5)  # Rate limiting 방어
            return news_list

        except Exception as e:
            logger.warning("뉴스 수집 실패: %s", e)
            return []
