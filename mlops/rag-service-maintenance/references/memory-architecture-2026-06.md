# Memory System Architecture — June 2026

Full topology discovered during vault restoration session (2026-06-08).

## Component Map

```
~/.hermes/memories/               ← Hermes built-in memory (memory tool)
  MEMORY.md (1,929 chars, 6 entries)
  USER.md   (1,395 chars, 4 entries)

~/memory-index/                   ← Obsidian vault (human-readable curated notes)
  index.md, log.md, schema.md     ← Wiki navigation triad
  facts/         — decisions.md, preferences.md, technical.md
  lessons/       — 12 date-stamped lessons (2026-03-18 through 2026-04-01)
  projects/      — m5-setup.md, m5-llama-configs.md, solana-dex.md,
                    algo-trading-agent-army.md, knowledge-system-pipeline.md
  infrastructure/ — hermes-config.md, local-llm-services.md
  models/        — sub-wiki with index/log/schema, full model catalog
  skill-graphs/  — router-troubleshooting.yaml, router-service-recovery.yaml, SCHEMA.md
  phase-plan.md, project-tracker.md, STATUS.md

~/llm-server/chroma_db/           ← RAG ChromaDB (234MB SQLite, 56+ collection dirs)
  Collection: documents           ← vault notes + skills SKILL.md (only skills if vault missing)
  Collection: skills              ← ~/.hermes/skills/ SKILL.md files (~13,600 chunks)
  Collection: sessions            ← ~/.hermes/sessions/*.jsonl (~800 chunks)

~/llm-server/                     ← Scripts
  rag_service.py        :8001     ← Flask + SentenceTransformer + ChromaDB
  rag_proxy.py          :8002     ← Smart router: auto-detects RAG need, injects context
  vault_indexer.py                ← Rebuilds documents+skills collections from disk
  session_backfill.py             ← Indexes new session JSONL → sessions collection
  obsidian_ingest.py              ← Incremental vault indexing (uses ~/memory-index/)
```

## Services

| Port | Binary | Systemd unit | Status (Jun 2026) |
|------|--------|-------------|-------------------|
| 8001 | `rag_service.py` | `rag-service.service` | Running ✓ |
| 8002 | `rag_proxy.py` | *(none)* | NOT running ✗ |

## Cron Jobs (Hermes)

| Job ID | Name | Schedule | Purpose |
|--------|------|----------|---------|
| `41e2a79cef2f` | vault-reindex | daily 8am | Rebuilds documents+skills ChromaDB collections |
| `fe20064b73e5` | session-backfill | every 6h | Indexes new session JSONL → sessions collection |

## Vault Locations

| Path | Status | Content |
|------|--------|---------|
| `~/memory-index/` | **Canonical location** | Should be the active vault |
| `~/memory-index-backup-2026-04-07/` | Backup | Full 45-file backup, 544KB |
| `/mnt/data1/cricri/memory-index` | Stale partial | 10 files from April 1, 60KB |

## Stale ChromaDB (safe to delete)

`~/.hermes/chroma/chroma.sqlite3` (196KB, May 27) — separate from the RAG service ChromaDB.
Never used by any active service. Leftover from experiment.

## Key Discovery (2026-06-08)

The `documents` collection was empty because `~/memory-index/` didn't exist.
`vault_indexer.py` silently skips missing directories — no warning, no error.
The RAG service still worked for skills+sessions queries, but curated human notes were invisible.
