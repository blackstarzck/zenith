from __future__ import annotations

import hashlib
import logging
import re
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
        self._target_currencies = [c.strip().upper() for c in self._currencies.split(",") if c.strip()]
        self._target_currency_set = set(self._target_currencies)
        self._max_news = config.max_news_per_poll
        self._timeout = config.api_timeout_sec
        self._endpoint = "https://cryptopanic.com/api/developer/v2/posts/"
        self._alias_map: dict[str, str] = {
            "비트코인": "BTC",
            "이더리움": "ETH",
            "리플": "XRP",
            "솔라나": "SOL",
            "도지코인": "DOGE",
            "에이다": "ADA",
            "카르다노": "ADA",
            "BITCOIN": "BTC",
            "ETHEREUM": "ETH",
            "RIPPLE": "XRP",
            "SOLANA": "SOL",
            "DOGECOIN": "DOGE",
            "CARDANO": "ADA",
        }
        self._market_symbol_pattern = re.compile(r"\b(?:KRW|BTC|USDT)-([A-Z0-9]{2,12})\b")
        self._ticker_pattern = re.compile(r"\b([A-Z]{2,12})\b")

    def _dedupe_keep_order(self, items: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    def _extract_currencies_from_result(self, result: dict[str, Any]) -> list[str]:
        raw = result.get("currencies")
        if not raw:
            return []

        extracted: list[str] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    extracted.append(item.upper().replace("KRW-", "").strip())
                elif isinstance(item, dict):
                    code = (
                        item.get("code")
                        or item.get("currency")
                        or item.get("symbol")
                        or item.get("ticker")
                    )
                    if isinstance(code, str) and code.strip():
                        extracted.append(code.upper().replace("KRW-", "").strip())
        elif isinstance(raw, str):
            extracted.extend([c.strip().upper().replace("KRW-", "") for c in raw.split(",") if c.strip()])

        return [c for c in self._dedupe_keep_order(extracted) if c in self._target_currency_set]

    def _extract_currencies_from_title(self, title: str) -> list[str]:
        upper_title = title.upper()
        matches: list[tuple[int, str]] = []

        # KRW-BTC 같은 마켓 표기 우선 추출
        for match in self._market_symbol_pattern.finditer(upper_title):
            symbol = match.group(1)
            if symbol in self._target_currency_set:
                matches.append((match.start(), symbol))

        # BTC/ETH 같은 티커 토큰 추출
        for match in self._ticker_pattern.finditer(upper_title):
            token = match.group(1)
            if token in self._target_currency_set:
                matches.append((match.start(), token))

        # 한글/영문 풀네임 별칭 매핑
        for alias, symbol in self._alias_map.items():
            idx = title.find(alias)
            if idx < 0:
                idx = upper_title.find(alias)
            if idx >= 0 and symbol in self._target_currency_set:
                matches.append((idx, symbol))

        matches.sort(key=lambda x: x[0])
        ordered = [symbol for _, symbol in matches]
        return self._dedupe_keep_order(ordered)

    def infer_currencies(self, *, title: str, result: dict[str, Any] | None = None) -> list[str]:
        """뉴스 단위 코인 목록을 추론합니다.

        우선순위:
        1) API 응답의 currencies 필드
        2) 제목 기반 심볼/티커/별칭 추출
        """
        extracted: list[str] = []
        if result is not None:
            extracted = self._extract_currencies_from_result(result)
        if not extracted:
            extracted = self._extract_currencies_from_title(title)
        return extracted

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

                extracted = self.infer_currencies(title=title, result=result)

                news_item = {
                    "news_id": news_id,
                    "title": title,
                    "source": "CryptoPanic",
                    "url": "",
                    "currencies": extracted,
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
