# Session Indexing Log — 2026-05-17

## Changes
- Skills re-indexed: **12,719 chunks** (from ~12,703)
- Sessions already indexed (0 new): **775 documents total** in sessions collection
- Documents collection: **0** (memory-index directory not found)

## Events
- **Port 8001 was occupied by a stale process.** Systemd tried to restart the service but got "Address already in use". After killing the stale process with `lsof -i :8001 -t | xargs kill -9`, systemd auto-restarted successfully.
- **ChromaDB n_results=0 returns HTTP 500.** Verified this: searching with `n_results=0` throws "Number of requested results 0, cannot be negative, or zero" — NOT an indicator that the service is down. Always use `n_results>=1`.

## Verification
- Port freed: confirmed via `lsof -i :8001 || echo "Port 8001 is free"`
- Service restarted by systemd (after port freed): confirmed via `systemctl --user status rag-service` showing `Active: active (running)`
- Skills search: working, returned results from `skills/software-development/test-driven-development/SKILL.md`
- Sessions search: working, returned results from session `20260413_083852_1423379e`

---

# Session Indexing Log — 2026-05-17 (continued)

## Later Run — Session Backfill
- Disk at 100% on /mnt/data1 (890G/938G). Backfill failed with "chromadb.errors.InternalError: database or disk is full".
- **Fix**: removed unused GGUF model file `Step-3.5-Flash-REAP-121B-A11B.i1-Q4_K_M.gguf` (~68G) — not in router config, not running.
- After cleanup: 93% full (68GB available). Backfill succeeded.
- **Sessions indexed**: 1 new session (20260517_092729, 2 chunks)
- **Collections**: sessions = 777 documents, skills/documents/supertank unchanged from prior run
