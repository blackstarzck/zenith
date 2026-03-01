# Decisions

- D1: Keep existing atr_stop_multiplier field as fallback + add 3 regime-specific fields
- D2: Regime hold is unidirectional — entering safety mode instant, leaving requires 20min hold
- D3: RSI slope dampening applies to raw score (×0.6), not weight
- D4: MA50 value computed inline in _score_bb_recovery() via rolling().mean().iloc[-1]
