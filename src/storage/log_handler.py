"""
커스텀 logging.Handler — src.* 로그를 Supabase system_logs 테이블로 전송합니다.
기존 logger.info/warning/error 호출만으로 프론트엔드 Drawer에 실시간 반영됩니다.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

# Python 로깅 레벨 → system_logs.level 매핑
_LEVEL_MAP: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


class _SrcOnlyFilter(logging.Filter):
    """src.* 네임스페이스만 통과시키되, storage 자체 로그는 제외 (재귀 방지)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("src.") and not record.name.startswith(
            "src.storage"
        )


class SupabaseLogHandler(logging.Handler):
    """src.* 로거의 INFO+ 레코드를 Supabase system_logs 테이블에 INSERT 합니다.

    - 로그 저장 실패가 봇 전체를 중단시키지 않도록 emit 내부에서 예외를 삼킵니다.
    - src.storage 네임스페이스는 필터링하여 무한 재귀를 방지합니다.
    """

    def __init__(self, supabase_client: Client, level: int = logging.INFO) -> None:
        super().__init__(level)
        self._client = supabase_client
        self.addFilter(_SrcOnlyFilter())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _LEVEL_MAP.get(record.levelno, "INFO")
            message = self.format(record)
            row = {
                "level": level,
                "message": message,
                "created_at": datetime.utcnow().isoformat(),
            }
            self._client.table("system_logs").insert(row).execute()
        except Exception as exc:
            # 로그 저장 실패가 시스템을 중단시키면 안 되지만, 완전히 삼키면 디버깅 불가
            print(
                f"[SupabaseLogHandler] emit 실패: {exc!r} | msg={record.getMessage()!r}",
                file=sys.stderr,
            )

    def verify_connection(self) -> bool:
        """핸들러 등록 직후 연결 검증용 — 테스트 INSERT 1건."""
        try:
            row = {
                "level": "INFO",
                "message": "[SupabaseLogHandler] 연결 검증 성공 — 실시간 로그 전송 활성화",
                "created_at": datetime.utcnow().isoformat(),
            }
            self._client.table("system_logs").insert(row).execute()
            return True
        except Exception as exc:
            print(
                f"[SupabaseLogHandler] 연결 검증 실패: {exc!r}",
                file=sys.stderr,
            )
            return False
