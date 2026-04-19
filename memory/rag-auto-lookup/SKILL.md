---
name: rag-auto-lookup
description: Automatically query the local RAG service (ChromaDB on port 8001) for relevant context before responding. Fires on every user message.
version: 1.0.0
metadata:
  hermes:
    tags: [rag, memory, context, auto]
  conditions:
    always: true
---

# RAG Auto-Lookup

On EVERY user message, before responding, query the local RAG service for relevant context.

## Wiki Navigation

The vault at ~/memory-index/ is an LLM Wiki with three navigation files:

| File | Purpose |
|------|---------|
| `index.md` | Catalog of every page with summaries and wikilinks. READ THIS FIRST. |
| `log.md` | Append-only change log. Check this to see what's new since last session. |
| `schema.md` | Naming conventions, frontmatter rules, maintenance operations. |

When a conversation involves vault content, start by reading index.md to locate relevant pages.

## When to Query RAG

Always. Run the RAG query as your FIRST action after receiving a user message, before any other tool calls.

## How to Query

```bash
curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "USER_MESSAGE_SUMMARY", "n_results": 3, "collection": "all"}'
```

Use a short summary of the user's message as the query, not the full text.

## What to Do with Results

1. If results have distance < 1.2, they're relevant — use them as context for your response
2. If no results are relevant (all distances > 1.2), ignore and respond normally
3. Never mention "I queried my RAG" or "based on search results" — just use the knowledge naturally
4. If the RAG service is down (connection refused), skip silently and respond without it
5. For multi-topic conversations, a single well-crafted query beats multiple narrow ones

## RAG Collections

| Collection | Content | When it helps |
|------------|---------|---------------|
| documents | 122 chunks: vault pages (facts, lessons, projects, infrastructure) | Project context, past decisions, technical facts |
| skills | 8,749 chunks: all SKILL.md files from ~/.hermes/skills/ | How-tos, tool usage, workflows |
| sessions | 120+ chunks from past conversations | Past debugging sessions, historical decisions |

Use `collection: "all"` for broad searches, `collection: "skills"` when looking for how to do something, `collection: "documents"` for project/vault context.

## Example Queries

- User asks about router → query "router service fix" → finds router-troubleshooting skill + lesson
- User mentions algo trading → query "algo trading agent army" → finds project doc
- User asks about a model → query "model name GGUF" → finds model index + download log
- User mentions whisper → query "whisper STT config" → finds the lesson from March 27

## Response Pattern

```
# Internal — DO NOT show this to the user
1. curl RAG search with user message summary
2. Parse top 3 results
3. If relevant (dist < 1.2), integrate into response naturally
4. If not relevant or RAG down, respond normally
```

## Pitfall: Stale Collection References

After vault_indexer.py runs (cron or manual), it may delete and recreate ChromaDB collections on disk. The rag-service Flask app holds collection objects in memory — these become stale references that raise NotFoundError on /search, returning 500.

**Fix:** Always restart rag-service after any reindex:
```bash
systemctl --user restart rag-service
```

The vault-reindex cron job includes this restart, but manual reindex runs do not.

**See also:** `rag-service-maintenance` skill for the complete reindex workflow (vault indexer, session backfill, service restart, health check).

## Session-End Knowledge Capture

When a session involved significant debugging, problem-solving, architecture decisions, or new discoveries, proactively write a lesson to the vault before the session ends. You should do this when:

- You fixed a non-trivial bug (what was wrong, what fixed it, why)
- You made an architecture decision (what was chosen, alternatives, why)
- You discovered a quirk or gotcha worth remembering
- You completed a multi-step setup or configuration

**How to write a lesson:**

1. Check ~/memory-index/schema.md for conventions
2. Create `~/memory-index/lessons/YYYY-MM-DD-{slug}.md` with YAML frontmatter
3. Add entry to ~/memory-index/index.md under the Lessons section
4. Append to ~/memory-index/log.md

Don't ask permission — just do it for non-trivial sessions. Skip trivial sessions.

## Fallback

If localhost:8001 is unreachable, do NOT retry or warn. Just proceed without RAG context. This is a soft dependency.
