# RAG Service Maintenance Log — 2026-08-28

Clean cron run.

- **Vault indexer**: completed, `skills` collection now **13,928** documents (up 3 from 13,925 on Aug 27).
- **Session backfill**: 0 new sessions (all 105 files already indexed); `sessions` collection stable at **801**.
- **Restart**: `systemctl --user restart rag-service` — auto-approved by smart approval, exit 0. **No crash-loop** (no restart counter in status).
- **Startup log**: `ChromaDB initialized (documents: 166, skills: 13928, sessions: 801)`, `Embedding model loaded`, `Starting RAG service on port 8001...`.
- **Health**: `{"embedding_model":"all-MiniLM-L6-v2","status":"ok"}`.
- **Search verify** (collection "all", n_results 1): HTTP 200, valid result, `collections_searched: "all"`.
- **Exact ChromaDB counts** via `.count()`: skills 13,928 / sessions 801 / supertank 250 / documents 166.

No errors. All OK.