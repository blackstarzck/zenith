# Plan: 매도 스코어를 거래대금 상위 종목 테이블에 표시

## Goal
보유 종목의 매도(exit) 스코어를 프론트엔드 대시보드의 "거래대금 상위 종목" 테이블에 컬럼으로 추가하여, 각 종목의 청산 스코어 현황을 실시간으로 확인할 수 있도록 한다.

## Scope
- **IN**: 백엔드 exit score 수집·저장, 프론트엔드 exit score 컬럼 표시
- **OUT**: 다른 페이지(TradingPage, AnalyticsPage 등) 표시, DB 스키마 변경, `evaluate_exit()` 반환 타입 변경

## Architecture Decision
- DB 스키마 변경 없이 기존 `bot_state.symbol_volatilities` JSONB 컬럼에 exit score 데이터를 병합 저장
- 매도 스코어는 `entry_price`가 필요하므로 반드시 백엔드에서 계산 (클라이언트 계산 불가)
- 기존 진입 스코어 UI 패턴(색상 숫자 + 툴팁 breakdown)을 미러링

## Critical Guard: 데이터 덮어쓰기 방지
`_tick()` 실행 순서: `_evaluate_exits()` → `_evaluate_entries()`.
`_evaluate_entries()`가 `symbol_indicators` 딕셔너리를 새로 생성하여 `upsert_bot_state(symbol_volatilities=...)`로 **완전 교체** 저장한다.
따라서 `_evaluate_exits()`에서 별도로 `upsert_bot_state()`를 호출하면 즉시 덮어써진다.

**해결책**: 2-Phase Instance Variable 패턴
- Phase 1 (`_evaluate_exits()`): exit scores를 `self._exit_scores` 인스턴스 변수에 임시 저장
- Phase 2 (`_evaluate_entries()`): `upsert_bot_state()` 호출 직전에 `self._exit_scores`를 `symbol_indicators`에 병합

## Files to Modify (3 files)

| File | Change Summary |
|------|----------------|
| `src/orchestrator.py` | `self._exit_scores` 초기화, exit 평가 시 수집, entry 평가 시 병합 |
| `frontend/src/types/database.ts` | `SymbolIndicators`에 optional exit score 필드 추가 |
| `frontend/src/pages/DashboardPage.tsx` | exit score 컬럼 추가, `parseInd()` 하위호환 유지 |

## Tasks

### TODO 1: `src/orchestrator.py` — `__init__`에 `self._exit_scores` 초기화

**파일**: `src/orchestrator.py`
**위치**: `__init__` 메서드, `self._regime_changed_at` 초기화 라인(68번) 부근

**작업**:
- `self._exit_scores: dict[str, dict] = {}` 추가
- 기존 인스턴스 변수 블록(`self._stop_loss_timestamps`, `self._entry_blocked_until`, `self._regime_changed_at`) 바로 아래에 추가

**코드**:
```python
# 매도 스코어 임시 저장 (tick 내 2-phase 병합용)
self._exit_scores: dict[str, dict] = {}
```

**QA**:
- `python -c "from src.orchestrator import Orchestrator"` 임포트 에러 없음 확인

---

### TODO 2: `src/orchestrator.py` — `_evaluate_exits()`에서 exit score 수집

**파일**: `src/orchestrator.py`
**위치**: `_evaluate_exits()` 메서드, `signal = self._strategy.evaluate_exit(...)` 호출 직후 (282번 라인 이후)

**작업**:
- `evaluate_exit()` 호출 후, signal의 score와 개별 컴포넌트 점수를 `self._exit_scores[symbol]`에 저장
- `has_sold_half=True`인 경우 score가 None이고 트레일링 대기 상태 → `exit_status: "trailing"` 표시
- 하드 룰(STOP_LOSS, trailing stop) 발동 시에도 score가 None → 동일하게 처리
- 개별 컴포넌트 점수는 엔진의 private 헬퍼를 직접 호출하여 추출 (이미 같은 snapshot 데이터 사용)

