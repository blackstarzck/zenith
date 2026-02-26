# Plan: .env → .env.backend 참조 업데이트

## Context
루트 `.env` 파일을 `.env.backend`로 이름 변경 완료 (Bun이 `.env`를 자동 로드하여 프론트엔드 충돌 방지).
이제 `.env`를 참조하는 4개 파일의 참조를 `.env.backend`로 업데이트해야 함.

## Scope
- **IN**: `.env` 참조를 `.env.backend`로 변경 (4개 파일, 총 9곳)
- **OUT**: 다른 파일 변경 없음

## Tasks

### TODO 1: `src/config.py` — load_dotenv 경로 변경
- **File**: `src/config.py`
- **Line**: 11
- **Change**: `load_dotenv()` → `load_dotenv(".env.backend")`
- **QA**: 파일 읽어서 변경 확인

### TODO 2: `.vscode/launch.json` — envFile 경로 변경 (6곳)
- **File**: `.vscode/launch.json`
- **Lines**: 10, 35, 45, 55, 65, 76
- **Change**: 모든 `"envFile": "${workspaceFolder}/.env"` → `"envFile": "${workspaceFolder}/.env.backend"`
- **QA**: 파일 내 `.env"` 검색하여 미변경 항목 없는지 확인

### TODO 3: `scripts/preflight_check.py` — load_dotenv 경로 변경
- **File**: `scripts/preflight_check.py`
- **Line**: 22
- **Change**: `load_dotenv()` → `load_dotenv(".env.backend")`
- **QA**: 파일 읽어서 변경 확인

### TODO 4: `scripts/kakao_auth.py` — load_dotenv + ENV_PATH 변경 (2곳)
- **File**: `scripts/kakao_auth.py`
- **Line 25**: `load_dotenv()` → `load_dotenv(".env.backend")`
- **Line 30**: `ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")` → `ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.backend")`
- **QA**: 파일 읽어서 두 곳 모두 변경 확인

## Final Verification Wave
- `grep -r "load_dotenv()" src/ scripts/` — 인자 없는 load_dotenv 호출이 남아있지 않은지 확인
- `grep -r '\.env"' .vscode/launch.json` — `.env.backend`가 아닌 `.env` 참조가 남아있지 않은지 확인
- `.env.backend` 파일이 루트에 존재하는지 확인
