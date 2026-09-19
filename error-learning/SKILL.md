---
name: error-learning
description: Load recent Hermes tool/skill errors to avoid repeating them.
category: meta
---

# Error Learning

Before taking any non-trivial action, check the error summary to avoid known pitfalls:

1. Run: `python3 ~/.hermes/scripts/error_scanner.py`
2. Read: `~/.hermes/error_summary.txt`
3. Note the top recurring errors and their advice
4. Check memory for previously saved error lessons (memory tool)

## Quick reference (from most recent scan — 2026-08-03)

- **model:api_error** (114): router :8079 contention under concurrent cron load. Transient, retry handles it.
- **tool:terminal:error** (70): broad terminal failures — check approval wall, process state, timeouts first.
- **tool:skill_manage:error** (66): #1 cause: models call `skill_manage(action='create')` without `content` param. Always provide content; check skills_list before querying.
- **tool:memory:error** (62): models call memory tool with invalid args (action=None, missing content). Not cron limitation.
- **tool:skill_view:error** (13): skill name hallucination — check available_skills before calling.
- **tool:patch:error** (7): non-unique match, escape-drift. Re-read file, use more specific context.
- **tool:tool_call:error** (7): tool_call arguments format error — check tool schema.
- **tool:browser_navigate:error** (5): no Chrome/CDP. Use Playwright MCP or web_extract instead.
- **tool:execute_code:status_error** (5): cron blocked. Use terminal instead.
- **tool:search_files:error** (3): background review denied in cron.
- **tool:read_file:error** (3): background review denied in cron.
- **model:503_unavailable** (3): router OOM/crash. Retry logic handles edge cases.
- **tool:execute_code:error** (3): background review denied in cron.

## Stable patterns (2026-08-03)

- model:api_error (114): router :8079 contention under concurrent cron load — transient, retry handles it
- tool:terminal:error (70): broad failures — check approval wall, process state, timeouts
- tool:skill_manage:error (66): **growing** — #1 cause still "content is required for 'create'" — models omit `content` param when creating skills
- tool:memory:error (62): **large jump from 15** — models call memory with invalid args (action=None, missing content). Not cron limitation.
- tool:skill_view:error (13): skill name hallucination — check available_skills list
- tool:patch:error (7): non-unique match, escape-drift — re-read file, use more specific context
- tool:tool_call:error (7): tool_call args format error — check tool schema
- tool:search_files:error (3), tool:read_file:error (3): background review denied in cron
- tool:execute_code:error (3): cron blocked, HTML leak — use terminal instead
- model:503_unavailable (3): router OOM/crash — retry handles edge cases
- tool:browser_navigate:error (5): no Chrome/CDP
- tool:execute_code:status_error (5): cron blocked

## Delta vs 2026-08-02 scan (232 errors)

- **model:api_error +18** (96→114) — router contention under concurrent cron load
- **tool:terminal:error +2** (68→70) — growing, mostly cron approval wall
- **tool:skill_manage:error +1** (65→66) — #1 cause: missing content param on create
- **tool:memory:error +47** (15→62) — **largest increase**: models call memory with invalid args (action=None, missing content)
- **tool:skill_view:error 0** (13→13) — skill name hallucination — stable
- **tool:patch:error 0** (7→7) — non-unique match, escape-drift
- **tool:tool_call:error 0** (7→7) — tool_call args format error
- **tool:browser_navigate:error 0** (5→5) — no Chrome/CDP
- **tool:execute_code:status_error +1** (4→5) — cron blocked
- **tool:search_files:error 0** (3→3) — background review denied in cron
- **tool:read_file:error 0** (3→3) — background review denied in cron
- **model:503_unavailable 0** (3→3) — router OOM/crash
- **tool:execute_code:error 0** (3→3) — background review denied in cron

## Notable patterns

### "Background review denied" epidemic — stable
~200+ errors across 8 tool types (patch, read_file, search_files, write_file, process, todo, execute_code, cronjob) all share the same root cause: **subagents spawned via `delegate_task` and cron sessions cannot use file-modifying tools**. Only memory and skill management tools are whitelisted for background/subagent tasks.