**코드 — `signal = self._strategy.evaluate_exit(...)` 바로 아래에 추가**:
```python
# 매도 스코어 수집 (Phase 1: 임시 저장 → _evaluate_entries에서 병합)
if signal.score is not None:
    self._exit_scores[symbol] = {
        "exit_score": round(signal.score, 1),
        "exit_rsi": round(self._strategy._score_exit_rsi_level(snapshot.rsi), 0),
        "exit_bb": round(self._strategy._score_exit_bb_position(snapshot.current_price, snapshot.bb), 0),
        "exit_profit": round(self._strategy._score_exit_profit(snapshot.current_price, pos.entry_price), 0),
        "exit_adx": round(self._strategy._score_exit_adx(snapshot.adx), 0),
    }
else:
    self._exit_scores[symbol] = {"exit_score": None, "exit_status": "trailing"}
```

**주의사항**:
- `self._strategy._score_exit_*` 메서드는 private이지만, 같은 프로젝트 내부 호출이므로 허용 (Python convention)
- `snapshot.bb`는 `BollingerBands` namedtuple — `_score_exit_bb_position(price, bb)` 시그니처에 그대로 전달
- 이 블록은 기존 `if signal.signal == Signal.STOP_LOSS:` 분기 **이전**에 위치해야 함 (매도 실행 전에 score 수집)

**QA**:
- `_evaluate_exits()` 내에서 `self._exit_scores`에 보유 종목 수만큼 데이터가 쌓이는지 로그로 확인 가능
- STOP_LOSS 발동 시에도 score 수집 후 매도가 진행되어야 함 (순서 중요)

---

### TODO 3: `src/orchestrator.py` — `_evaluate_entries()`에서 exit scores 병합

**파일**: `src/orchestrator.py`
**위치**: `_evaluate_entries()` 메서드, `if symbol_indicators:` 블록 (424-425번 라인) 직전

**작업**:
1. `self._exit_scores`의 데이터를 `symbol_indicators`에 병합
2. 보유 종목이 `self._target_symbols`에 없는 경우(extraHeld), exit score만으로 최소 엔트리 생성
3. 더 이상 보유하지 않는 종목의 stale exit score 자동 제거 (positions에 없으면 skip)
4. 병합 후 `self._exit_scores.clear()` 호출

**코드 — `if symbol_indicators:` 라인 바로 위에 추가**:
```python
# Phase 2: 매도 스코어 병합 (exit scores → symbol_indicators)
positions = self._risk.get_all_positions()
for sym, exit_data in self._exit_scores.items():
    if sym not in positions:
        continue  # 이미 매도된 종목의 stale 데이터 무시
    if sym in symbol_indicators:
        symbol_indicators[sym].update(exit_data)
    else:
        # 보유 종목이 상위 종목에 없는 경우 (extraHeld)
        symbol_indicators[sym] = exit_data
self._exit_scores.clear()
```

**주의사항**:
- `self._risk.get_all_positions()`는 이미 `_evaluate_exits()`에서 호출된 동일 데이터 — 추가 API 호출 없음
- `symbol_indicators`가 비어있어도 `self._exit_scores`에 데이터가 있으면 병합 후 저장되어야 함
- 기존 `if symbol_indicators:` 조건문도 exit_scores 병합 후에는 True가 될 수 있으므로, 병합 코드는 반드시 그 **위**에 위치

**QA**:
- 보유 종목이 상위 10개에 포함된 경우: `symbol_indicators[sym]`에 기존 진입 지표 + exit score가 모두 존재
- 보유 종목이 상위 10개에 미포함인 경우: `symbol_indicators[sym]`에 exit score만 존재
- 비보유 종목: exit score 필드 없음

---

### TODO 4: `frontend/src/types/database.ts` — `SymbolIndicators` 타입 확장

**파일**: `frontend/src/types/database.ts`
**위치**: `SymbolIndicators` 인터페이스 (36-43번 라인)

**작업**:
- 기존 6개 필드 유지, 5개 optional exit score 필드 추가

