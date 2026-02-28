# Plan: 매수 진입 로직 스코어링 시스템 전환

## 목표
현재 6개 AND-게이트 필터(`evaluate_entry()`)를 가중치 기반 스코어링 시스템으로 전환하여 매수 진입 빈도를 유연하게 조절한다.

## 배경
- 현재 6개 필터가 모두 통과해야 BUY 신호 발생 → 진입이 극도로 타이트
- 각 필터가 50% 통과율이라 해도, 6개 AND = ~1.5% 확률
- 특히 ADX ≤ 25, RSI ≤ 35 조합이 크립토 시장에서 동시 충족되기 어려움

## 핵심 설계 결정

### 스코어링 방식
- 각 필터가 0~100 점수를 반환
- 정규화 가중합산: `total_score = Σ(w_i × score_i) / Σ(w_i)`
- `total_score ≥ entry_score_threshold` → BUY, 미만 → HOLD
- 모든 가중치가 0이면 → HOLD (0 나누기 방지)

### 필터별 스코어 방향 (100 = 진입에 유리)
| 필터 | 100점 (유리) | 0점 (불리) | 스코어 공식 |
|------|-------------|-----------|------------|
| 변동성 | vol_ratio ≤ 1.0 (안정) | vol_ratio ≥ 3.0 (과부하) | `max(0, min(100, (3.0 - ratio) / 2.0 × 100))` |
| MA 추세 | MA20 > MA50 (상승추세) | MA20 < MA50 (하락추세) | 상승=100, 하락=0, 데이터부족=50 |
| ADX | ADX ≤ 15 (횡보, 평균회귀 적합) | ADX ≥ 40 (강한추세) | `max(0, min(100, (40 - adx) / 25 × 100))` |
| BB 복귀 | 최근 하단 이탈 후 복귀 완료 | 이탈 이력 없음 | recovered=100, below=30, none=0 |
| RSI 기울기 | slope > 3.0 (강한 상승전환) | slope ≤ 0 (하락 지속) | `max(0, min(100, slope / 3.0 × 100))` |
| RSI 수준 | RSI ≤ 20 (극심 과매도) | RSI ≥ 45 (과매도 아님) | `max(0, min(100, (45 - rsi) / 25 × 100))` |

### BB 상태: 무상태 전환
- 기존 `_was_below_lower` 인메모리 상태 추적 → `calc_bb_status()` (indicators.py:221-274) 활용
- `calc_bb_status()`는 캔들 데이터에서 직접 BB 이탈/복귀를 판별하므로 봇 재시작에도 안전
- `_was_below_lower` dict와 `recover_bb_state()`, `reset_tracking()` 메서드는 제거

### MARKET_PAUSE 시그널
- 변동성도 스코어링에 포함되므로, `Signal.MARKET_PAUSE`는 `evaluate_entry()`에서 더 이상 반환하지 않음
- enum 자체는 제거하지 않음 (다른 곳에서 사용 가능성)
- 오케스트레이터의 `MARKET_PAUSE` 분기(`orchestrator.py:374`)는 dead code가 되나, 안전을 위해 유지

### 기본 가중치 (하위호환성)
- 모든 가중치 기본값: `1.0` (동일 비중)
- `entry_score_threshold` 기본값: `85.0` (현행 AND-게이트 수준의 엄격함 유지)
- DB에 새 가중치 없이 코드만 배포되면 → 기본값으로 동작 → 기존과 유사한 엄격함

### TradeSignal 확장
- `score: float | None = None` 필드 추가
- reason 문자열에 스코어 포함: `"스코어 78.5 (Vol:90 MA:100 ADX:85 BB:100 RSI↗:60 RSI:80) ≥ 60.0"`

## 범위

