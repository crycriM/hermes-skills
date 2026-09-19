# RAG Service Maintenance Log — 2026-08-22

**Result:** Clean cron run (session backfill only).

## Steps
1. **Session backfill** — `timeout 120 /home/cricri/llm-server/venv/bin/python session_backfill.py`.
   - 105 session files found, all SKIP (already indexed).
   - Total sessions processed: 0, Total chunks created: 0.
   - sessions collection stable at **801**.
2. **Restart** — `systemctl --user restart rag-service` **auto-approved** by smart approval (no gate block). No `restart counter` line in status → started cleanly on first attempt, no crash-loop. Active (running), Main PID 898629, since 04:23:09 CEST.
3. **Verify** —
   - Health: `{"embedding_model":"all-MiniLM-L6-v2","status":"ok"}`.
   - Search "session backfill test" n_results=5 collection=all returned results (including a sessions-collection hit about the March backfill work).
   - `ss -tlnp | grep 8001` → port held by new PID 898629.
   - Note: journalctl for rag-service shows stale entries (last from Aug 04) — new run's stdout does not reach journald, but status/health confirm service is fine.

## Collection counts (direct ChromaDB query)
- documents: 166
- skills: 13510
- sessions: 801
- supertank: 250

---

## Second run — 08:02 CEST (full re-index)

**Result:** Clean full cron run (vault indexer + session backfill + restart).

## Steps
1. **Vault indexer** — `/home/cricri/llm-server/venv/bin/python vault_indexer.py` (background, exited 0). 271 batches, last batch 15 chunks. skills collection grew **13,510 → 13,515** (+5).
2. **Session backfill** — 105 session files found, all SKIP. Total processed: 0, chunks created: 0. sessions stable at **801**.
3. **Restart** — `systemctl --user restart rag-service` **auto-approved** by smart approval. No `restart counter` line → started cleanly, no crash-loop. Active (running), Main PID 1024216, since 08:02:13 CEST.
4. **Verify** — health `{"embedding_model":"all-MiniLM-L6-v2","status":"ok"}`; search query "test" n_results=1 collection=all → HTTP 200, `collections_searched: all`, 1 result (skills hit: test-curator-create reference).

## Collection counts (direct ChromaDB query)
- documents: 166
- skills: 13515
- sessions: 801
- supertank: 250

---

## Third run — 10:24 CEST (session backfill only)

**Result:** Clean cron run.

## Steps
1. **Session backfill** — `timeout 120 /home/cricri/llm-server/venv/bin/python session_backfill.py`. 105 session files found, all SKIP (already indexed). Total processed: 0, chunks created: 0. sessions stable at **801**.
2. **Restart** — `systemctl --user restart rag-service` **auto-approved** by smart approval. No `restart counter` line → started cleanly on first attempt, no crash-loop. Active (running), Main PID 1105890, since 10:24:18 CEST. Startup log: Embedding model loaded, ChromaDB initialized (documents: 166, skills: 13515, sessions: 801), listening on port 8001.
3. **Verify** — health `{"embedding_model":"all-MiniLM-L6-v2","status":"ok"}`.

## Collection counts (from rag-service startup log)
- documents: 166, skills: 13515, sessions: 801

---

## Fourth run — 16:25 CEST (session backfill only)

**Result:** Clean cron run.

## Steps
1. **Session backfill** — `timeout 120 /home/cricri/llm-server/venv/bin/python session_backfill.py`. 105 session files found, all SKIP (already indexed). Total processed: 0, chunks created: 0. sessions stable at **801**.
2. **Restart** — `systemctl --user restart rag-service` **auto-approved** by smart approval. No `restart counter` line → started cleanly on first attempt, no crash-loop. Active (running), Main PID 1314564, since 16:25:26 CEST. Startup log: Loading embedding model all-MiniLM-L6-v2.
3. **Verify** — health `{"embedding_model":"all-MiniLM-L6-v2","status":"ok"}`; search "test" n_results=5 collection=all → `{"total": 5, "collections_searched": "all"}`.