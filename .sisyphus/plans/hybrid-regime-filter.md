# 하이브리드 레짐 필터 구현

## 목표
현재 BTC ADX ≥ 25일 때 **모든 신규 진입을 하드 차단**하는 방식을, 레짐에 따라 `entry_score_threshold`를 **동적 가산(offset)**하는 하이브리드 방식으로 전환한다. 레짐 관련 파라미터 4개를 프론트엔드에서 조절 가능하게 노출한다.

## 배경
- 현재 문제: BTC ADX가 25만 넘으면 가동 시간의 ~95%가 진입 차단. 스코어가 70 넘어도 매수 불가.
- 스코어링 시스템에 이미 ADX/변동성 팩터가 포함되어 있어 이중 필터 상태.
- 하이브리드 방향: trending → threshold + offset, volatile → threshold + offset, ranging → 그대로.
- effective_threshold가 100을 초과하면 **99로 캡** (완전 차단 방지).

## 변경 파일 목록
| # | 파일 | 변경 유형 |
|---|------|-----------|
| 1 | `src/config.py` | 필드 추가 |
| 2 | `src/strategy/engine.py` | 시그니처 변경 + 로직 수정 |
| 3 | `src/orchestrator.py` | 하드 차단 제거 + offset 계산 |
| 4 | `frontend/src/components/StrategyEditModal.tsx` | interface 확장 + UI 섹션 추가 |
| 5 | `frontend/src/lib/strategyParams.ts` | DEFAULT + PRESETS + keys 업데이트 |
| 6 | `docs/Algorithm_Specification.md` | 진입 파이프라인 설명 업데이트 |

## Scope Boundary
### IN
- 레짐 판정 결과에 따른 **진입 행동** 변경 (하드 차단 → 동적 오프셋)
- 신규 파라미터 4개 추가 및 프론트엔드 노출
- 기존 4개 프리셋에 레짐 값 추가
- effective_threshold 99 캡 적용

### OUT (절대 금지)
- `regime.py`의 `classify_regime()` 분류 로직 수정
- `evaluate_exit()`에 레짐 오프셋 적용
- `regime_lookback_candles` 프론트엔드 노출
- 대시보드에 effective threshold 표시 기능 추가
- 프리셋 추가/삭제/이름 변경

## 파라미터 상세
| 파라미터 | 설명 | 기본값 | UI 범위 | 비고 |
|---------|------|-------|---------|------|
| `regime_adx_trending_threshold` | ADX 추세장 판정 기준 | 25.0 | 20~45 | 기존 (프론트엔드에만 추가) |
| `regime_vol_overload_ratio` | 변동성 폭발 판정 배율 | 2.0 | 1.5~4.0 | 기존 (프론트엔드에만 추가) |
| `regime_trending_offset` | 추세장 시 진입 임계치 가산 | 15.0 | 0~30 | **신규** |
| `regime_volatile_offset` | 변동성 폭발 시 진입 임계치 가산 | 25.0 | 0~30 | **신규** |

## 프리셋별 레짐 값
| 프리셋 | adx_threshold | vol_ratio | trending_offset | volatile_offset |
|--------|--------------|-----------|-----------------|-----------------|
| 보수적 | 25 | 2.0 | 20 | 30 |
| 공격적 | 25 | 2.0 | 5 | 10 |
| 횡보장 | 25 | 2.0 | 15 | 25 |
| 변동성 장세 | 25 | 2.0 | 10 | 15 |

---

## TODO

### TODO-1: `src/config.py` — 신규 필드 추가
- **파일**: `src/config.py`
- **위치**: `StrategyParams` 클래스, 기존 `regime_lookback_candles` 필드(line 83) 바로 아래
- **작업**: `@dataclass(frozen=True)` 필드 2개 추가
```python
# 하이브리드 레짐 오프셋 (레짐 상태별 진입 임계치 가산값)
regime_trending_offset: float = 15.0   # 추세장 시 entry_score_threshold에 가산
regime_volatile_offset: float = 25.0   # 변동성 폭발 시 entry_score_threshold에 가산
```
- **주의**: `regime_adx_trending_threshold`(25.0)와 `regime_vol_overload_ratio`(2.0)는 이미 존재. 추가하지 말 것.
- **검증**: `from_dict()`가 기존 DB 데이터(offset 필드 없음)에서 기본값 15.0/25.0을 적용하는지 확인. `from_dict()`는 `defaults = asdict(cls())`로 기본값을 채우므로 자동 호환됨.

