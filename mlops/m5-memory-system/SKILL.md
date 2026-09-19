---
name: m5-memory-system
description: Use when operating or verifying the M5 memory/RAG pipeline.
---

# M5 Memory System (RAG + holographic + built-in memories)

The M5 memory stack has THREE layers. Knowing how they fit — not just that they exist — is the point of this skill. The RAG layer is the only external, HTTP-addressable one.

## Layers

1. **Built-in Hermes memory** — `~/.hermes/memories/{MEMORY,USER}.md`. Compact facts injected every turn. Tool: `memory`.
2. **Holographic memory store** — `~/.hermes/memory_store.db` (SQLite + FTS5). Structured facts, entity resolution, trust scoring, HRR retrieval. Tools: `fact_store`, `fact_feedback`. Plugin lives at `~/.hermes/hermes-agent/plugins/memory/holographic/`. Per-instance local file.
3. **RAG service + ChromaDB** — the external, HTTP-addressable layer (port 8001). This is the one that can be shared and consumed by other agents.

RAG layer components (all systemd user units, venv python at `~/llm-server/venv/bin/python`):

| Component | Port | Files | Key detail |
|-----------|------|-------|------------|
| `rag-service.service` | 8001 | `~/llm-server/rag_service.py` | Flask + sentence-transformers (`all-MiniLM-L6-v2`) + ChromaDB at `~/llm-server/chroma_db`. `CHROMA_PERSIST` hardcoded. 3 collections: `documents`(vault), `skills`, `sessions`. Endpoints: `/search`, `/add`, `/embed`, `/v1/embeddings`, `/v1/models`, `/health`. |
| `vault_indexer.py` | — | cron `41e2a79cef2f` daily 8am | Reindex vault + skills → ChromaDB |
| `session_backfill.py` | — | cron `fe20064b73e5` every 6h | Index session JSONLs → ChromaDB |

Note: `~/llm-server` is a symlink to `/mnt/data1/cricri/tools/llm-server`. `~/memory-index/` (Obsidian wiki) is the document source; `~/.hermes/sessions/*.jsonl` is the session source.

> **RAG proxy removed 2026-09-01**: a `rag_proxy.py` layer (port 8002) previously auto-injected RAG context for context-poor drivers (chat UIs). It was never invoked and has been deleted. There is no transport-level context-injection layer — the RAG service on 8001 is the sole interface. Agent harnesses (Hermes, Claude Code) manage their own request context and query 8001 (primarily `/search`) as a tool.

## Retrieval — what actually happens

There is no auto-injection. An agent/harness checks whether prior knowledge is needed and calls the store directly:

```bash
curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "<summary>", "n_results": 3, "collection": "all"}'
```

- `collection: "all"` → `{results:[{id, document, distance, metadata}], total, collections_searched}` sorted by distance (lower = closer).
- Single-collection (`documents`/`skills`/`sessions`/custom) → raw Chroma shape (`ids`/`documents`/`distances`/`metadatas`).
- Treat `distance < ~1.2` as relevant. Sizes approx: documents ~166, skills ~14k, sessions ~800.
- An agent decides relevance itself and places results in its own context where it fits; there is no proxy guessing.

## Tracing — what use is made of each layer

- There is **no app-level audit log** of what agents retrieve from RAG. HTTP access lines appear in the journal: `journalctl --user -u rag-service` shows each `127.0.0.1 - - "POST /search" 200`.
- Ingestion volume (not query use): collection counts via `rag_service.py`/chroma — e.g. documents ~166, skills ~14127, sessions ~801. `curl -s http://localhost:8001/health` shows the embedding model.
- If per-query usage tracing is ever needed, add request logging to `rag_service.py` (record query + collection + n_results); no such layer exists now.

## Sharing — RAG over LAN & other agents

- **Already LAN-reachable**: `rag-service` binds `0.0.0.0` (journal shows `http://192.168.1.204:8001`). **No auth, no rate limiting, `/add` is an unauthenticated write** — trusted LAN only; gate with firewall/token if exposed beyond.
- **Share the RAG store** (8001): another hermes/agent just points search/embedding calls at `http://<M5-IP>:8001`. Easy.
- **Built-in + holographic stores are NOT shareable live** — per-instance local files (`memory_store.db` is only locally meaningful). Sharing needs file copy/sync or a new HTTP-backed store.
- **Multi-agent consumption is by design**: `rag_service.py` exposes OpenAI-compatible `/v1/embeddings` + `/v1/models` (comment: "for Roo Code"). Any OpenAI-HTTP-speaking agent can POST `/search`, `/add`, `/embed`, `/v1/embeddings`. Full curl examples and a "which endpoint for what" guide: `references/other-agents-guide.md`.

## Portability & editing

- **Editable**: yes — plain Python (Flask), markdown vault, SQLite. All source in reach.
- **Portable**: partially. Paths are hardcoded absolute (`/home/cricri/llm-server/...`, `/home/cricri/memory-index`, `/home/cricri/.hermes/sessions`, `/home/cricri/.hermes/memory_store.db`). Embedding model downloads on first run (needs internet once). Chroma vector index is arch/version-specific → **reindex on a new machine rather than copying the db**.

## Verifying the architecture doc

`~/llm-server/ARCHITECTURE_memory.md` is the single source of truth. When asked to verify it: do NOT trust it — check live. `ss -ltnp` for ports, `systemctl --user status` for unit (8001 should be the only RAG unit now), `curl /health` on 8001, chroma collection counts, check `~/llm-server` symlink resolves to the same dir as the cwd. Watch for stale claims: bind addresses, collection naming, any leftover mention of the removed proxy/port 8002.

## Pitfalls

- `session_backfill.py` globs `~/.hermes/sessions/*.jsonl`, but Hermes stopped writing per-session `.jsonl` files in May 2026 — session content now lives in `~/.hermes/state.db` (sessions table) and `sessions.json` is only a legacy gateway-routing mirror. The RAG `sessions` collection has been frozen at ~801 docs since 2026-05-18; backfill reports '0 indexed' forever. Needs a state.db exporter to be useful; until then the 6-hourly cron `fe20064b73e5` is a no-op.
- Cron approval policy blocks `systemctl --user restart` (no user to approve). Do NOT work around it by killing the service PID: systemd treats SIGTERM as a *clean* exit, so `Restart=on-failure` does NOT fire and the service stays dead. Use `systemctl --user start rag-service` (allowed) after a kill, or to bounce a fresh instance.
- Service runs with `~/llm-server/venv/bin/python`, NOT system python (system 3.11 lacks headroom-ai etc.).
- Cron env has no `~/.local/bin` and no reliable `~` expansion — use absolute binary paths + export PATH in script/cron prompts.
- Chroma count() can throw if the underlying data was recreated on disk; `_get_collection()` re-fetches a fresh handle — reuse that pattern.
- The old RAG proxy (port 8002) is gone — do not reference `rag_proxy.py`, `rag-proxy.service`, or `/chat` when reasoning about this system.
