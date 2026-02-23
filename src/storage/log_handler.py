"""
커스텀 logging.Handler — src.* 로그를 Supabase system_logs 테이블로 전송합니다.
기존 logger.info/warning/error 호출만으로 프론트엔드 Drawer에 실시간 반영됩니다.

안정성 개선:
- 큐 기반 비동기 버퍼링 (메인 루프 블로킹 방지)
- 연속 실패 시 자동 비활성화 (네트워크 장애 시 CPU/메모리 낭비 방지)
- 주기적 재활성화 시도 (네트워크 복구 후 자동 재개)
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
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

# 연속 실패 N회 초과 시 핸들러 비활성화
_MAX_CONSECUTIVE_FAILURES = 10
# 비활성화 후 재시도까지 무시할 레코드 수
_RETRY_AFTER_RECORDS = 300  # 약 5분 (10초 루프 × 3~5 로그/틱)


class _SrcOnlyFilter(logging.Filter):
    """src.* 네임스페이스만 통과시키되, storage 자체 로그는 제외 (재귀 방지)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("src.") and not record.name.startswith(
            "src.storage"
        )


class SupabaseLogHandler(logging.Handler):
    """src.* 로거의 INFO+ 레코드를 Supabase system_logs 테이블에 INSERT 합니다.

    안정성 개선:
    - 백그라운드 스레드에서 큐 기반으로 DB INSERT 실행 (메인 루프 비블로킹)
    - 연속 실패 시 자동 비활성화 → 주기적 재시도
    - 로그 저장 실패가 봇 전체를 중단시키지 않음
    """

    def __init__(self, supabase_client: "Client", level: int = logging.INFO) -> None:
        super().__init__(level)
        self._client = supabase_client
        self.addFilter(_SrcOnlyFilter())
        # 비동기 큐 (최대 500건 버퍼, 초과 시 오래된 로그 버림)
        self._queue: queue.Queue = queue.Queue(maxsize=500)
        self._consecutive_failures = 0
        self._disabled = False
        self._skip_counter = 0
        # 백그라운드 워커 스레드
        self._worker = threading.Thread(target=self._process_queue, daemon=True)
        self._worker.start()

    def emit(self, record: logging.LogRecord) -> None:
        # 비활성화 상태면 주기적으로 재시도
        if self._disabled:
            self._skip_counter += 1
            if self._skip_counter < _RETRY_AFTER_RECORDS:
                return
            # 재시도 시점 도달
            self._skip_counter = 0
            self._disabled = False
            self._consecutive_failures = 0

        try:
            level = _LEVEL_MAP.get(record.levelno, "INFO")
            message = self.format(record)
            row = {
                "level": level,
                "message": message,
                "created_at": datetime.utcnow().isoformat(),
            }
            # 큐가 가득 차면 가장 오래된 항목을 버림 (블로킹 방지)
            try:
                self._queue.put_nowait(row)
            except queue.Full:
                try:
                    self._queue.get_nowait()  # 오래된 항목 버림
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(row)
                except queue.Full:
                    pass
        except Exception:
            pass  # emit에서는 절대 예외를 전파하지 않음

    def _process_queue(self) -> None:
        """백그라운드 스레드: 큐에서 로그를 꺼내 DB에 저장합니다."""
        while True:
            try:
                row = self._queue.get(timeout=5.0)
            except queue.Empty:
                continue

            try:
                self._client.table("system_logs").insert(row).execute()
                self._consecutive_failures = 0
            except Exception as exc:
                self._consecutive_failures += 1
                if self._consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    self._disabled = True
                    print(
                        f"[SupabaseLogHandler] 연속 {_MAX_CONSECUTIVE_FAILURES}회 실패 — "
                        f"약 {_RETRY_AFTER_RECORDS}건 후 재시도합니다. 마지막 오류: {exc!r}",
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
