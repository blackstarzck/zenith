"""
Zenith — 암호화폐 AI 자동 매매 시스템.
변동성 조절형 평균 회귀 전략 기반 트레이딩 봇.
"""

import logging
import sys
from pathlib import Path

from supabase import create_client

from src.config import load_config
from src.orchestrator import Orchestrator
from src.storage.log_handler import SupabaseLogHandler


def setup_logging() -> None:
    """로깅을 설정합니다."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 루트 로거
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 콘솔 핸들러
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(console)

    # 파일 핸들러
    file_handler = logging.FileHandler(
        log_dir / "zenith.log",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(file_handler)

    # 에러 전용 파일 핸들러
    error_handler = logging.FileHandler(
        log_dir / "error.log",
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(error_handler)

    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def attach_supabase_handler(supabase_url: str, supabase_key: str) -> bool:
    """Supabase 로그 핸들러를 루트 로거에 추가하고 연결을 검증합니다."""
    client = create_client(supabase_url, supabase_key)
    handler = SupabaseLogHandler(client, level=logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    return handler.verify_connection()


def main() -> None:
    """봇 진입점."""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Zenith Trading Bot v1.0")
    logger.info("전략: 변동성 조절형 평균 회귀 (Adaptive Mean Reversion)")
    logger.info("=" * 60)

    try:
        config = load_config()

        # 필수 키 검증
        if not config.upbit.access_key or not config.upbit.secret_key:
            logger.critical("UPBIT API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
            sys.exit(1)

        if not config.supabase.url or not config.supabase.secret_key:
            logger.critical("SUPABASE 설정이 없습니다. .env 파일을 확인하세요.")
            sys.exit(1)

        # Supabase 로그 핸들러 등록 — 이후 src.* 로그가 자동으로 DB에 기록됨
        if attach_supabase_handler(config.supabase.url, config.supabase.secret_key):
            logger.info("Supabase 실시간 로그 핸들러 등록 및 검증 완료")
        else:
            logger.warning(
                "Supabase 로그 핸들러 등록됨, 검증 INSERT 실패 — "
                "system_logs 테이블 또는 RLS 정책을 확인하세요"
            )

        bot = Orchestrator(config)
        bot.run()

    except KeyboardInterrupt:
        logger.info("사용자에 의해 종료됨")
    except Exception:
        logger.critical("치명적 오류 발생", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
