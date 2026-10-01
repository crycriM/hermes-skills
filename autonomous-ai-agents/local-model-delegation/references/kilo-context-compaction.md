# Kilo Code context compaction mechanics (validated 2026-08-25)

Kilo is a fork of OpenCode. Source of truth for the mechanism:
https://kilo.ai/docs/customize/context/context-condensing

## Configuration (kilo.jsonc)

`"compaction": { "auto": true, "prune": true }`

- `auto = true` — automatic triggering. The TUI also has a manual `/compact` command,
  but one-shot `kilo run` never uses it: compaction is NEVER explicit between tasks.
- `prune = true` — older turns are dropped from context after summarization.

## Trigger

One computed trigger, evaluated every turn:

```
limit    = min(usable, limit.context)             # usable = context*threshold_percent/100
reserved = compaction.reserved ?? min(20000, maxOutputTokens)
trigger  = limit - reserved                       # fires when count(tokens) >= trigger
```

`maxOutputTokens = min(limit.output, 32000) || 32000`, so the safety buffer is at most
20'000 (`oD2` in the bundle), NOT the model's whole 32k output cap. With
`limit.context = 131072`, `threshold_percent: 60`, `output: 24576` the trigger lands near
59k tokens.

**`limit.context === 0` disables auto-compaction entirely** — the predicate returns false
before the trigger is computed, at any session size. That is the state of every custom
local model entry without an explicit `limit` block, and it (not a late trigger) is why
long local sessions in the outcomes below ran to the ceiling. A `limit` block is the fix,
and it is also what makes the trigger above computable in the first place.

## Behavior on trigger

An anchored summary replaces older conversation history; the most recent turns stay
verbatim when they fit; later triggers UPDATE the same summary (stale details dropped,
still-relevant kept) rather than restarting from scratch.

## Why it does not save long sessions by itself

- The endpoint's context is HARD and reserves `prompt + max_tokens` per request, so a
  session that grows past `context - max_tokens` gets a 400, not a truncation. Two
  >4-module runs died exit 1 mid-task at 131'617 / 131'742 tokens ("request exceeds the
  available context size") with compaction unarmed (no `limit` block).
- Even armed, a compaction is not a task boundary and the injected summary itself costs
  window. Consequence: for >1-module local-model delegations, write the prompt so partial
  completion is recoverable (scoped deliverables + report contract) and use the
  continuation pattern in context-ceiling-recovery.md (fresh session = window resets).
  Do not structure work around an expectation that auto-compaction will bridge tasks.

## Operational detail

- The local venv (skewbik/.venv) has NO `pip` module (`No module named pip`). In
  delegation prompts, verify dependency availability via `python -c "import <pkg>"`
  instead of `pip show` (scipy 1.17.1 confirmed importable this way).