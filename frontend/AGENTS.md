# Frontend (React) 가이드라인

> 상위 `/AGENTS.md`의 6가지 원칙을 따릅니다.

## 기술 스택
- React 19.2 + TypeScript 5.9 + Vite 7.3 + Ant Design 6.3
- Supabase JS Client 2.97 (인증 기능 비활성화 상태)

### ⚠️ 공식 문서 확인 의무 (Deprecated 방지)
라이브러리/프레임워크 API 사용 시 **반드시 공식 문서를 먼저 확인**한다.
학습 데이터에 의존하면 deprecated된 속성/메서드를 사용하게 됨.

**의무 절차**:
1. Ant Design 컴포넌트 사용/수정 시 → `context7_query-docs`로 **antd v6** 문서 조회
2. React 19 신규 API 사용 시 → `context7_query-docs`로 **React 19** 문서 조회
3. 기타 라이브러리 → `context7_resolve-library-id` → `context7_query-docs` 순서로 조회
4. 문서에서 deprecated 경고가 있으면 **대체 API를 사용**

**특히 주의할 AntD 6 변경사항**:
- `antd` v5→v6 마이그레이션으로 다수 prop이 변경/제거됨
- 컴포넌트 prop을 사용하기 전에 현재 버전(6.3.0) 문서 확인 필수
- 의심스러우면 **무조건 문서부터 조회**

---

## 디렉토리 구조

- `pages/`: 라우트 레벨 컴포넌트 (DashboardPage, TradingPage, AnalyticsPage, SettingsPage, ReportsPage)
- `components/`: 공유 위젯 (AppLayout — 메인 레이아웃 + 네비게이션 + 로그 Drawer)
- `hooks/`: 데이터 계층 (useSupabase.ts — 11개 커스텀 훅, useUpbitTicker.ts, useRecoverySignal.ts)
- `contexts/`: 전역 상태 (AuthContext — Kakao OAuth, RecoveryContext — 네트워크 복구)
- `lib/`: 유틸리티 (supabase.ts — 클라이언트 초기화, strategyParams.ts — 전략 프리셋)
- `types/`: 타입 정의 (database.ts — DB 테이블 타입)
- `assets/`: 정적 자원

---

## 필수 패턴

### 컴포넌트 구조 (파일 내부 순서)
1. Props interface 정의
2. Hooks 초기화 (`useForm`, `useMessage`, `useAuth`)
3. 로컬 상태 (`useState`)
4. 파생 상태/메모이제이션 (`useMemo`, `useDeferredValue`)
5. 사이드 이펙트 (`useEffect`)
6. 이벤트 핸들러 (`useCallback`)
7. JSX 반환

### 데이터 페칭
`hooks/useSupabase.ts`의 훅 패턴 따르기:
- `useState`로 data + loading 관리
- `useCallback`으로 fetch 함수 래핑
- `useEffect`로 초기 fetch + Supabase Realtime 구독
- cleanup에서 구독 해제
- ⚠️ **신규 데이터 훅은 반드시 `RecoveryProvider`(useRecoveryTick)와 통합** — 네트워크 복구 시 자동 refetch 보장

### 스타일링
- ✅ 인라인 `style={{}}` 객체 사용 (프로젝트 전체 컨벤션)
- ✅ Ant Design `ConfigProvider` + `theme.darkAlgorithm` 테마
- ✅ AntD 레이아웃 컴포넌트 (`Flex`, `Space`, `Row`, `Col`)
- ✅ 거래 특화 색상 상수: `COLOR_RISE: '#ff4d4f'`, `COLOR_FALL: '#1890ff'`
- ❌ CSS Modules 사용하지 않음
- ❌ Tailwind CSS 사용하지 않음
- ❌ styled-components 사용하지 않음

### 라우팅
- `React.lazy()` + `Suspense`로 모든 페이지 지연 로딩 (참조: `App.tsx`)
- `RequireAuth` 가드로 인증 보호
- `LoginPage`, `AuthCallbackPage`는 lazy 적용 안 함 (초기 로드 경로)

### 인증
- **Kakao OAuth** (`contexts/AuthContext.tsx`) — Supabase Auth 아님
- `vite.config.ts`에 Kakao API 프록시 설정됨 (`/kakao-token`, `/kakao-api`)

### 빌드 최적화
- `vite.config.ts`의 `manualChunks`로 벤더 분할 (react, antd, charts, supabase)
- 새 대형 의존성 추가 시 `manualChunks`에 등록

### 임포트 순서
1. React/표준 라이브러리
2. 서드파티 (Ant Design, Icons, Dayjs)
3. Contexts, Hooks
4. 로컬 컴포넌트
5. Types, Libs

### 네이밍
- 파일: PascalCase (컴포넌트/페이지), camelCase (훅/유틸)
- 변수: camelCase, 상수: UPPER_SNAKE_CASE
- 타입/인터페이스: PascalCase (DB 테이블명 미러링)

### 전략 파라미터 동기화
- `lib/strategyParams.ts` (프론트엔드 프리셋) ↔ `bot_state.strategy_params` (DB) ↔ `src/config.py` (백엔드)
- 프리셋 기본값 변경 시 **3곳 동기화 확인 필수**

---

## UX/UI 체크리스트

코드 수정 시 아래 항목 검토:
- **로딩 상태**: 데이터 로드 중 `Spin` 또는 `Skeleton` 표시하는가?
- **에러 상태**: API 실패 시 사용자에게 의미 있는 피드백 제공하는가?
- **빈 상태**: 데이터 없을 때 안내 메시지 있는가?
- **반응성**: 인터랙션(클릭, hover)에 즉각 피드백 있는가?
- **일관성**: 기존 UI 패턴/색상/간격과 일치하는가?
- **접근성**: Tooltip에 적절한 title, 버튼에 명확한 라벨 있는가?
- **실시간 데이터**: Realtime 구독 데이터가 화면에 자연스럽게 업데이트되는가?
- **다크 테마**: 새 요소가 다크 테마에서 가독성 있는가? (이 프로젝트는 **다크 테마 전용**)
- **성능**: 불필요한 리렌더 발생시키지 않는가? (`useMemo`, `useCallback`, `useDeferredValue` 적절히 사용)

---

## 금지 사항
- ❌ CSS Modules, Tailwind, styled-components 도입 금지
- ❌ Supabase Auth 기능 활성화 금지 (Kakao OAuth 사용)
- ❌ path alias 사용 금지 (상대 경로만 사용, 설정 안 됨)
- ❌ 새 전역 상태 관리 도구 (Redux, Zustand) 도입 금지 — Context로 충분
