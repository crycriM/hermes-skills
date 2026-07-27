---
title: "RAG Re-index Log — 2026-06-30"
created: 2026-06-30
---

# RAG Re-index — June 30, 2026

Clean cron run. No errors.

## Collection Counts

| Collection  | Count   | Delta vs last (Jun 22) |
|-------------|---------|------------------------|
| documents   | 157     | stable                 |
| skills      | 12,487  | up from 12,276 (+211)  |
| sessions    | 801     | stable                 |

## Notes

- Vault indexer: 250 batches (final batch 37 chunks), 12,487 skill chunks. Completed in foreground within 180s.
- Skills count up by 211 (12,276 → 12,487) — significant growth, likely new/updated skills since last full re-index.
- Session backfill: all 105 sessions already indexed, 0 new chunks.
- Old service (PID 3879360) killed with SIGTERM, port freed cleanly.
- `systemctl --user start rag-service` succeeded (no approval gate triggered).
- New service (PID 4017154) started with fresh collection references: documents=157, skills=12487, sessions=801.
- Embedding model loaded; health check OK; search test returned results from "all" collections.
- No crash-looping (restart counter=0, fresh PID 4017154).
- Service active since 08:06:03 CEST.