### IN (포함)
- `src/config.py` — StrategyParams에 7개 필드 추가
- `src/strategy/engine.py` — evaluate_entry() 스코어링 재구현 + TradeSignal.score 추가
- `frontend/src/components/StrategyEditModal.tsx` — 스코어링 가중치 UI
- `frontend/src/lib/strategyParams.ts` — 기본값/프리셋 업데이트
- `tests/test_strategy.py` — 진입 테스트 전면 재작성
- `tests/test_hotreload.py` — 직렬화 테스트에 가중치 필드 추가
- `docs/Algorithm_Specification.md` — 스코어링 알고리즘 반영
- `docs/frontend-design.md` — 모달 UI 변경 반영

### OUT (제외)
- `evaluate_exit()` 변경 없음
- DB 스키마 변경 없음 (score는 reason 문자열에 포함)
- `Signal` enum 변경 없음
- 오케스트레이터 호출 패턴 변경 없음 (BUY/HOLD 체크 동일)
- `regime.py` 변경 없음

## 영향도 분석
| 파일 | 변경 유형 | 위험도 |
|------|----------|--------|
| `src/config.py` | 필드 추가 (하위호환) | 🟢 낮음 |
| `src/strategy/engine.py` | 핵심 로직 재구현 | 🔴 높음 |
| `frontend/src/components/StrategyEditModal.tsx` | UI 섹션 추가 | 🟡 중간 |
| `frontend/src/lib/strategyParams.ts` | 기본값/프리셋 확장 | 🟢 낮음 |
| `tests/test_strategy.py` | 진입 테스트 재작성 | 🟡 중간 |
| `tests/test_hotreload.py` | 직렬화 테스트 확장 | 🟢 낮음 |
| `docs/Algorithm_Specification.md` | 문서 갱신 | 🟢 낮음 |
| `docs/frontend-design.md` | 문서 갱신 | 🟢 낮음 |

## 작업 의존성 그래프

```
Wave 1 (독립 — 병렬 실행):
├── Task 1: StrategyParams에 스코어링 필드 추가 (config.py)
└── Task 2: TradeSignal에 score 필드 추가 (engine.py)

Wave 2 (Wave 1 완료 후 — 병렬 실행):
├── Task 3: evaluate_entry() 스코어링 로직 재구현 (engine.py) ← Task 1, 2
└── Task 4: StrategyEditModal + strategyParams.ts UI 업데이트 ← Task 1

Wave 3 (Wave 2 완료 후 — 병렬 실행):
├── Task 5: 테스트 재작성 (test_strategy.py + test_hotreload.py) ← Task 3
└── Task 6: 문서 갱신 (Algorithm_Specification.md + frontend-design.md) ← Task 3, 4

최종 검증 Wave:
└── pytest tests/ -v && cd frontend && npx eslint . && npx tsc --noEmit
```

## Tasks

### Task 1: StrategyParams에 스코어링 필드 추가

- **파일**: `src/config.py`
- **카테고리**: `quick`
- **스킬**: `[]`
- **의존**: 없음

**작업 내용**:
`StrategyParams` frozen dataclass에 아래 7개 필드를 추가한다. 위치는 `adx_trend_threshold` 관련 필드들 다음 (line 81 이후):

```python
# 스코어링 가중치 (0.0 = 비활성, 높을수록 비중 큼)
w_volatility: float = 1.0
w_ma_trend: float = 1.0
w_adx: float = 1.0
w_bb_recovery: float = 1.0
w_rsi_slope: float = 1.0
w_rsi_level: float = 1.0

# 스코어링 진입 임계치 (0~100, 가중합산 스코어가 이 값 이상이면 BUY)
entry_score_threshold: float = 85.0
```

**주의사항**:
- `to_dict()`와 `from_dict()`는 `asdict()`/`dc_fields()` 기반이므로 자동으로 새 필드를 포함함 → 추가 코드 불필요
- `frozen=True`이므로 필드 추가만으로 충분

