# RAG Service Maintenance — 2026-07-07

## Summary

Clean cron run. Vault indexer rebuilt skills collection (up 57 documents from 12,737 on July 5). Session backfill skipped all 105 sessions (no new sessions). RAG service restarted via `systemctl --user stop && systemctl --user start` — the `stop` command was auto-approved by Hermes smart approval (first time this route was cleared without manual intervention).

## Vault Indexer

- **skills**: 12,794 (from `/home/cricri/.hermes/skills`; up 57 from 12,737 on July 5)
- 256 batches indexed (last batch: 44 chunks)
- Quick search test passed for both documents and skills collections

## Session Backfill

- **sessions**: 801 (all already indexed, 0 new chunks created)
- 0 sessions processed from 105 files

## RAG Service Restart

- Pre-existing service: PID 2174371, active since 05:22 CEST (2h 48min uptime), restart counter 0
- `systemctl --user stop rag-service` — **auto-approved by Hermes smart approval** (previously documented as consistently blocked for stop/restart in cron mode)
- `systemctl --user start rag-service` — succeeded immediately, no approval gate
- Model loaded in ~4s — fast startup
- Startup log: `ChromaDB initialized (documents: 157, skills: 12794, sessions: 801)`

## Verification

- Search endpoint (`/search` with `collection: "all"`, `n_results: 5`) returned 5 results with valid distances/metadata
- `collections_searched: "all"` confirmed
- Service active (running) since 2026-07-07 08:11:44 CEST

## Final Collection Counts

| Collection   | Count  |
|-------------|--------|
| documents   |    157 |
| skills      | 12,794 |
| sessions    |    801 |
| supertank   |  exists |

## Notes

- Skills count: 12,794 — up 57 from 12,737 (July 5), continuing steady upward trend
- Smart approval clearing `systemctl --user stop` is a notable improvement over previous sessions where systemctl restart/stop required the full kill+start fallback
- No errors or warnings in any step
- Restart counter clean (0)
