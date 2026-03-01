# Zenith 전략 개선 적용 보고서 — 2026-03-01

> `LOSS_REPORT_2026-03-01.md`에서 도출된 6가지 개선 제안 중 **5가지를 코드에 적용**하고,
> `SIGN_ANALYSIS_2026-03-01.md`에서 도출된 **트레일링 스탑 사문화 문제 1가지를 추가 적용**했습니다.

---

## 1. 적용 완료 — 파라미터 조정 (4건)

### 📁 수정 파일: `src/config.py`

| # | 파라미터 | 변경 전 | 변경 후 | 근거 |
|---|----------|---------|---------|------|
| ① | `entry_score_threshold` | 70.0 | **80.0** | Vol·MA·BB 3개가 상시 만점(하한 50점) → 70은 사실상 무조건 진입 허용. 80으로 상향하여 RSI·ADX 등 추가 근거 없이는 진입 차단 |
| ② | `regime_lookback_candles` | 3 | **1** | 히스테리시스 3캔들 다수결 → 레짐 전환 최소 55분 지연. 1캔들로 줄여 즉시 반영 |
| ③ | `atr_stop_multiplier` | 2.5 | **3.0** | 알트코인 일중 변동폭 4~5% 대비 ATR×2.5가 타이트 → 정상 노이즈에도 손절 발동. 3.0으로 여유 확보 |
| ④ | `regime_trending_offset` | 15.0 | **20.0** | 추세장 감지 시 진입 임계치 = 80+20 = 100 → 사실상 추세장 매수 완전 차단 (원래 의도대로) |

**효과 시뮬레이션** (3/1 손실 거래 4건 기준):
- XRP (스코어 74.1) → 80 미만 → **차단됨** ✅
- SOL (스코어 75.6) → 80 미만 → **차단됨** ✅
- BTC (스코어 71.3) → 80 미만 → **차단됨** ✅
- ETH (스코어 76.0) → 80 미만 → **차단됨** ✅
- SIGN (스코어 73.2) → 80 미만 → **차단됨** (이 거래는 수익이었으나, RSI 과매도 미충족 상태에서의 진입이므로 차단이 적절)

---

## 2. 적용 완료 — BB Recovery 스코어 보강 (로직 수정)

### 📁 수정 파일: `src/strategy/engine.py` — `_score_bb_recovery()` 메서드

#### 변경 내용

**Falling Knife Guard** (떨어지는 칼날 방어):
```python
# RSI < 15 (극단적 과매도) → BB recovered여도 100 대신 30점으로 제한
if rsi < 15.0:
    return 30.0
```

**MA20 추세 확인** (데드캣 바운스 방어):
```python
# MA20 < MA50 (하락 추세) → BB recovered여도 100 대신 30점으로 하향
ma_trend = calc_ma_trend(closes_series, params.ma_short_period, params.ma_long_period)
if ma_trend is False:
    return 30.0
```

#### 근거
- 3/1 손실의 핵심 원인: BB Recovery가 하락 추세에서도 "recovered" = 100점을 부여하여 점수를 부풀림
- RSI가 극단적으로 낮은 상태(< 15)는 "과매도 반등"이 아니라 "매도 압력 극심" 신호
- MA20 < MA50은 중기 하락 추세를 의미 → 일시적 BB 복귀는 진정한 반등이 아닌 데드캣 바운스

#### 함수 시그니처 변경
```python
# Before
def _score_bb_recovery(self, closes_series, params: StrategyParams) -> float:

# After — rsi 인자 추가
def _score_bb_recovery(self, closes_series, params: StrategyParams, rsi: float = 50.0) -> float:
```

`evaluate_entry()`에서 호출 시 `rsi=snapshot.rsi` 전달하도록 수정.

---

## 3. 적용 완료 — 레짐 감지 주기 단축

### 📁 수정 파일: `src/orchestrator.py`

```python
# Before: 10분마다 레짐 갱신 (60 루프 × 10초 = 600초)
if self._loop_count % 60 == 1:

# After: 2분마다 레짐 갱신 (12 루프 × 10초 = 120초)
if self._loop_count % 12 == 1:
```

#### 근거
- 3/1 레짐 전환 지연: 07:00 하락 시작 → 10:19 Trending 감지 = **3시간 19분 지연**
- 지연 원인: 10분 갱신 주기 + 3캔들 히스테리시스(→1로 축소)
- 개선 후 최대 지연: 2분 + 1캔들 히스테리시스 ≈ **17분** (기존 대비 ~12배 개선)

---

## 4. 적용 완료 — 연속 손절 브레이커

### 📁 수정 파일: `src/orchestrator.py`

#### 신규 메서드: `_record_stop_loss()`
```python
def _record_stop_loss(self) -> None:
    """30분 내 2건 이상 손절 시 신규 매수 30분 차단"""
    now = datetime.now()
    self._stop_loss_timestamps.append(now)
    # 30분 이전 기록 제거
    cutoff = now - timedelta(minutes=30)
    self._stop_loss_timestamps = [ts for ts in self._stop_loss_timestamps if ts >= cutoff]
    # 2건 이상 → 차단
    if len(self._stop_loss_timestamps) >= 2:
        self._entry_blocked_until = now + timedelta(minutes=30)
```