**QA**:
```bash
python -c "
from src.config import StrategyParams
p = StrategyParams()
assert p.w_volatility == 1.0
assert p.w_ma_trend == 1.0
assert p.w_adx == 1.0
assert p.w_bb_recovery == 1.0
assert p.w_rsi_slope == 1.0
assert p.w_rsi_level == 1.0
assert p.entry_score_threshold == 85.0
d = p.to_dict()
assert 'w_volatility' in d and 'entry_score_threshold' in d
p2 = StrategyParams.from_dict({'w_volatility': 2.0, 'entry_score_threshold': 60.0})
assert p2.w_volatility == 2.0 and p2.entry_score_threshold == 60.0
print('OK')
"
```

---

### Task 2: TradeSignal에 score 필드 추가

- **파일**: `src/strategy/engine.py`
- **카테고리**: `quick`
- **스킬**: `[]`
- **의존**: 없음

**작업 내용**:
`TradeSignal` dataclass (line 33-42)에 `score` 필드를 추가한다:

```python
@dataclass
class TradeSignal:
    """매매 신호 상세 정보."""
    signal: Signal
    symbol: str
    reason: str
    price: float
    stop_loss_price: float | None = None
    target_price_1: float | None = None  # 1차 목표가 (BB 중앙선)
    target_price_2: float | None = None  # 2차 목표가 (BB 상단선)
    score: float | None = None           # 스코어링 합산 점수 (0~100)
```

**주의사항**:
- `score`는 optional이므로 기존 `TradeSignal` 생성 코드와 하위호환
- `evaluate_exit()`에서도 `TradeSignal`을 반환하지만, score=None으로 기본 동작

**QA**:
```bash
python -c "
from src.strategy.engine import TradeSignal, Signal
t = TradeSignal(signal=Signal.HOLD, symbol='X', reason='test', price=100, score=75.5)
assert t.score == 75.5
t2 = TradeSignal(signal=Signal.HOLD, symbol='X', reason='test', price=100)
assert t2.score is None
print('OK')
"
```

---

### Task 3: evaluate_entry() 스코어링 로직 재구현

- **파일**: `src/strategy/engine.py`
- **카테고리**: `deep`
- **스킬**: `[]`
- **의존**: Task 1, Task 2

**작업 내용**:

#### 3-1. 6개 스코어링 헬퍼 메서드 추가

`MeanReversionEngine` 클래스에 private 메서드 6개를 추가한다. 각 메서드는 `float` (0~100)을 반환한다:

```python
def _score_volatility(self, vol_ratio: float) -> float:
    """변동성 스코어. 낮은 변동성 = 높은 점수."""
    # vol_ratio ≤ 1.0 → 100, vol_ratio ≥ 3.0 → 0, 선형 보간
    return max(0.0, min(100.0, (3.0 - vol_ratio) / 2.0 * 100.0))

def _score_ma_trend(self, closes_series, params: StrategyParams) -> float:
    """MA 추세 스코어. 상승추세 = 100, 하락추세 = 0."""
    if closes_series is None or len(closes_series) < params.ma_long_period:
        return 50.0  # 데이터 부족 시 중립
    is_uptrend = calc_ma_trend(closes_series, params.ma_short_period, params.ma_long_period)
    if is_uptrend is None:
        return 50.0
    return 100.0 if is_uptrend else 0.0

def _score_adx(self, adx: float) -> float:
    """ADX 스코어. 낮은 ADX(횡보) = 높은 점수 (평균회귀에 유리)."""
    # adx ≤ 15 → 100, adx ≥ 40 → 0, 선형 보간
    return max(0.0, min(100.0, (40.0 - adx) / 25.0 * 100.0))

def _score_bb_recovery(self, closes_series, params: StrategyParams) -> float:
    """BB 복귀 스코어. 무상태, calc_bb_status() 사용."""
    if closes_series is None or len(closes_series) < params.bb_period + 20:
        return 0.0  # 데이터 부족 시 불리
    status = calc_bb_status(closes_series, params.bb_period, params.bb_std_dev)
    if status == "recovered":
        return 100.0
    elif status == "below":
        return 30.0  # 이탈 중 — 부분 점수 (반등 가능성)
    else:  # "none"
        return 0.0

def _score_rsi_slope(self, closes_series, params: StrategyParams) -> float:
    """RSI 기울기 스코어. 양의 기울기(상승전환) = 높은 점수."""
    if closes_series is None or len(closes_series) <= 20:
        return 50.0  # 데이터 부족 시 중립
    slope = calc_rsi_slope(closes_series, params.rsi_period, lookback=params.rsi_slope_lookback)
    # slope ≤ 0 → 0, slope ≥ 3.0 → 100, 선형 보간
    return max(0.0, min(100.0, slope / 3.0 * 100.0))

def _score_rsi_level(self, rsi: float) -> float:
    """RSI 수준 스코어. 낮은 RSI(과매도) = 높은 점수."""
    # rsi ≤ 20 → 100, rsi ≥ 45 → 0, 선형 보간
    return max(0.0, min(100.0, (45.0 - rsi) / 25.0 * 100.0))
```

