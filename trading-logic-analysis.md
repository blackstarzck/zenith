# Zenith 매매 로직 정밀 분석 리포트

> **분석일**: 2026-02-27
> **대상**: 알고리즘 명세(`docs/Algorithm_Specification.md`) vs 실제 구현 코드
> **범위**: 진입/청산/리스크/주문실행 전 계층

---

## 데이터 흐름 요약

```
Orchestrator._tick() (10초 루프)
  │
  ├─ 1. UpbitCollector.get_top_volume_symbols() ─── 거래대금 상위 10종목 추출 (10분마다)
  │
  ├─ 2. UpbitCollector.get_ohlcv() ─────────────── 종목별 15분봉 200개 수집
  │
  ├─ 3. compute_snapshot() ─────────────────────── BB, RSI, ATR, ADX, 변동성비율 계산
  │
  ├─ 4. _evaluate_exits() ──────────────────────── 보유 종목 청산 조건 평가
  │     └─ MeanReversionEngine.evaluate_exit()
  │         ├─ 손절: price ≤ entry_price - ATR × 2.5 → STOP_LOSS (전량)
  │         ├─ 2차 익절: price ≥ BB 상단 → SELL_ALL (전량)
  │         └─ 1차 익절: price ≥ BB 중앙 + 수익률 ≥ 0.3% → SELL_HALF (50%)
  │
  ├─ 5. _evaluate_entries() ─────────────────────── 미보유 종목 진입 조건 평가
  │     ├─ RiskManager.can_enter() ── 중복/한도/일일정지 체크
  │     └─ MeanReversionEngine.evaluate_entry()
  │         ├─ 변동성 과부하 필터 (ratio ≥ 2.0 → MARKET_PAUSE)
  │         ├─ 추세 필터 (MA20 > MA50)
  │         ├─ BB 하단 이탈 후 복귀 확인
  │         └─ RSI 과매도 + 상승 전환 확증
  │
  └─ 6. _execute_buy() / _execute_sell_*() ──────── 주문 실행 + DB 기록 + 알림
```

---

## 1. 진입 알고리즘 (Entry Logic)

### ✅ 1단계: 시장 필터링 — 정상

| 명세 | 코드 | 위치 | 판정 |
|------|------|------|------|
| 거래 대금 상위 10개 종목 | `top_volume_count: int = 10` | `config.py` L63 | ✅ 일치 |
| 변동성 2배 이상 → 매매 중단 | `volatility_overload_ratio: float = 2.0` | `config.py` L53 | ✅ 일치 |

변동성 과부하 판단 코드 (`engine.py` L84-91):

```python
if snapshot.volatility_ratio >= params.volatility_overload_ratio:
    return TradeSignal(signal=Signal.MARKET_PAUSE, ...)
```

### ✅ 2단계: BB 하단 이탈 후 복귀 — 정상

**명세**: "가격이 볼린저 밴드 하단선을 뚫고 내려갔다가, 다시 밴드 안으로 들어와서 캔들이 마감될 때"

**코드** (`engine.py` L104-128):

```python
was_below = self._was_below_lower.get(symbol, False)
currently_below = price < bb.lower

if currently_below:
    self._was_below_lower[symbol] = True       # 이탈 기록
    return TradeSignal(signal=Signal.HOLD, ...)  # 복귀 대기

if not was_below:
    return TradeSignal(signal=Signal.HOLD, ...)  # 이탈 이력 없음

self._was_below_lower[symbol] = False  # 이력 초기화 → 복귀 확인 완료
```

2단계 로직은 명세를 정확히 구현하고 있습니다.
- 현재 가격 < BB 하단 → 이탈 상태 기록, 대기
- 이전에 이탈한 적 없음 → 진입 조건 미충족
- 이전에 이탈 + 현재 밴드 내 → **복귀 확인, 다음 단계 진행**

### 🔴 CRITICAL #1: RSI 상승 확증 우회 버그

**명세**: "RSI가 30 이하(과매도)에서 **고개를 들며 상승하는** 구간일 때 진입의 신뢰도를 높입니다"

**코드** (`engine.py` L130-151):

```python
# ── 3단계: RSI 확증 ──
rsi_rising = True  # 기본값
if closes_series is not None and len(closes_series) > 20:
    rsi_slope = calc_rsi_slope(closes_series, params.rsi_period, lookback=params.rsi_slope_lookback)
    rsi_rising = rsi_slope > 0

if rsi > params.rsi_oversold and not rsi_rising:        # ← 문제 지점: RSI > 30일 때만 체크
    return TradeSignal(signal=Signal.HOLD, reason="RSI 상승 전환 미확인")

if rsi > params.rsi_oversold + params.rsi_entry_ceiling_offset:  # RSI > 35 → 차단
    return TradeSignal(signal=Signal.HOLD, reason="RSI 과매도 구간 아님")
```

