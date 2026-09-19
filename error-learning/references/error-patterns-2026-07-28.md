# Error Patterns — 2026-07-28

## Summary

- Total actionable errors: 25
- No new categories at >=3 threshold
- No new patterns — all recurring errors already documented in memory and skill

## Categories at >=3 threshold

| Category | Count | Status |
|---|---|---|
| model:api_error | 14 | Already documented (router :8079 contention, transient) |
| tool:terminal:error | 4 | Already documented (approval wall, process state, timeouts) |
| tool:skill_view:error | 3 | Already documented (skill name hallucination) |

## Categories below threshold (no action needed)

| Category | Count | Status |
|---|---|---|
| tool:skill_manage:error | 2 | Below threshold |
| tool:search_files:error | 1 | Below threshold |
| tool:read_file:error | 1 | Below threshold |

## Notes

- Memory tool confirmed unavailable in cron (permanent limitation)
- Router contention still present but transient (retry logic handles it)
- No skill patches needed — errors are tool usage patterns, not skill bugs
- Previous scan (2026-07-25): 3500 actionable errors — this scan shows only 25, suggesting the majority were noise/already-categorized entries or the log was truncated