#### 진입 차단 로직 (`_evaluate_entries()` 상단)
```python
if self._entry_blocked_until and datetime.now() < self._entry_blocked_until:
    return  # 신규 매수 거부
```

#### 근거
- 3/1 사례: 07:15~07:42에 4건 연속 매수 → 08:52~12:33에 4건 연속 손절
- 첫 2건 손절(08:52~08:53) 후에도 BTC·ETH 포지션 유지 → 추가 손실 발생
- 브레이커가 있었다면: 08:53 시점에서 신규 매수 차단 → 하지만 이미 보유한 포지션은 영향 없음 (기존 포지션의 손절은 정상 작동)
- **향후 유사 상황에서 연쇄 진입 방지** 효과

#### 추가 변경
- `from datetime import date, datetime` → `from datetime import date, datetime, timedelta`
- `__init__`에 `_stop_loss_timestamps`, `_entry_blocked_until` 상태 변수 추가

---

## 5. 적용 완료 — 트레일링 스탑 실효화 수정 (SIGN 분석 도출)

### 📁 수정 파일: `src/strategy/engine.py` — `evaluate_exit()` 메서드

#### 문제
1차 익절(50%) 후 스코어링 매도가 트레일링 스탑보다 **항상 먼저 발동**하여, 트레일링 스탑이 사실상 사문화된 로직이었음.

**SIGN 사례**:
```
07:37  1차 익절(50%) @ +2.1%
07:41  스코어 71.7 → 전량 매도 (트레일링 작동 기회 없음)
이후   가격 +4%까지 상승 → 포착 실패
```

#### 수정 내용
```python
# 1차 익절 후(has_sold_half=True)에는 스코어링 익절을 건너뛰고,
# 오직 하드 룰(동적 손절 + 트레일링 스탑)만 작동하도록 변경
if has_sold_half:
    return TradeSignal(
        signal=Signal.HOLD,
        reason="1차 익절 완료 — 트레일링 스탑 대기 중 (스코어링 매도 비활성)",
        ...
    )
```

#### 동작 변경
| 상황 | 변경 전 | 변경 후 |
|------|---------|---------|
| 1차 익절 전 | 스코어 ≥ 70 → SELL_HALF | 동일 (변경 없음) |
| 1차 익절 후 | 스코어 ≥ 70 → 즉시 SELL_ALL | **스코어 무시**, 트레일링 스탑만 대기 |
| 트레일링 스탑 | 고점 - ATR×2.0 하락 시 SELL_ALL | 동일 (변경 없음) |
| 동적 손절 | 진입가 - ATR×3.0 하락 시 STOP_LOSS | 동일 (변경 없음) |

#### SIGN에 적용했을 경우 시뮬레이션
```
07:15  매수 @ 37.6
07:37  1차 익절(50%) @ 38.4 (+2.1%)
       ↓ 트레일링 고점 추적 시작 (스코어링 매도 비활성)
       가격 상승: 38.4 → 38.8 → 39.1 (고점 +4.0%)
       트레일링 고점 = 39.1
       ↓ 가격 하락 시
       트레일링 스탑 = 39.1 - ATR×2.0 터치 → 2차 매도
       
예상 추가 수익: 나머지 50%에서 +2~3%p 추가 포착 가능
```

---

## 6. 미적용 — Kelly Fraction 조기 확보

### 현황
- `kelly_min_trades = 30` 미달로 Half-Kelly 동적 포지션 사이징 미작동
- 고정 비율(20%) 폴백 사용 중

### 미적용 사유
- 아키텍처 수준 변경이 필요 (소액 거래 전략 추가)
- 현재 거래 빈도로는 자연적으로 30건 달성까지 수일 소요
- 파라미터 조정만으로는 해결 불가 → 별도 기획 필요

### 향후 계획
- `kelly_min_trades`를 15~20으로 하향 검토
- 또는 백테스트 결과를 초기 학습 데이터로 주입하는 방안

---

## 7. 2차 개선 — GPT 분석 기반 전략 리팩토링

> `GPT-ANALYSIS-ON-LOSS-REPORT.md`의 개선안을 기반으로 추가 리팩토링을 적용했습니다.

### 📁 수정 파일: `src/config.py`

