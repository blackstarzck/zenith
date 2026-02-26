"""
Zenith 런칭 전 프리플라이트 체크.

모든 외부 서비스 연결과 필수 설정을 검증합니다.
사용법: python scripts/preflight_check.py
"""

import asyncio
import io
import os
import sys

# Windows cp949 인코딩 문제 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(".env.backend")


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {Colors.GREEN}[PASS]{Colors.RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {Colors.RED}[FAIL]{Colors.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {Colors.YELLOW}[WARN]{Colors.RESET} {msg}")


def header(title: str) -> None:
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}{Colors.RESET}")


def main() -> None:
    results: dict[str, bool] = {}

    print(f"\n{Colors.BOLD}Zenith Preflight Check v1.0{Colors.RESET}")
    print(f"{'─' * 40}")

    # ── 1. 환경 변수 검증 ────────────────────────────────────
    header("1. 환경 변수 (.env)")

    env_checks = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
        "SUPABASE_SECRET_KEY": os.getenv("SUPABASE_SECRET_KEY", ""),
        "UPBIT_ACCESS_KEY": os.getenv("UPBIT_ACCESS_KEY", ""),
        "UPBIT_SECRET_KEY": os.getenv("UPBIT_SECRET_KEY", ""),
        "KAKAO_REST_API_KEY": os.getenv("KAKAO_REST_API_KEY", ""),
        "KAKAO_ACCESS_TOKEN": os.getenv("KAKAO_ACCESS_TOKEN", ""),
        "KAKAO_REFRESH_TOKEN": os.getenv("KAKAO_REFRESH_TOKEN", ""),
    }

    required = ["SUPABASE_URL", "SUPABASE_SECRET_KEY", "UPBIT_ACCESS_KEY", "UPBIT_SECRET_KEY"]
    optional = ["KAKAO_REST_API_KEY", "KAKAO_ACCESS_TOKEN", "KAKAO_REFRESH_TOKEN"]

    env_ok = True
    for key in required:
        if env_checks[key]:
            ok(f"{key} = {env_checks[key][:12]}...")
        else:
            fail(f"{key} 미설정 (필수)")
            env_ok = False

    for key in optional:
        if env_checks[key]:
            ok(f"{key} = {env_checks[key][:12]}...")
        else:
            warn(f"{key} 미설정 (카카오톡 알림 비활성화)")

    results["env"] = env_ok

    # ── 2. Supabase 연결 ─────────────────────────────────────
    header("2. Supabase 연결")

    if not env_checks["SUPABASE_URL"] or not env_checks["SUPABASE_SECRET_KEY"]:
        fail("Supabase 키 미설정 - 테스트 건너뜀")
        results["supabase"] = False
    else:
        try:
            from supabase import create_client

            client = create_client(env_checks["SUPABASE_URL"], env_checks["SUPABASE_SECRET_KEY"])

            # trades 테이블 존재 여부 확인
            resp = client.table("trades").select("id").limit(1).execute()
            ok("trades 테이블 접근 가능")

            resp = client.table("daily_stats").select("stats_date").limit(1).execute()
            ok("daily_stats 테이블 접근 가능")

            resp = client.table("system_logs").select("id").limit(1).execute()
            ok("system_logs 테이블 접근 가능")

            # 쓰기 테스트 (system_logs에 테스트 로그 작성 후 삭제)
            from datetime import datetime

            test_row = {
                "level": "INFO",
                "message": "[PREFLIGHT] Connection test",
                "created_at": datetime.utcnow().isoformat(),
            }
            insert_resp = client.table("system_logs").insert(test_row).execute()
            if insert_resp.data:
                test_id = insert_resp.data[0]["id"]
                client.table("system_logs").delete().eq("id", test_id).execute()
                ok("Supabase 읽기/쓰기 정상")
            else:
                fail("Supabase 쓰기 실패")

            results["supabase"] = True
        except Exception as e:
            error_msg = str(e)
            if "relation" in error_msg and "does not exist" in error_msg:
                fail(f"테이블이 존재하지 않습니다. supabase_migration.sql을 실행하세요.")
                fail(f"  상세: {error_msg[:100]}")
            else:
                fail(f"Supabase 연결 실패: {error_msg[:100]}")
            results["supabase"] = False

    # ── 3. Upbit API 연결 ────────────────────────────────────
    header("3. Upbit API 연결")

    if not env_checks["UPBIT_ACCESS_KEY"] or not env_checks["UPBIT_SECRET_KEY"]:
        fail("Upbit API 키 미설정 - 테스트 건너뜀")
        results["upbit"] = False
    else:
        try:
            import pyupbit

            upbit = pyupbit.Upbit(env_checks["UPBIT_ACCESS_KEY"], env_checks["UPBIT_SECRET_KEY"])

            # 잔고 조회 (조회 권한 테스트)
            balances = upbit.get_balances()
            if isinstance(balances, list):
                krw_balance = 0.0
                for b in balances:
                    if b.get("currency") == "KRW":
                        krw_balance = float(b.get("balance", 0))
                        break
                ok(f"Upbit 잔고 조회 성공 - KRW: {krw_balance:,.0f}원")
            else:
                fail(f"Upbit 잔고 조회 실패: {balances}")
                results["upbit"] = False
                raise Exception("balance check failed")

            # 시세 조회 (공개 API)
            price = pyupbit.get_current_price("KRW-BTC")
            if price and price > 0:
                ok(f"BTC 현재가 조회 성공 - {price:,.0f} KRW")
            else:
                warn("BTC 시세 조회 실패 (네트워크 확인)")

            # OHLCV 조회
            df = pyupbit.get_ohlcv("KRW-BTC", interval="minute15", count=5)
            if df is not None and len(df) > 0:
                ok(f"OHLCV 캔들 조회 성공 - {len(df)}개 캔들")
            else:
                warn("OHLCV 조회 실패")

            results["upbit"] = True

        except Exception as e:
            if "balance check failed" not in str(e):
                error_msg = str(e)
                if "401" in error_msg or "Unauthorized" in error_msg:
                    fail("Upbit API 키 인증 실패 - 키를 확인하세요")
                elif "no_authorization_ip" in error_msg:
                    fail("IP 허용 목록에 현재 IP가 등록되지 않았습니다")
                    fail("  Upbit 마이페이지 > Open API 관리에서 IP를 추가하세요")
                else:
                    fail(f"Upbit 연결 실패: {error_msg[:100]}")
                results["upbit"] = False

    # ── 4. KakaoTalk 연결 ────────────────────────────────────
    header("4. KakaoTalk 알림")

    if not env_checks["KAKAO_ACCESS_TOKEN"]:
        warn("KAKAO_ACCESS_TOKEN 미설정")
        warn("  카카오톡 알림 없이도 봇은 정상 동작합니다")
        warn("  설정하려면: python scripts/kakao_auth.py")
        results["kakao"] = None  # type: ignore[assignment]  # optional
    else:
        try:
            import httpx

            resp = httpx.get(
                "https://kapi.kakao.com/v2/user/me",
                headers={"Authorization": f"Bearer {env_checks['KAKAO_ACCESS_TOKEN']}"},
                timeout=10,
            )
            if resp.status_code == 200:
                user_info = resp.json()
                nickname = (
                    user_info.get("kakao_account", {})
                    .get("profile", {})
                    .get("nickname", "알 수 없음")
                )
                ok(f"카카오 인증 유효 - 사용자: {nickname}")
                results["kakao"] = True
            elif resp.status_code == 401:
                warn("Access Token 만료 - Refresh Token으로 자동 갱신됩니다")
                if env_checks["KAKAO_REFRESH_TOKEN"]:
                    ok("Refresh Token 설정됨 - 봇 실행 시 자동 갱신")
                    results["kakao"] = True
                else:
                    fail("Refresh Token도 없음 - python scripts/kakao_auth.py 재실행 필요")
                    results["kakao"] = False
            else:
                fail(f"카카오 API 응답 오류: {resp.status_code}")
                results["kakao"] = False
        except Exception as e:
            fail(f"카카오 연결 실패: {e}")
            results["kakao"] = False

    # ── 5. Python 모듈 임포트 테스트 ─────────────────────────
    header("5. 핵심 모듈 임포트")

    modules = [
        ("src.config", "설정 모듈"),
        ("src.collector.data_collector", "데이터 수집기"),
        ("src.strategy.indicators", "기술 지표"),
        ("src.strategy.engine", "전략 엔진"),
        ("src.risk.manager", "리스크 관리자"),
        ("src.executor.order_executor", "주문 실행기"),
        ("src.storage.client", "Supabase 클라이언트"),
        ("src.notifier.kakao", "카카오 알림"),
        ("src.orchestrator", "오케스트레이터"),
        ("src.backtest.engine", "백테스트 엔진"),
        ("src.backtest.paper_trading", "페이퍼 트레이딩"),
    ]

    import_ok = True
    for module_path, name in modules:
        try:
            __import__(module_path)
            ok(f"{name} ({module_path})")
        except Exception as e:
            fail(f"{name} ({module_path}): {e}")
            import_ok = False

    results["imports"] = import_ok

    # ── 6. 설정 로드 테스트 ──────────────────────────────────
    header("6. AppConfig 로드")

    try:
        from src.config import load_config

        config = load_config()
        ok(f"전략: BB({config.strategy.bb_period}, {config.strategy.bb_std_dev}), "
           f"RSI({config.strategy.rsi_period}), ATR({config.strategy.atr_period})")
        ok(f"리스크: 포지션 {config.risk.max_position_ratio * 100:.0f}%, "
           f"동시 {config.risk.max_concurrent_positions}개, "
           f"일일 손절 {config.risk.daily_loss_limit_ratio * 100:.0f}%")
        ok(f"루프 간격: {config.loop_interval_sec}초, "
           f"캔들: {config.candle_interval} x {config.candle_count}")
        results["config"] = True
    except Exception as e:
        fail(f"설정 로드 실패: {e}")
        results["config"] = False

    # ── 결과 요약 ────────────────────────────────────────────
    header("RESULT SUMMARY")

    total_pass = 0
    total_fail = 0
    total_warn = 0

    labels = {
        "env": "환경 변수",
        "supabase": "Supabase DB",
        "upbit": "Upbit API",
        "kakao": "KakaoTalk",
        "imports": "모듈 임포트",
        "config": "AppConfig",
    }

    for key, label in labels.items():
        val = results.get(key)
        if val is True:
            ok(label)
            total_pass += 1
        elif val is False:
            fail(label)
            total_fail += 1
        elif val is None:
            warn(f"{label} (선택 사항 - 미설정)")
            total_warn += 1

    print(f"\n{'─' * 40}")
    summary_parts = [f"{Colors.GREEN}{total_pass} PASS{Colors.RESET}"]
    if total_fail:
        summary_parts.append(f"{Colors.RED}{total_fail} FAIL{Colors.RESET}")
    if total_warn:
        summary_parts.append(f"{Colors.YELLOW}{total_warn} WARN{Colors.RESET}")
    print(f"  {' / '.join(summary_parts)}")

    if total_fail == 0:
        print(f"\n  {Colors.GREEN}{Colors.BOLD}All checks passed! 봇 실행 준비 완료.{Colors.RESET}")
        print(f"  실행: python main.py")
    else:
        print(f"\n  {Colors.RED}{Colors.BOLD}{total_fail}개 항목 실패. 위의 [FAIL] 항목을 수정하세요.{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
