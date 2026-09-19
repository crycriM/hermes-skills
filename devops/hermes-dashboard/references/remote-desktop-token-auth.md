# Remote desktop token auth + OAuth migration (dashboard 9119)

Verified 2026-08-26, Hermes 0.20.5. Companion to remote-access-diagnostics.md;
this one covers the dashboard-side auth model for the Electron desktop app.

## Windows desktop app config shape

Remote-mode config (stored by the app; `apps/desktop/src/global.d.ts` defines
`authMode: 'oauth' | 'token'`):

```json
{
  "mode": "remote",
  "remote": {
    "url": "http://<linux-host>:9119",
    "authMode": "token",
    "token": { "encoding": "safeStorage", "value": "<base64 blob>" }
  }
}
```

- The token blob is Electron safeStorage (DPAPI on Windows): cannot be
  decrypted from Linux. DO NOT try; verify the server side against the
  plaintext in ~/.hermes/.env instead (HTTP probe below).
- The app only speaks 'token' or 'oauth'. There is no 'password' authMode, so
  dashboard.basic_auth (password) does NOT help the desktop app — browser
  dashboard only.

## AUTH: what is accepted where (post June-2026 hardening)

| Bind | API (/api/*) | WS upgrade (/api/ws, /api/pty) |
|------|--------------|-------------------------------|
| loopback (127.0.0.1) | X-Hermes-Session-Token header or legacy Bearer `_SESSION_TOKEN` | `?token=<_SESSION_TOKEN>` |
| public (0.0.0.0, gate engaged) | session cookie via gated_auth_middleware (`request.state.session`); legacy token defers to gate | `?ticket=<single-use 30s>` (browser/native-client minted) or `?internal=<process credential>` (server-spawned children only). Legacy `?token=` unconditionally rejected |

Sources: `hermes_cli/web_server.py` `_require_token` (~line 640),
`_ws_auth_reason` (~line 16372), `_resolve_session_token` (line 539):
`os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN") or secrets.token_urlsafe(32)`.

Consequence: remote desktop ('token' authMode, public bind) worked only under
the pre-hardening `--host 0.0.0.0 --insecure` pattern. That pattern is gone;
the migration is authMode → 'oauth' + a registered OAuth provider.

## Why it broke (the update-rebinding failure mode)

- Old working setup (June 2026 session): `hermes dashboard --host 0.0.0.0 --no-open --insecure &`
  in background, token in .env, Windows app at http://<lan-ip>:9119 token mode.
- Aug 2026 `hermes update` to 0.20.5: update.log ended with
  `⟲ Restarting managed dashboard service ... ✓ restarted hermes-dashboard.service`.
  This is Hermes-managed (NOT systemd — no hermes-*.service units exist), and
  it starts the dashboard on DEFAULT 127.0.0.1:9119. Remote URL
  http://[REDACTED]:9119 instantly refused.
- `--insecure` no-op + auth gate (requires provider) + token rejected in gated
  mode ⇒ the old command cannot be restored verbatim on 0.20.5.
- The token itself was never the problem: probe showed the server validates the
  .env token fine (env_loader loads .env at startup).

First check after an update breaks remote Desktop: `ss -tlnp | grep 9119`
(127.0.0.1 vs 0.0.0.0), then `curl -s http://127.0.0.1:9119/api/status`.

## Fix paths

A. Tunnel (keeps token authMode, zero server change):
   Windows: `ssh -L 9119:localhost:9119 cricri@<host>` (OpenSSH client built in);
   app URL → `http://localhost:9119`. Token stays valid (loopback mode).
B. OAuth (true LAN access, no tunnel):
   1. `hermes auth add nous --no-browser` — device flow; prints
      `https://portal.nousresearch.com/manage-subscription?user_code=XXXX-XXXX`
      + code; CLI polls every 1s until the user approves in a browser.
      (`hermes dashboard register` alone fails with "You're not logged into
      Nous Portal" when the install was never portal-logged-in.)
   2. `hermes dashboard register --name <label>` — writes
      HERMES_DASHBOARD_OAUTH_CLIENT_ID to ~/.hermes/.env.
   3. Stop old dashboard pid (kill the 9119 listener; `hermes dashboard --stop`
      may also kill the desktop serve backend), start
      `hermes dashboard --host 0.0.0.0 --port 9119 --no-open --skip-build`
      (background). No --insecure, no --tui.
   4. Verify: `ss -tlnp | grep 9119` shows 0.0.0.0; `curl -s
      -o /dev/null -w '%{http_code}' http://<lan-ip>:9119/api/status` → 200;
      a protected route without a cookie now 401s/redirects (gate engaged).
   5. Windows: app authMode → 'oauth', keep URL http://<lan-ip>:9119, one
      Portal login in the app.

## Probe: does the server accept the .env token?

```bash
TOKEN=$(grep '^HERMES_DASHBOARD_SESSION_TOKEN=' ~/.hermes/.env | cut -d= -f2- | tr -d '"')
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9119/api/skills
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Hermes-Session-Token: $TOKEN" http://127.0.0.1:9119/api/skills
```

401→200 = accepted. /api/status is public (200 with or without). Note: on a
non-existent route you get 404 WITH token (auth passed, route missing) vs 401
without — read accordingly. /proc/<pid>/environ is NOT reliable for this (see
remote-access-diagnostics.md).

## Environment facts (this machine 2026-08-26)

- Gateway API server: 0.0.0.0:8642, root 404s (normal). Remote desktop sessions
  also hit `/v1/chat/completions` there with API_SERVER_KEY (from .env) — the
  model picker shows only the gateway's active model, not the llama.cpp router.
- sshd active on 0.0.0.0:22; LAN [REDACTED], Tailscale [REDACTED].
- desktop-ssh layouts and gui.log markers: see remote-access-diagnostics.md.