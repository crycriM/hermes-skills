# Using the M5 memory from another agent (HTTP API)

Light consumption guide for **any** AI agent (Hermes, Claude Code, Roo, Cody, scripts) to read/write the M5 shared memory over plain HTTP. This is the read/write surface. For deep ingest/curation see the `obsidian` skill and the vault schema.

> The RAG server is a single service on **port 8001** (`rag-service.service`, `rag_service.py`). The RAG proxy layer (port 8002) that auto-injected context was **removed 2026-09-01** — do not reference `rag_proxy.py` or `/chat`.

## Which driver are you?

- **Context-rich driver (agent harness: Hermes, Claude Code, Roo)** — call the store directly (`/search` on 8001) as a tool and manage your own request context (system prompt, memory, tools, session history, token budget). There is no transport-level auto-injection layer; you decide whether to retrieve and where to place results.
- **Context-poor driver (dumb script, non-agent tool)** — also call 8001 directly (`/search`, `/add`, `/embed`); there is no auto-inject wrapper anymore, so build the prompt yourself if you want context included.

Hermes chat does NOT auto-query RAG. It curls `/search` on 8001 when a skill or the agent decides it needs prior knowledge.

## Search (8001)

```bash
# all collections (documents + skills + sessions), ranked by distance
curl -s -X POST http://localhost:8001/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "router preset fix", "n_results": 5, "collection": "all"}'

# single collection: documents | skills | sessions | (any custom name)
curl -s -X POST http://localhost:8001/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "m5 hardware", "n_results": 3, "collection": "documents"}'
```

- `collection: "all"` → `{results:[{id, document, distance, metadata}], total, collections_searched}`, sorted by distance (lower = closer).
- Single-collection → raw Chroma shape (`ids`/`documents`/`distances`/`metadatas`).
- Treat `distance < ~1.2` as relevant; higher is loose. Sizes approx: documents ~166, skills ~14k, sessions ~800.

## Add (write to 8001)

```bash
curl -s -X POST http://localhost:8001/add \
  -H 'Content-Type: application/json' \
  -d '{"collection": "documents", "ids": ["note_1"], "documents": ["<text>"], "metadatas": [{"source": "my-agent", "type": "note"}]}'
```

`collection` defaults to `documents`; ids auto-generate as `doc_<i>` if omitted. Set `metadatas.source` for provenance.

## Embed (8001)

```bash
# simple
curl -s -X POST http://localhost:8001/embed -H 'Content-Type: application/json' \
  -d '{"texts": ["hello world"]}'            # {embeddings:[[]]}

# OpenAI-compatible (clients wired to /v1)
curl -s -X POST http://localhost:8001/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"input": "hello world"}'              # OpenAI-shaped {data:[{embedding}]}
```

Embedding model `all-MiniLM-L6-v2` (768-d). Point an OpenAI-compatible embeddings client at `http://<host>:8001/v1`.

## Health

```bash
curl -s http://localhost:8001/health   # {status, embedding_model}
```

## Notes

- No auth today; VLAN/firewall guard planned. Trusted LAN only.
- Partition the store: use a custom `collection` name per consuming agent (e.g. `cody`, `claude`) so you can write-disjoint namespaces and read via `collection`.