### TODO-2: `src/strategy/engine.py` — `evaluate_entry()` 시그니처 변경
- **파일**: `src/strategy/engine.py`
- **작업 A**: `evaluate_entry()` 시그니처에 `threshold_offset` 파라미터 추가
- **위치**: line 61-66
```python
# Before:
def evaluate_entry(
    self,
    symbol: str,
    snapshot: IndicatorSnapshot,
    closes_series: "pd.Series | None" = None,
) -> TradeSignal:

# After:
def evaluate_entry(
    self,
    symbol: str,
    snapshot: IndicatorSnapshot,
    closes_series: "pd.Series | None" = None,
    threshold_offset: float = 0.0,
) -> TradeSignal:
```
- **작업 B**: effective_threshold 계산 + 99 캡 적용
- **위치**: line 112 (`if total_score >= params.entry_score_threshold:`) 바로 위에 삽입
```python
# ── effective threshold 계산 (레짐 오프셋 + 99 캡) ──
effective_threshold = min(params.entry_score_threshold + threshold_offset, 99.0)
```
- **작업 C**: 임계치 비교를 `effective_threshold`로 변경
- **위치**: line 112, line 128 (두 곳 모두 수정)
```python
# Before (line 112):
if total_score >= params.entry_score_threshold:

# After:
if total_score >= effective_threshold:
```
```python
# Before (line 128):
reason=f"{reason_str} < {params.entry_score_threshold:.1f}",

# After:
reason=f"{reason_str} < {effective_threshold:.1f}",
```
- **작업 D**: 로그 메시지에 offset 정보 포함
- **위치**: line 117 (`reason=f"{reason_str} ≥ ..."`) 수정
```python
# Before:
reason=f"{reason_str} ≥ {params.entry_score_threshold:.1f}",

# After (offset > 0일 때만 offset 표시):
reason=f"{reason_str} ≥ {effective_threshold:.1f}" + (f" (기본 {params.entry_score_threshold:.1f} + 레짐 {threshold_offset:+.0f})" if threshold_offset > 0 else ""),
```
- **MUST NOT**: `evaluate_exit()` 메서드는 절대 변경하지 않는다.
- **TOOL**: 변경 전 `lsp_find_references`로 `evaluate_entry` 호출부를 확인하여 backtest 등 다른 호출부가 있는지 체크. `threshold_offset`의 기본값이 0.0이므로 기존 호출부는 영향 없음.

### TODO-3: `src/orchestrator.py` — 하드 차단 제거 + offset 계산
- **파일**: `src/orchestrator.py`
- **작업 A**: `_evaluate_entries()` 내 하드 차단 코드 제거 + offset 계산으로 교체
- **위치**: line 282-289 (현재 하드 차단 블록 전체)
```python
# Before (line 282-289 전체 삭제):
        # 레짐 기반 진입 필터 (trending/volatile → 신규 진입 차단)
        if self._current_regime in ("trending", "volatile"):
            if self._loop_count % 60 == 1:  # 10분에 1번만 로그
                logger.info(
                    "[진입 차단] 시장 레짐 '%s' — 신규 진입 대기 중",
                    self._current_regime,
                )
            return

# After (동일 위치에 삽입):
        # 레짐 기반 threshold offset 계산 (하이브리드 필터)
        regime_offset = 0.0
        if self._current_regime == "trending":
            regime_offset = self._config.strategy.regime_trending_offset
        elif self._current_regime == "volatile":
            regime_offset = self._config.strategy.regime_volatile_offset

        if regime_offset > 0 and self._loop_count % 60 == 1:
            logger.info(
                "[레짐 오프셋] 시장 레짐 '%s' — 진입 임계치 +%.0f 적용 중",
                self._current_regime, regime_offset,
            )
```
- **작업 B**: `evaluate_entry()` 호출에 `threshold_offset` 전달
- **위치**: line 369-371
```python
# Before:
                signal = self._strategy.evaluate_entry(
                    symbol, snapshot, closes,
                )

# After:
                signal = self._strategy.evaluate_entry(
                    symbol, snapshot, closes,
                    threshold_offset=regime_offset,
                )
```
- **주의**: `_evaluate_exits()` (line 230)는 변경하지 않는다. 매도는 레짐과 무관하게 동작.
- **주의**: `regime_offset` 변수는 `_evaluate_entries()` 메서드 상단(종목 루프 바깥)에서 한 번만 계산. 종목별로 반복 계산하지 않는다.

