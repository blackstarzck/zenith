# Zenith — 프로젝트 가이드라인

## 프로젝트 개요
- **Zenith**: 업비트(Upbit) 암호화폐 자동 매매 시스템
- **기술 스택**: Python 3.10+ (Backend) | React 19 + Ant Design 6 + Vite 7.3 (Frontend) | Supabase (DB)
- **배포**: 로컬 PC 상시 구동 (Docker/CI/CD 없음)
- **언어 컨벤션**: 모든 주석, docstring, 로그 메시지, UI 텍스트는 **한국어**

---

## 핵심 아키텍처: Shared Database

프론트엔드와 백엔드는 **직접 통신하지 않음** (REST API, GraphQL 없음).
모든 데이터는 Supabase(PostgreSQL)를 통해 흐름:

```
[Python Bot] → write → [Supabase DB] ← read/realtime ← [React UI]
[React UI] → write bot_state.strategy_params → [Supabase DB] ← poll ~1min ← [Python Bot]
```

### ⚠️ 스키마 변경 = 최고 위험 작업
테이블/컬럼 변경 시 아래 **4곳 동시 수정 필수**:
1. `supabase_*.sql` (마이그레이션)
2. `src/storage/client.py` (Python DB 클라이언트)
3. `frontend/src/types/database.ts` (TypeScript 타입)
4. `frontend/src/hooks/useSupabase.ts` (React 훅)

### 인증
- **Kakao OAuth** (`frontend/src/contexts/AuthContext.tsx`) — Supabase Auth 사용하지 않음

---

## 6가지 원칙 — 코드 수정 시 필수 체크리스트

### 원칙 1. 재사용성
- 새 컴포넌트/함수 생성 전: 기존 유사 구현 검색 (`grep`, `lsp_find_references`)
- 공통 로직은 `hooks/`, `lib/`, `src/` 하위 유틸로 분리
- 하드코딩된 값 → 상수/설정으로 추출

### 원칙 2. 확장성
- 인터페이스/타입 설계: 향후 필드 추가에 유연하게
- 조건 분기보다 패턴 기반 설계 선호 (strategy pattern 등)
- config 기반 동작: 로직보다 설정으로 제어 가능하게

### 원칙 3. 프레임워크 최적화
- 프론트엔드: → `frontend/AGENTS.md` 참조
- 백엔드: → `src/AGENTS.md` 참조
- ⚠️ **라이브러리/프레임워크 API 사용 시 반드시 공식 문서 확인** (`context7_query-docs` 활용) — 학습 데이터 의존 시 deprecated API 사용 위험

### 원칙 4. 영향도 분석 (Impact Analysis)
수정 전 **반드시** 수행:
1. `lsp_find_references`로 사용처 확인
2. `grep`으로 문자열/패턴 참조 검색
3. DB 스키마 관련 → 4곳 동시 수정 (위 참조)
4. 전략 파라미터 관련 → `src/config.py` ↔ `frontend/src/lib/strategyParams.ts` ↔ `bot_state` 동기화 확인
5. 훅/함수 시그니처 변경 → 호출부 모두 확인

수정 완료 시: **"영향받는 파일 N개, 모두 반영 완료"** 명시

### 원칙 5. UX/UI 고려
- → `frontend/AGENTS.md`의 UX/UI 섹션 참조
- 백엔드 변경이라도 UI에 노출되는 데이터면 표시 형식 고려
- 에러 메시지는 사용자 친화적으로 (기술 용어 최소화)

### 원칙 6. docs 수정 여부 판단
- 아래 매핑 테이블에 따라 관련 문서 업데이트 여부 판단
- 판단 후 수정이 필요하면 해당 문서도 **함께** 수정

---

## Docs 매핑 테이블

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

---

## 테스트
- **백엔드**: pytest (`tests/` 디렉토리) — 변경 시 관련 테스트 확인 → 있으면 업데이트, 없으면 추가 권장
- **프론트엔드**: 테스트 인프라 미구축 (린트만 가능: `npx eslint .`)
