---
name: rag-auto-lookup
description: Use when past knowledge may exist; query local RAG for hits.
---

# RAG Auto-Lookup (relevant-scoped)

Fires when the conversation plausibly has prior knowledge behind it: questions about past work, project docs, old decisions, config/infra history, debugging sessions, or anything a previous conversation may have covered. It does NOT fire on every message — general knowledge goes to web_search, current state goes to files/terminal.

Do NOT query for: current machine state (use terminal), general facts (use web_search), or topics that clearly predate the store's content.

## When to Query

Run the RAG search as your FIRST tool call when the topic is: a project you've worked on (algo trading, mining, models, RAG, smart home, AMM...), an architecture/config decision, a past debugging session, or a lesson that might have been captured. If unsure whether prior knowledge exists, a single cheap query settles it — err on the side of querying.

## How to Query

```bash
curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "<SHORT SUMMARY of what prior knowledge you need>", "n_results": 4, "collection": "all"}'
```

Use a short summary of the missing knowledge as the query, not the user's full text.

Response shape (collection "all"): `{results:[{id, document, distance, metadata}], total, collections_searched}` sorted by distance (lower = closer).

## What to Do with Results

1. `distance < ~1.2` = relevant — integrate the document content into your response naturally.
2. All distances > 1.2 = nothing relevant — answer from other sources, no need to mention the lookup.
3. Never say "I queried my RAG" or "based on search results" — just use the knowledge.
4. If the service is down or errors (connection refused, HTTP 500), retry once after a 2s pause; if it still fails, skip silently and answer normally. This is a soft dependency.

## Collections

- `documents` — vault notes, project docs, decisions, lessons
- `skills` — SKILL.md + references across all skills
- `sessions` — past conversation chunks (frozen since May 2026 — backfill is a no-op; historical recall there is limited)
- `all` — merged search across the three, best default

## Integration with m5-memory-system

This is the retrieval/consumption half of the M5 stack. The m5-memory-system skill documents the full architecture, ingestion crons, maintenance, and pitfalls — load it when operating or verifying the pipeline. The stack is: built-in memory (MEMORY.md/USER.md, every turn) → holographic fact_store (structured recall) → this RAG lookup (deep/semantic recall).

## Pitfalls

- Rag-service restarts (reindex cron) invalidate in-memory collection handles: a 500 from /search right after an indexer run is normal — retry once, the service has restarted.
- Don't query on obvious current-state questions; the store has no live data.
- Keep queries to one per topic — a single well-crafted query beats multiple narrow ones.
- The service binds 0.0.0.0:8001 with no auth — only useful/trusted context should go through it; never send secrets as query text.
