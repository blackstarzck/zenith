# GPT 개선안 기반 전략 리팩토링

## 메타데이터
- **생성일**: 2026-03-01
- **근거 문서**: `GPT-ANALYSIS-ON-LOSS-REPORT.md`, `LOSS_REPORT_2026-03-01.md`, `SIGN_ANALYSIS_2026-03-01.md`
- **수정 파일**: `src/config.py`, `src/strategy/engine.py`, `src/orchestrator.py`, `tests/test_hotreload.py`
- **Metis 검토**: 완료 (session: `ses_356480aceffeVP3M62aDQQrOX4`)

## 핵심 설계 결정 (사전 확정)

### D1: `atr_stop_multiplier` 기존 필드 유지 (Option A)
기존 `atr_stop_multiplier` 필드를 **제거하지 않고 폴백으로 유지**. 레짐별 신규 필드 3개 추가. 백테스트 모듈(`compare_strategies.py`)과 프론트엔드 핫리로드 호환성 보장.

### D2: 레짐 홀드 단방향 적용
`regime_min_hold_minutes`는 **단방향**:
- 안전 모드(ranging→trending, ranging→volatile) 전환은 **즉시 허용**
- 안전 모드 해제(trending→ranging, volatile→ranging) 전환만 **최소 유지 시간 적용**
- 이유: 급변장에서 안전 모드 진입이 20분 차단되면 위험

### D3: RSI slope 감쇠는 raw score에 적용
`evaluate_entry()`에서 scores 딕셔너리 구성 후, RSI < 15이면 `RSI↗` 스코어를 ×0.6. 가중치가 아닌 **점수 자체를 감쇠**.

### D4: BB Recovery 3단계에서 MA50 값은 인라인 계산
`_score_bb_recovery()` 내에서 `closes_series.rolling(params.ma_long_period).mean().iloc[-1]`로 직접 계산. `IndicatorSnapshot` 확장 불필요.

---

## Phase 0: 사전 검증 (테스트 기준선 확보)

- [x] TODO-0.1: 기존 테스트 assert 값 수정 (이미 깨진 상태)
**파일**: `tests/test_hotreload.py`

Metis가 발견한 문제: 테스트가 이전 기본값(2.5, 70.0)을 assert하지만 config는 이미 3.0, 80.0으로 변경됨.

**수정 내용**:
- **라인 52** 근처: `atr_stop_multiplier` assert 값 → `3.0` (현재 config 기본값 — 이 시점에서 아직 변경 전이므로 3.0)
- **라인 114** 근처: `entry_score_threshold` assert 값 → `80.0` (현재 config 기본값)
- 위치를 정확히 `grep`으로 찾아서 수정할 것

**QA**:
```bash
pytest tests/test_hotreload.py -v
# 모든 테스트 PASS 확인 — 이것이 리팩토링 기준선
```

---

## Phase 1: config.py 수정

- [x] TODO-1.1: ATR 레짐 적응형 필드 추가
**파일**: `src/config.py` — `StrategyParams` 클래스

**변경 내용**:
1. 기존 `atr_stop_multiplier: float = 3.0` 유지 (폴백용, 라인 67)
2. **바로 아래에** 레짐별 필드 3개 추가:
```python
    atr_stop_multiplier_ranging: float = 2.8   # 횡보장: 노이즈 허용 여유
    atr_stop_multiplier_trending: float = 2.2  # 추세장: 역추세 빠른 탈출
    atr_stop_multiplier_volatile: float = 2.5  # 변동성 폭발: 중립
```

3. `to_dict()` / `from_dict()` 는 `asdict()` + `dc_fields()` 기반이므로 **자동 반영됨** — 추가 수정 불필요

**QA**: `python -c "from src.config import StrategyParams; p = StrategyParams(); print(p.atr_stop_multiplier_ranging)"` → `2.8` 출력

- [x] TODO-1.2: `get_atr_multiplier()` 메서드 추가
**파일**: `src/config.py` — `StrategyParams` 클래스, `to_dict()` 메서드 바로 위

```python
    def get_atr_multiplier(self, regime: str = "ranging") -> float:
        """레짐에 따른 ATR 손절 배수를 반환합니다."""
        if regime == "ranging":
            return self.atr_stop_multiplier_ranging
        elif regime == "trending":
            return self.atr_stop_multiplier_trending
        elif regime == "volatile":
            return self.atr_stop_multiplier_volatile
        return self.atr_stop_multiplier  # 알 수 없는 레짐 → 기본 폴백
```

**위치**: `take_profit_sell_ratio` 필드 아래, `to_dict()` 위에 삽입
**QA**: `python -c "from src.config import StrategyParams; p = StrategyParams(); assert p.get_atr_multiplier('trending') == 2.2; assert p.get_atr_multiplier('unknown') == 3.0; print('OK')"` → `OK`