**문제**: 첫 번째 조건이 `rsi > 30 AND NOT rising`일 때만 차단합니다. RSI ≤ 30이면 `rsi_rising` 값에 상관없이 이 조건을 통과합니다.

| RSI 값 | rsi_rising | 현재 동작 | 올바른 동작 |
|--------|-----------|----------|-----------|
| 25 (하락 중) | `False` | **통과 (매수!)** | 차단해야 함 |
| 25 (상승 중) | `True` | 통과 (매수) | 통과 (매수) |
| 32 (하락 중) | `False` | 차단 | 차단 |
| 32 (상승 중) | `True` | 통과 | 통과 |

**실전 위험 시나리오**: RSI가 25 → 20 → 15로 급락하는 패닉 셀링 구간에서, BB 하단 이탈 후 일시적으로 밴드 내로 가격이 복귀하면 RSI 상승 확증 없이도 매수가 실행됩니다. "떨어지는 칼날"을 잡는 상황이 발생할 수 있습니다.

**수정 방향**: RSI 값에 관계없이 `rsi_rising` 체크를 적용해야 합니다.

```python
# 수정안: RSI 값에 무관하게 상승 전환 확인
if not rsi_rising:
    return TradeSignal(signal=Signal.HOLD, reason="RSI 상승 전환 미확인")
```

---

### 🔴 CRITICAL #2: ADX 추세 강도 필터 미사용 (유령 필터)

**인프라는 모두 갖춰져 있습니다**:

| 구성요소 | 위치 | 상태 |
|---------|------|------|
| `calc_adx()` 함수 | `indicators.py` L276-332 | ✅ 구현됨 |
| `compute_snapshot()`에서 ADX 계산 | `indicators.py` L372-375 | ✅ 호출됨 |
| `IndicatorSnapshot.adx` 필드 | `indicators.py` L34 | ✅ 존재 |
| `adx_trend_threshold: 25.0` 파라미터 | `config.py` L81 | ✅ 설정됨 |

**그러나** `engine.py`의 `evaluate_entry()` 함수에서 `snapshot.adx`를 **한 번도 참조하지 않습니다.**

**실전 위험 시나리오**: ADX가 40~50인 강한 하락 추세에서 BB 하단을 타고 내려가는 "밴드 라이딩" 패턴이 발생합니다. 가격이 일시적으로 밴드 안으로 들어오면 반등으로 오인하여 매수하지만, 추세가 계속 이어져 손절됩니다. 이 과정이 반복되면 연속 손실이 발생합니다.

**수정 방향**: 변동성 필터 이후에 ADX 체크를 추가합니다.

```python
# 추세 강도 필터: ADX가 높으면 강한 추세 → 역추세 진입 위험
if snapshot.adx > params.adx_trend_threshold:
    return TradeSignal(signal=Signal.HOLD,
        reason=f"강한 추세 (ADX={snapshot.adx:.1f} > {params.adx_trend_threshold})")
```

---

### ⚠️ 명세 차이 #1: 변동성 필터 시간 윈도우 불일치

| 항목 | 명세 | 코드 | 15분봉 환산 |
|------|------|------|-----------|
| 단기 윈도우 | **24시간** | `vol_short_window=16` | 16 × 15분 = **4시간** |
| 장기 윈도우 | **20일** | `vol_long_window=192` | 192 × 15분 ≈ **2일** |

**원인**: 캔들 수집량이 `candle_count=200`으로 제한됨. 명세대로 24시간(96개)/20일(1,920개)을 구현하려면 수집량을 대폭 늘려야 합니다.

**영향**: 2일 평균 대비 4시간 변동성을 비교하므로, 장기 시장 상황 변화를 감지하지 못할 수 있습니다. 다만 현재 윈도우도 실용적으로 작동하며, 데이터 수집 비용 대비 합리적인 절충안입니다.

**결정 필요**: 명세를 코드에 맞춰 수정하거나, 수집량을 늘려 명세에 맞출지 선택이 필요합니다.

---

## 2. 청산 알고리즘 (Exit Logic)

### ✅ 동적 손절 (ATR 기반) — 정상

