# 대시보드 스코어/실행 컬럼 미표시 버그 수정

## 목표
대시보드 "거래대금 상위 종목" 테이블에서 **스코어** 및 **실행** 컬럼이 항상 "-"로 표시되는 버그를 수정한다.
변동성/추세/BB/RSI 등 다른 지표는 정상 표시되므로, 스코어/실행 데이터만 `bot_state.symbol_volatilities` JSONB에 누락되는 원인을 찾아 해결한다.

## 근본 원인 분석

### 데이터 흐름
```
orchestrator._evaluate_entries()
  ├─ [Line 415-422] 기본 지표 저장 (vol, trend, bb, rsi, rsi_slope, adx)  ← ✅ 정상
  ├─ [Line 424-460] evaluate_entry() → 스코어 계산 → 게이트 체크 → .update()  ← ❌ 여기서 실패 시 스코어 누락
  └─ [Line 496-497] upsert_bot_state(symbol_volatilities=...)  ← 스코어 없는 dict 저장됨
```

### 핵심 문제
`orchestrator.py` `_evaluate_entries()` 메서드의 **try/except 블록 구조**:
- Line 369-472: 하나의 큰 try/except 블록 안에 기본 지표 수집(Line 415-422)과 스코어 계산(Line 424-460)이 모두 포함
- `evaluate_entry()` 호출(Line 425-429) 또는 게이트 체크(Line 440-448) 중 예외 발생 시:
  - 기본 지표는 이미 `symbol_indicators[symbol]`에 추가됨 → 변동성/추세/BB/RSI 정상 표시
  - 스코어/실행 데이터는 `.update()` 도달 전 → **누락** → 프론트엔드에서 "-" 표시
- `except ValueError` (Line 469): `logger.debug`로만 기록 → 로그에서 발견 어려움
- `except Exception` (Line 471): `logger.error`로 기록되지만 부분 데이터는 이미 dict에 남아 있음

### 가능한 직접 원인 (우선순위 순)
1. **`evaluate_entry()` 내부 예외**: `_score_bb_recovery()`에서 `closes_series` 길이 부족 시 인덱싱 에러
2. **`is_on_cooldown()` 또는 `can_enter()` 예외**: 초기화 전 호출 시 AttributeError
3. **조기 반환**: `_evaluate_entries()` Line 335-339 연속 손절 브레이커 활성 시 → 전체 메서드 반환 → 스코어 계산 자체 스킵
4. **봇 미실행/재시작 미반영**: 코드 변경 후 봇 재시작 안 됨

## 수정 범위

### IN (수정 대상)
- `src/orchestrator.py`: try/except 구조 개선, 스코어 계산 예외 격리
- 디버그 로깅 강화

### OUT (수정 제외)
- DB 스키마 변경 불필요 (JSONB 컬럼이므로 필드 자유 추가)
- 프론트엔드 변경 불필요 (이미 `entry_score`, `entry_executable` 렌더링 구현 완료)
- `strategy/engine.py` 변경 불필요 (로직 자체는 정상)

## 테스트 전략
- 수정 후 봇 재시작 → 대시보드에서 스코어/실행 컬럼 값 확인
- 에러 로그 모니터링 (`logger.error` / `logger.warning` 출력 확인)

---

## Tasks

### TODO-1: 스코어 계산 예외 격리 (orchestrator.py)
- **파일**: `src/orchestrator.py`
- **위치**: `_evaluate_entries()` 메서드, Line 424-460
- **작업**: 스코어 계산 및 게이트 체크 로직을 **별도 try/except**로 감싸서, 예외 발생 시에도 기본 지표는 물론 **안전한 기본값**으로 스코어 데이터를 채워넣기

#### 구체적 변경사항

현재 코드 (Line 369-472, 하나의 try/except):
```python
for symbol in self._target_symbols:
    try:
        # ... OHLCV 수집, 스냅샷 계산 ...
        # 기본 지표 저장 (Line 415-422)
        symbol_indicators[symbol] = { "vol": ..., "trend": ..., ... }
        
        # 스코어 계산 (Line 424-460) ← 여기서 예외 시 스코어 누락
        signal = self._strategy.evaluate_entry(...)
        # ... 게이트 체크 ...
        symbol_indicators[symbol].update({ "entry_score": ..., ... })
        
    except ValueError as e:
        logger.debug(...)
    except Exception as e:
        logger.error(...)
```