**코드 — `adx: number;` 라인 아래에 추가**:
```typescript
  // 매도 스코어 (보유 종목에만 존재, 백엔드에서 계산)
  exit_score?: number | null;    // 매도 가중합산 점수 (0~100), null이면 트레일링 대기
  exit_rsi?: number;             // RSI 과매수 스코어 (0~100)
  exit_bb?: number;              // BB 상단 접근 스코어 (0~100)
  exit_profit?: number;          // 수익률 스코어 (0~100)
  exit_adx?: number;             // ADX 추세 강도 스코어 (0~100)
  exit_status?: string;          // "trailing" = 트레일링 스탑 대기 중
```

**QA**:
- `npx tsc --noEmit` (frontend 디렉토리) — 타입 에러 없음
- 기존 코드에서 `SymbolIndicators`를 사용하는 모든 곳이 optional 필드 추가에 영향받지 않음 확인

---

### TODO 5: `frontend/src/pages/DashboardPage.tsx` — `parseInd()` 하위호환 유지

**파일**: `frontend/src/pages/DashboardPage.tsx`
**위치**: `parseInd()` 함수 (66-72번 라인)

**작업**:
- 기존 로직 유지 — exit 필드가 없는 데이터도 정상 파싱됨 (optional이므로 자동 호환)
- 이전 형식(number만 저장) fallback 분기에서 exit 필드가 없는 건 당연하므로 변경 불필요

**확인만**: `parseInd()`는 변경할 필요 없음. TypeScript의 optional 필드는 존재하지 않으면 `undefined`로 처리됨.

**QA**:
- 기존 데이터(exit 필드 없음)로 `parseInd()` 호출 시 에러 없음
- 새 데이터(exit 필드 포함)로 `parseInd()` 호출 시 exit 필드가 정상적으로 포함됨

---

### TODO 6: `frontend/src/pages/DashboardPage.tsx` — 매도 스코어 컬럼 추가

**파일**: `frontend/src/pages/DashboardPage.tsx`
**위치**: `buildBaseSymbolColumns()` 함수, 기존 진입 스코어 컬럼(376-435번 라인) 바로 뒤

**작업**:
- 기존 진입 스코어 컬럼 패턴을 미러링하여 매도 스코어 컬럼 추가
- 보유 종목만 스코어 표시, 비보유는 "-"
- `exit_status === "trailing"`이면 "트레일링" 텍스트 표시
- `exit_score`가 숫자이면 색상 표시 + 툴팁 breakdown
- 색상 기준: `exit_score_threshold` 이상 = 빨강(매도 임박), 근접 = 주황, 미달 = 초록
- 매도 스코어는 높을수록 매도에 가까우므로 **색상 반전** (진입은 높을수록 초록, 매도는 높을수록 빨강)