**명세**: "최근 시장의 평균적인 흔들림 폭(ATR)을 계산하여 그 폭의 2.5배 이상 가격이 떨어지면 즉시 매도"

**코드** (`engine.py` L193-202):

```python
stop_loss_price = entry_price - (snapshot.atr * params.atr_stop_multiplier)  # 2.5
if price <= stop_loss_price:
    return TradeSignal(signal=Signal.STOP_LOSS, ...)
```

정확히 일치합니다. `atr_stop_multiplier`는 config.py에서 `2.5`로 설정됩니다.

### ✅ 분할 익절 — 정상

**명세**:
- 1차: BB 중앙선 도달 → 50% 매도
- 2차: BB 상단선 도달 → 나머지 전량 매도

**코드의 청산 평가 우선순위** (`engine.py` L193-245):

```
1순위: 동적 손절 (ATR) → STOP_LOSS (전량)
2순위: BB 상단선 도달 → SELL_ALL (전량)     ← 2차 익절을 먼저 체크
3순위: BB 중앙선 도달 + 수익률 ≥ 0.3% → SELL_HALF (50%)  ← 1차 익절
```

**설계 포인트**: 2차 익절(BB 상단)을 1차(BB 중앙)보다 먼저 평가합니다. 가격이 한 번에 상단선을 돌파하면 50%가 아닌 전량을 매도하는 올바른 로직입니다.

### ✅ 1차 익절 실행 시 소액 처리 — 견고

`Orchestrator._execute_sell_half()` (`orchestrator.py` L456-490):

```
실제 보유량 조회 (업비트 잔고 기준)
  → 절반 금액 계산
  → 최소 주문금액(5,000 KRW) 비교
     ├── 절반 ≥ 5,000 → 50% 매도
     ├── 절반 < 5,000, 전량 ≥ 5,000 → 전량 매도로 전환
     └── 전량 < 5,000 → 더스트(dust) 정리 (포지션 제거만)
```

### ⚠️ 명세 차이 #2: 최소 수익률 필터 (명세에 없는 추가 조건)

**코드** (`engine.py` L217-229):

```python
if not has_sold_half and price >= bb.middle:
    if profit_pct < params.min_profit_margin:  # 0.3%
        return TradeSignal(signal=Signal.HOLD, reason="수익률 부족")
```

명세에는 "BB 중앙선 도달 시 50% 매도"로만 되어 있으나, 코드에는 수수료(0.1%) + 알파(0.2%) = **0.3%** 이상 수익이 확보되어야만 1차 익절을 실행합니다.

**평가**: 수수료 역마진 방지를 위한 **합리적인 추가 안전장치**입니다. 명세 업데이트를 권장합니다.

---

## 3. 리스크 관리 규정

### ✅ 자산 배분 — 정상

| 명세 | 코드 | 위치 | 판정 |
|------|------|------|------|
| 종목당 최대 20% | `max_position_ratio: 0.20` | `config.py` L100 | ✅ |
| 최대 5개 동시 보유 | `max_concurrent_positions: 5` | `config.py` L101 | ✅ |
| 일일 5% 손실 → 매매 중단 | `daily_loss_limit_ratio: 0.05` | `config.py` L102 | ✅ |

### ✅ 진입 가능 여부 판단 — 정상

`RiskManager.can_enter()` (`manager.py` L47-64):

```python
def can_enter(self, symbol, current_balance):
    if self._is_daily_stopped:       return False, "일일 손실 한도 초과"
    if symbol in self._positions:    return False, "이미 보유 중"
    if len(self._positions) >= 5:    return False, "동시 보유 한도 도달"
    return True, "진입 가능"
```

### ✅ 포지션 사이징 — 정상

`RiskManager.calc_position_size()` (`manager.py` L66-77):

```python
def calc_position_size(self, current_balance):
    max_amount = current_balance * self._params.max_position_ratio  # × 0.20
    if max_amount < self._params.min_order_amount_krw:              # < 5,000 KRW
        return 0.0
    return max_amount
```

### ✅ 일일 손실 한도 — 정상

`RiskManager.record_realized_pnl()` (`manager.py` L122-137):

```python
def record_realized_pnl(self, pnl):
    self._daily_realized_pnl += pnl
    loss_limit = self._initial_balance * self._params.daily_loss_limit_ratio  # × 0.05
    if self._daily_realized_pnl < -loss_limit:
        self._is_daily_stopped = True  # 매매 전면 중단
```

---

## 4. 주문 실행 계층

### ✅ 시장가 주문 — 정상

