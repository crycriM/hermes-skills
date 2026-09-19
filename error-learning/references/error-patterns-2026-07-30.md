# Error Patterns — 2026-07-30

## Summary

- Total actionable errors: 123
- 12 categories
- 11 unique sessions
- No new threshold crossings beyond what's already documented

## Categories at >=3 threshold

| Category | Count | Status |
|---|---|---|
| tool:terminal:error | 36 | Already documented (broad terminal failures) |
| model:api_error | 36 | Already documented (router :8079 contention, transient) |
| tool:skill_manage:error | 27 | Already documented (#1 cause: missing content param) |
| tool:skill_view:error | 5 | Already documented (skill name hallucination) |
| tool:memory:error | 5 | Already documented (cron sessions have NO memory tool) |
| tool:patch:error | 4 | Already documented (non-unique match, escape-drift) |
| tool:search_files:error | 3 | Already documented (background review denied) |

## Categories below threshold (no action needed)

| Category | Count | Status |
|---|---|---|
| tool:read_file:error | 2 | Below threshold |
| tool:process:status_not_found | 1 | Below threshold |
| model:503_unavailable | 1 | Below threshold |
| tool:clarify:error | 1 | Below threshold |
| tool:execute_code:error | 1 | Below threshold |
| tool:terminal:pending_approval | 1 | Below threshold |

## Delta vs 2026-07-29 scan (89 errors)

- **tool:skill_manage:error +14** (13→27) — same root cause, still #1: missing content param on create
- **tool:terminal:error +9** (27→36) — stable accumulation
- **tool:memory:error +5** (new) — already documented as permanent cron limitation
- **model:api_error +1** (35→36) — stable
- **tool:search_files:error +1** (2→3) — just crossed threshold
- **tool:patch:error +2** (2→4) — stable
- **tool:skill_view:error +2** (3→5) — stable

## Notes

- Memory tool confirmed unavailable in cron (permanent limitation)
- Router contention still present but transient (retry logic handles it)
- No skill patches needed — errors are tool usage patterns, not skill bugs
- All recurring errors already documented in skill and memory
- No new categories emerged — all 7 categories at >=3 threshold already covered
