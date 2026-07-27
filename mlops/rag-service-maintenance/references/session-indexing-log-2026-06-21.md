---
title: "RAG Re-index Log — 2026-06-21"
created: 2026-06-21
---

# RAG Re-index — June 21, 2026

Clean cron run. No errors.

## Collection Counts

| Collection | Count  | Delta vs last |
|------------|--------|---------------|
| documents  | 157    | stable        |
| skills     | 12,237 | down from 14,482 (June 16) |
| sessions   | 801    | stable        |
| supertank  | 250    | up from 164   |

## Notes

- Vault indexer: 245 batches, 12,237 skill chunks. Completed in foreground within 300s timeout.
- Session backfill: all 105 sessions already indexed, 0 new chunks.
- pkill returned exit -15 (known pitfall) but port 8001 was freed successfully.
- `systemctl --user start rag-service` succeeded (no approval gate triggered).
- Health check OK after 20s wait.
- Search test returned results from skills collection.
- Skills count dropped from 14,482 (June 16) to 12,237 — likely due to skill deletions/cleanup in the intervening days.
- Supertank grew from 164 to 250 (+86).
