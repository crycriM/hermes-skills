# Error Patterns — 2026-07-29

## Summary

- Total actionable errors: 89
- 4 categories crossed >=3 threshold
- New threshold crossing: tool:skill_manage:error (was 2, now 13)

## Categories at >=3 threshold

| Category | Count | Status |
|---|---|---|
| model:api_error | 35 | Already documented (router :8079 contention, transient) |
| tool:terminal:error | 27 | Already documented (approval wall, process state, timeouts) |
| tool:skill_manage:error | 13 | **NEW — threshold crossed**. #1 cause: models call `skill_manage(action='create')` without content param |
| tool:skill_view:error | 3 | Already documented (skill name hallucination) |

## Categories below threshold (no action needed)

| Category | Count | Status |
|---|---|---|
| tool:search_files:error | 2 | Below threshold |
| tool:read_file:error | 2 | Below threshold |
| tool:patch:error | 2 | Below threshold |
| tool:memory:error | 2 | Below threshold |
| tool:process:status_not_found | 1 | Below threshold |
| model:503_unavailable | 1 | Below threshold |
| tool:clarify:error | 1 | Below threshold |

## Notable changes from 2026-07-28

- **model:api_error**: 14 → 35 (significant increase, but still transient router contention)
- **tool:terminal:error**: 4 → 27 (increase, still broad terminal failures)
- **tool:skill_manage:error**: 2 → 13 (major increase, crossed threshold)
- **tool:skill_view:error**: 3 → 3 (stable)
- Overall actionable errors: 25 → 89 (3.5x increase)

## Notes

- Memory tool confirmed unavailable in cron (permanent limitation)
- Router contention still present but transient (retry logic handles it)
- No skill patches needed — skill_manage errors are model usage patterns, not skill bugs
- All recurring errors already documented in skill and memory
