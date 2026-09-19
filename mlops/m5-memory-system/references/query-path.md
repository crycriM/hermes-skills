# RAG Service retrieval path (rag_service.py, port 8001)

Concrete mechanics of the retrieval path. There is no proxy / auto-injection — a driver (agent harness or external client) calls the store directly and manages its own context. The RAG proxy layer (port 8002) that previously auto-injected context was **removed 2026-09-01**.

## rag_service.py /search behaviour

- `collection` param: `all` (default), `documents`, `skills`, `sessions`, or ANY arbitrary collection name (supertank etc.).
- `all` searches the three canonical collections, merges, sorts by distance (lower = better), truncates to n_results (default 5). Returns `results`, `total`, `collections_searched`.
- Non-`all`: passes through Chroma raw result shape (ids/documents/distances/metadatas).
- Collection handles are re-fetched per request via `_get_collection()`; count() throws if underlying data was recreated on disk, so it re-creates a fresh handle.

## Other rag_service endpoints (OpenAI-compatible, for other agents)

- `POST /embed` — `{texts:[...]}`, returns `{embeddings:[...]}`.
- `POST /add` — `{documents, ids?, metadatas?, collection}`; computes embeddings server-side. Unauthenticated write.
- `POST /v1/embeddings` — OpenAI format `{input: str|list, model}` → OpenAI-shaped response with usage.
- `GET /v1/models` — returns `all-MiniLM-L6-v2` as an available model.
- `GET /health` — `{status, embedding_model}`.

For consumer agent usage (search/add/embed examples, which endpoint to use), see `references/other-agents-guide.md`.
