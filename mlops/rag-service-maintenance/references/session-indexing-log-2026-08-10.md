# RAG Re-index Log — 2026-08-10

## Run A (session backfill + restart only; vault not re-indexed)

Clean cron run.

- Session backfill: all 105 sessions already indexed (SKIP), sessions **801** (stable), 0 new chunks.
- Restart: `systemctl --user restart rag-service` auto-approved by smart approval (no gate block). Clean single start, **no restart counter** (no crash-loop).
- Startup log: embedding model loaded, `ChromaDB initialized (documents: 157, skills: 13178, sessions: 801)`, port 8001.
- Health check: `{"embedding_model":"all-MiniLM-L6-v2","status":"ok"}`.
- Collections: documents 157, skills 13,178, sessions 801.

## Run B (full re-index: vault + sessions + restart)

Clean full re-index cron run.

- Vault indexer: `documents` 157 (rebuilt), `skills` **13,180** (rebuilt; 264 batches — 263×50 + final 30). Ran in background, completed cleanly in under 60s wait window.
- Session backfill: 0 new chunks, sessions **801** (stable, all already indexed).
- Restart: `systemctl --user restart rag-service` auto-approved by smart approval. Clean single start, no restart counter (no crash-loop). Embedding model loaded in ~3s.
- Startup log: `ChromaDB initialized (documents: 157, skills: 13180, sessions: 801)`.
- Verify search `n_results=1, collection=all` → HTTP 200, returned 1 skill result.
- Collections (direct ChromaDB count): documents 157, skills 13,180, sessions 801, supertank 250.
