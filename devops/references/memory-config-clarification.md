# Hermes Memory Config: Two-Layer Architecture

A common diagnostic pitfall: tools/scripts that warn about `memory.provider: ''` claiming
"memory is not available." This is incorrect. Hermes has TWO independent memory layers:

## Layer 1: Built-in (always works when enabled)
- Files: `~/.hermes/memories/MEMORY.md` and `USER.md`
- Config: `memory.memory_enabled: true` and `memory.user_profile_enabled: true`
- Code: `tools/memory_tool.py` → `MemoryStore` class
- Active when: `memory_enabled: true` AND `skip_memory` is false
- The `memory.provider` key has NO effect on this layer

## Layer 2: External plugin provider (optional add-on)
- Config: `memory.provider: 'honcho'` (or 'mem0', 'chroma', etc.)
- Providers ship in: `plugins/memory/<name>/`
- Requires: API keys in `.env`, pip dependencies
- This layer runs ALONGSIDE built-in, not instead of it

## The "Memory is not available" error
This error (from `memory_tool()` line 614) means `store is None` — the MemoryStore
was never created. Root causes:
1. `memory.memory_enabled: false` in config.yaml
2. `skip_memory=True` passed to AIAgent init
3. Exception during MemoryStore creation (silently caught)

It is NEVER caused by `memory.provider: ''` — empty provider means "built-in only"
which is the default and fully correct.

## Stale artifacts to watch for
- `honcho: {}` — empty section in config.yaml from incomplete setup
- `~/.hermes/chroma/chroma.sqlite3` — leftover Chroma DB from experimentation
- `.env` entries like `HONCHO_API_KEY=` with no value
