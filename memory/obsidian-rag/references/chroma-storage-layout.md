# ChromaDB Storage Hygiene

## Active Storage Locations

| Path | Purpose | Size | Status |
|------|---------|------|--------|
| `~/llm-server/chroma_db/` | **RAG service** — vault_indexer.py, session_backfill.py, rag_service.py all point here via `CHROMA_PERSIST = ~/llm-server/chroma_db` | ~71MB + 35 collection subdirs | **ACTIVE — keep** |
| `~/.hermes/chroma/` | Old location, still accessed (188KB, no collection subdirs) | 188KB | **Stale — monitor** |
| `~/openwebui_data/vector_db/` | **OpenWebUI's own ChromaDB** — completely separate instance | ~71MB + collections | **Separate system — don't touch** |

## Stale / Orphaned Locations (safe to delete)

These are 188KB ChromaDB init attempts that failed to create collections. All identical, all dead:

```
~/chroma_db/              # Legacy from old session_backfill.py
~/.chroma/                # Old ChromaDB default location
~/llm-server/chroma_data/  # Apr 13 init attempt
~/llm-server/chromadb/     # Apr 27 init attempt
~/llm-server/chroma-data/  # May 17 init attempt
~/.cache/chroma/           # pip install cache
~/.local/share/chroma/     # pip package dist-info
~/.local/bin/chroma        # CLI shim
~/venv/bin/chroma          # Old venv CLI
~/open-webui-venv/bin/chroma  # Old venv CLI
```

### Cleanup Command

```bash
# Trash stale ChromaDB remnants (active DB unaffected)
rm -rf ~/chroma_db ~/.chroma
rm -rf ~/llm-server/chroma_data ~/llm-server/chromadb ~/llm-server/chroma-data
rm -rf ~/.cache/chroma ~/.local/share/chroma ~/.local/bin/chroma
rm -rf ~/venv/bin/chroma ~/open-webui-venv/bin/chroma
```

## Key Insight

All `~/llm-server/` scripts share a single `CHROMA_PERSIST` env. The three orphan directories (`chroma_data`, `chromadb`, `chroma-data`) are failed attempts to create the real `chroma_db/`. The 188KB SQLite files without collection subdirs are the telltale sign of a broken init — a healthy ChromaDB has the SQLite + UUID-named collection directories.

## Current Active Config

```python
# rag_service.py, vault_indexer.py, session_backfill.py all use:
CHROMA_PERSIST = os.path.expanduser("~/llm-server/chroma_db")
```

Service: `rag-service.service` → `WorkingDirectory=/home/cricri/llm-server` → `ExecStart=.../venv/bin/python rag_service.py`