# Plan: Drawer/Tooltip 인터랙션 지연 최적화

## Metadata
- **Created**: 2025-02-24
- **Goal**: Drawer 열림/닫힘 및 Tooltip 노출 시 체감 지연(jank) 제거
- **Scope**: `frontend/src/` 내 렌더링 성능 최적화 (기능 변경 없음)
- **Tech Stack**: React 19, Ant Design 6.3.0, Vite 7.3, Supabase Realtime, WebSocket

## Root Cause Analysis

### 지연 원인 (우선순위순)

1. **Log Realtime → AppLayout → Outlet 캐스케이드** (최고 영향)
   - `useSystemLogs`가 Drawer 닫혀 있어도 항상 실행 (`AppLayout.tsx:129`)
   - Supabase realtime INSERT → `logs` state 변경 → AppLayout 리렌더 → `<Outlet />` → DashboardPage 전체 리렌더
   - 봇이 로그를 자주 남기면 **틱커 업데이트와 무관하게** 지속적 리렌더 발생

2. **Ticker → allRows → Table 전체 리렌더** (높은 영향)
   - `useUpbitTicker` 500ms flush → `tickers` Map 교체 → `allRows` useMemo 재계산 (deps에 `tickers` 포함)
   - `allRows`에 ticker 데이터가 임베딩 → 매 500ms마다 새 객체 배열 생성 → Table 전체 리렌더
   - `React.memo`로 Table을 감싸도 `allRows` 자체가 새 참조이므로 **효과 없음**

3. **Drawer 500개 로그 DOM 즉시 생성** (중간 영향)
   - `logs.map()`으로 최대 500개 DOM 노드 한 번에 생성
   - Ant Design Drawer 애니메이션과 동시 실행 → 프레임 드롭

4. **Code Splitting 미적용** (낮은 영향)
   - 모든 페이지가 eager import → 초기 번들 크기 불필요하게 큼

## Scope

### IN
- AppLayout.tsx: Drawer 렌더링 최적화
- DashboardPage.tsx: Table 리렌더 격리, Tooltip 최적화
- useSupabase.ts: `useSystemLogs` 조건부 활성화
- App.tsx: Route-level code splitting

### OUT
- `useUpbitTicker.ts` 내부 로직 (FLUSH_INTERVAL 등) — 이미 최적화됨
- `useRecoverySignal.ts` — 전체 앱 영향, 별도 이슈
- `useBotState` 중복 호출 통합 — 구조적 리팩터링, 별도 이슈
- 인라인 스타일 최적화 — 병목이 아님, 낮은 ROI
- 테스트 코드 작성 — 테스트 인프라 미구축 상태

## Conventions
- 기존 패턴 준수: `useCallback` + `useEffect` 패턴 (useSupabase.ts)
- 모듈 레벨 상수 정의 패턴 유지 (symbolTableColumns 등)
- 새 패키지 추가 지양 (Ant Design 내장 기능 우선 사용)
- 컴포넌트 파일 분리 최소화 (기존 파일 내에서 해결)

## Verification Wave (각 Task 완료 후)
- `npx tsc --noEmit` — 타입 에러 없음
- `npx vite build` — 빌드 성공
- 브라우저에서 Drawer 열기/닫기 정상 작동
- Dashboard 실시간 시세 표시 정상 작동

---

## Tasks

<!-- TASKS_START -->

### Task 1: Drawer 조건부 마운트 — useSystemLogs 지연 로딩

**파일**: `frontend/src/hooks/useSupabase.ts`, `frontend/src/components/AppLayout.tsx`

**목표**: Drawer가 닫혀 있을 때 `useSystemLogs`의 데이터 fetch와 Supabase realtime 구독을 비활성화하여, 로그 INSERT가 AppLayout → Outlet → DashboardPage 리렌더 캐스케이드를 유발하지 않도록 한다.

**변경사항**:

#### 1-1. `useSystemLogs`에 `enabled` 파라미터 추가 (`useSupabase.ts`)

```typescript
// 시그니처 변경
export function useSystemLogs(date: string | null = null, limit = 500, enabled = true) {
```

