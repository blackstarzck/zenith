# 매도 청산 스코어링 시스템 + 트레일링 스탑

## 설계 결정 요약

| 결정 | 선택 |
|------|------|
| evaluate_exit 시그니처 | Position 객체 전달 |
| 트레일링 스탑 활성화 | 1차 익절(SELL_HALF) 완료 후 |
| 임계값 | 단일 `exit_score_threshold` → has_sold_half로 SELL_HALF/SELL_ALL 결정 |
| 하위 호환성 | 비슷한 동작 (완전 동일 불가) |
| 가격 스냅샷 take_profit | BB 상단선 유지 (기존 그대로) |
| trailing_high 복구 | 재시작 시 현재가부터 추적 (제한사항 수용) |

## 핵심 규칙

- STOP_LOSS는 **하드 룰** — 스코어링 이전에 체크, 무조건 발동
- 트레일링 스탑은 **하드 룰** — has_sold_half=True일 때만 활성, 스코어링 이전 체크
- 익절(SELL_HALF/SELL_ALL)은 **스코어링 기반** — 가중합산 점수 ≥ exit_score_threshold
- Signal enum 변경 금지
- evaluate_entry() 변경 금지
- DB 스키마 변경 금지

## 변경 대상 파일 (8개)

| 파일 | 변경 유형 |
|------|----------|
| `src/config.py` | 수정: 죽은 코드 제거 + 매도 가중치/파라미터 추가 |
| `src/risk/manager.py` | 수정: Position에 trailing_high 추가 + update 메서드 |
| `src/strategy/engine.py` | 수정: evaluate_exit() 스코어링 재작성 |
| `src/executor/order_executor.py` | 수정: sell_half 비율 파라미터화 |
| `src/orchestrator.py` | 수정: Position 전달 + trailing_high 업데이트 |
| `frontend/src/components/StrategyEditModal.tsx` | 수정: 매도 청산 섹션 추가 |
| `frontend/src/lib/strategyParams.ts` | 수정: DEFAULT + PRESETS + getActivePresetName |
| `tests/test_strategy.py` | 수정: 기존 6개 적응 + 신규 5개 이상 |

## 변경하지 않는 파일 (명시적 제외)

- `src/strategy/indicators.py` — 신규 지표 없음
- `src/storage/client.py` — DB 변경 없음
- `frontend/src/types/database.ts` — Record<string, number>로 유연
- `supabase_*.sql` — 마이그레이션 없음

---

## TODO

### Task 1: config.py — 죽은 코드 제거 + 매도 파라미터 추가

**파일**: `src/config.py`

**1-1. 죽은 코드 제거** (L55-57):
```python
# 삭제할 필드:
take_profit_ratio_1st: float = 0.5
take_profit_ratio_2nd: float = 1.0
```

**1-2. 매도 파라미터 추가** (`entry_score_threshold` 뒤, L97 이후):
```python
# 매도 청산 스코어링 가중치 (0.0 = 비활성, 높을수록 비중 큼)
w_exit_rsi_level: float = 1.0       # RSI 과매수 → 높은 청산 점수
w_exit_bb_position: float = 1.0     # BB 상단 접근 → 높은 청산 점수
w_exit_profit_pct: float = 1.0      # 수익률 높을수록 → 높은 청산 점수
w_exit_adx_trend: float = 1.0       # 강한 추세(ADX 높음) → 추세 전환 경고

# 매도 청산 임계치 (0~100, 가중합산 스코어가 이 값 이상이면 익절)
exit_score_threshold: float = 70.0

# 트레일링 스탑 (1차 익절 후 활성화)
trailing_stop_atr_multiplier: float = 2.0  # 고점 대비 ATR * N 하락 시 전량 매도
# 분할 매도 비율 (SELL_HALF 시 매도 비율)
take_profit_sell_ratio: float = 0.5
```

**QA**:
```bash
python -c "from src.config import StrategyParams; p = StrategyParams(); assert hasattr(p, 'w_exit_rsi_level'); assert hasattr(p, 'exit_score_threshold'); assert hasattr(p, 'trailing_stop_atr_multiplier'); assert hasattr(p, 'take_profit_sell_ratio'); assert not hasattr(p, 'take_profit_ratio_1st'); print('OK')"
```

