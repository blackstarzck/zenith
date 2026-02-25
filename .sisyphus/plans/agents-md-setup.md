# Plan: AGENTS.md 가이드라인 시스템 구축

## Metadata
- **Created**: 2025-02-25
- **Goal**: 프로젝트 전역/프론트엔드/백엔드에 AGENTS.md를 생성하여 유저의 6가지 원칙을 모든 코드 수정 요청에 자동 적용
- **Scope**: `AGENTS.md`, `frontend/AGENTS.md`, `src/AGENTS.md` 3개 파일 생성
- **Tech Stack**: Python 3.10+ (Backend), React 19 + Ant Design 6 + Vite 7.3 + TypeScript 5.9 (Frontend), Supabase (DB)

## Background: 유저의 6가지 원칙

모든 코드 수정 요청 시 에이전트가 자동으로 고려해야 하는 원칙:
1. **재사용성** — 컴포넌트/모듈/함수의 재사용 가능성 검토
2. **확장성** — 향후 기능 확장에 유연한 설계인지 검토
3. **프레임워크 최적화** — React 19 / Python 각각의 best practice 준수
4. **영향도 분석** — 수정이 다른 영역에 미치는 영향 체크 (데이터 + 로직)
5. **UX/UI 고려** — 사용자 경험과 인터페이스 품질에 대한 깊은 고려
6. **docs 수정 여부 판단** — 코드 변경 시 `docs/` 문서 업데이트 필요 여부 확인 후 실행

## 핵심 아키텍처: Shared Database 패턴

이 프로젝트의 **가장 중요한 아키텍처 특성**:
- 프론트엔드와 백엔드는 **직접 통신하지 않음** (REST API, GraphQL 없음)
- 모든 데이터는 **Supabase(PostgreSQL)**를 통해 흐름:
  - Python Bot → Supabase 테이블에 write
  - React UI → Supabase에서 read + Realtime 구독
  - UI → Bot 제어: `bot_state.strategy_params`에 write → Bot이 ~1분마다 poll
- **스키마 변경이 최고 위험 작업**: SQL ↔ `src/storage/client.py` ↔ `frontend/src/types/database.ts` ↔ `frontend/src/hooks/useSupabase.ts` 동시 수정 필요

## Scope

### IN
- `AGENTS.md` (루트) — 전역 원칙, 영향도 체크리스트, docs 매핑 테이블
- `frontend/AGENTS.md` — React 19 패턴, AntD 6 컨벤션, UX/UI 체크리스트
- `src/AGENTS.md` — Python 패턴, 동기 전용 제약, 방어적 에러 핸들링

### OUT
- 코드 수정 (`.ts`, `.py` 등) — 문서 생성만 수행
- docs/ 문서 업데이트 — 별도 이슈로 관리
- `.env.example` 보정 — 별도 이슈

## Conventions
- 각 AGENTS.md는 **200줄 이내** (길면 에이전트가 무시함)
- 불릿 포인트 기반 (문단 X)
- 구체적 `file:line` 참조 포함 (패턴 증거)
- 한국어로 작성 (프로젝트 전체 컨벤션 일치)
- 자식 파일은 루트를 상속: "상위 `AGENTS.md` 원칙을 따름" 선언
- 코드 스니펫은 3줄 이내

## Verification Wave (각 Task 완료 후)
- 파일이 올바른 경로에 생성됨
- 유효한 UTF-8 Markdown
- 200줄 이내
- 참조된 모든 파일 경로가 실제로 존재
- 3개 파일 간 상충하는 지침 없음
- 민감 정보(API 키 등) 미포함

---

## Tasks

<!-- TASKS_START -->

### Task 1: 루트 AGENTS.md 생성 — 전역 원칙 + 영향도 체크리스트 + Docs 매핑

**파일**: `AGENTS.md` (프로젝트 루트)

**목표**: 모든 에이전트가 자동으로 읽는 전역 가이드라인 파일 생성. 6가지 원칙을 코드 수정 요청마다 적용하도록 구조화.

**파일 내용 구조** (200줄 이내):