**임포트 추가** (engine.py 상단):
```python
from src.strategy.indicators import (
    IndicatorSnapshot,
    calc_bollinger_bands,
    calc_ma_trend,
    calc_rsi_slope,
    calc_bb_status,  # ← 새로 추가
)
```

#### 3-2. evaluate_entry() 재구현

기존 `evaluate_entry()` 본문 (line 57~173)을 아래 구조로 **전면 교체**:

```python
def evaluate_entry(
    self,
    symbol: str,
    snapshot: IndicatorSnapshot,
    closes_series: "pd.Series | None" = None,
) -> TradeSignal:
    """매수 진입 조건을 스코어링 방식으로 평가합니다.

    각 필터가 0~100 점수를 반환하고, 가중합산 점수가
    entry_score_threshold 이상이면 BUY 신호를 생성합니다.

    Args:
        symbol: 마켓 코드
        snapshot: 현재 지표 스냅샷
        closes_series: RSI 기울기/BB 상태 계산용 종가 시리즈 (선택)

    Returns:
        TradeSignal (score 필드 포함)
    """
    price = snapshot.current_price
    bb = snapshot.bb
    params = self._params

    # ── 개별 필터 스코어 계산 ──
    scores = {
        "Vol": (params.w_volatility, self._score_volatility(snapshot.volatility_ratio)),
        "MA": (params.w_ma_trend, self._score_ma_trend(closes_series, params)),
        "ADX": (params.w_adx, self._score_adx(snapshot.adx)),
        "BB": (params.w_bb_recovery, self._score_bb_recovery(closes_series, params)),
        "RSI↗": (params.w_rsi_slope, self._score_rsi_slope(closes_series, params)),
        "RSI": (params.w_rsi_level, self._score_rsi_level(snapshot.rsi)),
    }

    # ── 정규화 가중합산 ──
    total_weight = sum(w for w, _ in scores.values())
    if total_weight == 0:
        return TradeSignal(
            signal=Signal.HOLD,
            symbol=symbol,
            reason="모든 스코어링 가중치가 0 — 진입 불가",
            price=price,
            score=0.0,
        )

    total_score = sum(w * s for w, s in scores.values()) / total_weight

    # ── 스코어 breakdown 문자열 ──
    breakdown = " ".join(f"{name}:{s:.0f}" for name, (_, s) in scores.items())
    reason_str = f"스코어 {total_score:.1f} ({breakdown})"

    # ── 임계치 비교 ──
    if total_score >= params.entry_score_threshold:
        stop_loss = price - (snapshot.atr * params.atr_stop_multiplier)
        return TradeSignal(
            signal=Signal.BUY,
            symbol=symbol,
            reason=f"{reason_str} ≥ {params.entry_score_threshold:.1f}",
            price=price,
            stop_loss_price=stop_loss,
            target_price_1=bb.middle,
            target_price_2=bb.upper,
            score=total_score,
        )

    return TradeSignal(
        signal=Signal.HOLD,
        symbol=symbol,
        reason=f"{reason_str} < {params.entry_score_threshold:.1f}",
        price=price,
        score=total_score,
    )
```

