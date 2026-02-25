"""
Zenith 프로세스 감시 스크립트 (Watchdog).

봇 프로세스가 비정상 종료 시 자동으로 재시작합니다.
사용법: python scripts/watchdog.py

환경변수:
    WATCHDOG_MAX_RESTARTS  — 연속 재시작 상한 (기본 10)
    WATCHDOG_COOLDOWN_SEC  — 재시작 사이 대기 시간 (기본 10초)
    WATCHDOG_RESET_AFTER   — 정상 실행 N초 후 재시작 카운터 리셋 (기본 300)
"""

import io
import os
import subprocess
import sys
import time

# Windows cp949 인코딩 문제 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 프로젝트 루트 — scripts/ 의 상위 디렉토리
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAX_RESTARTS = int(os.environ.get("WATCHDOG_MAX_RESTARTS", "10"))
COOLDOWN_SEC = int(os.environ.get("WATCHDOG_COOLDOWN_SEC", "10"))
RESET_AFTER = int(os.environ.get("WATCHDOG_RESET_AFTER", "300"))


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    python = sys.executable
    main_script = os.path.join(PROJECT_ROOT, "main.py")

    if not os.path.isfile(main_script):
        print(f"[{_timestamp()}] [WATCHDOG] main.py를 찾을 수 없습니다: {main_script}")
        sys.exit(1)

    restart_count = 0

    print(f"[{_timestamp()}] [WATCHDOG] Zenith Watchdog 시작")
    print(f"[{_timestamp()}] [WATCHDOG] Python: {python}")
    print(f"[{_timestamp()}] [WATCHDOG] 최대 연속 재시작: {MAX_RESTARTS}")
    print(f"[{_timestamp()}] [WATCHDOG] 쿨다운: {COOLDOWN_SEC}초")
    print(f"[{_timestamp()}] [WATCHDOG] 카운터 리셋 기준: {RESET_AFTER}초 정상 실행")
    print()

    while True:
        start_time = time.time()

        print(f"[{_timestamp()}] [WATCHDOG] 봇 프로세스 시작 (재시작 #{restart_count})")

        try:
            proc = subprocess.Popen(
                [python, main_script],
                cwd=PROJECT_ROOT,
            )
            exit_code = proc.wait()
        except KeyboardInterrupt:
            print(f"\n[{_timestamp()}] [WATCHDOG] Ctrl+C 감지 — 봇과 함께 종료합니다.")
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
            break
        except Exception as exc:
            print(f"[{_timestamp()}] [WATCHDOG] 프로세스 실행 오류: {exc}")
            exit_code = -1

        elapsed = time.time() - start_time

        # 정상 종료 (exit code 0) — 의도적 종료이므로 워치독도 종료
        if exit_code == 0:
            print(f"[{_timestamp()}] [WATCHDOG] 봇이 정상 종료됨 (exit 0, {elapsed:.0f}초 실행) — 워치독 종료")
            break

        print(
            f"[{_timestamp()}] [WATCHDOG] 봇 비정상 종료 "
            f"(exit {exit_code}, {elapsed:.0f}초 실행)"
        )

        # 충분히 오래 실행됐으면 재시작 카운터 리셋
        if elapsed >= RESET_AFTER:
            restart_count = 0

        restart_count += 1

        if restart_count > MAX_RESTARTS:
            print(
                f"[{_timestamp()}] [WATCHDOG] 연속 재시작 {MAX_RESTARTS}회 초과 — "
                f"워치독을 중단합니다. 수동 점검이 필요합니다."
            )
            sys.exit(2)

        print(
            f"[{_timestamp()}] [WATCHDOG] {COOLDOWN_SEC}초 후 재시작 "
            f"({restart_count}/{MAX_RESTARTS})"
        )
        try:
            time.sleep(COOLDOWN_SEC)
        except KeyboardInterrupt:
            print(f"\n[{_timestamp()}] [WATCHDOG] Ctrl+C 감지 — 종료합니다.")
            break


if __name__ == "__main__":
    main()