- `enabled === false`일 때:
  - `fetchLogs()` 내부에서 early return (`setLogs([]); setLoading(false); return;`)
  - `useEffect` 내 Supabase channel 구독 스킵 (`if (!enabled || !isToday) return;`)
  - 기존 채널이 있으면 cleanup에서 제거 (기존 cleanup 로직 유지)
- `enabled === true`로 전환 시: 기존 로직대로 fetchLogs() 실행 + realtime 구독

구체적 수정 위치:
- `useSupabase.ts:92` — 함수 시그니처에 `enabled = true` 추가
- `useSupabase.ts:102-113` — `fetchLogs` 내부 첫 줄에 `if (!enabled) { setLogs([]); setLoading(false); return; }` 가드 추가
- `useSupabase.ts:115-135` — subscription useEffect의 deps에 `enabled` 추가, `if (!enabled) return;` 가드를 `fetchLogs()` 호출 전에 추가
- `useSupabase.ts:137-139` — recovery useEffect에 `if (!enabled)` 가드 추가

#### 1-2. AppLayout에서 조건부 호출 적용 (`AppLayout.tsx`)

```typescript
// 기존 (line 129):
const { logs, loading: logsLoading } = useSystemLogs(selectedDate);

// 변경:
const { logs, loading: logsLoading } = useSystemLogs(selectedDate, 500, drawerOpen);
```

**⚠️ 가드레일 — Badge 카운트**:
- `AppLayout.tsx:283`의 `<Badge count={logs.length}>` — Drawer 닫힘 시 `logs`가 빈 배열이 되므로 badge가 0으로 표시됨
- **확정 방침**: `count={logs.length}` 그대로 유지. Drawer 닫힘 시 0 표시는 의도된 동작. Drawer 열리면 fetch 완료 후 자동 갱신됨.

**QA**:
- Dashboard 페이지 로드 후 Network 탭에서 `system_logs` 요청이 없어야 함
- Drawer 열기 → `system_logs` 요청 발생 확인
- Drawer 닫기 → Supabase channel unsubscribe 확인 (콘솔 로그 없음)
- Drawer 닫힌 상태에서 DashboardPage가 불필요하게 리렌더되지 않음 (React DevTools Profiler)

---

### Task 2: Drawer 로그 리스트 가상화

**파일**: `frontend/src/components/AppLayout.tsx`

**목표**: 최대 500개 로그를 한 번에 DOM에 렌더링하지 않고 가시 영역만 렌더링하여 Drawer 열림 시 초기 렌더 비용을 줄인다.

**변경사항**:

#### 2-1. Ant Design `List` 컴포넌트의 virtual 모드 활용 또는 직접 windowing 구현

Ant Design v6의 `<List>` 컴포넌트는 `virtual` prop을 지원하지만 스타일 커스터마이징이 제한적이므로, **`height` + `overflow: auto` + CSS `content-visibility: auto`** 조합으로 경량 가상화를 적용한다.

**접근법 A (권장 — CSS content-visibility)**:
- `AppLayout.tsx:442-479`의 `logs.map()` 블록을 감싸는 컨테이너에 스크롤 영역 설정
- 각 로그 행 `<div>` (`AppLayout.tsx:445-477`)에 CSS `content-visibility: auto` + `contain-intrinsic-size: auto 36px` 적용
- 이 방식은 **라이브러리 추가 없이** 브라우저 네이티브 렌더링 최적화를 활용

구체적 수정:
```typescript
// AppLayout.tsx:430 — 로그 리스트 컨테이너
<div style={{
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  fontSize: 12,
  height: 'calc(100vh - 120px)',  // Drawer 헤더 제외한 높이
  overflowY: 'auto',
}}>
```

```typescript
// AppLayout.tsx:445-477 — 각 로그 행에 content-visibility 추가
<div
  key={log.id}
  style={{
    // ... 기존 스타일 유지 ...
    contentVisibility: 'auto',
    containIntrinsicSize: 'auto 36px',
  }}
>
```

