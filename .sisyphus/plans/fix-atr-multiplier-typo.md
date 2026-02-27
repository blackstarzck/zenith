# Plan: fix-atr-multiplier-typo

> DashboardPage.tsx의 `atr_multiplier` 타입 불일치 버그 수정

## Context

`frontend/src/pages/DashboardPage.tsx` 563번줄에서 `StrategyParams` 초기값 설정 시
존재하지 않는 필드명 `atr_multiplier`를 사용하고 있음.
정식 필드명은 `atr_stop_multiplier` (StrategyEditModal.tsx, strategyParams.ts, config.py 모두 일치).

### Evidence

| 파일 | 줄 | 필드명 | 상태 |
|------|-----|--------|------|
| `frontend/src/components/StrategyEditModal.tsx` | 26 | `atr_stop_multiplier: number` | ✅ 정식 타입 정의 |
| `frontend/src/lib/strategyParams.ts` | 10 | `atr_stop_multiplier: 2.5` | ✅ 올바름 |
| `src/config.py` | 50 | `atr_stop_multiplier: float = 2.5` | ✅ 올바름 |
| `frontend/src/pages/DashboardPage.tsx` | 563 | `atr_multiplier: 2.5` | ❌ **잘못된 필드명** |

## Scope

- **IN**: DashboardPage.tsx 563번줄 1개 토큰 수정
- **OUT**: 같은 파일의 다른 문제 (예: `top_volume_count` 누락 — 별도 이슈), 다른 파일

## Constraints

- 정확히 1파일, 1줄, 1토큰만 수정
- 인접 줄 리포맷/리팩터링 금지
- 이미 올바른 파일(StrategyEditModal.tsx, strategyParams.ts, config.py) 수정 금지

---

## TODO-01: `atr_multiplier` → `atr_stop_multiplier` 타입 오류 수정

- **Category**: `quick`
- **Skills**: `[]`
- **Depends**: 없음
- **File**: `frontend/src/pages/DashboardPage.tsx`
- **Line**: 563

### What

563번줄의 `atr_multiplier: 2.5`를 `atr_stop_multiplier: 2.5`로 변경.

### Before (현재 코드)

```tsx
// Line 561-564
const [currentStrategyParams, setCurrentStrategyParams] = useState<StrategyParams>({
  bb_period: 20, bb_std_dev: 2.0, rsi_period: 14, rsi_oversold: 30,
  atr_period: 14, atr_multiplier: 2.5,
});
```

### After (수정 후)

```tsx
// Line 561-564
const [currentStrategyParams, setCurrentStrategyParams] = useState<StrategyParams>({
  bb_period: 20, bb_std_dev: 2.0, rsi_period: 14, rsi_oversold: 30,
  atr_period: 14, atr_stop_multiplier: 2.5,
});
```

### QA

```bash
# 1. 잘못된 필드명이 사라졌는지 확인
grep "atr_multiplier" frontend/src/pages/DashboardPage.tsx
# 기대: 출력 없음 (atr_stop_multiplier만 매칭되면 안 됨 — 정확한 패턴 사용)

# 2. 올바른 필드명이 있는지 확인
grep "atr_stop_multiplier" frontend/src/pages/DashboardPage.tsx
# 기대: 563번줄에 atr_stop_multiplier: 2.5 출력

# 3. TypeScript 컴파일 확인 (frontend/ 디렉토리에서 실행)
npx tsc --noEmit 2>&1 | findstr "atr_multiplier"
# 기대: 출력 없음 (이 필드 관련 TS 에러 제거됨)
```

---

## Final Verification Wave

모든 TODO 완료 후:

1. `npx tsc --noEmit` 실행 → `atr_multiplier` 관련 에러 0건 확인
2. 기존 TS 에러가 있을 수 있으나, 이 수정과 무관한 에러는 범위 밖

---

## Notes

- **Metis 지적**: `currentStrategyParams` 초기값에 `top_volume_count`가 누락되어 있음 → 별도 이슈로 분리 (이 계획 범위 밖)
- 이 버그는 Market Regime Detector 작업과 무관한 기존 버그