#### 섹션 1: 프로젝트 개요 (~10줄)
- 프로젝트명: Zenith — 암호화폐 자동 매매 시스템 (Upbit)
- 기술 스택 한 줄 요약: Python 3.10+ (Backend) | React 19 + AntD 6 + Vite 7.3 (Frontend) | Supabase (DB)
- 로컬 PC 상시 구동 (Docker/CI/CD 없음)
- 한국어 컨벤션: 모든 주석, docstring, 로그 메시지, UI 텍스트는 한국어

#### 섹션 2: 핵심 아키텍처 — Shared Database (~15줄)
- 프론트엔드 ↔ 백엔드 직접 통신 없음 (REST API, GraphQL 없음)
- 데이터 흐름도 (텍스트 기반):
  ```
  [Python Bot] → write → [Supabase DB] ← read/realtime ← [React UI]
  [React UI] → write bot_state.strategy_params → [Supabase DB] ← poll ~1min ← [Python Bot]
  ```
- ⚠️ **스키마 변경 = 최고 위험 작업**: 테이블/컬럼 변경 시 아래 4곳 동시 수정 필수:
  1. `supabase_*.sql` (마이그레이션)
  2. `src/storage/client.py` (Python DB 클라이언트)
  3. `frontend/src/types/database.ts` (TypeScript 타입)
  4. `frontend/src/hooks/useSupabase.ts` (React 훅)
- 인증: Kakao OAuth (`frontend/src/contexts/AuthContext.tsx`), Supabase Auth 사용하지 않음

#### 섹션 3: 6가지 원칙 — 코드 수정 시 필수 체크리스트 (~40줄)

각 원칙에 대해 구체적 체크 항목 나열:

**원칙 1. 재사용성**
- 새 컴포넌트/함수 생성 전: 기존 유사 구현 검색 (Grep/LSP)
- 공통 로직은 `hooks/`, `lib/`, `src/` 하위 유틸로 분리
- 하드코딩된 값 → 상수/설정으로 추출

**원칙 2. 확장성**
- 인터페이스/타입 설계: 향후 필드 추가에 유연하게
- 조건 분기보다 패턴 기반 설계 선호 (strategy pattern 등)
- config 기반 동작: 로직보다 설정으로 제어 가능하게

**원칙 3. 프레임워크 최적화**
- 프론트엔드: → `frontend/AGENTS.md` 참조
- 백엔드: → `src/AGENTS.md` 참조

**원칙 4. 영향도 분석 (Impact Analysis)**
- 수정 전 반드시 수행:
  1. `lsp_find_references`로 사용처 확인
  2. `grep`으로 문자열/패턴 참조 검색
  3. DB 스키마 관련 → 4곳 동시 수정 (섹션 2 참조)
  4. 전략 파라미터 관련 → `src/config.py` ↔ `frontend/src/lib/strategyParams.ts` ↔ `bot_state` 동기화 확인
  5. 훅 시그니처 변경 → 호출부 모두 확인
- 영향 범위 보고: 수정 완료 시 "영향받는 파일 N개, 모두 반영 완료" 명시

**원칙 5. UX/UI 고려**
- → `frontend/AGENTS.md`의 UX/UI 섹션 참조
- 백엔드 변경이라도 UI에 노출되는 데이터면 표시 형식 고려
- 에러 메시지는 사용자 친화적으로 (기술 용어 최소화)

**원칙 6. docs 수정 여부 판단**
- 아래 매핑 테이블에 따라 관련 문서 업데이트 여부 판단
- 판단 후 수정이 필요하면 해당 문서도 함께 수정

#### 섹션 4: Docs 매핑 테이블 (~25줄)

| 문서 | 수정 트리거 (이 영역이 바뀌면 문서 검토) |
|------|-------|
| `docs/PRD.md` | 핵심 전략 철학 변경, 제품 범위를 바꾸는 신규 기능 |
| `docs/System-Architecture-Design.md` | `src/` 내 신규 모듈, 외부 서비스 연동 추가, 데이터 흐름 변경 |
| `docs/Algorithm_Specification.md` | `src/strategy/engine.py`, `src/strategy/indicators.py`, 진입/청산 로직 |
| `docs/API_Integration.md` | `src/executor/`, `src/collector/`, `src/notifier/kakao.py`, `src/storage/client.py` |
| `docs/Data_Model_ERD.md` | `supabase_*.sql` 변경, `src/storage/client.py` 테이블 메서드, `frontend/src/types/database.ts` |
| `docs/Risk_Security_Protocol.md` | `src/risk/manager.py`, `src/config.py` (RiskParams), 손절/포지션 사이징 로직 |
| `docs/Backtesting_Plan.md` | `src/backtest/` 디렉토리 |
| `docs/frontend-design.md` | `frontend/src/pages/`, `frontend/src/components/`, 신규 페이지 또는 대규모 UI 구조 변경 |
| `docs/API-Keys.md` | `.env.example`, `frontend/.env.example`, 신규 API 키 요구사항 |

