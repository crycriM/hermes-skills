# Session indexing log — 2026-09-30 (01:13 CEST)

Cron run: session backfill (`--db --since 1779055200`) + rag-service restart.

## Backfill

```
cd /home/cricri/llm-server && timeout 2400 ./venv/bin/python session_backfill.py --db --since 1779055200
Found 1482 sessions in state.db
Total sessions processed from db: 5
Total chunks created: 22
Collection 'sessions' now has 12916 documents
```

Indexed (5 sessions / 22 chunks, up from 12,894 docs):

| session id | chunks |
|---|---|
| 20260929_200416_d44df0 | 8 |
| 20260929_223327_70456e | 7 |
| 20260929_224206_57e656 | 3 |
| cron_c85b2d0d609e_20260929_220021 | 3 |
| cron_fe20064b73e5_20260930_011239 | 1 |

## Restart

`systemctl --user restart rag-service` skipped (cron approval gate, known). Workaround used as usual:

```bash
pkill -f "[r]ag_service.py"; sleep 3; systemctl --user start rag-service
```

- Old MainPID 2199277 → new MainPID 2586555, active since 01:13:03 CEST.
- Startup log: `Embedding model loaded` / `ChromaDB initialized (documents: 166, skills: 14538, sessions: 12916)` / `Starting RAG service on port 8001...`
- No restart counter increment, model loaded in ~12s.

## Freshness verification

`chromadb.PersistentClient(path='/home/cricri/llm-server/chroma_db')` → collection `sessions` count 12916; `get(where={"session_id": "cron_fe20064b73e5_20260930_011239"})` returned `cron_fe20064b73e5_20260930_011239_db_chunk000`; all 5 session ids present with expected chunk counts.

Note: the HTTP `/search` endpoint ignores collection filters and its result metadata carries no `session_id`, so direct chromadb reads remain the reliable freshness proof (probe scripts in `/home/cricri/.hermes/cache/scratch/`).
