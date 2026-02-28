# Learnings — hybrid-regime-filter

## Codebase State (2026-02-28)
- Worktree: `C:\Users\찬기\Desktop\workspace\projects\zenith-hybrid-regime`
- Branch: `feat/hybrid-regime-filter` off main (df04c8c)
- The exit scoring system (w_exit_*, exit_score_threshold, trailing_stop_*, etc.) already exists in main
- `saveStrategyParams()` already uses RPC approach (not upsert)
- `StrategyEditModal.tsx` has exit scoring UI sections (lines ~486-515)
- Plan line references are based on the main branch — verify exact lines before editing

## Key Constraints
- `regime.py` classify_regime() — DO NOT MODIFY
- `evaluate_exit()` — DO NOT add regime offset
- effective_threshold cap: 99.0 (never reach 100)
- All comments/logs in Korean
- Backend: synchronous only, no async/await
- Frontend: AntD 6.3, inline styles only, dark theme only
- `@dataclass(frozen=True)` pattern for config