---

### Task 2: risk/manager.py — Position에 trailing_high 추가

**파일**: `src/risk/manager.py`

**2-1. Position 데이터클래스에 필드 추가**:
```python
@dataclass
class Position:
    symbol: str
    entry_price: float
    volume: float
    amount: float
    has_sold_half: bool = False
    entry_fee: float = 0.0
    trailing_high: float = 0.0  # 1차 익절 후 추적 고점 (0이면 비활성)
```

**2-2. update_trailing_high 메서드 추가** (RiskManager 클래스):
```python
def update_trailing_high(self, symbol: str, current_price: float) -> None:
    """보유 종목의 트레일링 고점을 업데이트합니다.

    1차 익절(has_sold_half=True) 후에만 추적합니다.
    """
    pos = self._positions.get(symbol)
    if pos is None or not pos.has_sold_half:
        return
    if current_price > pos.trailing_high:
        pos.trailing_high = current_price
```

**2-3. mark_half_sold 수정** — 1차 익절 시 trailing_high 초기화:
기존 `mark_half_sold`에서 `has_sold_half = True` 설정할 때 `trailing_high`를 현재가로 초기화해야 함.
단, mark_half_sold 시그니처에 current_price를 추가:
```python
def mark_half_sold(self, symbol: str, current_price: float = 0.0) -> None:
    pos = self._positions.get(symbol)
    if pos:
        pos.has_sold_half = True
        pos.trailing_high = current_price  # 트레일링 추적 시작
```

**주의**: `mark_half_sold` 호출부(orchestrator.py L539)도 current_price 전달하도록 수정 필요 → Task 5에서 처리.

**QA**:
```bash
python -c "
from src.risk.manager import Position
p = Position(symbol='T', entry_price=100, volume=1, amount=100)
assert p.trailing_high == 0.0
print('OK')
"
```

---

### Task 3: order_executor.py — sell_half 비율 파라미터화

**파일**: `src/executor/order_executor.py`

**3-1. sell_half 메서드 수정** (L191-194):
```python
def sell_half(self, symbol: str, total_volume: float, ratio: float = 0.5) -> OrderResult:
    """보유 수량의 지정 비율을 시장가 매도합니다."""
    sell_volume = total_volume * ratio
    return self.sell_market(symbol, sell_volume)
```

**QA**: 기존 호출부(orchestrator.py L534)가 ratio 미지정 시 기본값 0.5 적용 → 하위호환 유지.

---

### Task 4: engine.py — evaluate_exit 스코어링 재작성

**파일**: `src/strategy/engine.py`

**4-1. evaluate_exit 시그니처 변경**:
```python
def evaluate_exit(
    self,
    symbol: str,
    snapshot: IndicatorSnapshot,
    position: "Position",  # 기존 entry_price + has_sold_half 대신
) -> TradeSignal:
```

상단에 타입 임포트 추가:
```python
from __future__ import annotations
# TYPE_CHECKING 블록:
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.risk.manager import Position
```

**4-2. evaluate_exit 본문 — 3단계 구조**:

```python
def evaluate_exit(self, symbol, snapshot, position):
    price = snapshot.current_price
    bb = snapshot.bb
    params = self._params
    entry_price = position.entry_price
    has_sold_half = position.has_sold_half

    # ── [하드 룰 1] 동적 손절 (ATR 기반) — 무조건 우선 ──
    stop_loss_price = entry_price - (snapshot.atr * params.atr_stop_multiplier)
    if price <= stop_loss_price:
        return TradeSignal(
            signal=Signal.STOP_LOSS,
            symbol=symbol,
            reason=f"동적 손절 발동 (가격 {price:,.2f} ≤ 손절선 {stop_loss_price:,.2f})",
            price=price,
            stop_loss_price=stop_loss_price,
        )

    # ── [하드 룰 2] 트레일링 스탑 (1차 익절 후 활성) ──
    if has_sold_half and position.trailing_high > 0:
        trailing_stop = position.trailing_high - (snapshot.atr * params.trailing_stop_atr_multiplier)
        if price <= trailing_stop:
            return TradeSignal(
                signal=Signal.SELL_ALL,
                symbol=symbol,
                reason=f"트레일링 스탑 발동 (고점 {position.trailing_high:,.2f} → 현재 {price:,.2f} ≤ {trailing_stop:,.2f})",
                price=price,
                stop_loss_price=trailing_stop,
            )

    # ── [스코어링] 익절 조건 평가 ──
    scores = {
        "RSI↑": (params.w_exit_rsi_level, self._score_exit_rsi_level(snapshot.rsi)),
        "BB↑": (params.w_exit_bb_position, self._score_exit_bb_position(price, bb)),
        "수익": (params.w_exit_profit_pct, self._score_exit_profit(price, entry_price)),
        "ADX": (params.w_exit_adx_trend, self._score_exit_adx(snapshot.adx)),
    }

    total_weight = sum(w for w, _ in scores.values())
    if total_weight == 0:
        return TradeSignal(
            signal=Signal.HOLD, symbol=symbol,
            reason="모든 매도 스코어링 가중치가 0 — 청산 불가",
            price=price, stop_loss_price=stop_loss_price, score=0.0,
        )

    total_score = sum(w * s for w, s in scores.values()) / total_weight
    breakdown = " ".join(f"{name}:{s:.0f}" for name, (_, s) in scores.items())
    reason_str = f"청산 스코어 {total_score:.1f} ({breakdown})"

    if total_score >= params.exit_score_threshold:
        # 최소 수익 마진 확인 (1차 익절 시에만)
        profit_pct = (price - entry_price) / entry_price if entry_price > 0 else 0.0
        if not has_sold_half and profit_pct < params.min_profit_margin:
            return TradeSignal(
                signal=Signal.HOLD, symbol=symbol,
                reason=f"{reason_str} ≥ {params.exit_score_threshold:.1f} 이나 수익률 부족 ({profit_pct:.2%} < {params.min_profit_margin:.2%})",
                price=price, stop_loss_price=stop_loss_price, score=total_score,
            )
        signal_type = Signal.SELL_ALL if has_sold_half else Signal.SELL_HALF
        return TradeSignal(
            signal=signal_type, symbol=symbol,
            reason=f"{reason_str} ≥ {params.exit_score_threshold:.1f}",
            price=price,
            stop_loss_price=stop_loss_price,
            target_price_1=bb.middle if not has_sold_half else None,
            target_price_2=bb.upper,
            score=total_score,
        )

    return TradeSignal(
        signal=Signal.HOLD, symbol=symbol,
        reason=f"{reason_str} < {params.exit_score_threshold:.1f}",
        price=price, stop_loss_price=stop_loss_price, score=total_score,
    )
```

**4-3. 매도 스코어링 헬퍼 메서드 추가** (evaluate_exit 아래):

```python
# ── 매도 스코어링 헬퍼 ──────────────────────────────────

def _score_exit_rsi_level(self, rsi: float) -> float:
    """RSI 과매수 스코어. 높은 RSI = 높은 청산 점수."""
    # rsi ≤ 40 → 0, rsi ≥ 70 → 100, 선형 보간
    return max(0.0, min(100.0, (rsi - 40.0) / 30.0 * 100.0))

def _score_exit_bb_position(self, price: float, bb) -> float:
    """BB 포지션 스코어. 상단 접근/초과 = 높은 청산 점수."""
    if bb.upper == bb.lower:
        return 50.0
    # lower → 0, upper → 100, 초과 시 100 캡
    position = (price - bb.lower) / (bb.upper - bb.lower)
    return max(0.0, min(100.0, position * 100.0))

def _score_exit_profit(self, price: float, entry_price: float) -> float:
    """수익률 스코어. 수익 클수록 높은 청산 점수."""
    if entry_price <= 0:
        return 0.0
    profit_pct = ((price / entry_price) - 1.0) * 100.0  # %
    # 0% → 0, 3% → 100, 선형 보간
    return max(0.0, min(100.0, profit_pct / 3.0 * 100.0))

def _score_exit_adx(self, adx: float) -> float:
    """ADX 추세 강도 스코어. 강한 추세 = 높은 청산 점수 (추세 전환 경고)."""
    # adx ≤ 20 → 0, adx ≥ 40 → 100, 선형 보간
    return max(0.0, min(100.0, (adx - 20.0) / 20.0 * 100.0))
```