- [x] TODO-1.3: 레짐 파라미터 변경
**파일**: `src/config.py`

1. `regime_lookback_candles: int = 1` → `regime_lookback_candles: int = 2` (라인 100)
2. `regime_volatile_offset` 라인(103) 바로 아래에 추가:
```python
    regime_min_hold_minutes: int = 20  # 레짐 변경 후 최소 유지 시간 (분) — 플래핑 방지
```

- [x] TODO-1.4: 스코어링 가중치 재조정
**파일**: `src/config.py` — 라인 106~111

**변경 전**:
```python
    w_volatility: float = 1.0
    w_ma_trend: float = 1.0
    w_adx: float = 1.0
    w_bb_recovery: float = 1.0
    w_rsi_slope: float = 1.0
    w_rsi_level: float = 1.0
```

**변경 후** (GPT 제안 기반):
```python
    w_volatility: float = 0.8       # 상시 만점 경향 → 비중 하향
    w_ma_trend: float = 1.2         # 추세 컨텍스트 강화
    w_adx: float = 1.1              # 추세 강도 반영 강화
    w_bb_recovery: float = 0.9      # 상시 만점 경향 → 비중 하향
    w_rsi_slope: float = 1.2        # 과매도 품질 반영 강화
    w_rsi_level: float = 1.3        # 과매도 수준 가장 중요
```

- [x] TODO-1.5: 진입 임계치 조정
**파일**: `src/config.py` — 라인 114

`entry_score_threshold: float = 80.0` → `entry_score_threshold: float = 78.0`

**근거**: 가중치 재분포로 스코어 분포가 변경되므로 임계치도 재조정. GPT 제안: "반드시 스코어 재분포 이후 재튜닝" → 78이 적절.

**Phase 1 QA**:
```bash
python -c "
from src.config import StrategyParams
p = StrategyParams()
assert p.atr_stop_multiplier == 3.0, '폴백 필드 유지'
assert p.atr_stop_multiplier_ranging == 2.8
assert p.atr_stop_multiplier_trending == 2.2
assert p.atr_stop_multiplier_volatile == 2.5
assert p.get_atr_multiplier('ranging') == 2.8
assert p.get_atr_multiplier('trending') == 2.2
assert p.get_atr_multiplier('unknown') == 3.0
assert p.regime_lookback_candles == 2
assert p.regime_min_hold_minutes == 20
assert p.w_volatility == 0.8
assert p.w_rsi_level == 1.3
assert p.entry_score_threshold == 78.0
print('Phase 1 OK')
"
```

---

## Phase 2: engine.py 수정

- [x] TODO-2.1: `evaluate_entry()` — regime 파라미터 추가
**파일**: `src/strategy/engine.py` — `evaluate_entry()` 메서드 시그니처 (라인 61~67)

**변경**: `threshold_offset: float = 0.0,` 다음 줄에 추가:
```python
        regime: str = "ranging",
```

- [x] TODO-2.2: `evaluate_entry()` — Falling Knife RSI slope 감쇠
**파일**: `src/strategy/engine.py` — scores 딕셔너리 구성 직후 (라인 93 `}` 뒤)

**추가**:
```python
        # Falling Knife Guard: RSI < 15 시 RSI↗ 기울기 스코어 감쇠 (×0.6)
        # 극저 RSI에서의 일시적 반등 기울기는 신뢰도가 낮음
        if snapshot.rsi < 15.0:
            w, s = scores["RSI↗"]
            scores["RSI↗"] = (w, s * 0.6)
```

- [x] TODO-2.3: `evaluate_entry()` — 레짐 적응형 ATR 적용
**파일**: `src/strategy/engine.py` — BUY 신호 생성 부분 (라인 117)

**변경 전**: `stop_loss = price - (snapshot.atr * params.atr_stop_multiplier)`
**변경 후**: `stop_loss = price - (snapshot.atr * params.get_atr_multiplier(regime))`

- [x] TODO-2.4: `_score_bb_recovery()` — 3단계 평가
**파일**: `src/strategy/engine.py` — `_score_bb_recovery()` 메서드 전체 교체 (라인 158~179)

**시그니처 변경**: 
```python
def _score_bb_recovery(self, closes_series, params: StrategyParams, rsi: float = 50.0, adx: float = 20.0, current_price: float = 0.0) -> float:
```

**호출부 변경** (`evaluate_entry` 내 scores 딕셔너리, 라인 90):
```python
"BB": (params.w_bb_recovery, self._score_bb_recovery(closes_series, params, rsi=snapshot.rsi, adx=snapshot.adx, current_price=price)),
```