**QA**:
- 500개 로그 로드 후 Drawer 열기 → 초기 렌더 시간이 이전 대비 감소
- 스크롤 시 로그가 정상적으로 표시됨
- 새 로그 realtime 도착 시 목록 상단에 정상 추가됨
- Chrome DevTools Performance 탭에서 Drawer 열기 시 Scripting 시간 감소 확인

---

### Task 3: DashboardPage Table 리렌더 격리 — Ticker 데이터 디커플링

**파일**: `frontend/src/pages/DashboardPage.tsx`

**목표**: 500ms마다 발생하는 ticker 업데이트로 인한 DashboardPage 리렌더가 Drawer/Tooltip 같은 urgent 인터랙션을 블로킹하지 않도록 한다.

**확정 접근법**: `useDeferredValue` (React 19 네이티브)

코드 변경이 최소이며, React 19의 `useDeferredValue`가 Drawer 열기 같은 urgent 업데이트를 ticker 리렌더보다 우선 처리하게 해준다. tickersRef + column override 방식은 복잡도 대비 이득이 적으므로 채택하지 않는다.

**변경사항**:

#### 3-1. `useDeferredValue`로 ticker 업데이트 우선순위 낮추기

```typescript
// DashboardPage.tsx — import 추가
import { useState, useRef, useMemo, useDeferredValue } from 'react';

// DashboardPage 컴포넌트 본문 (line 514 이후)
const { tickers } = useUpbitTicker(allSymbols);
const deferredTickers = useDeferredValue(tickers);  // 추가
```

#### 3-2. `allRows` useMemo에서 `tickers` → `deferredTickers` 교체

```typescript
// DashboardPage.tsx:537-559 — deps 배열에서 tickers를 deferredTickers로 교체
const allRows = useMemo<SymbolRow[]>(() => {
  const extraHeld = heldSymbols.filter((s) => !topSymbols.includes(s));
  return [
    ...topSymbols.map((symbol, idx) => ({
      key: symbol,
      rank: idx + 1,
      symbol,
      indicators: parseInd(rawIndMap[symbol]),
      pos: heldPositions.get(symbol) ?? null,
      snap: latestSnapshots.get(symbol) ?? null,
      ticker: deferredTickers.get(symbol) ?? null,  // deferredTickers 사용
    })),
    ...extraHeld.map((symbol) => ({
      key: symbol,
      rank: null as number | null,
      symbol,
      indicators: parseInd(rawIndMap[symbol]),
      pos: heldPositions.get(symbol) ?? null,
      snap: latestSnapshots.get(symbol) ?? null,
      ticker: deferredTickers.get(symbol) ?? null,  // deferredTickers 사용
    })),
  ];
}, [topSymbols, heldSymbols, rawIndMap, heldPositions, latestSnapshots, deferredTickers]);
//                                                                      ^^^^^^^^^^^^^^^^^
```

**동작 원리**: `useDeferredValue`는 `tickers`가 변경되어도 현재 진행 중인 urgent 렌더(Drawer 열림 애니메이션 등)가 완료될 때까지 `deferredTickers` 업데이트를 지연시킨다. 유저 인터랙션이 없는 idle 상태에서는 거의 즉시 반영되므로 시세 표시에 체감 차이 없음.

**QA**:
- React DevTools Profiler에서 5초 녹화 → Table 컴포넌트 렌더 횟수가 기존 ~10회에서 크게 감소
- 또는 `useDeferredValue` 적용 시: Drawer 열기/닫기 중 ticker 업데이트가 지연되어 애니메이션이 부드러움
- 실시간 시세가 여전히 ~500ms 간격으로 업데이트됨 (기능 회귀 없음)
- 수익률, 손절가, 익절가 표시가 정확함

---

### Task 4: Tooltip 최적화

**파일**: `frontend/src/components/AppLayout.tsx`, `frontend/src/pages/DashboardPage.tsx`

**목표**: 불필요한 Tooltip DOM 노드 누적을 방지하고, Drawer 내부 Tooltip의 렌더링 비용을 줄인다.

**변경사항**:

#### 4-1. AppLayout Header Tooltip에 `destroyTooltipOnHide` 적용