**QA**:
```bash
python -m pytest tests/test_strategy.py -v
```
(기존 테스트는 Task 8에서 적응 — 이 시점에서는 시그니처 변경으로 실패 예상)

---

### Task 5: orchestrator.py — Position 전달 + trailing_high 업데이트

**파일**: `src/orchestrator.py`

**5-1. _evaluate_exits 수정** (L230-274):
```python
def _evaluate_exits(self) -> None:
    positions = self._risk.get_all_positions()
    if not positions:
        return

    for symbol, pos in positions.items():
        try:
            df = self._collector.get_ohlcv(...)
            if df.empty:
                continue
            snapshot = compute_snapshot(...)

            # 트레일링 고점 업데이트 (evaluate_exit 호출 전)
            self._risk.update_trailing_high(symbol, snapshot.current_price)

            # Position 객체 직접 전달 (기존: entry_price, has_sold_half 개별 전달)
            signal = self._strategy.evaluate_exit(symbol, snapshot, pos)

            if signal.signal == Signal.STOP_LOSS:
                self._execute_sell_all(symbol, pos, signal.reason, label="손절 매도")
            elif signal.signal == Signal.SELL_ALL:
                self._execute_sell_all(symbol, pos, signal.reason, label="2차 익절")
            elif signal.signal == Signal.SELL_HALF:
                self._execute_sell_half(symbol, pos, signal.reason)

            time.sleep(0.2)
        except ValueError as e:
            ...
```

핵심 변경: L257-259의 `self._strategy.evaluate_exit(symbol, snapshot, pos.entry_price, pos.has_sold_half)` → `self._strategy.evaluate_exit(symbol, snapshot, pos)`

**5-2. _execute_sell_half에서 mark_half_sold 호출 수정** (L539):
```python
# 기존: self._risk.mark_half_sold(symbol)
# 변경: current_price 전달
self._risk.mark_half_sold(symbol, current_price=result.price)
```

**5-3. _execute_sell_half에서 sell_half 호출에 ratio 전달** (L534):
```python
# 기존: result = self._executor.sell_half(symbol, actual_volume)
# 변경: ratio 전달
result = self._executor.sell_half(symbol, actual_volume, ratio=self._config.strategy.take_profit_sell_ratio)
```

**5-4. L510 half_volume 계산 수정** (min-order 체크용):
```python
# 기존: half_volume = actual_volume * 0.5
# 변경:
sell_ratio = self._config.strategy.take_profit_sell_ratio
half_volume = actual_volume * sell_ratio
```

**QA**:
```bash
python -m pytest tests/ -v
```

---

### Task 6: StrategyEditModal.tsx — 매도 청산 섹션 추가

**파일**: `frontend/src/components/StrategyEditModal.tsx`

**6-1. StrategyParams 인터페이스 확장**:
```typescript
export interface StrategyParams {
  // ... 기존 필드 유지 ...
  // 매도 청산
  w_exit_rsi_level?: number;
  w_exit_bb_position?: number;
  w_exit_profit_pct?: number;
  w_exit_adx_trend?: number;
  exit_score_threshold?: number;
  trailing_stop_atr_multiplier?: number;
  take_profit_sell_ratio?: number;
  min_profit_margin?: number;
}
```

**6-2. EXAMPLE_EXIT_SCORES 상수 추가** (모듈 레벨):
```typescript
const EXAMPLE_EXIT_SCORES: Record<string, { label: string; score: number; field: string }> = {
  rsi_level:   { label: 'RSI 과매수', score: 83, field: 'w_exit_rsi_level' },
  bb_position: { label: 'BB 위치', score: 75, field: 'w_exit_bb_position' },
  profit_pct:  { label: '수익률', score: 67, field: 'w_exit_profit_pct' },
  adx_trend:   { label: 'ADX 추세', score: 55, field: 'w_exit_adx_trend' },
};
```

