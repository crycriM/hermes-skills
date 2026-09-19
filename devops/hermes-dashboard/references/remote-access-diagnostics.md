# Remote access diagnostics (dashboard + desktop app)

Verified 2026-08-26, Hermes 0.20.5, dashboard started as
`hermes dashboard --port 9119 --no-open --skip-build`.

## Ground truth check

```bash
ss -tlnp | grep -E ':(9119|8642)\b'        # bind address + pid per service
curl -s http://127.0.0.1:9119/api/status   # dashboard health: version, gateway_state, gateway_platforms
```

- Dashboard health JSON includes `gateway_running:true`, `gateway_state:"running"`,
  and per-platform states (telegram/discord `"connected"`).
- Gateway root path returns 404 — that is normal for the API server (no UI routes);
  the dashboard proxies gateway status. Do not read 404 as "gateway down".

## 0.0.0.0 bind request fails (exact transcript)

Command: `hermes dashboard --host 0.0.0.0 --port 9119 --insecure --tui --no-open --skip-build`

Output:
```
→ Skipping web UI build (--skip-build); using dist at <hermes_home>/hermes_cli/web_dist
Refusing to bind dashboard to 0.0.0.0 — the auth gate engages on non-loopback binds (0.0.0.0), but no auth providers are registered.

Configure an auth provider before exposing the dashboard:
  • Password: set dashboard.basic_auth.username + password_hash in config.yaml
    (hash with: python -c "from plugins.dashboard_auth.basic import hash_password; print(hash_password('your-password'))")
  • OAuth: run `hermes dashboard register` (Nous Portal) or install a DashboardAuthProvider plugin.
There is no unauthenticated public-dashboard option. For local-only use, bind 127.0.0.1 and leave dashboard.public_url unset; a configured external public URL requires auth even when a local reverse proxy reaches a loopback backend.
EXIT=1
```

Notes:
- `--insecure` is consumed but a no-op (help text: "DEPRECATED / NO-OP").
- `--tui` is not in `hermes dashboard --help` usage and is silently ignored — the
  embedded TUI chat is always enabled (`_DASHBOARD_EMBEDDED_CHAT_ENABLED = True`).
- Run the exact user command BEFORE explaining: it fails fast and harmlessly, and
  the real output is more convincing than the skill's predicted refusal.

## HERMES_DASHBOARD_SESSION_TOKEN semantics

Source: `hermes_cli/web_server.py:530-556`.

- Purpose: the desktop shell mints the token and injects it via the env var so
  the Electron main process can authenticate its own /api calls
  (X-Hermes-Session-Token header). It protects "sensitive endpoints (reveal)" and
  is injected into the SPA HTML so only the legitimate web UI can use it.
- `_resolve_session_token()` = `os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN") or secrets.token_urlsafe(32)` —
  if the env var is absent, the server generates a fresh random token per start.
- It is NOT an auth provider: does not unlock the 0.0.0.0 bind gate.
- A value sitting in ~/.hermes/.env may or may not be loaded by the running
  server — /proc/<pid>/environ is UNRELIABLE for this: it showed zero
  SESSION_TOKEN matches while the server still validated the .env token on an
  HTTP probe (env_loader loads .env into os.environ at startup). Ground truth
  is the probe, not /proc:
  ```bash
  TOKEN=$(grep '^HERMES_DASHBOARD_SESSION_TOKEN=' ~/.hermes/.env | cut -d= -f2- | tr -d '"')
  curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9119/api/skills
  curl -s -o /dev/null -w '%{http_code}\n' -H "X-Hermes-Session-Token: $TOKEN" http://127.0.0.1:9119/api/skills
  # 401 without → protected route; 200 with → server accepts the .env token.
  # On a non-existent route, 401-without vs 404-with still means auth PASSED.
  ```
- The "# Browserbase Project ID" comment above the var in .env can be a
  misleading leftover — not evidence of what the token does.

## Desktop app remote connect

The Electron desktop app remote login drives a dedicated backend:

```
hermes serve --isolated --host 127.0.0.1 --port 0 \
  --ssh-session-token-file ~/.hermes/desktop-ssh/<ownershipId>/<nonce>.token \
  --ssh-owner-nonce <nonce>
```

- Layout: `~/.hermes/desktop-ssh/<ownershipId>/`
  - `backend.lock.json` → `{"ownershipId":..., "spawnNonce":..., "pid":..., "port":..., "profile":"", "hermesPath":..., "hermesHome":..., "logPath":..., "tokenFin..."}`
  - `<nonce>.log` → `HERMES_BACKEND_READY port=NNNN` then a jsonrpc event stream
    (`session.reclaimed` reason=`ws_orphan_reap`, `sessions.changed`, `cron.changed`).
- `~/.hermes/logs/gui.log`:
  - `tui_gateway.ws: ws accepted peer=127.0.0.1:<port>` = desktop connected.
  - `ws closed peer=127.0.0.1:<port> reason=client_disconnect(code=1006) ... reaped_sessions=N` = dropped abnormally.
  - `Desktop cron scheduler will tick N profile(s): [...]` appears each serve startup.
- serve binding to 127.0.0.1 + dynamic port is by design: the desktop spawns it
  locally (or over its own SSH path). To use the dashboard from a remote machine,
  SSH-tunnel 9119; the serve backend needs no tunnel of its own when the desktop
  app has SSH access to this machine.

## Environment facts (this machine, 2026-08-26)

- sshd active on 0.0.0.0:22 (`systemctl is-active ssh`), so SSH tunnels work.
- LAN IP [REDACTED], Tailscale IP [REDACTED] (CGNAT 100.64/10).
- Typical verification for a tunnel request:
  ```bash
  hostname -I ; ss -tlnp | grep ':22' ; systemctl is-active ssh
  ```