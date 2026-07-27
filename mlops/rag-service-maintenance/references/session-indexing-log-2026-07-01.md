# RAG Service Maintenance — 2026-07-01

## Summary

Clean cron run. Vault indexer re-indexed both collections (deleted old, rebuilt fresh). Session backfill skipped all 105 sessions (no new sessions since last index). RAG service restarted cleanly with systemctl start.

## Vault Indexer

- **documents**: 157 (from `/home/cricri/memory-index`)
- **skills**: 12,551 (from `/home/cricri/.hermes/skills`)

## Session Backfill

- **sessions**: 801 (all already indexed, 0 new)

## RAG Service Restart

- pkill -f returned -15 (itself terminated)
- port 8001 verified free with `ss -tlnp`
- systemctl --user start rag-service succeeded (no approval gate trigger)
- Startup log: ChromaDB initialized (documents: 157, skills: 12551, sessions: 801)

## Final Collection Counts

| Collection   | Count  |
|-------------|--------|
| documents   |    157 |
| skills      | 12,551 |
| sessions    |    801 |
| supertank   |    250 |

## Health

- Search endpoint responds with HTTP 200, all collections searchable
- No crash-loop, restart counter clean
- Service active (running), started 2026-07-01 08:06:56 CEST