#### 3-3. 불필요 코드 제거/정리 + 외부 호출처 제거

**engine.py 내부 제거:**
- `_was_below_lower: dict[str, bool]` 인스턴스 변수 → **제거** (`__init__`에서)
- `recover_bb_state()` 메서드 (line 256-292) → **제거** (무상태로 전환)
- `reset_tracking()` 메서드 (line 294-296) → **제거**

**⚠️ 외부 호출처 — 반드시 함께 제거 (확인 완료):**

| 파일 | 라인 | 호출 | 처리 |
|------|------|------|------|
| `src/orchestrator.py` | 763 | `self._strategy.recover_bb_state(symbol, df["close"], ...)` | **전체 try 블록 내 해당 호출 라인 제거** (BB 상태 복구 불필요) |
| `src/orchestrator.py` | 531 | `self._strategy.reset_tracking(symbol)` | **해당 라인 제거** (더스트 정리 시) |
| `src/orchestrator.py` | 567 | `self._strategy.reset_tracking(symbol)` | **해당 라인 제거** (`_execute_sell_all` 내 보유량 0 분기) |
| `src/orchestrator.py` | 584 | `self._strategy.reset_tracking(symbol)` | **해당 라인 제거** (`_execute_sell_all` 내 매도 완료 후) |
| `src/backtest/paper_trading.py` | 500 | `self._strategy.reset_tracking(symbol)` | **해당 라인 제거** (페이퍼 트레이딩 매도 후) |

**orchestrator.py 추가 정리:**
- `_recover_bb_states()` 메서드 (line 747-771) — `recover_bb_state`를 루프 호출하는 메서드. **메서드 전체 제거**
- `self._recover_bb_states()` 호출 (line 102, `__init__` 내부) — **해당 라인 제거**

**주의**: 이 호출들은 단순 라인 삭제. 앞뒤 로직(risk.remove_position 등)은 유지해야 함.

**QA**:
```bash
python -c "
from src.config import StrategyParams
from src.strategy.engine import MeanReversionEngine, Signal
from src.strategy.indicators import BollingerBands, IndicatorSnapshot
import pandas as pd
import numpy as np

# 유리한 조건: 낮은 변동성, 낮은 ADX, 낮은 RSI
snap = IndicatorSnapshot(
    bb=BollingerBands(52000, 50000, 48000, 0.08),
    rsi=25, atr=500, current_price=48500,
    volatility_ratio=1.0, adx=15
)
# BB recovered를 위한 종가 시리즈 생성
closes = pd.Series([47000]*5 + [48500]*15 + [49000]*180)

params = StrategyParams(entry_score_threshold=60.0)
engine = MeanReversionEngine(params)
sig = engine.evaluate_entry('KRW-BTC', snap, closes)
assert sig.score is not None and 0 <= sig.score <= 100
print(f'Score={sig.score:.1f}, Signal={sig.signal.name}, Reason={sig.reason}')

# 모든 가중치 0 → HOLD
params_zero = StrategyParams(w_volatility=0, w_ma_trend=0, w_adx=0, w_bb_recovery=0, w_rsi_slope=0, w_rsi_level=0)
engine2 = MeanReversionEngine(params_zero)
sig2 = engine2.evaluate_entry('KRW-BTC', snap)
assert sig2.signal == Signal.HOLD
print('All-zero weights: HOLD OK')
"
```

---

### Task 4: StrategyEditModal + strategyParams.ts 업데이트

- **파일**: `frontend/src/components/StrategyEditModal.tsx`, `frontend/src/lib/strategyParams.ts`
- **카테고리**: `visual-engineering`
- **스킬**: `["frontend-ui-ux"]`
- **의존**: Task 1

**⚠️ AntD 6 Slider 문서를 반드시 확인**: `context7_query-docs`로 antd v6 Slider 컴포넌트 API를 조회할 것.

