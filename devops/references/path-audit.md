# Hermes Path Audit

Systematic check for path inconsistencies across config, dotenv, and skills.

## Trigger

- User reports files "lost", duplicated, or not found
- After migration, profile change, or disk reorganization
- Periodically as preventive maintenance

## Workflow

1. Read `~/.hermes/config.yaml` — scan for relative paths, missing targets
2. Read `~/.hermes/.env` — check all `_PATH` vars are set and point to existing dirs
3. Search skills: `search_files(pattern='/home/cricri/', path='~/.hermes/skills')` and `search_files(pattern='~/\\.hermes', path='~/.hermes/skills')` — look for inconsistencies
4. Verify key directories exist: `for d in ~/memory-index ~/llm-server/chroma_db ~/.hermes/sessions ~/.hermes/logs; do ... done`
5. Check for orphan ChromaDBs: `find ~/ -maxdepth 4 -name "chroma.sqlite3" 2>/dev/null`

## Known Pitfalls

### OBSIDIAN_VAULT_PATH not set

**Symptom:** Skills disagree on vault location. obsidian skill defaults to `~/Documents/Obsidian Vault` (non-existent), obsidian-rag defaults to `~/memory-index/` (correct). Files appear "lost" depending on which skill is loaded.

**Fix:** Add to `~/.hermes/.env`:
```
OBSIDIAN_VAULT_PATH=~/memory-index
```
Restart gateway or start new session to pick up.

### Stale ChromaDB databases

**Symptom:** Multiple `chroma.sqlite3` files scattered across the system. `chromadb.PersistentClient()` called without a path argument creates DBs at default locations (`~/.chromadb/`, `~/.local/share/chroma/`). These compete with the real RAG service DB at `~/llm-server/chroma_db/`.

**Fix:** Identify stale DBs (by modification date vs active service), trash via `gio trash <path>` (trash-cli may not be installed). Keep only the active RAG DB.

### Cron scripts with hardcoded paths

**Symptom:** Cron job `workdir` updated but job still fails. Script references old directory internally.

**Fix:** Read every script referenced by a cron job (`script` field) and check for `cd` statements. Update both the cron job and the script.

**Example:** `numerai-crypto-submit.sh` had `cd /home/cricri/projects/numerai/numerai-crypto-bot` hardcoded — must be updated alongside the cron job's `workdir`.

### Known active paths (single-user system)

| Purpose | Path |
|---------|------|
| Hermes home | ~/.hermes |
| Config | ~/.hermes/config.yaml |
| Secrets/env | ~/.hermes/.env |
| Skills | ~/.hermes/skills/ |
| Sessions | ~/.hermes/sessions/ |
| Logs | ~/.hermes/logs/ |
| Memory (built-in) | ~/.hermes/memories/ |
| Obsidian vault | ~/memory-index/ |
| RAG ChromaDB | ~/llm-server/chroma_db/ |
| OpenWebUI data | ~/openwebui_data/ |
| STT binary | /home/cricri/whisper.cpp/build/bin/whisper-cli |
| STT model | /opt/whisper.cpp/models/ggml-small.bin |
| Router preset | ~/llm-server/router-preset.ini |
