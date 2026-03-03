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
    """Groq API 기반 뉴스 감성 분석기(OpenAI 호환 엔드포인트)."""

    _ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, config: SentimentConfig) -> None:
        """감성 분석기를 초기화합니다."""
        self._api_key = config.groq_api_key
        self._model = config.groq_model
        self._timeout = config.api_timeout_sec
        self._min_conf_for_direction = config.directional_decision_min_confidence
        self._min_abs_score_for_direction = config.directional_decision_min_abs_score
        self._horizon_short_min = max(1, int(config.verification_horizon_short_minutes))
        self._horizon_long_min = max(1, int(config.verification_horizon_long_minutes))
        self._horizon_conf_threshold = float(config.horizon_ab_confidence_threshold)

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _select_horizon_min(self, *, decision: str, confidence: float) -> int:
        """신뢰도 기반 A/B 검증 구간을 선택합니다."""
        if decision in {"BUY", "SELL"} and confidence >= self._horizon_conf_threshold:
            return self._horizon_short_min
        return self._horizon_long_min

    def _normalize_result(
        self, raw: dict[str, Any], *, no_symbol: bool = False
    ) -> dict[str, Any]:
        """모델 응답을 보정하고 방향성 게이트를 적용합니다."""
        score = float(raw.get("sentiment_score") or 0.0)
        score = self._clamp(score, -1.0, 1.0)
        confidence = float(raw.get("confidence") or 0.0)
        confidence = self._clamp(confidence, 0.0, 100.0)

        decision = str(raw.get("decision") or "WAIT").upper()
        if decision not in {"BUY", "SELL", "HOLD", "WAIT"}:
            decision = "WAIT"

        sentiment_label = str(raw.get("sentiment_label") or "neutral").lower()
        if sentiment_label not in {"bullish", "bearish", "neutral"}:
            sentiment_label = "neutral"

        reasoning_chain = str(raw.get("reasoning_chain") or "분석 근거 없음")
        pending_reason = raw.get("pending_reason")

        if no_symbol:
            decision = "WAIT"
            confidence = 0.0
            sentiment_label = "neutral"
            score = 0.0
            pending_reason = "코인 식별 실패"
            reasoning_chain = "코인 식별 실패로 방향성 판단을 건너뜀"

        if decision in {"BUY", "SELL"}:
            if (
                confidence < self._min_conf_for_direction
                or abs(score) < self._min_abs_score_for_direction
            ):
                pending_reason = (
                    f"방향성 게이트 미통과(conf={confidence:.1f}, score={score:+.2f})"
                )
                decision = "WAIT"

        return {
            "sentiment_score": round(score, 6),
            "sentiment_label": sentiment_label,
            "decision": decision,
            "confidence": round(confidence, 2),
            "reasoning_chain": reasoning_chain,
            "keywords": raw.get("keywords", []),
            "positive_factors": raw.get("positive_factors", []),
            "negative_factors": raw.get("negative_factors", []),
            "verification_horizon_min": self._select_horizon_min(
                decision=decision,
                confidence=confidence,
            ),
            "pending_reason": pending_reason,
        }

    def analyze(self, title: str, source: str, currencies: list[str]) -> dict[str, Any]:
        """뉴스를 감성 분석합니다."""
        default_result = {
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
            "decision": "WAIT",
            "confidence": 0.0,
            "reasoning_chain": "분석 실패",
            "keywords": [],
            "positive_factors": [],
            "negative_factors": [],
            "verification_horizon_min": self._horizon_long_min,
            "pending_reason": "분석 실패",
        }

        if not self._api_key:
            logger.warning("Groq API 키가 설정되지 않았습니다.")
            return default_result

        if not currencies:
            logger.info("[감성 분석] 코인 식별 실패로 WAIT 처리")
            return self._normalize_result(default_result, no_symbol=True)

        system_prompt = """당신은 암호화폐 시장 전문 감성 분석가입니다.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.

응답 JSON:
{
  "sentiment_score": (float, -1.0~1.0, 음수=약세, 양수=강세),
  "sentiment_label": ("bullish" 또는 "bearish" 또는 "neutral"),
  "decision": ("BUY" 또는 "SELL" 또는 "HOLD" 또는 "WAIT"),
  "confidence": (float, 0~100),
  "reasoning_chain": "(단계별 추론 과정의 짧은 문장 연결)",
  "keywords": ["키워드1", "키워드2", ...],
  "positive_factors": ["긍정요인1", ...],
  "negative_factors": ["부정요인1", ...]
}"""

        user_prompt = (
            f"뉴스 제목: {title}\n출처: {source}\n관련 코인: {', '.join(currencies)}"
        )

        base_payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        payload_variants: list[dict[str, Any]] = [
            {
                **base_payload,
                "max_completion_tokens": 1024,
                "response_format": {"type": "json_object"},
            },
            {
                **base_payload,
                "max_tokens": 1024,
                "response_format": {"type": "json_object"},
            },
            {
                **base_payload,
                "max_tokens": 1024,
            },
            {
                **base_payload,
                "max_completion_tokens": 1024,
            },
        ]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for idx, payload in enumerate(payload_variants):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(
                        self._ENDPOINT, json=payload, headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()

                choices = data.get("choices", [])
                if not choices:
                    logger.warning("Groq 응답에 choices가 없습니다.")
                    return default_result

                text = choices[0].get("message", {}).get("content", "")
                text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\s*```$", "", text)
                text = text.strip()

                result = json.loads(text)
                if idx > 0:
                    logger.info(
                        "감성 분석 요청 호환 모드로 복구 완료(variant=%d)", idx + 1
                    )
                return self._normalize_result(result)

            except Exception as e:
                last_error = e
                continue

        logger.warning("감성 분석 실패: %s", last_error)
        return default_result