**작업 내용**:

#### 4-1. StrategyEditModal.tsx

**TS 인터페이스 확장** (line 20-28):
```typescript
export interface StrategyParams {
  bb_period: number;
  bb_std_dev: number;
  rsi_period: number;
  rsi_oversold: number;
  atr_period: number;
  atr_stop_multiplier: number;
  top_volume_count?: number;
  // 스코어링 가중치
  w_volatility?: number;
  w_ma_trend?: number;
  w_adx?: number;
  w_bb_recovery?: number;
  w_rsi_slope?: number;
  w_rsi_level?: number;
  entry_score_threshold?: number;
}
```

**새 섹션 추가** (기존 "프리셋" Divider 전, ATR 손절 Row 다음에):

```tsx
<Divider titlePlacement="left" plain>
  스코어링 가중치
</Divider>
<Alert
  title="각 필터의 비중(0~10)과 진입 임계치(0~100)를 조정합니다. 가중치 0 = 해당 필터 비활성화"
  type="warning"
  showIcon
  style={{ marginBottom: 12 }}
/>
<Row gutter={16}>
  <Col span={12}>
    <Form.Item label="변동성 가중치" name="w_volatility">
      <Slider min={0} max={10} step={0.1} />
    </Form.Item>
  </Col>
  <Col span={12}>
    <Form.Item label="MA 추세 가중치" name="w_ma_trend">
      <Slider min={0} max={10} step={0.1} />
    </Form.Item>
  </Col>
</Row>
<Row gutter={16}>
  <Col span={12}>
    <Form.Item label="ADX 가중치" name="w_adx">
      <Slider min={0} max={10} step={0.1} />
    </Form.Item>
  </Col>
  <Col span={12}>
    <Form.Item label="BB 복귀 가중치" name="w_bb_recovery">
      <Slider min={0} max={10} step={0.1} />
    </Form.Item>
  </Col>
</Row>
<Row gutter={16}>
  <Col span={12}>
    <Form.Item label="RSI 기울기 가중치" name="w_rsi_slope">
      <Slider min={0} max={10} step={0.1} />
    </Form.Item>
  </Col>
  <Col span={12}>
    <Form.Item label="RSI 수준 가중치" name="w_rsi_level">
      <Slider min={0} max={10} step={0.1} />
    </Form.Item>
  </Col>
</Row>
<Row gutter={16}>
  <Col span={12}>
    <Form.Item label="진입 임계치 (0~100)" name="entry_score_threshold">
      <InputNumber min={0} max={100} step={1} style={{ width: '100%' }} />
    </Form.Item>
  </Col>
</Row>
```

**임포트 추가**: `Slider` 를 antd 임포트 목록에 추가.

#### 4-2. strategyParams.ts

**DEFAULT_STRATEGY 확장**:
```typescript
export const DEFAULT_STRATEGY: StrategyParams = {
  bb_period: 20,
  bb_std_dev: 2.0,
  rsi_period: 14,
  rsi_oversold: 30,
  atr_period: 14,
  atr_stop_multiplier: 2.5,
  top_volume_count: 10,
  // 스코어링
  w_volatility: 1.0,
  w_ma_trend: 1.0,
  w_adx: 1.0,
  w_bb_recovery: 1.0,
  w_rsi_slope: 1.0,
  w_rsi_level: 1.0,
  entry_score_threshold: 85,
};
```

