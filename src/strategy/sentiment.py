from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from src.config import SentimentConfig

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Groq API 기반 뉴스 감성 분석기 (OpenAI 호환 엔드포인트)."""

    _ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, config: SentimentConfig) -> None:
        """
        감성 분석기를 초기화합니다.

        Args:
            config: 감성 분석 설정 (API 키, 모델명 등 포함)
        """
        self._api_key = config.groq_api_key
        self._model = config.groq_model
        self._timeout = config.api_timeout_sec

    def analyze(self, title: str, source: str, currencies: list[str]) -> dict[str, Any]:
        """
        뉴스의 감성을 분석합니다.

        Args:
            title: 뉴스 제목
            source: 뉴스 출처
            currencies: 관련 코인 목록

        Returns:
            분석 결과 딕셔너리
        """
        default_result = {
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
            "decision": "WAIT",
            "confidence": 0.0,
            "reasoning_chain": "분석 실패",
            "keywords": [],
            "positive_factors": [],
            "negative_factors": [],
        }

        if not self._api_key:
            logger.warning("Groq API 키가 설정되지 않았습니다.")
            return default_result

        system_prompt = """당신은 암호화폐 시장 전문 감성 분석가입니다.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.

응답 JSON:
{
  "sentiment_score": (float, -1.0~1.0, 음수=약세, 양수=강세),
  "sentiment_label": ("bullish" 또는 "bearish" 또는 "neutral"),
  "decision": ("BUY" 또는 "SELL" 또는 "HOLD" 또는 "WAIT"),
  "confidence": (float, 0~100),
  "reasoning_chain": "(단계별 추론 과정을 한 문장씩 → 로 연결)",
  "keywords": ["키워드1", "키워드2", ...],
  "positive_factors": ["긍정요인1", ...],
  "negative_factors": ["부정요인1", ...]
}"""

        user_prompt = f"뉴스 제목: {title}\n출처: {source}\n관련 코인: {', '.join(currencies)}"

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_completion_tokens": 1024,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(self._ENDPOINT, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            choices = data.get("choices", [])
            if not choices:
                logger.warning("Groq 응답에 choices가 없습니다.")
                return default_result

            text = choices[0].get("message", {}).get("content", "")

            # ```json 마커 제거
            text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

            result = json.loads(text)
            return result

        except Exception as e:
            logger.warning("감성 분석 실패: %s", e)
            return default_result
