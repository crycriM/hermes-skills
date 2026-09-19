---
name: hermes-dashboard
description: Run/troubleshoot Hermes Dashboard, bind rules, and auth.
version: 1.1.0
metadata:
  hermes:
    tags: [hermes, dashboard, config, security]
    category: devops
---

# Hermes Dashboard

The Hermes Dashboard is a web UI for managing config, API keys, sessions, skills, cron jobs, and analytics. It runs on **port 9119** by default.

## When to Use

- User asks about port 9119
- User wants to start, stop, or reconfigure the dashboard
- User asks about remote access to Hermes features (incl. Desktop app remote connect failing)
- Dashboard refuses to start with a bind/auth error
- "Is HERMES_DASHBOARD_SESSION_TOKEN configured?" — it is NOT an auth provider; see Desktop App Remote section

## Commands

| Action | Command |
|--------|---------|
| Start | `hermes dashboard --port 9119 --no-open` |
| Start (skip build) | `hermes dashboard --port 9119 --no-open --skip-build` |
| Stop all | `hermes dashboard --stop` |
| Status | `hermes dashboard --status` |
| Auto port | `hermes dashboard --port 0` (OS-assigns) |
| Register OAuth | `hermes dashboard register` (Nous Portal) |

## Managed systemd service (persistent bind changes)

On managed installs the dashboard runs as a systemd USER service; the bind host and port live in `ExecStart`, not just in an ad-hoc command. Change bind/port PERSISTENTLY by editing the unit, then reload+restart:

```bash
# unit: ~/.config/systemd/user/hermes-dashboard.service
# ExecStart=%h/.local/bin/hermes dashboard --port 9119 --host 0.0.0.0 --no-open --skip-build
systemctl --user daemon-reload
systemctl --user restart hermes-dashboard.service
systemctl --user status hermes-dashboard.service --no-pager   # expect HERMES_DASHBOARD_READY port=9119
```

- Default unit has NO `--host` flag → binds 127.0.0.1. Adding `--host 0.0.0.0` is the durable way to expose it on the LAN.
- After restart, confirm the actual bind with `ss -ltnp | grep 9119` — an upstream `hermes update` can silently revert the unit/bind to loopback (see Desktop App Remote section).
- `hermes dashboard --status` reports the running PIDs/args, useful to confirm the flag landed.

## Auth Rules (June 2026 hardening)

The `--insecure` flag is **deprecated and a no-op**. It no longer bypasses authentication.

- **127.0.0.1 only (default)**: no auth required — safe for local access
- **0.0.0.0 (network bind)**: REQUIRES an auth provider. Refuses to start otherwise with:
  ```
  Refusing to bind dashboard to 0.0.0.0 — the auth gate engages on non-loopback
  binds, but no auth providers are registered.
  ```

### Configuring Auth

**Password auth:**
```yaml
# config.yaml
dashboard:
  basic_auth:
    username: admin
    password_hash: <hash>
```
Generate hash:
```bash
python -c "from plugins.dashboard_auth.basic import hash_password; print(hash_password('your-password'))"
```

**OAuth:** `hermes dashboard register` connects to Nous Portal.
- Fails with `✗ You're not logged into Nous Portal. Run hermes setup (or hermes auth add nous) first` when the install was never portal-logged-in. Avoid `hermes setup` (it also rewrites model/provider config) — use the narrow login: `hermes auth add nous --no-browser` (device flow: prints portal URL + user code, CLI polls until approval). Then re-run `hermes dashboard register --name <label>`, then restart the dashboard with `--host 0.0.0.0`.
- **Diagnostic when user asks for "0.0.0.0 with OAuth" but OAuth isn't set up:** check the real prereqs BEFORE offering to enable it. OAuth is registered only if BOTH `config.yaml` has a non-empty `dashboard.oauth.client_id`/`portal_url` AND a Nous Portal login exists (verify via `hermes auth list` / `~/.hermes/auth.json` — the `nous` provider must appear; also grep `~/.hermes/.env` for `HERMES_DASHBOARD_OAUTH_CLIENT_ID`). On this machine the `oauth:` block was present but empty (client_id/portal_url = `''`) and no `nous` login existed — so OAuth was NOT available. In that state, `basic_auth` (username + scrypt hash in `config.yaml`) already satisfies the 0.0.0.0 gate, so the user can choose password auth now and defer OAuth. Don't claim OAuth is enabled just because an empty `oauth:` block exists.

### Remote Access Without Auth

Bind to 127.0.0.1 and tunnel:
- SSH: `ssh -L 9119:localhost:9119 user@host`
- Tailscale: both machines on Tailscale, connect to 127.0.0.1:9119 locally

## Desktop App Remote Connection (hermes serve)

The Electron desktop app does NOT connect to the dashboard (9119) or the gateway (8642) for remote login. It drives a dedicated backend spawned as:

```
hermes serve --isolated --host 127.0.0.1 --port 0 --ssh-session-token-file ~/.hermes/desktop-ssh/<ownershipId>/<nonce>.token --ssh-owner-nonce <nonce>
```

Loopback only, OS-assigned port — that is expected, not a bug.

- Each spawn writes `~/.hermes/desktop-ssh/<ownershipId>/`: `backend.lock.json` (pid, port, hermesPath) and a log containing `HERMES_BACKEND_READY port=NNNN`.
- Live sessions show in `~/.hermes/logs/gui.log` as `tui_gateway.ws: ws accepted peer=127.0.0.1:...`; an abnormal close (`client_disconnect(code=1006)`) plus `ws_orphan_reap` events in the backend log = dropped desktop session.
- Remote desktop use rides an SSH tunnel (or the desktop app's own SSH spawn to this machine); a loopback-bound serve backend is by design.
- Full diagnostic walkthrough: `references/remote-access-diagnostics.md`

### Remote desktop → dashboard (9119): token vs OAuth

The desktop app's connection config supports exactly `authMode: 'token' | 'oauth'` (apps/desktop/src/global.d.ts).

- 'token' mode = the HERMES_DASHBOARD_SESSION_TOKEN handshake (X-Hermes-Session-Token header on /api, ?token= on WS). Accepted ONLY on loopback binds; in gated (public-bind) mode the legacy token is explicitly rejected for API and WS — the gate only accepts a session cookie for /api and `?ticket=` (single-use, 30s TTL) or `?internal=` (server-spawned children) for the WS upgrade.
- Remote desktop over a public/LAN bind (e.g. Windows app → `http://[REDACTED]:9119`) therefore REQUIRES switching the app to authMode 'oauth'. There is no password mode in the desktop app.
- The pre-hardening remote pattern (`hermes dashboard --host 0.0.0.0 --insecure` + token in .env) worked into mid-2026, then a `hermes update` silently killed it: updates restart the managed dashboard service on DEFAULT LOOPBACK bind and `--insecure` became a no-op. If remote Desktop breaks right after an update, suspect the rebinding first (check `ss -tlnp` for 127.0.0.1 vs 0.0.0.0 on 9119), then the gate.
- Full session detail (Windows config shape, probes, OAuth onboarding): `references/remote-desktop-token-auth.md`

## Pitfalls

- Never claim `--insecure` works for public binds — it was removed in June 2026
- Don't set `--host 0.0.0.0` without configuring an auth provider first — the command will fail with exit code 1
- The dashboard is separate from the gateway (port 8642); features like sessions, skills, config are dashboard-only
- Starting a dashboard with `--port 0` prints the port to stdout; capture it if scripting
- The desktop app's default dashboard URL is `http://127.0.0.1:9119`; if you change the port, update the app's settings
- `--tui` is NOT a valid `hermes dashboard` flag — silently ignored, and the embedded TUI chat is always enabled anyway. Don't pass it.
- `HERMES_DASHBOARD_SESSION_TOKEN` (even when set in ~/.hermes/.env) does NOT satisfy the 0.0.0.0 auth gate. It is the desktop-shell→server handshake token (X-Hermes-Session-Token header) protecting sensitive /api endpoints; if absent, the server mints its own per-start token. Verify a running server ACCEPTS it with an HTTP probe — never /proc/<pid>/environ (proven unreliable: showed no SESSION_TOKEN yet the server still validated the .env token):
  ```bash
  TOKEN=$(grep '^HERMES_DASHBOARD_SESSION_TOKEN=' ~/.hermes/.env | cut -d= -f2- | tr -d '"')
  curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9119/api/skills                        # 401 = route is protected
  curl -s -o /dev/null -w '%{http_code}\n' -H "X-Hermes-Session-Token: $TOKEN" http://127.0.0.1:9119/api/skills  # 200 = token accepted
  ```
  Gotcha: on a non-existent route, 401-without-token vs 404-with-token still means auth PASSED (middleware runs before routing).
- A timed-out clarify() is NOT consent: for infra decisions (auth provider, bind host), if the user doesn't answer, WAIT for their next message — do not proceed on "best judgement" (user explicitly corrected this).

## Verification

```bash
ss -tlnp | grep 9119   # 127.0.0.1:9119 = loopback, 0.0.0.0:9119 = network bind
curl -s http://127.0.0.1:9119/api/status | head -c 200
```
A running dashboard returns status JSON. Stopped returns connection refused.

For a 0.0.0.0 (gated) bind, confirm the gate actually engaged, not an open server:
```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9119/           # 302 -> /login?next=%2F
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9119/api/skills  # 401 without creds = gate on
```
LAN + Tailscale reachability: `ip -4 -o addr` to find the node IP (e.g. 192.168.1.x, 100.x tailscale); a 302 to /login confirms the login page is reachable over the network. On this machine port 9119 is TLS-absent, so the reachable URL is plain http under the network bind.
