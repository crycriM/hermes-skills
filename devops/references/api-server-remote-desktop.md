# API Server Remote Desktop — Error Transcript & Fix

## Original Error

Session: 2026-06-09, model deepseek-v4-flash via OpenCode Go.

**User report:** "hermes desktop on remote can't run sessions, even though connection is OK and token is still valid."

## Diagnosis Steps

### Step 1: Check running services

```text
$ systemctl --user status hermes-gateway
-> Active: active (running)
-> Main PID running

$ ss -tlnp | grep -E '8642|9119|8088'
-> 9119: LISTEN (dashboard running)
-> 8088: LISTEN (Open WebUI running)
-> 8642: NOT LISTENING (missing!)
```

### Step 2: Check gateway logs

```text
$ grep 'api_server' ~/.hermes/logs/gateway.log | tail -10

2026-06-09 22:46:56,094 ERROR gateway.platforms.api_server:
  [Api_Server] Refusing to start: API_SERVER_KEY is required for the
  API server, including loopback-only binds on 0.0.0.0.

2026-06-09 22:46:56,100 INFO gateway.run:
  Reconnect api_server failed, next retry in 300s
```

The gateway retries every 300s (5 min) — by the time we checked, it was on attempt 208.

### Step 3: Check .env for the required variable

```text
$ grep 'API_SERVER_KEY\|DASHBOARD_SESSION' ~/.hermes/.env
HERMES_DASHBOARD_SESSION_TOKEN=ks_CD3...i67I
```

The token existed but under `HERMES_DASHBOARD_SESSION_TOKEN`, not `API_SERVER_KEY`. The API server component reads only `API_SERVER_KEY`.

## The Fix

```bash
# 1. Add the alias (same value)
echo 'API_SERVER_KEY=<full-token-value>' >> ~/.hermes/.env

# 2. Restart the gateway
systemctl --user restart hermes-gateway

# 3. Verify
sleep 5 && ss -tlnp | grep 8642
# -> LISTEN 0 128 0.0.0.0:8642

# 4. Confirm in logs
grep 'api_server listening' ~/.hermes/logs/gateway.log
# -> [Api_Server] API server listening on http://0.0.0.0:8642
```

### Critical Pitfall: Obfuscated grep output

`grep` output in Hermes terminal sessions may obfuscate confidential values with `...` (e.g. `ks_CD3aYR...Ci67I` from `grep HERMES_DASHBOARD_SESSION_TOKEN ~/.hermes/.env`). If you append this literally — `echo "API_SERVER_KEY=ks_CD3...i67I"` — the file gets the *literal* `...` characters, not the real token. The API server will then reject requests with `Invalid API key`.

**Always** read the actual value from the file via `grep` and copy it directly rather than relying on screen-displayed snippets. Or use `sed` to rewrite the line in-place from a known-correct extract:

```bash
TOKEN=$(grep '^HERMES_DASHBOARD_SESSION_TOKEN=' ~/.hermes/.env | cut -d= -f2-)
sed -i "s/^API_SERVER_KEY=.*$/API_SERVER_KEY=$TOKEN/" ~/.hermes/.env
```

### Verification: Test the API server with auth

```bash
# Test models endpoint
API_KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env | cut -d= -f2-)
curl -s -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8642/v1/models

# Expected response:
# {"object":"list","data":[{"id":"hermes-agent",...}]}

# Test chat completion
curl -s -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"hi"}],"max_tokens":10}' \
  http://127.0.0.1:8642/v1/chat/completions

# Expected: returns a valid chat completion with usage stats
```

## Component Map

| Component | Port | Env Var | Status |
|-----------|------|---------|--------|
| Gateway (core) | - | - | systemd service |
| Dashboard (extended APIs) | 9119 | - | Separate process |
| API Server (chat, sessions) | 8642 | `API_SERVER_KEY` | Refuses start without key |
| Open WebUI | 8088 | - | Docker/standalone |

