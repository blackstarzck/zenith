# Plan: 프리셋 저장 버그 수정 + UI 활성 표시 통합

## 배경

프론트엔드에서 프리셋을 선택하면 `saveStrategyParams()`가 호출되어 Supabase `bot_state.strategy_params`에 저장해야 하나, **실제로 DB에 값이 기록되지 않음**. 새로고침 시 기본값으로 돌아가고, 활성 프리셋 표시도 사라짐.

## 근본 원인

`saveStrategyParams()`가 `supabase.from('bot_state').upsert()`를 사용 중.
Supabase의 `upsert`는 내부적으로 `INSERT ... ON CONFLICT UPDATE`를 실행.
RLS가 활성화된 `anon` 키 환경에서 INSERT 권한 평가 과정에서 **에러 없이 조용히 무시(silently ignored)** 되는 것이 원인.

**해결책**: `upsert` → `update().eq('id', 1)`로 변경. `bot_state` 테이블은 단일 행(id=1)이 항상 존재하므로 INSERT가 필요 없음. UPDATE만 수행하면 RLS 문제를 회피.

## 영향도 분석

- `saveStrategyParams()`는 `frontend/src/lib/strategyParams.ts`에 정의
- 호출처 3곳:
  1. `SettingsPage.tsx` — 프리셋 버튼 클릭 시 (L244, L267), 파라미터 저장 버튼 (L70)
  2. `DashboardPage.tsx` — 모달 적용 시 (L815)
- 호출처는 수정 불필요 (함수 시그니처 동일)
- 백엔드 `src/storage/client.py`의 `upsert_bot_state()`는 **service_role 키**를 사용하므로 이 문제에 해당하지 않음 (수정 불필요)

## Docs 영향

없음. API 변경 없음, 스키마 변경 없음, 데이터 흐름 변경 없음.

---

## Tasks

### Task 1: saveStrategyParams — upsert → update 변경

**파일**: `frontend/src/lib/strategyParams.ts`
**위치**: L59-67 (`saveStrategyParams` 함수)

**현재 코드**:
```typescript
export async function saveStrategyParams(params: StrategyParams): Promise<boolean> {
  const { error } = await supabase
    .from('bot_state')
    .upsert(
      { id: 1, strategy_params: params, updated_at: new Date().toISOString() },
      { onConflict: 'id' },
    );
  return !error;
}
```

**변경할 코드**:
```typescript
export async function saveStrategyParams(params: StrategyParams): Promise<boolean> {
  const { error } = await supabase
    .from('bot_state')
    .update({ strategy_params: params, updated_at: new Date().toISOString() })
    .eq('id', 1);
  if (error) {
    console.error('[saveStrategyParams] 저장 실패:', error.message, error.details);
  }
  return !error;
}
```

**변경 포인트**:
1. `.upsert({ id: 1, ... }, { onConflict: 'id' })` → `.update({ ... }).eq('id', 1)`
2. `id: 1` 필드 제거 (update에서는 `.eq('id', 1)`로 조건 지정)
3. 에러 발생 시 `console.error`로 상세 로깅 추가 (디버깅용)

**QA**:
- 프리셋 클릭 → F12 Network 탭에서 PATCH 요청 확인 (기존 POST → PATCH로 변경됨)
- 응답 코드 200 + Supabase 대시보드에서 `strategy_params` 컬럼 값 확인
- 새로고침 후 설정값 유지 확인
- 대시보드 모달에서 적용 → 새로고침 → 값 유지 확인

### Task 2: 타입 체크 검증

**명령어**: `npx tsc --noEmit` (frontend 디렉토리에서 실행)
**기대 결과**: 에러 없음

## Final Verification Wave

- [ ] `npx tsc --noEmit` 통과
- [ ] 변경 파일 1개: `frontend/src/lib/strategyParams.ts`
- [ ] 호출처 3곳 시그니처 영향 없음 확인 (반환 타입 `Promise<boolean>` 동일)
