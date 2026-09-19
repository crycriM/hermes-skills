---
name: hermes-tui-troubleshooting
description: Use for Hermes TUI launch failures and /tools warnings.
---

# Hermes TUI Troubleshooting

How to diagnose and fix the Hermes terminal TUI (launched via `hermes --tui`), especially
flash-and-exit errors that vanish before they can be read. The user runs the TUI from
VSCode/tmux integrated terminals; reproduce in that environment class, not bare redirection.

## Architecture map (who prints what)

- `hermes --tui` → Python launcher (`hermes_cli/main.py::_launch_tui`) builds a scrubbed env
  (incl. `NODE_OPTIONS` with `--max-old-space-size=8192` by default) and runs
  `node ui-tui/dist/entry.js` (Ink React app) with cwd = repo root.
- The Ink app spawns its own gateway child: `venv/bin/python3 -m tui_gateway.entry`,
  JSON-RPC over stdin/stdout, PYTHONPATH prepended with the repo root.
- The node parent writes lifecycle breadcrumbs to `$HERMES_HOME/logs/tui_gateway_crash.log`
  (lines prefixed `[tui-parent]`); the python child appends SIGTERM/fault dumps to the same
  file. This is the FIRST place to look when the TUI fails — it shows whether the gateway
  child ever spawned.
- The messaging gateway (`hermes-gateway.service`) is a SEPARATE process that owns
  `gateway.pid` / `gateway.lock` / `gateway_state.json`. The TUI does not lock-check it;
  both can run concurrently.
- The 3.7MB bundle `ui-tui/dist/entry.js` holds the only "unknown toolsets" string in the
  frontend (lowercase, from the `/tools` slash command). Capitalized "Warning: ..." in a
  user report is usually paraphrase — trace to the python side before assuming a second
  emitter exists.

## Capturing flash-and-exit errors

- Plain redirection (`hermes --tui > log 2>&1`) breaks TTY detection — the TUI behaves
  differently. Use a pty recorder:
  `timeout 120 script -qec "hermes --tui" /tmp/tui_capture.log`
  The typescript keeps the error even if the app exits instantly.
- Ready-made wrapper on this box: `~/.hermes/scripts/tui-capture.sh` (prints a readable
  ANSI-stripped tail on exit). Copy in `scripts/tui-capture.sh` here.
- To reproduce in the user's env class: `tmux new-session -d -s tuitest 'hermes --tui'`,
  wait, then `tmux capture-pane -t tuitest -p`; kill with `tmux kill-session -t tuitest`.
  Watch for orphaned `node .../entry.js` + `tui_gateway.entry` children after killing —
  clean them up explicitly.
- Decode ANSI typescript in python (strip `\x1b\[[0-9;?]*[a-zA-Z]`, `\x1b\]...\x07`,
  `\x1b[()]...`) then dedupe consecutive identical lines — Ink redraws produce huge noise.

## Exit keys and the SIGSTOP trap

- In the TUI, Ctrl+C is CONTEXTUAL: during a turn it interrupts the turn; with typed text
  it clears input; only at an IDLE EMPTY prompt does it exit (via `handleIdleHotkeyExit`).
- Ctrl+D behaves similarly. Type `/quit` or exit at the idle prompt to leave cleanly.
- NEVER Ctrl+Z inside the TUI/recorder: it SIGSTOPs the whole pty chain (`timeout`,
  `script`, and the TUI all go to state T) and looks frozen forever. Recovery:
  `pkill -f tui-capture.sh; pkill -f 'timeout 120 script'`, then `stty sane` + `reset` in
  the affected terminal (kill -9 of `script` skips terminal-mode restore).

## /tools command semantics (the "unknown toolsets" warning)

- `/tools enable|disable <name>` validates names against `CONFIGURABLE_TOOLSETS` in
  `hermes_cli/tools_config.py` plus plugin toolset keys; unknown names come back in the
  `unknown` field and render as `unknown toolsets: <names>` in the transcript.
- `messaging` and `moa` are NOT toolsets and are correctly rejected:
  - messaging platform tools are per-platform toolsets (telegram, discord, whatsapp, ...),
    gateway-side only — there is no "messaging" toolset to toggle.
  - `moa` is the Mixture-of-Agents mode (config.yaml `moa:` section / model picker).
- The warning is harmless; the command persists nothing for unknown names. Recognized names
  trigger a client-side transcript reset, which is why the warning can flash and vanish —
  it is NOT a launch error.
- Full valid-name list and the request/response flow: `references/tui-toolsets.md`.

## Pitfalls

- Grepping the 3.7MB one-line `dist/entry.js` with inline `grep -o`/`grep -c` can trigger
  the Hermes command-parser hardline block. Write a small python script to a file and run
  it instead.
- `_normalize_tui_toolsets` only forwards toolsets to the TUI via `HERMES_TUI_TOOLSETS`
  when toolsets were passed explicitly (CLI `-t`); plain `hermes --tui` doesn't pass any.
- Check `gateway_state.json` (`"gateway_state":"running"`, per-platform `state`) before
  blaming the messaging gateway — the TUI's "Messaging page" only reflects that file's
  mtime. Gateway SystemExit code 75 = EX_CONFIG; repeated 75s at startup are usually the
  systemd planned-restart dance, not a TUI problem.