Symptom: "Background review denied non-whitelisted tool: <tool>. Only memory/skill tools are allowed."

This is a **Hermes Agent platform limitation**, not a config issue the user can fix. Workarounds:
- Delegate tightly-scoped tasks that don't need file tools (reasoning, review, research)
- Use cron jobs instead of delegate_task for multi-phase builds (cron jobs run in fresh sessions with full tool access)
- Do file work yourself in the orchestrating session, not via subagents
- Save subagent output to memory/skills instead of writing files via subagent

### Model server instability (router :8079 — concurrent cron job collisions — stable)
Intermittent 503/502/500 errors from the local llama.cpp router at `localhost:8079/v1/`. Multiple cron jobs used to fire at ~10:00 AM simultaneously, causing model loading contention.

**Fix applied 2026-07-03**: staggered start times (see `devops` skill → `references/router-collision-resolution.md`):
- `10:00` → Coinalyze OI (no_agent shell script — negligible router load)
- `10:05` → Error Scanner (qwen36-35b via opencode-go)
- `10:15` → Paris music research (qwen36-27b via local :8079, Saturdays only)
- `22:00` → M5 power quiet (no_agent shell)
- `22:05` → august-nightly-dream (no_agent shell)

Remaining risk: one LLM job hitting the router while another is still loading its model. Retry logic (3 attempts) should handle edge cases.

### Memory tool near capacity
Memory store at ~2,500 char limit (raised from 2,200). MEMORY.md does not exist. When adding entries would exceed the limit, replace/remove old entries first. This is a recurring issue in cron sessions where memory entries accumulate without cleanup.

### Memory tool invalid arg errors (62x — 2026-08-03)
Models call the `memory` tool with invalid arguments:
- `action=None` (unknown action) — happens when model omits `action` parameter
- Missing `content` on `replace` action
- Missing `content` on `add` action (shouldn't happen but does)

**Fix**: Models must always validate they're passing valid `action` values (add/replace/remove) and include `content` when required. This is NOT a cron limitation — it's a model hallucination issue. Memory tool IS available in cron sessions.

### Browser tools — two different toolkits
Two separate browser toolkits exist. See `devops` skill for full details.

**1. Playwright MCP** (`mcp_playwright_browser_*`) — WORKS. Playwright 1.59.1 with Chromium 1226 at `~/.cache/ms-playwright/chromium-1226`. Runs headless, no DISPLAY needed. Use for all browsing/scraping.

**2. Old Hermes core browser tools** (`browser_navigate`, `browser_click`, `browser_console`, `browser_vision`, etc.) — FAIL. Expect system Chrome/CDP with X display. No X server here.

**Guidance**: Always `mcp_playwright_browser_*`. Old tools fail because they need Chrome+display. If a cron job triggers browser errors, update its prompt to use `mcp_playwright_browser_navigate` + `mcp_playwright_browser_snapshot`.

### Cron job tool restrictions
Cron sessions have additional restrictions beyond subagent limitations:
- **execute_code** is BLOCKED: "Cron jobs run without a user present to approve" — use `terminal` instead
- **sudo** requires terminal: "sudo: A terminal is required to authenticate" — use wrapper scripts or pre-configure sudoers
- **Background review** blocks patch/read_file/search_files/write_file/process/todo — only memory/skill tools work

Note: memory tool IS available in cron sessions (store is None when called, but the tool is not blocked — errors are from invalid args, not tool restriction).

Note: memory tool IS available in cron sessions (store is None when called, but the tool is not blocked — errors are from invalid args, not tool restriction).

## Cron job

Daily error learning job: `f2f203ebc9b1` (10:05 AM) — scans errors and saves lessons to memory. Staggered to avoid router collision with other cron jobs.

## Profile notes

- No "default" profile config exists — cron runs without a Hermes profile directory
- Profile-level overrides: `august` has `memory_enabled: false` explicitly
- `mcp_jina_reader_extract_pdf:error` 1 actual PDF failure + 2 skill_manage text-match artifacts — stable