| 항목 | 구현 | 위치 |
|------|------|------|
| 매수 | `buy_market_order(symbol, amount_krw)` — KRW 기반 | `order_executor.py` L99 |
| 매도 | `sell_market_order(symbol, volume)` — 수량 기반 | `order_executor.py` L156 |
| 체결 대기 | 30초 폴링 (2초 간격) | `order_executor.py` L202-237 |
| 타임아웃 시 | 미체결 취소 + 30분 쿨다운 | `order_executor.py` L122-123 |
| 수수료 조회 | 체결 후 `get_order()`로 실제 `paid_fee` 조회 | `order_executor.py` L269 |

### ✅ 체결 상태 판별 — 견고

`_wait_for_fill()` (`order_executor.py` L202-237):

```python
# "cancel" 상태라도 executed_volume > 0이면 부분 체결 성공으로 처리
if order.get("state") == "cancel":
    if float(order.get("executed_volume", 0)) > 0:
        return True   # 부분 체결 성공
    return False      # 체결 없이 취소 → 즉시 실패 (대기 불필요)
```

시장가 주문의 특성상 즉시 체결 후 잔여분이 cancel 처리될 수 있는 케이스를 올바르게 처리하고 있습니다.

### 🟢 Minor: PnL 계산 시 매수 수수료 미반영

**코드** (`orchestrator.py` L502, L535):

```python
pnl = result.amount - (pos.entry_price * result.volume) - result.fee
```

이 계산은 `매도 금액 - (진입가 × 매도수량) - 매도 수수료`입니다. **매수 시 지불한 수수료**는 PnL에 반영되지 않아 실제보다 미세하게 과대 계산됩니다. 업비트 수수료율 0.05% 기준으로 100만 원 매수 시 약 500원 차이로 실운영에 미치는 영향은 미미합니다.

**수정 방향**: `Position` 데이터클래스에 `entry_fee` 필드를 추가하고 PnL 계산 시 차감합니다.

---

## 5. 명세에 없는 추가 구현 (코드에만 존재)

| 기능 | 코드 위치 | 목적 | 평가 |
|------|----------|------|------|
| MA20 > MA50 추세 필터 | `engine.py` L93-102 | 하락 추세 진입 방지 | ✅ 보수적, 합리적 |
| RSI 상한 오프셋 (rsi_oversold + 5.0) | `engine.py` L144-151 | RSI 35 초과 시 과매도 아님 판정 | ✅ 합리적 |
| 최소 익절 마진 (0.3%) | `engine.py` L219 | 수수료 역마진 방지 | ✅ 합리적 |
| BB 상태 복구 (봇 재시작 시) | `engine.py` L247-283 | 인메모리 상태 연속성 보장 | ✅ 견고한 설계 |
| 체결 실패 30분 쿨다운 | `order_executor.py` L44 | 문제 종목 반복 주문 방지 | ✅ 합리적 |
| 소액 전량 전환 / 더스트 정리 | `orchestrator.py` L474-490 | 최소 주문금액 미달 시 처리 | ✅ 매우 견고 |

---

## 최종 판정 요약

| 등급 | 항목 | 파일:라인 | 설명 |
|------|------|----------|------|
| 🔴 Critical | RSI 상승 확증 우회 | `engine.py` L136 | RSI ≤ 30일 때 `rsi_rising` 체크를 건너뜀. 급락 중 매수 위험 |
| 🔴 Critical | ADX 필터 미사용 | `engine.py` (전체) | 계산만 하고 진입 조건에 미적용. 강한 하락 추세 역추세 매수 위험 |
| 🟡 Medium | 변동성 윈도우 불일치 | `config.py` L73-74 | 명세(24h/20d) vs 코드(4h/2d). 데이터 수집량 한계 |
| 🟢 Minor | PnL 매수수수료 누락 | `orchestrator.py` L502,535 | 매도 수수료만 반영. 실영향 미미 |
| ✅ 정상 | 동적 손절 (ATR × 2.5) | `engine.py` L194 | 명세 정확히 일치 |
| ✅ 정상 | 분할 익절 (50% / 전량) | `engine.py` L207-236 | 우선순위 올바름 |
| ✅ 정상 | 리스크 관리 3대 규정 | `manager.py` 전체 | 20%/5종목/5% 모두 일치 |
| ✅ 정상 | 주문 실행 + 체결 확인 | `order_executor.py` 전체 | 시장가, 폴링, 쿨다운 견고 |
| ✅ 정상 | 포지션 동기화/복구 | `orchestrator.py` L588-659 | 봇 재시작 연속성 보장 |
