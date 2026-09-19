---
name: hermes-tui-gateway-troubleshooting
description: Use when Hermes TUI/gateway launch fails or flashes errors.
---

# Hermes TUI / Gateway / Desktop launch troubleshooting

Diagnose startup failures and flash-and-disappear error banners on Hermes
surfaces (CLI TUI, messaging gateway, desktop app). The hard part is never the
fix — it's catching the error text and knowing WHICH surface emitted it.

## How a TUI launch actually works (architecture map)

- `hermes --tui` (NOT `hermes tui` — that is an invalid subcommand) →
  `hermes_cli/main.py::_launch_tui` builds env (`NODE_OPTIONS` gains
  `--max-old-space-size`, default 8192MB) → replaces the process with
  `node ui-tui/dist/entry.js` (or tsx in --dev).
- entry.js spawns a child gateway: `python -m tui_gateway.entry` with
  `HERMES_PYTHON_SRC_ROOT` set, cwd = repo root, PYTHONPATH prepended with
  root. The child's stdout is JSON-RPC protocol; its stderr lines surface in
  the TUI as `gateway.stderr` log entries.
- `HERMES_TUI_GATEWAY_URL` switches the TUI to ATTACH mode (no child spawned)
  — used by the dashboard's Chat tab (`HERMES_TUI_SIDECAR_URL` is the
  dashboard sidecar). A normal terminal launch always spawns the child.
- The tui_gateway child has NO lock check against the main messaging gateway:
  it coexists with `hermes-gateway.service`. Conflict is not the default cause.
- The TUI frontend bundle contains NO user-facing text with the word
  "messaging". That wording lives in the DESKTOP app (i18n: "Messaging
  gateway stopped", "Messaging platforms failed to load") and gateway internals
  (`gateway/run.py` "No connected messaging platforms remain..."). If a TUI
  launch error "talks about messaging", it is either desktop-side or a
  transient main-gateway state banner, not a string from the TUI itself.

## Workflow

1. Reproduce in a disposable pty FIRST, before reading code:
   `timeout 25 script -qec "hermes --tui" /tmp/tui_capture.log`
   Decode with the ANSI-strip python snippet (see references) — Ink TUI output
   is escape-code soup; strip `\x1b[...m` sequences and `\r`→`\n`, dedupe
   consecutive lines, tail the result.
2. Reproduce in a detached tmux pane (matches VSCode-integrated / tmux user
   env): `tmux new-session -d -s tuitest 'hermes --tui; sleep 60'`, wait,
   `tmux capture-pane -t tuitest -p -S -300`. ALWAYS kill the session after,
   then pgrep and kill the orphaned node/entry.js + python tui_gateway.entry
   children (tmux kill does NOT reap them).
3. If it launches clean in both, your env class is not the cause. Check the
   log inventory (references/hermes-surface-launch-logs.md): tui_gateway_crash.log
   for child lifecycle/fatal entries, errors.log for today's errors,
   gateway.log around the failure window, gateway-exit-diag.log for exit codes.
4. Check gateway_state.json + gateway.pid + gateway.lock freshness and
   `gateway_state.gateway_state`. A gateway restart storm (repeated
   `SystemExit: 75` in gateway-exit-diag.log) means EX_CONFIG-class exits —
   check whether the user's launch coincided with a restart window. Planned
   restarts log "Launched systemd planned-restart helper".
5. Attribute the error text: grep the codebase for the exact wording the user
   glimpsed (`grep -rn -i "<word>" ui-tui/src apps/desktop/src tui_gateway/`)
   to find which surface owns it. TUI frontend ≈ no "messaging"; desktop has
   i18n strings; gateway has logger.error texts.
6. If still unreproducible, hand the user a capture wrapper (scripts/tui-capture.sh
   — also installed at ~/.hermes/scripts/tui-capture.sh) so their next launch
   logs itself, then read the file. Asking "how do you launch" first (flag vs
   desktop vs REPL vs integrated terminal) targets the right surface.

## Pitfalls

- Do NOT restart/stop the live messaging gateway to test a hypothesis if your
  own session runs under it (`_HERMES_GATEWAY=1` in env ⇒ same process).
  Reproduce with a scratch pty/tmux instead.
- Plain `hermes` uses the classic REPL unless display.interface: tui is set;
  verify which surface the user actually means before assuming `hermes --tui`.
- Don't pipe TUI output through head/tail — you mask exit codes; capture to a
  file and inspect.
- The TUI working once does not clear a session: transient gateway-restart
  collisions resolve within minutes. Check the restart window before shipping
  a "broken TUI" conclusion.
- gateway_state.json start_time is NOT epoch seconds; compare pid values to
  gateway.pid instead.

## Support files

- references/hermes-surface-launch-logs.md — log/state-file inventory.
- scripts/tui-capture.sh — wrapper that records a full TUI launch to
  ~/.hermes/logs/tui-user-capture.log and prints a decoded tail on exit.