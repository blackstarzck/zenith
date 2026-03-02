# Plan: Antd Tooltip Deprecated Props 수정

## 개요
DashboardPage.tsx에서 antd v6에서 deprecated된 `overlayStyle` / `overlayInnerStyle` prop을 `styles` prop으로 교체한다.

## 배경
- 브라우저 콘솔에 `Warning: antd: Tooltip 'overlayStyle' is deprecated.` 경고 발생
- antd v6.3.0 공식 문서 확인 결과: `overlayStyle`, `overlayInnerStyle`, `overlayClassName` 모두 deprecated
- 대체 API: `styles` prop (semantic keys: `root`, `container`, `title`, `content`, `arrow`)
- 매핑: `overlayStyle` → `styles.root` / `overlayInnerStyle` → `styles.container`

## 범위
- **IN**: `frontend/src/pages/DashboardPage.tsx` — Tooltip 2개의 deprecated prop 교체
- **OUT**: 상수명 변경 (HEADER_TOOLTIP_STYLE, HEADER_TOOLTIP_INNER_STYLE는 유지), PRD.md 수정, 다른 파일 수정

---

## Tasks

### Task 1: Tooltip deprecated props → styles prop 교체

- **파일**: `frontend/src/pages/DashboardPage.tsx`
- **Category**: `quick`
- **Skills**: `[]`
- **Depends On**: 없음

#### 변경 내용

**변경 위치 A — 시장 레짐 Tooltip (라인 ~891-894)**

```tsx
// BEFORE
<Tooltip
  destroyOnHidden
  overlayStyle={HEADER_TOOLTIP_STYLE}
  overlayInnerStyle={HEADER_TOOLTIP_INNER_STYLE}
  title={(...)}
>

// AFTER
<Tooltip
  destroyOnHidden
  styles={{ root: HEADER_TOOLTIP_STYLE, container: HEADER_TOOLTIP_INNER_STYLE }}
  title={(...)}
>
```

**변경 위치 B — Kelly 비중 Tooltip (라인 ~933-936)**

```tsx
// BEFORE
<Tooltip
  destroyOnHidden
  overlayStyle={HEADER_TOOLTIP_STYLE}
  overlayInnerStyle={HEADER_TOOLTIP_INNER_STYLE}
  title={(...)}
>

// AFTER
<Tooltip
  destroyOnHidden
  styles={{ root: HEADER_TOOLTIP_STYLE, container: HEADER_TOOLTIP_INNER_STYLE }}
  title={(...)}
>
```

#### 가드레일 (MUST NOT)
- 상수 `HEADER_TOOLTIP_STYLE`, `HEADER_TOOLTIP_INNER_STYLE` 정의(라인 61-69) 수정 금지
- `destroyOnHidden`, `title`, 자식 요소 등 다른 prop 수정 금지
- DashboardPage.tsx 외 다른 파일 수정 금지
- 인접 코드 리팩토링 금지

#### QA / 검증 기준
1. `grep -rn "overlayStyle\|overlayInnerStyle\|overlayClassName" frontend/src/` → **0건** (deprecated prop 완전 제거 확인)
2. `grep -n "styles={{" frontend/src/pages/DashboardPage.tsx` → **정확히 2건** (새 styles prop 존재 확인)
3. `cd frontend && npx tsc --noEmit` → 정상 종료 (TypeScript 컴파일 에러 없음)
4. `cd frontend && npx eslint src/pages/DashboardPage.tsx` → 정상 종료 (린트 에러 없음)

---

## Final Verification Wave

모든 Task 완료 후 아래 검증 일괄 수행:

```bash
# 1. deprecated prop 잔존 여부
cd frontend && grep -rn "overlayStyle\|overlayInnerStyle\|overlayClassName" src/
# 기대: 출력 없음

# 2. 새 styles prop 존재 확인
cd frontend && grep -n "styles={{" src/pages/DashboardPage.tsx
# 기대: 정확히 2줄

# 3. TypeScript 컴파일
cd frontend && npx tsc --noEmit
# 기대: exit code 0

# 4. ESLint
cd frontend && npx eslint src/pages/DashboardPage.tsx
# 기대: exit code 0
```