### TODO-4: `frontend/src/components/StrategyEditModal.tsx` — interface 확장 + UI 섹션
- **파일**: `frontend/src/components/StrategyEditModal.tsx`
- **작업 A**: `StrategyParams` interface에 4개 필드 추가 (optional)
- **위치**: line 59 (`min_profit_margin?: number;`) 바로 아래
```typescript
  // 시장 레짐 설정
  regime_adx_trending_threshold?: number;
  regime_vol_overload_ratio?: number;
  regime_trending_offset?: number;
  regime_volatile_offset?: number;
```
- **작업 B**: "시장 레짐 설정" Divider 섹션 추가
- **위치**: "매도 상세 설정" 섹션(line 486-515)과 `</Form>` 사이에 삽입
- **UI 구조**: 기존 패턴(BB/RSI 섹션)을 따라 `Divider` + `Alert` 설명 + `Row/Col/InputNumber` + `Text` 설명 구성
- **TOOL**: `context7_query-docs`로 AntD 6의 `InputNumber` props 확인 후 사용
```
섹션 레이아웃:

<Divider> 시장 레짐 설정 </Divider>
<Alert> 설명: BTC 기준으로 시장 상태를 판단하여 진입 임계치를 동적으로 조정합니다. 추세장/변동성 폭발 시 임계치를 높여 더 확실한 기회만 포착합니다. </Alert>

Row 1 (gutter={16}):
  Col span={12}: ADX 추세장 기준 (InputNumber min=20 max=45 step=1)
    Form.Item name="regime_adx_trending_threshold"
    설명: "BTC의 ADX가 이 값 이상이면 추세장으로 판단합니다."
  Col span={12}: 변동성 폭발 기준 (InputNumber min=1.5 max=4.0 step=0.1)
    Form.Item name="regime_vol_overload_ratio"
    설명: "변동성 비율이 이 값 이상이면 변동성 폭발로 판단합니다."

Row 2 (gutter={16}):
  Col span={12}: 추세장 임계치 가산 (InputNumber min=0 max=30 step=1)
    Form.Item name="regime_trending_offset"
    설명: "추세장에서 진입 임계치를 이 값만큼 높입니다. 높을수록 진입이 어려워집니다."
  Col span={12}: 변동성 폭발 임계치 가산 (InputNumber min=0 max=30 step=1)
    Form.Item name="regime_volatile_offset"
    설명: "변동성 폭발 시 진입 임계치를 이 값만큼 높입니다. 높을수록 진입이 어려워집니다."
```
- **주의**: Slider가 아닌 InputNumber 사용 (범위가 좁고 정확한 값 입력이 중요하므로). 기존 BB/RSI/ATR 섹션 패턴과 동일.

### TODO-5: `frontend/src/lib/strategyParams.ts` — DEFAULT + PRESETS + keys 업데이트
- **파일**: `frontend/src/lib/strategyParams.ts`
- **작업 A**: `DEFAULT_STRATEGY`에 4개 필드 추가
- **위치**: line 26 (`min_profit_margin: 0.003,`) 바로 아래
```typescript
  // 시장 레짐 설정
  regime_adx_trending_threshold: 25,
  regime_vol_overload_ratio: 2.0,
  regime_trending_offset: 15,
  regime_volatile_offset: 25,
```
- **작업 B**: 4개 PRESETS에 레짐 값 추가
- 각 프리셋의 `params` 객체 끝에 추가:
```
보수적 (line 33):    regime_adx_trending_threshold: 25, regime_vol_overload_ratio: 2.0, regime_trending_offset: 20, regime_volatile_offset: 30
공격적 (line 38):    regime_adx_trending_threshold: 25, regime_vol_overload_ratio: 2.0, regime_trending_offset: 5, regime_volatile_offset: 10
횡보장 (line 43):    regime_adx_trending_threshold: 25, regime_vol_overload_ratio: 2.0, regime_trending_offset: 15, regime_volatile_offset: 25
변동성 장세 (line 48): regime_adx_trending_threshold: 25, regime_vol_overload_ratio: 2.0, regime_trending_offset: 10, regime_volatile_offset: 15
```
- **작업 C**: `getActivePresetName()` 내 `keys` 배열에 4개 키 추가
- **위치**: line 54-59 (하드코딩된 keys 배열)
```typescript
// Before:
const keys: (keyof StrategyParams)[] = [
    'bb_period', 'bb_std_dev', ... 'min_profit_margin',
];

// After: 배열 끝에 4개 추가
const keys: (keyof StrategyParams)[] = [
    'bb_period', 'bb_std_dev', ... 'min_profit_margin',
    'regime_adx_trending_threshold', 'regime_vol_overload_ratio',
    'regime_trending_offset', 'regime_volatile_offset',
];
```
- **주의**: keys 배열에 빠지면 레짐 값이 달라도 프리셋 매칭이 깨진다. 반드시 추가.