**전체 로직**:
```python
    def _score_bb_recovery(self, closes_series, params: StrategyParams, rsi: float = 50.0, adx: float = 20.0, current_price: float = 0.0) -> float:
        """BB 복귀 스코어. 3단계 추세 컨텍스트 평가.

        - RSI < 15 (극단적 과매도) → 30점 (떨어지는 칼날 방어)
        - MA20 < MA50 (하락 추세) → 30점 (데드캣 바운스 방어)
        - ADX > 25 & 가격 < MA50 (추세 의심) → 40점
        - 그 외 → 100점 (정상 평균회귀)
        """
        if closes_series is None or len(closes_series) < params.bb_period + 20:
            return 0.0  # 데이터 부족 시 불리
        status = calc_bb_status(closes_series, params.bb_period, params.bb_std_dev)
        if status == "recovered":
            # 1단계: Falling Knife Guard — 극단적 과매도에서 반등 신호 신뢰도 하향
            if rsi < 15.0:
                return 30.0
            # 2단계: MA 데드크로스 — 확정적 하락 추세
            ma_trend = calc_ma_trend(closes_series, params.ma_short_period, params.ma_long_period)
            if ma_trend is False:
                return 30.0
            # 3단계: 추세 의심 구간 — ADX > 25이면서 가격이 MA50 아래
            if adx > 25.0 and current_price > 0:
                ma50 = closes_series.rolling(window=params.ma_long_period).mean().iloc[-1]
                if current_price < ma50:
                    return 40.0
            return 100.0
        elif status == "below":
            return 30.0  # 이탈 중 — 부분 점수 (반등 가능성)
        else:  # "none"
            return 0.0
```

- [x] TODO-2.5: `evaluate_exit()` — regime 파라미터 추가 + 레짐 적응형 ATR
**파일**: `src/strategy/engine.py` — `evaluate_exit()` 메서드

1. **시그니처** (라인 194~199): `position: "Position",` 다음 줄에 추가:
```python
        regime: str = "ranging",
```

2. **동적 손절 계산** (라인 222):
**변경 전**: `stop_loss_price = entry_price - (snapshot.atr * params.atr_stop_multiplier)`
**변경 후**: `stop_loss_price = entry_price - (snapshot.atr * params.get_atr_multiplier(regime))`

**Phase 2 QA**:
```bash
python -m py_compile src/strategy/engine.py && echo "engine.py OK"
```

---

## Phase 3: orchestrator.py 수정

- [x] TODO-3.1: 레짐 플래핑 방지 상태 변수 추가
**파일**: `src/orchestrator.py` — `__init__` 내, `_entry_blocked_until` 변수 선언 바로 아래 (라인 67)

```python
        self._regime_changed_at: datetime | None = None  # 레짐 변경 시각 (플래핑 방지)
```

- [x] TODO-3.2: `_update_market_regime()` — 단방향 홀드 로직
**파일**: `src/orchestrator.py` — `_update_market_regime()` 내 레짐 변경 분기 (라인 663~670)

**변경 전**:
```python
            new_regime = result.regime.value
            if new_regime != self._current_regime:
                logger.info(
                    "[레짐 변경] %s → %s | ADX=%.1f, Vol=%.2f | 사유: %s",
                    self._current_regime, new_regime,
                    result.adx, result.volatility_ratio, result.reason,
                )
                self._current_regime = new_regime
```

**변경 후**:
```python
            new_regime = result.regime.value
            if new_regime != self._current_regime:
                # 단방향 홀드: 안전 모드(trending/volatile) 진입은 즉시 허용,
                # 안전 모드 해제(→ ranging)는 최소 유지 시간 적용
                allow_change = True
                is_leaving_safety = (
                    self._current_regime in ("trending", "volatile")
                    and new_regime == "ranging"
                )
                if is_leaving_safety and self._regime_changed_at:
                    min_hold = self._config.strategy.regime_min_hold_minutes
                    elapsed = (datetime.now() - self._regime_changed_at).total_seconds() / 60
                    if elapsed < min_hold:
                        allow_change = False
                        logger.debug(
                            "[레짐 홀드] %s → %s 전환 차단 (최소 %d분 유지, 경과: %.0f분)",
                            self._current_regime, new_regime, min_hold, elapsed,
                        )
                if allow_change:
                    logger.info(
                        "[레짐 변경] %s → %s | ADX=%.1f, Vol=%.2f | 사유: %s",
                        self._current_regime, new_regime,
                        result.adx, result.volatility_ratio, result.reason,
                    )
                    self._current_regime = new_regime
                    self._regime_changed_at = datetime.now()
```

- [x] TODO-3.3: `evaluate_exit()` 호출에 regime 전달
**파일**: `src/orchestrator.py` — `_evaluate_exits()` 내 (라인 281)

