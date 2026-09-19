# Memory System Architecture Reference

Canonical file: `~/llm-server/ARCHITECTURE.md`

This is the single source of truth for the M5 memory pipeline. Contains:
- Full system diagram (vault → indexer → ChromaDB → RAG → proxy → LLM)
- Component catalog with file paths, ports, systemd units
- Cron job table (vault-reindex daily 8am, session-backfill every 6h)
- Search API reference (curl examples)
- Maintenance procedures (reindex, backfill, health checks)
- Related files map

Always read ARCHITECTURE.md before debugging or modifying any memory/RAG component.