`AppLayout.tsx`의 Header 영역 Tooltip 5개 (lines 221, 236, 251, 266, 282, 350)에 prop 추가:

```typescript
// 각 <Tooltip> 에 추가
<Tooltip title={...} destroyTooltipOnHide>
```

수정 대상 라인:
- `AppLayout.tsx:221` — 업비트 상태 Tooltip
- `AppLayout.tsx:236` — 카카오 상태 Tooltip
- `AppLayout.tsx:251` — API 사용량 Tooltip
- `AppLayout.tsx:266` — Heartbeat Tooltip
- `AppLayout.tsx:282` — 백엔드 로그 Tooltip
- `AppLayout.tsx:350` — Drawer 내부 로그 유형 안내 Tooltip

#### 4-2. DashboardPage 테이블 헤더 Tooltip — 변경 없음

`symbolTableColumns`의 6개 헤더 Tooltip은 **모듈 레벨 상수**로 정의되어 있어 컴포넌트 리렌더와 무관하게 안정적이다. 이들은 변경하지 않는다.

**QA**:
- Tooltip hover → unhover 후 DOM에서 tooltip 노드가 제거됨 (Elements 패널에서 확인)
- 모든 Tooltip이 정상적으로 표시됨 (내용, 위치)
- Drawer 내부 InfoCircle Tooltip도 정상 작동

---

### Task 5: Route-level Code Splitting

**파일**: `frontend/src/App.tsx`

**목표**: 각 페이지를 lazy import하여 초기 번들 크기를 줄이고, 라우트 전환 시 필요한 코드만 로드한다.

**변경사항**:

#### 5-1. Eager import → React.lazy 전환

```typescript
// 기존 (App.tsx:7-13):
import DashboardPage from './pages/DashboardPage';
import TradingPage from './pages/TradingPage';
import AnalyticsPage from './pages/AnalyticsPage';
import SettingsPage from './pages/SettingsPage';
import ReportsPage from './pages/ReportsPage';

// 변경:
import { lazy, Suspense } from 'react';
import { Spin } from 'antd';

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const TradingPage = lazy(() => import('./pages/TradingPage'));
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
```

#### 5-2. Suspense fallback 추가

```typescript
// App.tsx — RequireAuth 내부 또는 AppLayout 감싸기
<RequireAuth>
  <Suspense fallback={
    <div style={{ textAlign: 'center', padding: 80 }}>
      <Spin size="large" />
    </div>
  }>
    <AppLayout />
  </Suspense>
</RequireAuth>
```

주의: `LoginPage`와 `AuthCallbackPage`는 lazy 적용하지 않음 (초기 로드 경로).

**QA**:
- `npx vite build` 출력에서 별도 chunk 파일 생성 확인 (TradingPage, AnalyticsPage 등)
- 각 라우트 네비게이션 시 해당 chunk가 Network 탭에서 로드됨
- 라우트 전환 시 Spin 로딩이 잠시 표시된 후 페이지 로드

---

### Task 6: 최종 검증 및 정리

**파일**: 전체

**목표**: 모든 변경사항의 통합 검증 및 빌드 확인

**체크리스트**:
1. `npx tsc --noEmit` — 타입 에러 0건
2. `npx vite build` — 빌드 성공, 별도 chunk 생성 확인
3. 브라우저 통합 테스트:
   - Dashboard 로드 → 실시간 시세 업데이트 정상
   - Drawer 열기 → 로그 정상 표시, 애니메이션 부드러움
   - Drawer 닫기 → 후속 리렌더 없음
   - Tooltip hover/unhover → 지연 없이 즉시 표시/소멸
   - 각 라우트 네비게이션 → 정상 전환
4. Chrome DevTools Performance 탭에서 Drawer 열기/닫기 시 Long Task 없음 (50ms 미만)

<!-- TASKS_END -->

## Final Verification Wave

모든 Task 완료 후:
1. `npx tsc --noEmit` 통과
2. `npx vite build` 통과
3. 기능 회귀 없음 확인 (실시간 시세, 로그, 차트)