**변경 전**: `signal = self._strategy.evaluate_exit(symbol, snapshot, pos)`
**변경 후**: `signal = self._strategy.evaluate_exit(symbol, snapshot, pos, regime=self._current_regime)`

- [x] TODO-3.4: `evaluate_entry()` 호출에 regime 전달
**파일**: `src/orchestrator.py` — `_evaluate_entries()` 내 (라인 404~407)

**변경 전**:
```python
                signal = self._strategy.evaluate_entry(
                    symbol, snapshot, closes,
                    threshold_offset=regime_offset,
                )
```

**변경 후**:
```python
                signal = self._strategy.evaluate_entry(
                    symbol, snapshot, closes,
                    threshold_offset=regime_offset,
                    regime=self._current_regime,
                )
```

- [x] TODO-3.5: `_save_price_snapshots()` 레짐 적응형 ATR 적용
**파일**: `src/orchestrator.py` — `_save_price_snapshots()` 내 (라인 457)

**변경 전**: `stop_loss = pos.entry_price - (snapshot.atr * params.atr_stop_multiplier)`
**변경 후**: `stop_loss = pos.entry_price - (snapshot.atr * params.get_atr_multiplier(self._current_regime))`

**Phase 3 QA**:
```bash
python -m py_compile src/orchestrator.py && echo "orchestrator.py OK"
```

---

## Phase 4: 테스트 업데이트

- [x] TODO-4.1: test_hotreload.py assert 값 최종 갱신
**파일**: `tests/test_hotreload.py`

`grep` 으로 정확한 위치를 찾아 수정:
- `atr_stop_multiplier` assert → `3.0` (폴백 필드 값 유지)
- `entry_score_threshold` assert → `78.0`
- 가중치 assert들 → 각각 `0.8, 1.2, 1.1, 0.9, 1.2, 1.3` 으로 변경 (해당 assert가 있는 경우에만)

- [x] TODO-4.2: 신규 테스트 추가
**파일**: `tests/test_strategy.py` (또는 적절한 테스트 파일)

다음 테스트 케이스 추가:
1. `test_get_atr_multiplier_by_regime`: 각 레짐별 반환값 + unknown 레짐 폴백 검증
2. `test_bb_recovery_middle_tier`: ADX>25 & price<MA50 일 때 40점 반환 검증
3. `test_rsi_slope_dampening`: RSI<15 일 때 RSI↗ 스코어가 ×0.6 감쇠 검증
4. `test_regime_adaptive_stop_loss`: 레짐에 따라 stop_loss_price가 다르게 계산되는지 검증

**Phase 4 QA**:
```bash
pytest tests/ -v --tb=short
# 모든 테스트 PASS
```

---

## Phase 5: 문서 업데이트

- [x] TODO-5.1: IMPROVEMENT_REPORT 갱신
**파일**: `IMPROVEMENT_REPORT_2026-03-01.md`

GPT 개선안 기반으로 재작성된 내용 반영:
- 레짐 적응형 ATR (일률 3.0 → 레짐별 2.2/2.8/2.5)
- 스코어링 가중치 재조정
- BB Recovery 3단계
- RSI slope 감쇠
- 레짐 플래핑 방지
- entry_score_threshold 78

---

## Final Verification Wave

```bash
# 1. 구문 검증
python -m py_compile src/config.py && echo "config OK"
python -m py_compile src/strategy/engine.py && echo "engine OK"
python -m py_compile src/orchestrator.py && echo "orchestrator OK"

# 2. 전체 테스트
pytest tests/ -v --tb=short

# 3. Config 호환성
python -c "
from src.config import StrategyParams
# 기존 from_dict 호환
old = {'atr_stop_multiplier': 3.0, 'entry_score_threshold': 80.0}
p = StrategyParams.from_dict(old)
assert p.get_atr_multiplier('ranging') == 2.8
assert p.get_atr_multiplier('trending') == 2.2
assert p.get_atr_multiplier('unknown') == p.atr_stop_multiplier
print('Backward compat OK')
"

# 4. 백테스트 모듈 호환
python -c "from src.backtest.compare_strategies import STRATEGIES; print(f'{len(STRATEGIES)} strategies OK')"
```

## MUST NOT

- ❌ `async/await` 추가 금지
- ❌ 기존 `atr_stop_multiplier` 필드 제거 금지 (백테스트 호환)
- ❌ `classify_regime()` 함수 수정 금지 (히스테리시스는 regime.py 책임)
- ❌ `_record_stop_loss()` / 연속 손절 브레이커 수정 금지
- ❌ 매도 스코어링 가중치/임계치 변경 금지 (매수 진입만 수정)
- ❌ 새 외부 패키지 추가 금지
- ❌ 추상 클래스 / Protocol 등 불필요한 추상화 금지