#### 섹션 5: 테스트 (~5줄)
- 테스트 프레임워크: pytest (`tests/` 디렉토리)
- 프론트엔드 테스트 인프라: 미구축 상태 (린트만 가능: `npx eslint .`)
- 백엔드 변경 시 관련 테스트 존재 여부 확인 → 있으면 업데이트, 없으면 신규 추가 권장

**QA**:
- `AGENTS.md` 파일이 프로젝트 루트에 존재
- Markdown 문법 오류 없음
- 200줄 이내
- docs 매핑 테이블의 9개 문서가 모두 `docs/` 내에 실제 존재 확인
- 민감 정보 미포함

---

### Task 2: Backend AGENTS.md 생성 — Python 패턴 + 모듈 구조

**파일**: `src/AGENTS.md`

**목표**: Python 백엔드 작업 시 에이전트가 따라야 할 구체적 패턴과 제약 사항 정의.

**파일 내용 구조** (200줄 이내):

#### 섹션 1: 상속 선언 + 기술 스택 (~5줄)
- "상위 `/AGENTS.md`의 6가지 원칙을 따릅니다"
- Python 3.10+, 완전 동기 (async/await 절대 금지)
- 의존성: `pyupbit`, `pandas`, `numpy`, `ta`, `supabase`, `httpx`

#### 섹션 2: 모듈 구조 + 데이터 흐름 (~20줄)
- 모듈 순서 (오케스트레이터가 호출하는 순서):
  ```
  collector/ → strategy/ → executor/ → storage/ → notifier/
  + risk/ (횡단), report/ (일일), backtest/ (오프라인)
  ```
- 각 모듈 역할 한 줄 설명:
  - `collector/data_collector.py`: Upbit API 시세/호가 수집 + rate limiting
  - `strategy/engine.py`: 평균 회귀 신호 생성 + 상태 복구
  - `strategy/indicators.py`: 기술 지표 계산 (BB, RSI, ATR)
  - `executor/order_executor.py`: 주문 집행 + 타임아웃 + 쿨다운
  - `risk/manager.py`: 포지션 사이징 + 일일 손실 한도
  - `storage/client.py`: Supabase CRUD + 에러 차폐
  - `notifier/kakao.py`: 카카오톡 알림 (동기 HTTP)
  - `report/generator.py`: 일일 리포트 마크다운 생성
  - `orchestrator.py`: 중앙 조율자 — 메인 루프, 모듈 초기화, 에러 복구
- 운영 스크립트: `scripts/kakao_auth.py`, `scripts/preflight_check.py`, `scripts/watchdog.py`

#### 섹션 3: 필수 패턴 (~40줄)

**설정 패턴**: `@dataclass(frozen=True)` for ALL config classes (참조: `config.py`)
```python
@dataclass(frozen=True)
class StrategyParams:
    bb_window: int = 20
```

**에러 핸들링**: 모든 DB 호출은 try/except로 래핑 — DB 장애가 봇을 죽이면 안 됨 (참조: `storage/client.py`)
```python
try:
    result = self._supabase.table('trades').insert(data).execute()
except Exception as e:
    logger.exception('DB insert 실패: %s', e)
```

**알림 안전**: `_safe_notify()` 패턴 — 알림 실패가 메인 루프를 죽이면 안 됨 (참조: `orchestrator.py`)

**복구 전략**: exponential backoff — `min(interval * 2^consecutive_errors, 300s)` (참조: `orchestrator.py`)

**핫 리로드**: `_reload_strategy_params()` — `bot_state` 테이블에서 ~1분 간격 poll (참조: `orchestrator.py`)