**4개 프리셋 업데이트** — 각 프리셋에 스코어링 파라미터 추가:
```typescript
// 보수적: 높은 임계치, BB/RSI 비중 높음
{ ..., w_volatility: 1.5, w_ma_trend: 1.0, w_adx: 1.0, w_bb_recovery: 2.0, w_rsi_slope: 1.0, w_rsi_level: 1.5, entry_score_threshold: 90 }

// 공격적: 낮은 임계치, 골고루
{ ..., w_volatility: 0.5, w_ma_trend: 0.5, w_adx: 0.5, w_bb_recovery: 1.0, w_rsi_slope: 1.0, w_rsi_level: 1.0, entry_score_threshold: 55 }

// 횡보장: ADX/BB 비중 높음
{ ..., w_volatility: 1.0, w_ma_trend: 0.5, w_adx: 2.0, w_bb_recovery: 2.0, w_rsi_slope: 1.0, w_rsi_level: 1.0, entry_score_threshold: 70 }

// 변동성 장세: 변동성 가중치 높음, 높은 임계치
{ ..., w_volatility: 2.0, w_ma_trend: 1.0, w_adx: 1.0, w_bb_recovery: 1.5, w_rsi_slope: 1.5, w_rsi_level: 1.5, entry_score_threshold: 85 }
```

**getActivePresetName() 키 목록 업데이트** (line 39):
```typescript
const keys: (keyof StrategyParams)[] = [
  'bb_period', 'bb_std_dev', 'rsi_period', 'rsi_oversold',
  'atr_period', 'atr_stop_multiplier', 'top_volume_count',
  'w_volatility', 'w_ma_trend', 'w_adx', 'w_bb_recovery',
  'w_rsi_slope', 'w_rsi_level', 'entry_score_threshold',
];
```

**QA**:
```bash
cd frontend && npx eslint . && npx tsc --noEmit
```

---

### Task 5: 테스트 재작성

- **파일**: `tests/test_strategy.py`, `tests/test_hotreload.py`
- **카테고리**: `unspecified-high`
- **스킬**: `[]`
- **의존**: Task 3

**작업 내용**:

#### 5-1. test_strategy.py — TestEntrySignals 재작성

기존 8개 진입 테스트를 스코어링 기반으로 재작성. **청산 테스트(TestExitSignals)는 변경하지 않는다.**

**기존 → 새 테스트 매핑**:

| 기존 테스트 | 새 테스트 | 검증 내용 |
|------------|----------|----------|
| `test_volatility_overload_pauses_trading` | `test_high_volatility_lowers_score` | vol_ratio=3.0 → Vol 스코어=0, 전체 스코어 하락 |
| `test_no_bb_breakout_history_hold` | `test_no_bb_history_lowers_bb_score` | BB 이탈 이력 없음 → BB 스코어=0 |
| `test_currently_below_bb_lower_hold` | `test_below_bb_gives_partial_score` | 현재 하단 이탈 → BB 스코어=30 |
| `test_bb_recovery_with_rsi_oversold_triggers_buy` | `test_favorable_conditions_trigger_buy` | 모든 조건 유리 → 높은 스코어 → BUY |
| `test_bb_recovery_but_rsi_too_high_hold` | `test_high_rsi_lowers_score` | RSI=55 → RSI 스코어=0 → 전체 스코어 하락 |
| `test_different_symbols_tracked_independently` | (제거) | 무상태로 전환되어 의미 없음 |
| `test_reset_tracking_clears_state` | (제거) | `reset_tracking()` 메서드 제거됨 |
| `test_adx_strong_trend_blocks_entry` | `test_high_adx_lowers_score` | ADX=40 → ADX 스코어=0 |
| `test_adx_weak_trend_allows_entry` | `test_low_adx_raises_score` | ADX=15 → ADX 스코어=100 |

**새로 추가할 테스트**:
```python
def test_score_always_in_0_100_range():
    """스코어는 항상 0~100 범위."""

def test_weight_zero_excludes_filter():
    """가중치 0인 필터는 결과에 영향 없음."""

def test_all_weights_zero_returns_hold():
    """모든 가중치 0이면 HOLD."""

def test_threshold_boundary():
    """임계치 정확히 일치 시 BUY."""

def test_default_params_backward_compat():
    """기본 파라미터로 유리한 조건 = BUY (하위호환)."""

def test_score_field_populated():
    """TradeSignal.score 필드가 채워짐."""

def test_reason_contains_score_breakdown():
    """reason 문자열에 스코어 내역 포함."""
```

