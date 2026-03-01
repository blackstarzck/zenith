# Learnings

## Initial State
- Plan has 19 TODOs across 6 phases
- Tests already broken (assert values outdated)
- All modifications are Python backend only
- No async/await allowed
- frozen=True dataclass requires method additions carefully

## 2026-03-01: 전략 파라미터 기본값 변경에 따른 테스트 코드 업데이트
- 의  기본값이 변경됨에 따라 의 단언(assert) 값을 동기화함.
- 주요 변경 사항:
  - : 2.5 -> 3.0
  - : 70.0 -> 80.0
- 테스트 결과: ============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\����\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\����\Desktop\workspace\projects\zenith
plugins: anyio-4.12.1, langsmith-0.6.9
collecting ... collected 13 items

tests/test_hotreload.py::TestStrategyParamsSerialization::test_to_dict_returns_all_fields PASSED [  7%]
tests/test_hotreload.py::TestStrategyParamsSerialization::test_from_dict_with_full_data PASSED [ 15%]
tests/test_hotreload.py::TestStrategyParamsSerialization::test_from_dict_with_partial_data PASSED [ 23%]
tests/test_hotreload.py::TestStrategyParamsSerialization::test_from_dict_with_empty_data PASSED [ 30%]
tests/test_hotreload.py::TestStrategyParamsSerialization::test_from_dict_ignores_unknown_keys PASSED [ 38%]
tests/test_hotreload.py::TestStrategyParamsSerialization::test_from_dict_ignores_none_values PASSED [ 46%]
tests/test_hotreload.py::TestStrategyParamsSerialization::test_roundtrip_to_dict_from_dict PASSED [ 53%]
tests/test_hotreload.py::TestStrategyParamsSerialization::test_to_dict_includes_scoring_fields PASSED [ 61%]
tests/test_hotreload.py::TestStrategyParamsSerialization::test_from_dict_with_scoring_weights PASSED [ 69%]
tests/test_hotreload.py::TestEngineUpdateParams::test_update_params_changes_behavior PASSED [ 76%]
tests/test_hotreload.py::TestEngineUpdateParams::test_update_params_affects_exit_evaluation PASSED [ 84%]
tests/test_hotreload.py::TestAppConfigImmutability::test_new_appconfig_with_changed_strategy PASSED [ 92%]
tests/test_hotreload.py::TestAppConfigImmutability::test_strategy_params_equality PASSED [100%]

============================= 13 passed in 0.74s ============================== 13개 테스트 모두 통과 확인.
- 교훈: 전략 파라미터 기본값을 변경할 때는 이를 참조하는 유닛 테스트 코드도 반드시 함께 업데이트해야 함.


## 2026-03-01: 전략 파라미터 기본값 변경에 따른 테스트 코드 업데이트
- src/config.py의 StrategyParams 기본값이 변경됨에 따라 tests/test_hotreload.py의 단언(assert) 값을 동기화함.
- 주요 변경 사항:
  - atr_stop_multiplier: 2.5 -> 3.0
  - entry_score_threshold: 70.0 -> 80.0
- 테스트 결과: pytest tests/test_hotreload.py -v 13개 테스트 모두 통과 확인.
- 교훈: 전략 파라미터 기본값을 변경할 때는 이를 참조하는 유닛 테스트 코드도 반드시 함께 업데이트해야 함.
## Phase 1: StrategyParams Refactor (Regime-Adaptive ATR & Scoring)

### Changes
- Added regime-adaptive ATR fields: `atr_stop_multiplier_ranging`, `atr_stop_multiplier_trending`, `atr_stop_multiplier_volatile`.
- Added `get_atr_multiplier(regime)` method to `StrategyParams`.
- Updated regime parameters: `regime_lookback_candles` (1 -> 2), added `regime_min_hold_minutes` (20).
- Updated scoring weights (`w_volatility`, `w_ma_trend`, `w_adx`, `w_bb_recovery`, `w_rsi_slope`, `w_rsi_level`).
- Updated `entry_score_threshold` (80.0 -> 78.0).

### Test Impact
- `tests/test_hotreload.py`: 2 tests failed due to changed default values.
  - `test_to_dict_includes_scoring_fields`: Fails on `w_volatility` (0.8 != 1.0).
  - `test_from_dict_with_scoring_weights`: Fails on `w_ma_trend` (1.2 != 1.0).
- These failures are expected and will be addressed in Phase 4.

### Learnings
- `StrategyParams` is a `frozen=True` dataclass, but methods can still be added.
- When using `edit` tool with `pos` and `end`, ensure the parameter name is `end`, not `total_end`.
- Redefining fields in a dataclass body results in the last definition being used, which can cause subtle bugs if not careful during refactoring.

## Phase 2: engine.py regime-adaptive changes (2026-03-01)
- All 7 changes applied in a single edit call — no conflicts
- `evaluate_entry()` and `evaluate_exit()` now accept `regime: str = "ranging"` — backward compatible
- RSI slope dampening: applied to raw score (x0.6) when RSI < 15, inserted AFTER scores dict, BEFORE normalization
- Entry/exit stop_loss now uses `params.get_atr_multiplier(regime)` instead of `params.atr_stop_multiplier`
- `_score_bb_recovery()` upgraded to 3-tier: RSI<15->30, MA dead cross->30, ADX>25+price<MA50->40, else->100
- MA50 computed inline via `closes_series.rolling(window=params.ma_long_period).mean().iloc[-1]`
- File grew from 343 to 359 lines (+16 lines net)
- `python -m py_compile` passed clean

## Phase 3: orchestrator.py regime integration (2026-03-01)
- All 5 changes applied in a single edit call — no conflicts
- `_regime_changed_at` state variable added after `_entry_blocked_until` (line 67)
- Unidirectional regime hold: safety mode entry instant, exit requires `regime_min_hold_minutes` (20min default)
- `evaluate_exit()` and `evaluate_entry()` now pass `regime=self._current_regime`
- `_save_price_snapshots()` uses `params.get_atr_multiplier(self._current_regime)` instead of `params.atr_stop_multiplier`
- No new imports needed — `datetime` already imported at line 11
- `python -m py_compile` passed clean

## Phase 4: Test Fixes and New Test Cases (2026-03-01)
- Fixed 5 failing tests, added 4 new regime-adaptive test cases
- test_hotreload.py: Updated scoring field defaults, w_ma_trend=1.2, atr_stop_multiplier_ranging replaces atr_stop_multiplier
- test_strategy.py: has_sold_half=True now disables scoring, returns HOLD with trailing stop
- 4 new TestRegimeAdaptiveStrategy tests: atr_multiplier_by_regime, bb_recovery, rsi_dampening, regime_stop_loss
- All 95 tests passed (32.44s)