**로깅**:
- `logger = logging.getLogger(__name__)` 표준 사용
- 레벨 가이드: critical(초기화 실패/일일 한도), error(API 장애), warning(일시적 네트워크), info(상태 변경), debug(고빈도 노이즈)
- 로그 메시지에 컨텍스트 포함: `[매수 진입] {symbol} | 사유: {reason}`

**임포트 순서**:
1. `from __future__ import annotations` + `TYPE_CHECKING`
2. 표준 라이브러리 (`logging`, `time`, `datetime`)
3. 서드파티 (`pyupbit`, `pandas`, `supabase`)
4. 로컬 모듈 (`from src.config import ...`)

**네이밍**:
- 클래스: PascalCase (`OrderExecutor`)
- 함수/변수: snake_case (`fetch_ticker`)
- 상수: UPPER_SNAKE_CASE (`_SNAPSHOT_INTERVAL`)
- private: 단일 언더스코어 (`self._config`, `self._execute_buy()`)

**Supabase 패턴**:
- upsert: 단일 행 상태성 데이터 (`bot_state`, `kakao_tokens`)
- insert: 시계열/이벤트 데이터 (`trades`, `balance_snapshots`, `system_logs`)
- cleanup: 7일 이상 오래된 스냅샷 자동 삭제

#### 섹션 4: 금지 사항 (~10줄)
- ❌ `async/await`, `asyncio`, FastAPI 도입 금지 — 완전 동기 아키텍처
- ❌ 새 외부 패키지 추가 시 반드시 `requirements.txt` 업데이트
- ❌ `orchestrator.py`의 메인 루프 구조 변경 시 각별히 주의 (단일 장애점)
- ❌ rate limiting 제거/완화 금지 (거래소 API 차단 위험)

**QA**:
- `src/AGENTS.md` 파일이 존재
- 루트 AGENTS.md와 상충 없음
- 200줄 이내
- 참조된 파일 경로 유효 확인

---

### Task 3: Frontend AGENTS.md 생성 — React 패턴 + UX/UI 체크리스트

**파일**: `frontend/AGENTS.md`

**목표**: 프론트엔드 작업 시 에이전트가 따라야 할 React 19 패턴, Ant Design 6 컨벤션, UX/UI 품질 기준 정의.

**파일 내용 구조** (200줄 이내):

#### 섹션 1: 상속 선언 + 기술 스택 (~5줄)
- "상위 `/AGENTS.md`의 6가지 원칙을 따릅니다"
- React 19.2 + TypeScript 5.9 + Vite 7.3 + Ant Design 6.3
- Supabase JS Client 2.97 (인증 기능 비활성화 상태)

#### 섹션 2: 디렉토리 구조 + 역할 (~15줄)
- `pages/`: 라우트 레벨 컴포넌트 (DashboardPage, TradingPage, AnalyticsPage, SettingsPage, ReportsPage)
- `components/`: 공유 위젯 (AppLayout — 메인 레이아웃 + 네비게이션 + 로그 Drawer)
- `hooks/`: 데이터 계층 (useSupabase.ts — 11개 커스텀 훅, useUpbitTicker.ts, useRecoverySignal.ts)
- `contexts/`: 전역 상태 (AuthContext — Kakao OAuth, RecoveryContext — 네트워크 복구)
- `lib/`: 유틸리티 (supabase.ts — 클라이언트 초기화, strategyParams.ts — 전략 프리셋)
- `types/`: 타입 정의 (database.ts — DB 테이블 타입)
- `assets/`: 정적 자원

#### 섹션 3: 필수 패턴 (~50줄)

**컴포넌트 구조** (파일 내부 순서):
1. Props interface 정의
2. Hooks 초기화 (`useForm`, `useMessage`, `useAuth`)
3. 로컬 상태 (`useState`)
4. 파생 상태/메모이제이션 (`useMemo`, `useDeferredValue`)
5. 사이드 이펙트 (`useEffect`)
6. 이벤트 핸들러 (`useCallback`)
7. JSX 반환

**데이터 페칭**: `hooks/useSupabase.ts`의 훅 패턴 따르기:
- `useState`로 data + loading 관리
- `useCallback`으로 fetch 함수 래핑
- `useEffect`로 초기 fetch + Supabase Realtime 구독
- cleanup에서 구독 해제
- ⚠️ **신규 데이터 훅은 반드시 `RecoveryProvider`(useRecoveryTick)와 통합** — 네트워크 복구 시 자동 refetch 보장

