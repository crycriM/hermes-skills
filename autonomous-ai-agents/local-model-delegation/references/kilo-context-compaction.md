# Kilo Code context compaction mechanics (validated 2026-08-25)

Kilo is a fork of OpenCode. Source of truth for the mechanism:
https://kilo.ai/docs/customize/context/context-condensing

## Configuration (kilo.jsonc)

`"compaction": { "auto": true, "prune": true }`

- `auto = true` — automatic triggering. The TUI also has a manual `/compact` command,
  but one-shot `kilo run` never uses it: compaction is NEVER explicit between tasks.
- `prune = true` — older turns are dropped from context after summarization.

## Trigger (whichever comes first)

1. The conversation tally reaches `compaction.threshold_percent` (default 75).
2. The remaining window hits the reserved safety buffer. For models that declare a
   single context window (all local llama.cpp models via the :8079 proxy), kilo
   reserves the model's FULL output cap — up to 32'000 tokens, because kilo always
   sends `max_tokens: 32000` — so compaction fires before usable context drops below
   ~32k.

## Behavior on trigger

An anchored summary replaces older conversation history; the most recent turns stay
verbatim when they fit; later triggers UPDATE the same summary (stale details dropped,
still-relevant kept) rather than restarting from scratch.

## Why it does not save long sessions on this stack

- qwen38-27b via :8079 has a HARD 131'072-token ceiling. Two >4-module runs died
  exit 1 mid-task at 131'617 / 131'742 tokens ("request exceeds the available context
  size"). The summary injection itself costs window, and kilo's token accounting
  cannot see the proxy's hard cap — compaction triggered too late or not at all.
- Consequence: for >1-module local-model delegations, write the prompt so partial
  completion is recoverable (scoped deliverables + report contract) and use the
  continuation pattern in context-ceiling-recovery.md (fresh session = window resets).
  Do not structure work around an expectation that auto-compaction will bridge tasks.

## Operational detail

- The local venv (skewbik/.venv) has NO `pip` module (`No module named pip`). In
  delegation prompts, verify dependency availability via `python -c "import <pkg>"`
  instead of `pip show` (scipy 1.17.1 confirmed importable this way).