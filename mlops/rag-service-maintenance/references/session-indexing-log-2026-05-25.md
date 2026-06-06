# Session Indexing Log — 2026-05-25

## Vault Indexer
- **Timeout:** 120s was sufficient (13,054 chunks, 262 batches)
- **Skills indexed:** 13,054 chunks (262 batches of 50, last batch 4)
- **Documents:** 0 (vault notes path `/home/cricri/memory-index` not found)
- **Warning:** `embeddings.position_ids | UNEXPECTED` — normal, can be ignored

## Session Backfill
- **Sessions found:** 105 session files
- **All already indexed:** 0 new sessions
- **Sessions collection:** 801 documents

## RAG Service Restart — Port Already In Use
- **Symptom:** `systemctl --user restart` → service exits with "Address already in use" on port 8001, crash-looping every ~10s
- **Root cause:** A stale Python process (PID 2569328) held port 8001 with OLD ChromaDB data (skills: 10,600)
- **Systemd kept restarting** (counter reached 1143) but each attempt failed because port was bound
- **Interesting timing:** During this crash-loop, the vault_indexer and session_backfill ran successfully — they write to ChromaDB on disk, so the indexers worked fine even with the RAG service in a broken state
- **Fix:** Killed stale process with `kill $(lsof -ti :8001)`. Once port was free, systemd auto-restarted and picked up fresh data (skills: 13,054)
- **Lesson:** When `systemctl --user restart` is stuck crash-looping on port conflict, the indexers can still run safely (they write to disk, not through the service). Kill the port holder and let systemd auto-restart — no need for the full pkill/background-start workaround.

## Collection Counts (post-reindex)
| Collection | Documents |
|---|---|
| skills | 13,054 |
| sessions | 801 |
| documents | 0 |
| supertank | 157 |