**스타일링**:
- ✅ 인라인 `style={{}}` 객체 사용 (프로젝트 전체 컨벤션)
- ✅ Ant Design `ConfigProvider` + `theme.darkAlgorithm` 테마
- ✅ AntD 레이아웃 컴포넌트 (`Flex`, `Space`, `Row`, `Col`)
- ✅ 거래 특화 색상 상수: `COLOR_RISE: '#ff4d4f'`, `COLOR_FALL: '#1890ff'`
- ❌ CSS Modules 사용하지 않음
- ❌ Tailwind CSS 사용하지 않음
- ❌ styled-components 사용하지 않음

**라우팅**:
- `React.lazy()` + `Suspense`로 모든 페이지 지연 로딩 (참조: `App.tsx`)
- `RequireAuth` 가드로 인증 보호
- `LoginPage`, `AuthCallbackPage`는 lazy 적용 안 함 (초기 로드 경로)

**인증**:
- Kakao OAuth (`contexts/AuthContext.tsx`) — Supabase Auth 아님
- `vite.config.ts`에 Kakao API 프록시 설정됨 (`/kakao-token`, `/kakao-api`)

**빌드 최적화**:
- `vite.config.ts`의 `manualChunks`로 벤더 분할 (react, antd, charts, supabase)
- 새 대형 의존성 추가 시 `manualChunks`에 등록

**임포트 순서**:
1. React/표준 라이브러리
2. 서드파티 (Ant Design, Icons, Dayjs)
3. Contexts, Hooks
4. 로컬 컴포넌트
5. Types, Libs

**네이밍**:
- 파일: PascalCase (컴포넌트/페이지), camelCase (훅/유틸)
- 변수: camelCase, 상수: UPPER_SNAKE_CASE
- 타입/인터페이스: PascalCase (DB 테이블명 미러링)

**전략 파라미터 동기화**:
- `lib/strategyParams.ts` (프론트엔드 프리셋) ↔ `bot_state.strategy_params` (DB) ↔ `src/config.py` (백엔드)
- 프리셋 기본값 변경 시 3곳 동기화 확인 필수

#### 섹션 4: UX/UI 체크리스트 (~20줄)

코드 수정 시 아래 항목 검토:
- **로딩 상태**: 데이터 로드 중 `Spin` 또는 `Skeleton` 표시하는가?
- **에러 상태**: API 실패 시 사용자에게 의미 있는 피드백 제공하는가?
- **빈 상태**: 데이터 없을 때 안내 메시지 있는가?
- **반응성**: 인터랙션(클릭, hover)에 즉각 피드백 있는가?
- **일관성**: 기존 UI 패턴/색상/간격과 일치하는가?
- **접근성**: Tooltip에 적절한 title, 버튼에 명확한 라벨 있는가?
- **실시간 데이터**: Realtime 구독 데이터가 화면에 자연스럽게 업데이트되는가?
- **다크 테마**: 새 요소가 다크 테마에서 가독성 있는가? (이 프로젝트는 다크 테마 전용)
- **성능**: 불필요한 리렌더 발생시키지 않는가? (`useMemo`, `useCallback`, `useDeferredValue` 적절히 사용)

#### 섹션 5: 금지 사항 (~10줄)
- ❌ CSS Modules, Tailwind, styled-components 도입 금지
- ❌ Supabase Auth 기능 활성화 금지 (Kakao OAuth 사용)
- ❌ path alias 사용 금지 (상대 경로만 사용, 설정 안 됨)
- ❌ 새 전역 상태 관리 도구 (Redux, Zustand) 도입 금지 — Context로 충분

**QA**:
- `frontend/AGENTS.md` 파일이 존재
- 루트 AGENTS.md와 상충 없음
- 200줄 이내
- 참조된 파일 경로 유효 확인
- UX/UI 체크리스트가 다크 테마 전용 프로젝트 특성을 반영

<!-- TASKS_END -->

## Final Verification Wave

모든 Task 완료 후:
1. 3개 AGENTS.md 파일이 모두 존재하고 유효한 Markdown인지 확인
2. 참조된 file:line이 실제로 해당 패턴과 일치하는지 spot-check
3. 3개 파일 간 상충 지침이 없는지 검토
4. 각 파일 200줄 이내 확인