**6-3. 매도 시뮬레이션 useMemo 추가** (기존 simulationResult와 동일 패턴):
entry 스코어 시뮬레이션과 동일 로직으로 exit 시뮬레이션 결과 계산.

**6-4. JSX — 매도 청산 섹션 추가** (진입 조건 시뮬레이션 div 뒤, `</Form>` 앞):
- `<Divider>매도 청산 조건 (스코어링)</Divider>`
- Alert: "각 조건이 맞을 때마다 청산 점수를 부여합니다. 총점이 '청산 스코어 임계값'을 넘으면 봇이 매도를 실행합니다."
- 4개 가중치 슬라이더 (Row/Col, min=0 max=3 step=0.1):
  - w_exit_rsi_level: "RSI가 높을수록(과매수) 하락 가능성이 높아 높은 청산 점수를 줍니다."
  - w_exit_bb_position: "가격이 볼린저 밴드 상단에 가까울수록 높은 청산 점수를 줍니다."
  - w_exit_profit_pct: "수익률이 높을수록 이익 실현을 위해 높은 청산 점수를 줍니다."
  - w_exit_adx_trend: "ADX가 높을수록(강한 추세) 추세 전환 위험으로 높은 청산 점수를 줍니다."
- exit_score_threshold 슬라이더+InputNumber (entry와 동일 패턴)
  - marks: 55='공격적', 70='균형', 90='보수적'
- 매도 시뮬레이션 패널 (entry와 동일 구조)

**6-5. 추가 파라미터** (매도 청산 섹션 아래, 프리셋 위):
- `<Divider>매도 상세 설정</Divider>`
- trailing_stop_atr_multiplier: InputNumber (min=0.5 max=5 step=0.1), "1차 익절 후 고점 대비 ATR × 이 값만큼 하락하면 전량 매도합니다."
- take_profit_sell_ratio: InputNumber (min=0.1 max=0.9 step=0.1), "1차 익절 시 매도할 비율입니다. 0.5 = 50% 매도."
- min_profit_margin: InputNumber (min=0 max=0.05 step=0.001), "1차 익절 실행을 위한 최소 수익률입니다. 수수료(0.1%) + 알파."

**스타일**: 인라인 style={{}} 전용. 기존 패턴 따르기.
**텍스트**: 전부 한국어.

**QA**:
```bash
npx tsc --noEmit
```

---

### Task 7: strategyParams.ts — DEFAULT + PRESETS + getActivePresetName

**파일**: `frontend/src/lib/strategyParams.ts`

**7-1. DEFAULT_STRATEGY에 매도 필드 추가**:
```typescript
export const DEFAULT_STRATEGY: StrategyParams = {
  // ... 기존 유지 ...
  w_exit_rsi_level: 1.0,
  w_exit_bb_position: 1.0,
  w_exit_profit_pct: 1.0,
  w_exit_adx_trend: 1.0,
  exit_score_threshold: 70,
  trailing_stop_atr_multiplier: 2.0,
  take_profit_sell_ratio: 0.5,
  min_profit_margin: 0.003,
};
```

**7-2. 4개 PRESETS에 매도 필드 추가**:

보수적:
```
w_exit_rsi_level: 1.5, w_exit_bb_position: 2.0, w_exit_profit_pct: 1.0, w_exit_adx_trend: 1.0,
exit_score_threshold: 60, trailing_stop_atr_multiplier: 1.5, take_profit_sell_ratio: 0.5, min_profit_margin: 0.005
```

공격적:
```
w_exit_rsi_level: 0.5, w_exit_bb_position: 1.0, w_exit_profit_pct: 1.5, w_exit_adx_trend: 0.5,
exit_score_threshold: 80, trailing_stop_atr_multiplier: 2.5, take_profit_sell_ratio: 0.5, min_profit_margin: 0.002
```

