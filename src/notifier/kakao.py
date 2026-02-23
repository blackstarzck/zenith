"""
카카오톡 알림 모듈.
수익/손실 발생, 에러 발생 시 카카오톡으로 알림을 전송합니다.
프론트엔드에서 OAuth 인증 후 Supabase에 저장된 토큰을 사용합니다.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

import httpx

from src.config import KakaoConfig

if TYPE_CHECKING:
    from src.storage.client import StorageClient

logger = logging.getLogger(__name__)

# 카카오 API 엔드포인트
KAKAO_MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"

# HTTP 타임아웃 (초)
_HTTP_TIMEOUT = 10.0


class KakaoNotifier:
    """카카오톡 '나에게 보내기' 알림 발송기.

    변경 사항 (안정성 개선):
    - async → sync 전환 (asyncio.run() 반복 호출로 인한 이벤트 루프 누수 방지)
    - Persistent httpx.Client 사용 (매 호출마다 새 클라이언트 생성 방지)
    - 토큰 갱신 후 재시도 1회 제한 (무한 재귀 방지)
    """

    def __init__(
        self,
        config: KakaoConfig,
        storage: StorageClient | None = None,
    ) -> None:
        self._config = config
        self._storage = storage
        # .env 토큰을 폴백으로 유지, Supabase 토큰 우선
        self._access_token = config.access_token
        self._refresh_token = config.refresh_token
        self._tokens_loaded = False
        self._api_status: str = "unknown"  # connected | token_expired | send_failed | no_token
        # Persistent HTTP 클라이언트 (소켓 재사용, 리소스 누수 방지)
        self._client = httpx.Client(timeout=_HTTP_TIMEOUT)

    def close(self) -> None:
        """HTTP 클라이언트를 정리합니다."""
        self._client.close()

    @property
    def api_status(self) -> str:
        """최근 카카오 API 호출 결과 기반 상태를 반환합니다."""
        return self._api_status

    def _ensure_tokens(self) -> None:
        """Supabase에서 최신 토큰을 로드합니다 (1회)."""
        if self._tokens_loaded or self._storage is None:
            return

        tokens = self._storage.get_kakao_tokens()
        if tokens:
            self._access_token = tokens.get("access_token", "") or self._access_token
            self._refresh_token = tokens.get("refresh_token", "") or self._refresh_token
            logger.info("Supabase에서 카카오 토큰 로드 완료")

        self._tokens_loaded = True

    # ── 메시지 전송 ──────────────────────────────────────────

    def send_text(self, message: str, *, _retry: bool = True) -> bool:
        """텍스트 메시지를 나에게 보냅니다.

        Args:
            message: 전송할 메시지 본문
            _retry: 토큰 만료 시 갱신 후 재시도 허용 여부 (재귀 방지, 내부 전용)

        Returns:
            성공 여부
        """
        self._ensure_tokens()

        if not self._access_token:
            logger.warning("카카오 Access Token이 설정되지 않아 알림을 건너뜁니다.")
            self._api_status = "no_token"
            return False

        template = {
            "object_type": "text",
            "text": message,
            "link": {
                "web_url": "https://zenith.local",
                "mobile_url": "https://zenith.local",
            },
            "button_title": "대시보드 확인",
        }

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"template_object": json.dumps(template)}

        try:
            resp = self._client.post(KAKAO_MEMO_URL, headers=headers, data=data)

            if resp.status_code == 401 and _retry:
                # 토큰 만료 → 갱신 후 1회만 재시도 (_retry=False로 무한 재귀 방지)
                self._api_status = "token_expired"
                if self._refresh_access_token():
                    return self.send_text(message, _retry=False)
                return False

            if resp.status_code == 200:
                logger.info("카카오톡 알림 전송 성공")
                self._api_status = "connected"
                return True

            logger.warning("카카오톡 알림 실패: %d %s", resp.status_code, resp.text)
            self._api_status = "send_failed"
            return False

        except Exception:
            logger.exception("카카오톡 알림 전송 중 오류")
            self._api_status = "send_failed"
            return False

    # ── 수익/손실 알림 템플릿 ──────────────────────────────

    def notify_pnl(
        self,
        symbol: str,
        price: float,
        pnl: float,
        pnl_pct: float,
        reason: str,
    ) -> bool:
        """수익/손실 발생 알림을 전송합니다."""
        emoji = "💰" if pnl >= 0 else "📉"
        label = "수익 실현" if pnl >= 0 else "손실 발생"
        msg = (
            f"{emoji} [{label}]\n"
            f"종목: {symbol}\n"
            f"매도가: {price:,.2f} KRW\n"
            f"수익률: {pnl_pct:+.2f}%\n"
            f"손익: {pnl:+,.0f} KRW\n"
            f"사유: {reason}"
        )
        return self.send_text(msg)

    def notify_error(self, error_msg: str) -> bool:
        """에러 알림을 전송합니다."""
        msg = f"🚨 [시스템 에러]\n{error_msg}"
        return self.send_text(msg)

    def notify_daily_report(
        self,
        total_balance: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        trade_count: int,
    ) -> bool:
        """일일 리포트를 전송합니다."""
        emoji = "📊"
        msg = (
            f"{emoji} [일일 리포트]\n"
            f"총 자산: {total_balance:,.0f} KRW\n"
            f"당일 손익: {daily_pnl:+,.0f} KRW ({daily_pnl_pct:+.2f}%)\n"
            f"거래 횟수: {trade_count}건"
        )
        return self.send_text(msg)

    def notify_daily_stop(self, loss_amount: float) -> bool:
        """일일 손실 한도 초과 알림을 전송합니다."""
        msg = (
            f"🛑 [매매 중단]\n"
            f"일일 손실 한도 초과\n"
            f"누적 손실: {loss_amount:+,.0f} KRW\n"
            f"금일 자동 매매가 중단되었습니다."
        )
        return self.send_text(msg)

    # ── 토큰 갱신 ────────────────────────────────────────────

    def _refresh_access_token(self) -> bool:
        """카카오 Access Token을 갱신합니다."""
        if not self._refresh_token or not self._config.rest_api_key:
            logger.error("토큰 갱신 불가: refresh_token 또는 REST API 키 없음")
            return False

        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": self._config.rest_api_key,
            "refresh_token": self._refresh_token,
        }
        if self._config.client_secret:
            data["client_secret"] = self._config.client_secret

        try:
            resp = self._client.post(KAKAO_TOKEN_URL, data=data)

            if resp.status_code != 200:
                logger.error("토큰 갱신 실패: %d %s", resp.status_code, resp.text)
                return False

            result = resp.json()
            self._access_token = result["access_token"]
            # refresh_token도 갱신되었을 수 있음
            if "refresh_token" in result:
                self._refresh_token = result["refresh_token"]

            # 갱신된 토큰을 Supabase에 저장
            if self._storage is not None:
                self._storage.upsert_kakao_tokens(
                    self._access_token, self._refresh_token,
                )

            logger.info("카카오 Access Token 갱신 완료")
            return True

        except Exception:
            logger.exception("토큰 갱신 중 오류")
            return False