**헬퍼 업데이트**: `make_snapshot()`은 변경 없음. 필요시 `closes_series`를 생성하는 헬퍼 추가:
```python
def make_closes(below_bb: bool = False, recovered: bool = False) -> pd.Series:
    """BB 상태 테스트용 종가 시리즈 생성."""
    # calc_bb_status()가 recovered/below/none을 반환하도록 시리즈 구성
    ...
```

**주의**: `calc_bb_status()`는 실제 캔들 데이터에서 BB를 계산하므로, 테스트 시리즈가 충분히 길어야 한다 (`bb_period + lookback` = 40개 이상).

#### 5-2. test_hotreload.py — 직렬화 테스트 확장

`TestStrategyParamsSerialization` 클래스에 추가:

```python
def test_to_dict_includes_scoring_fields(self):
    """to_dict는 스코어링 필드를 포함합니다."""
    d = StrategyParams().to_dict()
    assert d["w_volatility"] == 1.0
    assert d["entry_score_threshold"] == 85.0

def test_from_dict_with_scoring_weights(self):
    """from_dict는 스코어링 가중치를 복원합니다."""
    data = {"w_volatility": 2.0, "entry_score_threshold": 60.0}
    params = StrategyParams.from_dict(data)
    assert params.w_volatility == 2.0
    assert params.entry_score_threshold == 60.0
    # 나머지 기본값 유지
    assert params.w_ma_trend == 1.0
```

`TestEngineUpdateParams` 클래스:
- `test_update_params_changes_behavior` → 스코어링 파라미터 변경 테스트로 수정 (volatility_overload_ratio 대신 entry_score_threshold 변경)
- `test_update_params_preserves_bb_tracking` → **제거** (`_was_below_lower` 삭제됨)
- `test_update_params_affects_exit_evaluation` → **변경 없음** (청산 로직 무관)

**QA**:
```bash
pytest tests/test_strategy.py tests/test_hotreload.py -v
```

---

### Task 6: 문서 갱신

- **파일**: `docs/Algorithm_Specification.md`, `docs/frontend-design.md`
- **카테고리**: `writing`
- **스킬**: `[]`
- **의존**: Task 3, Task 4

**작업 내용**:

#### 6-1. Algorithm_Specification.md

"1. 진입 알고리즘" 섹션 (현재 line 7~)을 스코어링 방식으로 갱신:
- AND-게이트 설명 → 스코어링 설명으로 교체
- 6개 스코어 함수 공식 표로 정리
- 정규화 가중합산 공식 명시
- 임계치 비교 로직 설명
- "모든 조건이 동시에 충족되어야 합니다" 문장 → "가중합산 스코어가 임계치 이상이면 진입합니다"로 변경

#### 6-2. frontend-design.md

StrategyEditModal 설명에 "스코링 가중치" 섹션 추가:
- 6개 Slider 컨트롤 설명 (각 필터별 가중치 0~10)
- 진입 임계치 InputNumber 설명
- 프리셋에 스코어링 파라미터가 포함됨을 명시

**QA**: 문서 파일에 "스코어링" 또는 "가중치" 텍스트 포함 확인.

---

## Final Verification Wave

모든 Task 완료 후 실행:

```bash
# 백엔드 테스트
pytest tests/ -v

# 프론트엔드 린트 + 타입 체크
cd frontend && npx eslint . && npx tsc --noEmit
```

## 커밋 전략
1. Tasks 1+2: `feat: StrategyParams/TradeSignal에 스코어링 필드 추가`
2. Task 3: `feat: evaluate_entry() AND-게이트를 가중치 스코어링으로 전환`
3. Task 4: `feat: StrategyEditModal에 스코어링 가중치 UI 추가`
4. Task 5: `test: 스코어링 시스템 테스트 전면 재작성`
5. Task 6: `docs: 알고리즘 명세/프론트엔드 설계 문서에 스코어링 반영`