수정 후:
```python
for symbol in self._target_symbols:
    try:
        # ... OHLCV 수집, 스냅샷 계산 ...
        # 기본 지표 저장
        symbol_indicators[symbol] = { "vol": ..., "trend": ..., ... }

        # ── 스코어 계산 (예외 격리) ──
        try:
            signal = self._strategy.evaluate_entry(
                symbol, snapshot, closes,
                threshold_offset=regime_offset,
                regime=self._current_regime,
            )

            entry_threshold_base = self._config.strategy.entry_score_threshold
            entry_threshold_effective = min(entry_threshold_base + regime_offset, 99)
            entry_score = round(signal.score, 1) if signal.score is not None else None
            entry_decision = "BUY" if signal.signal == Signal.BUY else (
                "PAUSE" if signal.signal == Signal.MARKET_PAUSE else "HOLD"
            )

            # 진입 게이트 체크
            global_entry_block_reason: str | None = None
            if self._executor.is_on_cooldown(symbol):
                global_entry_block_reason = "쿨다운"
            else:
                can_enter, reason = self._risk.can_enter(symbol, current_balance)
                if not can_enter:
                    global_entry_block_reason = reason or "리스크 차단"

            entry_executable = (
                signal.signal == Signal.BUY and global_entry_block_reason is None
            )

            # 스코어 데이터 추가
            symbol_indicators[symbol].update({
                "entry_score": entry_score,
                "entry_threshold_base": entry_threshold_base,
                "entry_threshold_effective": entry_threshold_effective,
                "entry_regime_offset": regime_offset,
                "entry_decision": entry_decision,
                "entry_block_reason": global_entry_block_reason or signal.reason,
                "entry_executable": entry_executable,
            })

            # 실제 매수 실행
            if entry_executable:
                self._execute_buy(symbol, signal, current_balance)
            elif signal.signal == Signal.MARKET_PAUSE:
                logger.info("[%s] %s", symbol, signal.reason)

        except Exception as e:
            logger.warning("스코어 계산/게이트 체크 실패 [%s]: %s", symbol, e)
            # 스코어 계산 실패 시에도 기본 폴백값 제공 (프론트엔드에서 "-" 대신 상태 표시)
            symbol_indicators[symbol].update({
                "entry_score": None,
                "entry_decision": "ERROR",
                "entry_block_reason": f"스코어 계산 오류: {str(e)[:50]}",
                "entry_executable": False,
            })

        time.sleep(0.2)
    except ValueError as e:
        logger.debug("진입 평가 건너뜀 [%s]: %s", symbol, e)
    except Exception as e:
        logger.error("진입 평가 오류 [%s]: %s", symbol, e)
```

#### QA 검증
1. 변경 후 `python -c "from src.orchestrator import Orchestrator"` 임포트 확인
2. 봇 재시작 후 10초 내 대시보드에서 스코어/실행 컬럼에 값 표시되는지 확인
3. 의도적으로 예외 유발 테스트: 스코어 폴백값(`entry_decision: "ERROR"`)이 표시되는지 확인
4. 정상 동작 시: 스코어 숫자값 + 실행 ✓/✗ 표시 확인

### TODO-2: 조기 반환 시에도 기존 지표 유지 (orchestrator.py)
- **파일**: `src/orchestrator.py`
- **위치**: `_evaluate_entries()` 메서드, Line 332-339
- **작업**: 연속 손절 브레이커 활성 시 조기 반환하면 `symbol_indicators`가 빈 dict → `upsert_bot_state`도 호출 안 됨 → 이전 틱의 스코어 데이터가 stale하게 남는 문제는 허용 (실시간 갱신 아닐 뿐 기존 데이터 유지)

#### 분석 결과
Line 335-339:
```python
if self._entry_blocked_until and datetime.now() < self._entry_blocked_until:
    if self._loop_count % 60 == 1:
        ...
    return  # ← 여기서 전체 반환 → 이번 틱의 symbol_indicators는 빈 dict → upsert 호출 안 됨
```

**이 경우는 버그가 아님**: `return` 시 `upsert_bot_state`도 호출되지 않으므로 **이전 틱의 데이터가 그대로 유지**됨. 프론트엔드에서는 이전에 저장된 스코어가 표시됨.

**단, 최초 실행 시 문제**: 봇 시작 직후 연속 손절 브레이커가 활성화되면 `symbol_volatilities`가 한 번도 저장되지 않아 테이블 전체가 비어있을 수 있음. 이 경우 사용자가 보고한 증상(다른 지표는 보임)과 다르므로 현재 이슈의 원인은 아님.

**조치**: 변경 불필요. TODO-1만으로 충분.

### TODO-3: 프론트엔드 "ERROR" 결정 표시 지원 (DashboardPage.tsx)
- **파일**: `frontend/src/pages/DashboardPage.tsx`
- **위치**: `getEntryDecisionLabel()` 함수 (Line 90-94)
- **작업**: 백엔드에서 `entry_decision: "ERROR"` 전송 시 적절히 표시

#### 구체적 변경사항

현재 코드 (Line 90-94):
```typescript
function getEntryDecisionLabel(decision: string | null | undefined): { text: string; color: string } {
  if (decision === 'BUY') return { text: '매수', color: '#389e0d' };
  if (decision === 'PAUSE') return { text: '일시중지', color: '#fa8c16' };
  return { text: '대기', color: '#999' };
}
```

수정 후:
```typescript
function getEntryDecisionLabel(decision: string | null | undefined): { text: string; color: string } {
  if (decision === 'BUY') return { text: '매수', color: '#389e0d' };
  if (decision === 'PAUSE') return { text: '일시중지', color: '#fa8c16' };
  if (decision === 'ERROR') return { text: '오류', color: '#cf1322' };
  return { text: '대기', color: '#999' };
}
```

#### QA 검증
1. 정상 상태에서 스코어 Tooltip에 "매수"/"일시중지"/"대기" 표시 확인
2. 에러 상태에서 "오류" 빨간색 표시 확인

## Final Verification Wave

수정 완료 후 전체 검증:
1. **봇 재시작**: `python main.py` (또는 기존 실행 방식)
2. **대시보드 확인**: 10초 후 거래대금 상위 종목 테이블에서:
   - 스코어 컬럼: 숫자값 표시 (예: 45, 72, 88)
   - 실행 컬럼: ✓ 또는 ✗ 표시
3. **에러 로그 확인**: `"스코어 계산/게이트 체크 실패"` 경고가 출력되면 → 근본 원인 추가 조사 필요
4. **영향받는 파일 2개, 모두 반영 완료** 확인