횡보장:
```
w_exit_rsi_level: 1.0, w_exit_bb_position: 2.0, w_exit_profit_pct: 1.0, w_exit_adx_trend: 0.5,
exit_score_threshold: 65, trailing_stop_atr_multiplier: 2.0, take_profit_sell_ratio: 0.5, min_profit_margin: 0.003
```

변동성 장세:
```
w_exit_rsi_level: 1.5, w_exit_bb_position: 1.5, w_exit_profit_pct: 2.0, w_exit_adx_trend: 1.5,
exit_score_threshold: 60, trailing_stop_atr_multiplier: 1.5, take_profit_sell_ratio: 0.5, min_profit_margin: 0.003
```

**7-3. getActivePresetName keys 배열에 매도 필드 추가** (L46-49):
```typescript
const keys: (keyof StrategyParams)[] = [
  // 기존 유지...
  'w_exit_rsi_level', 'w_exit_bb_position', 'w_exit_profit_pct', 'w_exit_adx_trend',
  'exit_score_threshold', 'trailing_stop_atr_multiplier', 'take_profit_sell_ratio', 'min_profit_margin',
];
```

**QA**:
```bash
npx tsc --noEmit
```

---

### Task 8: tests/test_strategy.py — 기존 적응 + 신규 테스트

**파일**: `tests/test_strategy.py`

**8-1. 기존 6개 exit 테스트 적응**:
- `evaluate_exit(symbol, snapshot, entry_price, has_sold_half)` → `evaluate_exit(symbol, snapshot, position)`
- Position 객체를 생성하여 전달:
```python
from src.risk.manager import Position
pos = Position(symbol=symbol, entry_price=entry_price, volume=1.0, amount=entry_price, has_sold_half=has_sold_half)
```

**8-2. 신규 테스트 추가** (최소 5개):

1. `test_exit_scoring_above_threshold` — 스코어 ≥ threshold → SELL_HALF (has_sold_half=False)
2. `test_exit_scoring_below_threshold` — 스코어 < threshold → HOLD
3. `test_exit_scoring_sell_all_after_half` — has_sold_half=True, 스코어 ≥ threshold → SELL_ALL
4. `test_trailing_stop_triggers` — has_sold_half=True, trailing_high 설정, 가격 하락 → SELL_ALL
5. `test_trailing_stop_inactive_before_half` — has_sold_half=False → 트레일링 무시
6. `test_exit_all_weights_zero` — 모든 가중치 0 → HOLD (fallback)
7. `test_exit_min_profit_guard` — 스코어 충분하지만 수익률 부족 → HOLD

**QA**:
```bash
python -m pytest tests/test_strategy.py -v
# 예상: 기존 적응 6개 + 신규 7개 = 13개 이상 통과
python -m pytest tests/ -v
# 예상: 전체 테스트 통과
```

---

## 구현 순서

1. Task 1 (config.py) → `python -c "from src.config import StrategyParams; print('OK')"`
2. Task 2 (risk/manager.py) → `python -c "from src.risk.manager import Position; print('OK')"`
3. Task 3 (order_executor.py) → 기존 테스트 확인
4. Task 4 (engine.py) → 시그니처 변경으로 exit 테스트 일시 실패 예상
5. Task 5 (orchestrator.py) → 통합 확인
6. Task 8 (tests) → `pytest tests/ -v` 전체 통과 확인
7. Task 7 (strategyParams.ts) → `npx tsc --noEmit`
8. Task 6 (StrategyEditModal.tsx) → `npx tsc --noEmit`

## Final Verification Wave

```bash
# 백엔드
python -m pytest tests/ -v
# 프론트엔드
cd frontend && npx tsc --noEmit
```

## 알려진 제한사항
- trailing_high는 메모리 전용 — 봇 재시작 시 현재가부터 재추적
- 기본 가중치의 매도 스코어링이 기존 IF문과 완전히 동일하지는 않음 (비슷한 동작)
- 매도 스코어 시뮬레이션은 예시 시장 상황 기반 (실시간 시장 데이터 아님)