The dashboard (:9119) and API server (:8642) are separate concerns. The dashboard provides `/api/sessions`, `/api/skills`, etc. The API server serves `/v1/chat/completions` and session endpoints that the remote desktop client connects to. Both must be running for the remote desktop to work fully.

## Important: Remote Desktop Connects to Port 9119 (Dashboard)

**Confirmed in session (2026-06-09):** When the user says the remote desktop "is connected to 9119", it means the workspace web UI is pointed at the dashboard port. The workspace probes `http://127.0.0.1:9119/api/status` on startup to detect it. This is expected.

However, the dashboard at :9119 does **not** serve chat endpoints:
- No `/v1/chat/completions` (that's on :8642 via the API server)
- No POST `/api/sessions` for creation (only GET for listing)
- Session creation happens implicitly via `/v1/chat/completions` on :8642

**If the API server (:8642) is down**, clicking "start session" in the workspace will fail. The UI shows dashboard functions (sessions list, config, skills) but session creation returns an error (often a flash 400/401 the UI doesn't display long enough to read).

**Diagnosis technique for flash errors** on the remote desktop:

```bash
# 1. Enable DEBUG logging to capture request details
hermes config set logging.level DEBUG
systemctl --user restart hermes-gateway

# 2. Reproduce the error, then check:
grep -i '400\|error\|rejected\|invalid' ~/.hermes/logs/gateway.log | tail -20
journalctl --user -u hermes-gateway --since "1 min ago" --no-pager | grep -i 'error\|rejected\|invalid\|400'

# 3. Revert when done:
hermes config set logging.level INFO
systemctl --user restart hermes-gateway
```

## Dashboard Auth Inconsistency

The dashboard's `/api/status` returns `auth_required: false`, suggesting open access. However, `/api/sessions` and other `/api/*` endpoints return `401 Unauthorized` when called without a Bearer token. The auth header expected is `Authorization: Bearer <API_SERVER_KEY>`.

**Diagnostic:** Use the OpenAPI schema to discover available endpoints:

```bash
curl -s http://127.0.0.1:9119/openapi.json | python3 -m json.tool
```

## Model Picker Limitation

The API server's `/v1/models` endpoint returns only a single model: `hermes-agent` — the gateway's currently active model. It does **not** proxy to or enumerate the downstream llama.cpp router's model list (even though the Hermes provider uses `base_url: http://localhost:8079/v1` which points to the router).

This means the remote desktop's model picker will never show your local router models (qwen36-27b, devstral-24b, etc.). It only reflects what Hermes itself is currently configured to use.

**Impact:** The remote desktop picks whatever model the gateway is set to. If you need a specific model on remote, change the gateway provider/model on the server side first, then connect.

## Debug Logging for Transient Errors

**Symptom:** The remote desktop shows a brief error flash (e.g. Error 400) that disappears too fast to read, and the gateway log at INFO level shows nothing useful.

**Diagnostic method:** Toggle the gateway to DEBUG logging to capture individual API request details:

```bash
hermes config set logging.level DEBUG
systemctl --user restart hermes-gateway
```

Then reproduce the error on the remote desktop and check:

```bash
# Check gateway log for 400s, rejections, etc.
grep -i '400\|error\|rejected\|invalid\|bad request' ~/.hermes/logs/gateway.log | tail -20

# Also check journalctl for things that may not hit the log file
journalctl --user -u hermes-gateway --since "5 min ago" --no-pager | grep -i 'error\|rejected\|invalid\|400'
```

After debugging, revert logging to INFO:

```bash
hermes config set logging.level INFO
systemctl --user restart hermes-gateway
```

The DEBUG level logs every API request with method, path, and status — useful for catching errors the remote desktop UI swallows.

### Common 400 Causes

If the API key is wrong (e.g. from the obfuscated grep pitfall above), the response is `{"error":{"message":"Invalid API key","type":"invalid_request_error","code":"invalid_api_key"}}` — a 401, not 400, but the remote desktop may render it generically. Check the auth header the remote desktop is sending matches `API_SERVER_KEY` in `.env` exactly.
