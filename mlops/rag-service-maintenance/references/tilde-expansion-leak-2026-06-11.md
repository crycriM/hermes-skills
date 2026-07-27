# Tilde Expansion Leak — 2026-06-11

**Symptom:** A ghost directory `/home/cricri/llm-server/~/llm-server/chroma_db` appeared inside `llm-server/` at 08:12 on June 11, alongside a `db/` directory (empty ChromaDB, 0 collections).

**Timescale:**
- 08:11 — `db/` created (empty ChromaDB with 188KB sqlite3, 0 collections)
- 08:12 — `chroma_db/` last modified (the real 234MB ChromaDB with 4 collections, 15,403 embeddings)
- 08:13 — vault-reindex cron job finished (job 41e2a79cef2f)

**Root cause:** The vault-reindex cron job's prompt said `cd ~/llm-server && ~/llm-server/venv/bin/python vault_indexer.py`. The cron agent (an LLM subprocess) constructed a shell command with literal `~` that wasn't expanded by the shell. This caused ChromaDB's `PersistentClient(path="~/llm-server/chroma_db")` to create a database at a literal `~` path instead of `/home/cricri/`.

**Why Python `os.path.expanduser()` didn't save us:** The Python scripts used `os.path.expanduser("~/llm-server/chroma_db")` which works correctly in normal execution. But the cron agent ran the script from a shell context where `~` wasn't expanded in the `cd` command first, which confused the working directory and may have led to a secondary ChromaDB instance being created at `db/`.

**Detection:**
```bash
# Check for directories with ~ in path
find /home/cricri/ -maxdepth 6 -path '*~*' 2>/dev/null

# Check for stale empty ChromaDB directories
for d in /home/cricri/llm-server/db /home/cricri/llm-server/.chroma /home/cricri/llm-server/chroma_data; do
  python3 -c "import chromadb; c=chromadb.PersistentClient(path='$d'); print('$d:', len(c.list_collections()), 'collections')" 2>/dev/null
done
```

**Fix applied:**
1. `vault_indexer.py` — `os.path.expanduser("~/llm-server/chroma_db")` → `/home/cricri/llm-server/chroma_db`
2. `session_backfill.py` — same substitution
3. `rag_service.py` — same substitution
4. vault-reindex cron prompt — `cd ~/llm-server` → `cd /home/cricri/llm-server`
5. session-backfill cron prompt — same substitution
6. `rag-service-maintenance` skill — all `~` references replaced with absolute paths
7. Ghost dirs `db/`, `.chroma/`, `chroma_data/` trashed (all empty — 0 collections)

**Cleanup:**
```bash
mkdir -p ~/.trash
mv ~/llm-server/db ~/.trash/db-$(date +%Y%m%d-%H%M%S)
mv ~/llm-server/.chroma ~/.trash/.chroma-$(date +%Y%m%d-%H%M%S)
mv ~/llm-server/chroma_data ~/.trash/chroma_data-$(date +%Y%m%d-%H%M%S)
```

**Prevention:** Never use `~` in cron prompts, cron scripts, or file paths that an LLM agent constructs. Always hardcode `/home/cricri/...`.