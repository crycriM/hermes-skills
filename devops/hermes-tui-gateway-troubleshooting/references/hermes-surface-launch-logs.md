# Hermes surface launch — log & state file inventory

All under `~/.hermes/` unless noted. Gathered while diagnosing a flash-and-exit
TUI launch error (2026-08-18).

## Logs (`~/.hermes/logs/`)

| File | Contains | Use |
|---|---|---|
| tui_gateway_crash.log | Node TUI parent lifecycle lines (`[tui-parent] ... spawned gateway child pid=...`, graceful-exit/kill lines) AND python tui_gateway child SIGTERM/SIGHUP stack dumps | First check for TUI launch failures. Timestamps in UTC — convert to local (+02:00 CEST) before matching user-observed windows. Filter out your own test runs. |
| gateway.log | Main messaging gateway: platform connect/disconnect, "✓ telegram connected", "Launched systemd planned-restart helper", shutdown phases | Reconstruct the gateway's state during the failure window. Can be binary (grep needs `-a`). |
| gateway-exit-diag.log | JSON records: gateway.start (pid, python, argv), asyncio.run.SystemExit with code + traceback, gateway.exit_nonzero | **Code 75 = EX_CONFIG class** (config error / no messaging platforms). Repeated 75s = restart storm; check whether user launch coincided. |
| errors.log | Recent tool/agent errors (error scanner's target) | No error here + healthy gateway ⇒ failure was transient or env-specific. |
| gui.log | Desktop/electron web server; plugin route mounts; DB errors | `sqlite3.OperationalError: no such column` = frontend/backend schema drift (older backend vs newer desktop). |
| mcp-stderr.log | MCP server spawn log | A burst of "starting MCP server 'playwright'" lines means several Hermes surfaces (gateway, desktop, TUI) launched near-simultaneously — context for restart-window collisions. |
| agent.log | Agent session activity incl. API calls | Confirms session came up; distinguishes TUI launches from gateway activity. |

## State files

- `~/.hermes/gateway.pid` and `~/.hermes/gateway.lock` — JSON with pid/kind/argv.
- `~/.hermes/gateway_state.json` — `gateway_state:"running"`, per-platform
  `state`/`error_code`/`error_message`, `updated_at`. Compare PIDS across files,
  not `start_time` (it is a tick counter, NOT epoch seconds).
- `~/.hermes/state.db` — sessions/messages SQLite (messages + FTS tables).
  Schema-aware queries only; a bare `sqlite3` CLI may fail on this DB.

## Quick health ladder

1. `systemctl --user status hermes-gateway` — service up?
2. `cat ~/.hermes/gateway_state.json` — platform states all "connected"?
3. `tail -50 ~/.hermes/logs/gateway.log` — clean connect sequence?
4. `grep -a "2026-08-18" ~/.hermes/logs/gateway.log | grep -i restart` — planned
   restart helper fired around the user's attempt?

## ANSI-strip decode recipe (script/typescript output)

```python
import re, sys
data = open(sys.argv[1], 'rb').read().decode('utf-8', 'replace')
for pat in (r'\x1b\[[0-9;?]*[a-zA-Z]', r'\x1b\][^\x07]*\x07', r'\x1b[()][0-9A-Za-z]'):
    data = re.sub(pat, '', data)
lines = [l.rstrip() for l in data.replace('\r', '\n').split('\n') if l.strip()]
seen = []
for l in lines:
    if not seen or seen[-1] != l:
        seen.append(l)
print('\n'.join(seen[-70:]))
```

Also dedupe consecutive identical lines — Ink redraws the full frame repeatedly.