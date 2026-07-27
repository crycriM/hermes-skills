---
title: "RAG Re-index Log — 2026-06-22"
created: 2026-06-22
---

# RAG Re-index — June 22, 2026

Clean cron run. No errors.

## Collection Counts

| Collection | Count  | Delta vs last (Jun 21) |
|------------|--------|------------------------|
| documents  | 157    | stable                 |
| skills     | 12,276 | up from 12,237 (+39)   |
| sessions   | 801    | stable                 |

(Note: supertank is no longer reported separately — the startup log only lists documents, skills, and sessions.)

## Notes

- Vault indexer: 246 batches (final batch 26 chunks), 12,276 skill chunks. Completed in foreground within 120s.
- Skills count up by 39 (12,237 → 12,276) — modest growth, likely new/updated skills.
- Session backfill: all 105 sessions already indexed, 0 new chunks.
- Port 8001 freed successfully (pkill + ss verification).
- `systemctl --user start rag-service` succeeded (no approval gate triggered).
- Embedding model loaded in ~1s; health check OK after 20s wait.
- Search test returned results from `all` collections (total=1, collections_searched="all").
- No crash-looping (restart counter=0, fresh PID 672301).
- Service active since 08:02:22 CEST.
