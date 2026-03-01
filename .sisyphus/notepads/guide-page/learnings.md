# Learnings — guide-page

## Codebase State (2026-02-28)
- Worktree: `C:\Users\찬기\Desktop\workspace\projects\zenith-guide-page`
- Branch: `feat/guide-page` off main (7503ab5)
- Frontend: React 19 + AntD 6.3 + Vite 7.3
- Dark theme only, inline styles only, Korean UI text
- Existing pages: Dashboard, Trading, Analytics, Settings, Reports (all lazy-loaded)
- menuItems in AppLayout.tsx lines 31-37
- ReportsPage.tsx has page header pattern to follow
- docs/Strategy-Parameters-Guide.md (119 lines) — primary content source
- docs/Algorithm_Specification.md (80 lines) — secondary content source
- StrategyEditModal.tsx already has EXAMPLE_SCORES + weight-based simulator (DO NOT modify)

## Key Constraints
- StrategyEditModal.tsx — DO NOT MODIFY
- No new npm dependencies
- No Supabase queries/hooks (static page)
- No exit score simulator — entry only
- No CSS Modules/Tailwind/styled-components
- Menu label: English 'Guide' (matches convention)
- Icon: BookOutlined (InfoCircleOutlined already used for log tooltip)
- AntD v6 API must be verified via context7_query-docs before use
- Documentation update for new pages is mandatory per AGENTS.md.
- Markdown files do not have LSP support in this environment, so manual verification via Read is necessary.