### TODO-6: `docs/Algorithm_Specification.md` — 문서 업데이트
- **파일**: `docs/Algorithm_Specification.md`
- **작업 A**: "1단계: 시장 필터링" 섹션(line 11-14)에 하이브리드 설명 추가
- 기존 "매매를 일시 중단합니다" → "진입 임계치를 동적으로 높여 더 강한 신호만 통과시킵니다"로 변경
- **작업 B**: "진입 파이프라인 요약" (line 46) 업데이트
```markdown
# Before:
`시장 레짐 필터(Regime Filter)` → `매수 신호 발생(Signal)` → ...

# After:
`시장 레짐 판정(Regime Detection)` → `임계치 동적 조정(Threshold Offset)` → `매수 신호 발생(Signal)` → ...
```
- **작업 C**: 하이브리드 오프셋 설명 추가 (1단계 아래에 새 단락)
```markdown
* **하이브리드 레짐 오프셋:** 시장이 추세장(ADX ≥ 25)이면 진입 임계치를 +15점, 변동성 폭발(변동성 ≥ 2배)이면 +25점 높여 더 확실한 기회만 포착합니다. 횡보장에서는 원래 임계치를 그대로 사용합니다. effective threshold의 상한은 99점으로 제한됩니다.
```

## Final Verification Wave

### QA-1: 백엔드 필드 존재 확인
```bash
python -c "from src.config import StrategyParams; p = StrategyParams(); print(f'trending_offset={p.regime_trending_offset}, volatile_offset={p.regime_volatile_offset}')"
# Assert: trending_offset=15.0, volatile_offset=25.0
```

### QA-2: from_dict() 하위 호환성
```bash
python -c "from src.config import StrategyParams; old = {'bb_period': 20, 'entry_score_threshold': 70}; p = StrategyParams.from_dict(old); print(f'offset={p.regime_trending_offset}')"
# Assert: offset=15.0 (기본값 적용)
```

### QA-3: evaluate_entry() 시그니처 확인
```bash
python -c "from src.strategy.engine import MeanReversionEngine; import inspect; sig = inspect.signature(MeanReversionEngine.evaluate_entry); print('threshold_offset' in sig.parameters)"
# Assert: True
```

### QA-4: 하드 차단 코드 제거 확인
```bash
grep -n "in (\"trending\", \"volatile\"):" src/orchestrator.py
# Assert: 결과 없음 (하드 차단 제거됨)
```

### QA-5: TypeScript 컴파일
```bash
npx tsc --noEmit --project frontend/tsconfig.app.json
# Assert: 에러 0개
```

### QA-6: ESLint 검사
```bash
npx eslint frontend/src/components/StrategyEditModal.tsx frontend/src/lib/strategyParams.ts
# Assert: 에러 0개
```

### QA-7: 프론트엔드 필드 존재 확인
```bash
grep -c "regime_trending_offset\|regime_volatile_offset\|regime_adx_trending_threshold\|regime_vol_overload_ratio" frontend/src/lib/strategyParams.ts
# Assert: 최소 4 이상
```

### QA-8: getActivePresetName keys 배열 확인
```bash
grep "regime_trending_offset" frontend/src/lib/strategyParams.ts
# Assert: keys 배열 내에 포함
```

### QA-9: pytest 회귀 테스트
```bash
python -m pytest tests/ -v
# Assert: 모든 테스트 통과
```

### QA-10: 백엔드-프론트엔드 필드 동기화
```bash
python -c "
from src.config import StrategyParams
fields = {f.name for f in __import__('dataclasses').fields(StrategyParams)}
regime_fields = {'regime_adx_trending_threshold', 'regime_vol_overload_ratio', 'regime_trending_offset', 'regime_volatile_offset'}
assert regime_fields.issubset(fields), f'Missing: {regime_fields - fields}'
print(f'All {len(regime_fields)} regime fields present in backend')
"
# Assert: "All 4 regime fields present in backend"
```
