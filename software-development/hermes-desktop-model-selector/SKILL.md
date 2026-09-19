---
name: hermes-desktop-model-selector
description: "Use when desktop model picker or Thinking toggle misbehaves."
version: 1.0.0
author: PinceMi
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, desktop, model-picker, reasoning, thinking, troubleshooting]
---

# Hermes Desktop Model Selector & Thinking Toggle

Where the model picker lives in the Hermes desktop app, how the Thinking/effort/Fast controls are gated, and how to verify what the backend actually serves. Covers `apps/desktop` (Electron renderer) plus the `tui_gateway`/`hermes_cli` backends that feed it. Repo: `~/.hermes/hermes-agent`.

## The two surfaces (pick the right one)

1. **Model picker dialog** — `apps/desktop/src/components/model-picker.tsx` (`ModelPickerDialog`). A plain searchable model list with prices. **No thinking/fast controls, by design.** Opened when the live gateway menu is unavailable for that surface (the composer pill falls back to it when `model.modelMenuContent` is absent).
2. **Live catalog menu** — `apps/desktop/src/app/shell/model-catalog-menu.tsx` (`ModelCatalogMenu`), the composer pill's real dropdown. Model rows expose an **Options submenu on HOVER** (`model-edit-submenu.tsx`): Thinking switch + effort scale (`minimal..ultra`) + Fast toggle. **Hover, don't click** — clicking commits the model and closes.

The profile default (`agent.reasoning_effort`) lives in **Settings → Model** (`apps/desktop/src/app/settings/model-settings.tsx`) with values including `none` (Off).

## Gating — why a toggle is hidden

```ts
showThinkingToggle = reasoning && canDisableReasoning !== false   // model-edit-submenu.tsx
```

- `reasoning` — computed in `hermes_cli/inventory.py::_apply_capabilities`: from models.dev (`agent.models_dev.get_model_capabilities`), **defaults to True when unknown**. A serving aggregator catalog (Nous/OpenRouter only) that reports `supports_reasoning: False` overrides it to False (no reasoning parameter on the route → no controls).
- `can_disable_reasoning` — only Nous/OpenRouter publish it. `False` on reasoning-mandatory routes (upstream answers a disable with HTTP 400), so the toggle is hidden rather than offered as a control that silently fails. Absent = no restriction known = toggle shown.

Verified live payload: opencode-go and local providers carry no reasoning catalog, so **every model reports `{reasoning: true}`** and the toggle is available. On openrouter, `anthropic/claude-fable-5` is mandatory (`can_disable_reasoning: false`, toggle hidden); all other models allowed.

## Write path (why a flip might fail)

Toggle/effort → `controller.setOptions` → `patchReasoning` (`apps/desktop/src/app/shell/model-menu-panel.tsx`) → gateway RPC `config.set {key:'reasoning', session_id, value}` (`tui_gateway/server.py`, `config.set` handler) → `parse_reasoning_effort(value)` → session `create_reasoning_override` / `agent.reasoning_config` → provider profile `build_api_kwargs_extras` translates to wire params (e.g. opencode-go plugin: DeepSeek/Kimi OC-family get `extra_body.thinking` **or** top-level `reasoning_effort`, never both — the relay 400s "cannot specify both thinking and reasoning_effort").

`parse_reasoning_effort` accepts `none|minimal|low|medium|high|xhigh|max|ultra` — the toggle never sends a value the backend rejects. If the switch "snaps back" with an updateFailed toast, the gateway RPC itself failed (patchReasoning rolls back) — check `tui_gateway`/agent logs, not capabilities.

## Verify what the picker serves (no auth needed)

Desktop serve backends (`hermes serve --isolated`) authenticate via *transient* SSH token files under `~/.hermes/desktop-ssh/<id>/`; the token vanishes after startup, so direct curl to the serve port 401s. Reproduce the payloads in-process instead (venv python from the repo root):

```bash
cd ~/.hermes/hermes-agent
venv/bin/python scripts/probe-model-caps.py opencode-go        # caps for one provider
venv/bin/python scripts/probe-model-caps.py --picker           # full picker payload, providers + caps
venv/bin/python -c "from hermes_constants import parse_reasoning_effort; print(parse_reasoning_effort('high'))"
```

## Pitfalls

- The picker dialog is not where thinking lives — check the hover submenu or Settings → Model before concluding anything is broken.
- `agent.reasoning_effort: none` in config.yaml means thinking is off by default for every new chat; the toggle's checked state follows it.
- Rows hide/disable per capability; never assume a missing toggle is a bug until the caps payload for that exact provider+model has been dumped.
- Line numbers in `tui_gateway/server.py` (16k+ lines) drift; anchor on function names (`config.set` handler, `_apply_capabilities`) when grepping.

See `references/model-options-flow.md` for the full code map; `scripts/probe-model-caps.py` is the re-runnable probe.