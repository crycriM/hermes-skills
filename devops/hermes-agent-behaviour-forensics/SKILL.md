---
name: hermes-agent-behaviour-forensics
description: Use when a Hermes profile misbehaves; prove tool vs model.
version: 1.0.0
author: Hermes Agent
license: MIT
tags:
  - hermes
  - profiles
  - diagnostics
  - state-db
  - guardrails
metadata:
  hermes:
    tags: [hermes, profiles, diagnostics, state-db, guardrails, tool-availability]
    related_skills: [multi-agent-profile-config, compression-error-diagnosis, hermes-cron-operations]
---

# Hermes agent behaviour forensics

When a profile's agent "failed at X" — never called a tool, looped, stopped early, ignored an
instruction — do NOT change config first. Prove from artefacts whether the capability was
unavailable or the model simply never used it. Two different diagnoses, two different fixes; guess
wrong and you rewrite a config that was never broken.

## When to Use

- A profile's agent "failed at" / "couldn't use" a tool, looped, or stopped mid-task.
- A tool seems missing from a profile's schema (vision, browser, image gen, MCP) and you are about to
  change model/provider/aux config.
- A profile ignores an instruction that lives in its `AGENTS.md`, `SOUL.md`, or a skill.
- A `guardrail_halt` / `identical_call_streak_halt` / repeated-identical-call turn in `agent.log`.
- Cron or background sessions of a profile behave differently from interactive ones.

Not for: provider/credential setup errors that already say what is missing (fix those directly), or
context-length failures — use `compression-error-diagnosis` for those.

## Procedure

1. **Find the session.** Per-profile logs: `~/.hermes/profiles/<name>/logs/agent.log` (INFO+),
   `errors.log` (WARNING+), `gateway.log`. A secondary profile writes nothing to the host journal, so
   an empty `journalctl` means nothing. Read the end of the turn: `Turn ended: reason=...`
   (`text_response`, `max_iterations`, `guardrail_halt`, `budget_exhausted`) tells you the failure
   class before you look anywhere else.
2. **Ask `state.db` whether the tool was ever called.** Read-only:
   `sqlite3.connect('file:' + path + '?mode=ro', uri=True)`. `messages` holds each tool result with
   `tool_name` set and the assistant's requests in `tool_calls` (JSON). `WHERE tool_name='<tool>'`
   gives real invocations; `WHERE tool_calls LIKE '%<tool>%'` shows what was asked for. If every hit
   sits inside a `tool_describe`/`tool_search` call, the tool was never invoked — stop hunting a tool
   bug.
3. **Ask the logs whether it was available.** The registry logs
   `<check_fn> returned False; dependent tools will be unavailable this turn` at INFO while a check is
   false, and a WARNING when it drops a previously-available tool. Those lines are the availability
   record; no such lines across recent turns means the gate passed.
4. **Reproduce the gate with the turn runtime bound** (see pitfalls) using
   `scripts/profile_tool_gate_probe.py`, run with the interpreter the `hermes` launcher names.
5. **If the fix is a prompt edit, prove it landed and expect a rebuild.**
   `SELECT instr(prompt, '<distinctive phrase>') FROM system_prompts` non-zero = it reached the
   model.

Deeper recipes (SQL, decoys, interpreter selection): `references/profile-behaviour-forensics.md`.

## Always-on rules

- **"The model didn't use the tool" is not "the tool is broken".** Decide from `state.db` + the
  registry check log before touching config.
- **Two decoys that look like availability evidence but are not:** `tool_describe`'s
  `'X' is a directly-listed tool, not a deferred one` is built from static name knowledge, not the
  turn's schema; and `tool_search` matches only DEFERRED tools, so zero matches for a built-in tool
  proves nothing about that built-in.
- **Gate checks can be runtime-bound.** Provider-resolving gates (vision, video) return False from a
  bare interpreter with no turn bound, and True in the live turn. Call `set_runtime_main(provider,
  model, base_url=..., api_key=...)` before evaluating, or you will "fix" a working profile.
- **Probe with the runtime interpreter**: the python the `hermes` launcher names
  (`~/.hermes/tools/python-*/bin/python3`) with `sys.path.insert(0, '~/.hermes/hermes-agent')` and
  `HERMES_HOME=~/.hermes/profiles/<name>`. `hermes-agent/venv/bin/python` is not that interpreter and
  fails to import Hermes modules.
- **A profile-home `AGENTS.md` is injected like `SOUL.md`** (both read from HERMES_HOME), even though
  `AGENTS.md` elsewhere is a git-root→cwd chain. Verify with `system_prompts` rather than assuming,
  and remember the live agent caches its system prompt: a prompt edit lands on the next new session
  or gateway rebuild, never mid-conversation.
- **Weak local model + Tool-Search bridge = a tool-call detour.** When ≥1 deferred tool exists the
  bridge (`tool_search`/`tool_describe`/`tool_call`) is injected and a small model may route a
  normal, directly-listed tool through it: search → no match → `tool_describe` → the same verbatim
  refusal 5× → `identical_call_streak_halt` ends the turn. Cheapest fix: a one-line directive in that
  profile's `AGENTS.md` naming the tool as directly callable. Structural fix:
  `tools.tool_search.enabled: off` (or `defer: []`), costing prompt tokens because the deferred tools
  become eager.
- **Ask before editing a profile's config or restarting its gateway** — this user wants the choice,
  and offer the cheapest option first.
- **Report the diagnosis with its evidence**: which artefact proved what, then the fix and whether it
  needs a rebuild. File the finding in holographic memory so it is not re-derived next time.
