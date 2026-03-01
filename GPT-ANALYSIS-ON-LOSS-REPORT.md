# Zenith 전략 개선 실행안

작성일: 2026-03-01
기반: 손실 분석 리포트 + 추가 비판 분석

---

# 1. 목표 정의

본 개선안의 목표는 단순 손실 감소가 아니라 다음 3가지를 동시에 달성하는 것이다.

* 역추세 진입 구조적 차단
* 신호 품질(signal quality) 향상
* 추세장 내 생존력 강화

> 핵심 원칙: **파라미터 튜닝보다 신호 구조 개선을 우선한다.**

---

# 2. 우선순위 로드맵

## Phase 1 — 즉시 안정화 (1~3일)

* 레짐 감지 지연 축소
* Falling knife 방어
* BB Recovery 과대평가 교정

## Phase 2 — 신호 품질 개선 (1~2주)

* 스코어 구조 재정규화
* 컴포넌트 가중 재설계
* 노이즈 손절 최적화

## Phase 3 — 전략 구조 개선 (중기)

* 하이브리드 전략 도입
* 레짐별 전략 분리
* Kelly 학습 안정화

---

# 3. Phase 1 — 즉시 적용 항목

## 3.1 레짐 감지 가속 (HIGH PRIORITY)

### 문제

현재 구조는 레짐 전환이 과도하게 느리다.

### 조치

#### (1) 레짐 갱신 주기 단축

```python
# before
if loop_count % 60 == 1:
    update_regime()

# after (권장)
if loop_count % 12 == 1:  # 약 2분
    update_regime()
```

#### (2) 히스테리시스 완화

```python
# before
regime_lookback_candles = 3

# after (권장)
regime_lookback_candles = 2
```

> ⚠️ 1로 바로 낮추지 말 것 — regime flapping 위험

#### (3) Flapping 방지 장치 추가 (필수)

```python
MIN_REGIME_HOLD_MINUTES = 20
```

레짐 변경 후 최소 유지 시간을 둔다.

---

## 3.2 Falling Knife Guard (CRITICAL)

### 문제

극저 RSI 구간에서 mean reversion 실패율 높음.

### 구현

```python
if rsi < 15:
    bb_score = min(bb_score, 30)
    rsi_slope_score *= 0.6
```

### 기대 효과

* 역추세 초입 진입 감소
* 급락장 손절 연쇄 완화

---

## 3.3 BB Recovery 재평가 (VERY IMPORTANT)

### 문제

현재 BB recovered = 거의 자동 진입 트리거

### 개선 로직

```python
if bb_recovered:
    if ma20_slope < 0:
        bb_score = 30  # 하락 추세 내 반등
    elif adx > 25 and price < ma50:
        bb_score = 40  # 추세 의심 구간
    else:
        bb_score = 100  # 정상 mean reversion
```

### 핵심

단순 복귀 여부가 아니라 **추세 컨텍스트 기반 평가**로 전환

---

# 4. Phase 2 — 스코어 구조 재설계

## 4.1 스코어 분포 정상화 (HIGH IMPACT)

### 문제

현재 컴포넌트 다수가 상시 100점 근처 → 변별력 부족

### 목표

각 컴포넌트 평균이 40~70 범위에 분포하도록 조정

---

## 4.2 하드 캡 제거 + 소프트 스케일링

### before (문제 구조)

```python
score = 100 if condition else 0
```

### after (권장)

```python
score = sigmoid(normalized_value) * 100
```

또는

```python
score = clamp(linear_scale(value), 0, 100)
```

### 기대 효과

* threshold 민감도 감소
* 신호 미세 구분 가능

---

## 4.3 가중치 재조정

현재: 전부 weight = 1.0

### 권장 가중치

| 컴포넌트       | weight |
| ---------- | ------ |
| BB         | 0.9    |
| RSI slope  | 1.2    |
| RSI level  | 1.3    |
| ADX        | 1.1    |
| MA trend   | 1.2    |
| Volatility | 0.8    |

> 목적: 과매도 품질과 추세 맥락을 더 강하게 반영

---

## 4.4 Entry Threshold 재설정 (보조 조치)

### 권장

```python
entry_score_threshold = 78
```

> 단, 반드시 스코어 재분포 이후 재튜닝

---

# 5. Phase 2 — 리스크 관리 개선

## 5.1 ATR 손절 재설계 (주의)

### 현재 문제

단순 multiplier 증가는 tail risk 증가 가능

### 권장 방식

```python
if regime == "ranging":
    atr_mult = 2.8
elif regime == "trending":
    atr_mult = 2.2
else:
    atr_mult = 2.5
```

> 레짐 적응형 손절로 전환

---

## 5.2 연속 손절 브레이커 (보조 안전장치)

```python
if stop_loss_count_last_30m >= 2:
    block_new_entries(minutes=30)
```

### 목적

* 이상장 보호
* 연쇄 손실 완화

> 단, edge 대체 수단으로 사용 금지

---

# 6. Phase 3 — 전략 구조 개선 (중기 핵심)

## 6.1 하이브리드 전략 도입

### 현재 문제

mean reversion 단일 전략 → 추세장에서 구조적 취약

### 구조

```text
Ranging regime   → Mean Reversion
Trending regime  → Momentum / Breakout
Volatile regime  → Position size 축소
```

---

## 6.2 Early Trend Detector 추가

ADX 기반은 후행성이 있음.

### 보조 지표 권장

* MA slope acceleration
* lower low / lower high 패턴
* BB midline 기울기

```python
early_trend_score = (
    ma_slope_accel
    + structure_break
    + bb_mid_slope
)
```

---

## 6.3 Kelly 학습 가속

### 조치

```python
kelly_min_trades = 20  # 임시
```

또는

* micro position으로 샘플 축적
* rolling window 적용

---

# 7. 검증 계획 (필수)

## 7.1 백테스트 요구사항

* 최소 6개월
* 상승장 / 하락장 / 횡보장 포함
* walk-forward 검증

## 7.2 핵심 KPI

* Expectancy
* Max drawdown
* Regime별 승률
* 평균 손절 크기
* 진입 대비 MAE/MFE

---

# 8. 즉시 실행 체크리스트

## 이번 주 적용

* [ ] 레짐 갱신 주기 단축
* [ ] hysteresis 3→2
* [ ] falling knife guard
* [ ] BB recovery 재평가
* [ ] regime hold time 추가

## 다음 스프린트

* [ ] 스코어 분포 분석
* [ ] 가중치 재튜닝
* [ ] adaptive ATR
* [ ] early trend detector

## 중기

* [ ] 하이브리드 전략
* [ ] Kelly 안정화

---

# 9. 최종 결론

현재 손실의 본질은 단순 파라미터 문제가 아니라:

> **(1) 레짐 인식 지연 + (2) 신호 과대평가 + (3) mean reversion 단일 구조**

따라서 가장 효과적인 개선 순서는 다음과 같다.

1. 신호 품질 교정
2. 레짐 반응 속도 개선
3. 스코어 분포 정상화
4. 전략 다변화

---

**핵심 원칙:**

> "진입을 줄이는 것이 손절을 늦추는 것보다 항상 먼저다."
