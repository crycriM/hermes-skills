# Error Patterns — 2026-07-31

## Summary

- Total actionable errors: 157
- 13 categories
- 13 unique sessions
- No new threshold crossings beyond what's already documented

## Categories at >=3 threshold

| Category | Count | Sessions | Status |
|---|---|---|---|
| tool:skill_manage:error | 46 | 10 | Already documented (#1: missing content param) |
| tool:terminal:error | 43 | 13 | Already documented (broad terminal failures) |
| model:api_error | 36 | 9 | Already documented (router :8079 contention, transient) |
| tool:skill_view:error | 7 | 5 | Already documented (skill name hallucination) |
| tool:patch:error | 6 | 3 | Already documented (non-unique match, escape-drift) |
| tool:memory:error | 5 | 2 | Already documented (cron sessions have NO memory tool) |
| tool:search_files:error | 3 | 3 | Already documented (background review denied) |
| tool:execute_code:error | 3 | 2 | Already documented (cron blocked, HTML leak) |

## Categories below threshold (no action needed)

| Category | Count | Status |
|---|---|---|
| tool:read_file:error | 2 | Below threshold |
| model:503_unavailable | 2 | Below threshold |
| tool:process:status_not_found | 1 | Below threshold |
| tool:clarify:error | 1 | Below threshold |
| tool:terminal:pending_approval | 1 | Below threshold |
| tool:browser_click:error | 1 | Below threshold |

## Delta vs 2026-07-30 scan (123 errors)

- **tool:skill_manage:error +19** (27→46) — same root cause, still #1: missing content param on create. Accumulating.
- **tool:terminal:error +7** (36→43) — stable accumulation
- **model:api_error -1** (36→36) — stable
- **tool:skill_view:error +2** (5→7) — stable
- **tool:patch:error +2** (4→6) — stable
- **tool:memory:error 0** (5→5) — stable
- **tool:search_files:error 0** (3→3) — stable
- **tool:execute_code:error +2** (1→3) — just crossed threshold
- **model:503_unavailable +1** (1→2) — stable, below threshold
- **new: tool:read_file:error** (2) — below threshold
- **new: tool:process:status_not_found** (1) — below threshold
- **new: tool:clarify:error** (1) — below threshold
- **new: tool:terminal:pending_approval** (1) — below threshold
- **new: tool:browser_click:error** (1) — below threshold

## Notes

- Memory tool confirmed unavailable in cron (permanent limitation)
- Router contention still present but transient (retry logic handles it)
- No skill patches needed — errors are tool usage patterns, not skill bugs
- All recurring errors already documented in skill and memory
- No new categories emerged beyond the 8 at >=3 threshold
- skill_manage errors continue to grow (+19 since last scan) — models still omitting content param