| # | 파라미터 | 변경 전 | 변경 후 | 근거 |
|---|----------|---------|---------|------|
| ① | `atr_stop_multiplier_ranging` | (신규) | **2.8** | 횡보장: 노이즈 허용 여유 |
| ② | `atr_stop_multiplier_trending` | (신규) | **2.2** | 추세장: 역추세 빠른 탈출 |
| ③ | `atr_stop_multiplier_volatile` | (신규) | **2.5** | 변동성 폭발: 중립 |
| ④ | `regime_lookback_candles` | 1 | **2** | 플래핑 완화, 2캔들 다수결 |
| ⑤ | `regime_min_hold_minutes` | (신규) | **20** | 레짐 플래핑 방지 최소 유지 시간 |
| ⑥ | `w_volatility` | 1.0 | **0.8** | 상시 만점 경향 → 비중 하향 |
| ⑦ | `w_ma_trend` | 1.0 | **1.2** | 추세 컨텍스트 강화 |
| ⑧ | `w_adx` | 1.0 | **1.1** | 추세 강도 반영 강화 |
| ⑨ | `w_bb_recovery` | 1.0 | **0.9** | 상시 만점 경향 → 비중 하향 |
| ⑩ | `w_rsi_slope` | 1.0 | **1.2** | 과매도 품질 반영 강화 |
| ⑪ | `w_rsi_level` | 1.0 | **1.3** | 과매도 수준 가장 중요 |
| ⑫ | `entry_score_threshold` | 80.0 | **78.0** | 가중치 재분포 후 재튜닝 |

### 📁 수정 파일: `src/strategy/engine.py`

| # | 변경 사항 | 설명 |
|---|----------|------|
| ① | `evaluate_entry(regime=)` 파라미터 추가 | 레짐별 ATR 배수 적용 |
| ② | RSI slope 감쇠 (×0.6) | RSI < 15 시 RSI↗ 기울기 스코어 감쇠 |
| ③ | 레짐 적응형 ATR 진입 손절 | `get_atr_multiplier(regime)` 사용 |
| ④ | BB Recovery 3단계 평가 | RSI<15→30, MA데드크로스→30, ADX>25+price<MA50→40, 정상→100 |
| ⑤ | `evaluate_exit(regime=)` 파라미터 추가 | 레짐별 ATR 배수 적용 |
| ⑥ | 레짐 적응형 ATR 청산 손절 | `get_atr_multiplier(regime)` 사용 |

### 📁 수정 파일: `src/orchestrator.py`

| # | 변경 사항 | 설명 |
|---|----------|------|
| ① | `_regime_changed_at` 상태 변수 | 레짐 변경 시각 기록 |
| ② | 단방향 레짐 홀드 로직 | 안전 모드 진입 즉시, 해제만 20분 홀드 |
| ③ | `evaluate_exit(regime=)` 전달 | 현재 레짐 기반 동적 손절 |
| ④ | `evaluate_entry(regime=)` 전달 | 현재 레짐 기반 진입 손절 |
| ⑤ | 가격 스냅샷 레짐 ATR | 대시보드 손절선 표시 정확도 향상 |

### 핵심 설계 결정

1. **기존 `atr_stop_multiplier` 유지**: 백테스트 호환을 위해 폴백 필드로 보존. 레짐별 신규 필드 3개 추가.
2. **레짐 홀드 단방향**: 안전 모드(trending/volatile) 진입은 즉시 허용, 해제(→ranging)만 20분 홀드. 급변장 안전 보장.
3. **RSI slope 감쇠**: 가중치가 아닌 점수 자체에 ×0.6 적용. 극저 RSI에서의 일시적 반등 기울기 신뢰도 하향.
4. **BB Recovery MA50 인라인 계산**: `closes_series.rolling().mean().iloc[-1]`로 직접 계산. IndicatorSnapshot 확장 불필요.

---

## 8. 수정 파일 요약

| 파일 | 변경 유형 | 개선 항목 |
|------|-----------|-----------|
| `src/config.py` | 파라미터 조정 | ①~⑫ 진입 임계치, 가중치, 레짐별 ATR, 레짐 홀드 |
| `src/strategy/engine.py` | 로직 보강 | RSI slope 감쇠, BB Recovery 3단계, 레짐 적응형 ATR |
| `src/orchestrator.py` | 로직 수정 | 레짐 홀드, 레짐 기반 손절선 계산 및 전달 |

---

## 9. 리스크 평가

### 의도된 부작용
- **매수 빈도 감소**: 임계치 상향 및 가중치 조정으로 정밀한 타이밍만 허용
- **손절 유연성 확보**: 레짐별 ATR 배수 차등화로 추세장 빠른 탈출 및 횡보장 노이즈 허용
- **2차 익절 극대화**: 트레일링 스탑 실효화로 추세 추종 수익 확보

### 주의 사항
- 레짐 홀드 20분 적용으로 급격한 횡보 전환 시 대응이 약간 늦어질 수 있음 (안전 우선 설계)
- RSI slope 감쇠로 인해 극저점 반등 초기 진입이 늦어질 수 있음

---

> 📅 적용일: 2026-03-01
> 🔗 근거 문서: `LOSS_REPORT_2026-03-01.md`, `SIGN_ANALYSIS_2026-03-01.md`, `GPT-ANALYSIS-ON-LOSS-REPORT.md`
> 🤖 생성 도구: Zenith 전략 개선 시스템