**코드 — 진입 스코어 컬럼 객체 닫는 `}` 뒤, `];` 이전에 추가**:
```tsx
{
  title: (
    <Space size={4}>
      <span>매도</span>
      <Tooltip destroyOnHidden
        title={
          <div>
            <div>청산 스코어 (가중치 합산)</div>
            <div style={{ marginTop: 6 }}>
              <span style={{ color: '#cf1322' }}>■</span> 임계치 이상 — 매도 임박
            </div>
            <div>
              <span style={{ color: '#fa8c16' }}>■</span> 임계치 -15 이상 — 주의
            </div>
            <div>
              <span style={{ color: '#389e0d' }}>■</span> 미달 — 보유 유지
            </div>
          </div>
        }
      >
        <InfoCircleOutlined style={{ fontSize: 11, color: '#999', cursor: 'pointer' }} />
      </Tooltip>
    </Space>
  ),
  dataIndex: 'indicators',
  width: 75,
  align: 'center' as const,
  render: (_: unknown, record: SymbolRow) => {
    const ind = record.indicators;
    // 비보유 종목 또는 지표 없음
    if (!ind || !record.pos) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;

    // 트레일링 스탑 대기 중
    if (ind.exit_status === 'trailing') {
      return <Text style={{ fontSize: 11, color: '#1890ff', fontWeight: 500 }}>트레일링</Text>;
    }

    const exitScore = ind.exit_score;
    if (exitScore == null) return <Text type="secondary" style={{ fontSize: 12 }}>-</Text>;

    const weights = strategyParams ?? DEFAULT_STRATEGY;
    const exitThreshold = weights.exit_score_threshold ?? 70;

    // 매도 스코어: 높을수록 매도 임박 → 빨강
    const color = exitScore >= exitThreshold ? '#cf1322' : exitScore >= exitThreshold - 15 ? '#fa8c16' : '#389e0d';

    const breakdown: Record<string, { weight: number; score: number }> = {
      'RSI↑': { weight: weights.w_exit_rsi_level ?? 1.0, score: ind.exit_rsi ?? 0 },
      'BB↑': { weight: weights.w_exit_bb_position ?? 1.0, score: ind.exit_bb ?? 0 },
      '수익': { weight: weights.w_exit_profit_pct ?? 1.0, score: ind.exit_profit ?? 0 },
      'ADX': { weight: weights.w_exit_adx_trend ?? 1.0, score: ind.exit_adx ?? 0 },
    };

    return (
      <Tooltip destroyOnHidden
        title={
          <div style={{ minWidth: 120 }}>
            {Object.entries(breakdown).map(([name, { weight, score }]) => (
              <div key={name} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                <span>{name}:</span>
                <span>{Math.round(score)} (×{weight.toFixed(1)})</span>
              </div>
            ))}
            <div style={{ borderTop: '1px solid #444', marginTop: 6, paddingTop: 6, textAlign: 'right' }}>
              임계치: {exitThreshold.toFixed(1)}
            </div>
          </div>
        }
      >
        <Text style={{ fontSize: 12, color, fontWeight: 600, cursor: 'help' }}>
          {Math.round(exitScore)}
        </Text>
      </Tooltip>
    );
  },
},
```

**주의사항**:
- `strategyParams`는 `buildBaseSymbolColumns`의 매개변수로 이미 클로저 스코프에 있음
- `DEFAULT_STRATEGY` import는 이미 존재 (33번 라인)
- `exit_score_threshold`, `w_exit_*` 가중치는 `StrategyParams` 타입에 이미 정의되어 있음 (`strategyParams.ts:19-23`)
- `SYMBOL_TABLE_SCROLL`의 `x: 1200`을 `x: 1280`으로 증가시켜 새 컬럼 공간 확보

**QA**:
- 비보유 종목: "-" 표시
- 보유 종목 + 스코어 있음: 숫자 + 색상 + 툴팁 breakdown
- 보유 종목 + 트레일링 대기: "트레일링" 파란색 텍스트
- 보유 종목 + 데이터 없음: "-" 표시
- 툴팁에 4개 컴포넌트 breakdown + 임계치 표시

---

### TODO 7: `frontend/src/pages/DashboardPage.tsx` — 테이블 스크롤 너비 조정

**파일**: `frontend/src/pages/DashboardPage.tsx`
**위치**: `SYMBOL_TABLE_SCROLL` 상수 (616번 라인)

**작업**:
- `x: 1200` → `x: 1280`으로 변경 (매도 스코어 컬럼 75px 추가 반영)

**코드**:
```typescript
const SYMBOL_TABLE_SCROLL = { x: 1280 } as const;
```

**QA**:
- 테이블 가로 스크롤이 모든 컬럼을 커버하는지 확인

---

## Final Verification Wave

모든 TODO 완료 후:

1. **백엔드 임포트 검증**: `python -c "from src.orchestrator import Orchestrator; print('OK')"`
2. **프론트엔드 타입 검증**: `cd frontend && npx tsc --noEmit`
3. **프론트엔드 린트 검증**: `cd frontend && npx eslint src/pages/DashboardPage.tsx src/types/database.ts`
4. **영향받는 파일 3개, 모두 반영 완료** 확인

## Defaults Applied
- 매도 스코어 색상: 높을수록 빨강 (매도 임박 = 위험 신호) — 진입 스코어와 반대
- `has_sold_half` 상태: "트레일링" 파란색 텍스트로 표시
- 테이블 스크롤 너비: +80px (1200 → 1280)
