# Learnings

## 2026-02-28: Plan Analysis
- Plan: fix-preset-save (프리셋 저장 버그 수정)
- Root cause: `upsert()` silently fails with RLS + anon key; `update().eq('id', 1)` bypasses this
- Only 1 file needs modification: `frontend/src/lib/strategyParams.ts`
- 3 call sites: SettingsPage.tsx (L244, L267, L70), DashboardPage.tsx (L815)
- Call sites do NOT need changes (function signature unchanged)
- Backend `upsert_bot_state()` uses service_role key — NOT affected
