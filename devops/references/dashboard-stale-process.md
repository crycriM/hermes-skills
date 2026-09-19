# Stale Dashboard Process & OpenRouter Model Resolution

## Symptom

Remote desktop connects fine to port 9119, can browse sessions, but starting a new chat fails with a flash 400 error. The gateway log shows no errors. The dashboard journal shows:

```
⚠️  API call failed (attempt 1/3): BadRequestError [HTTP 400]
   🔌 Provider: custom  Model: qwen36-27b
   🌐 Endpoint: https://openrouter.ai/api/v1
   📝 Error: HTTP 400: qwen36-27b is not a valid model ID
   📋 Details: {'message': 'qwen36-27b is not a valid model ID', 'code': 400}
❌ Non-retryable client error (HTTP 400). Aborting.
```

The model `qwen36-27b` is a local GGUF model served by llama.cpp on :8080/proxy :8079, but the dashboard's TUI subprocess is routing it to OpenRouter.

## Root Cause

The dashboard process (separate PID from the gateway) was started at boot (~05:58) and ran for 17+ hours. When the desktop connects and initiates a chat, the dashboard spawns `hermes --tui` via PTY. That subprocess inherits a stale environment or model-resolution path that sends requests to OpenRouter despite `config.yaml` having:

```yaml
model:
  default: qwen36-27b
  provider: custom
  base_url: http://localhost:8079/v1
```

## Diagnosis

```bash
# 1. Check which process is on port 9119
ss -tlnp | grep 9119
# Shows PID and age

# 2. Check dashboard journal for the actual error (NOT gateway.log)
journalctl --user -u hermes-dashboard --since "5 min ago" --no-pager | grep -i '400\|error\|abort\|invalid\|retry'

# 3. The error shows the endpoint URL — if it says openrouter.ai for a local model,
#    the dashboard TUI has stale config resolution
```

## Fix

Kill the old dashboard process and restart it:

```bash
kill <dashboard-pid>
hermes dashboard --host 0.0.0.0 --no-open --insecure &
# or via systemd if a unit exists
```

After restart, verify the new dashboard is on :9119 and test from the remote desktop.

## Why This Happens

The dashboard process loads config at startup. When it spawns `hermes --tui` for the embedded Chat tab, the subprocess inherits the parent's config. Over long uptime, config reloads or environment changes (like restoring `API_SERVER_KEY`) don't propagate to the already-running dashboard. The TUI may also pick up a different model-resolution path from the cached provider setup.

The gateway (systemd unit) and dashboard process are independent — restarting the gateway does NOT restart the dashboard.

## Pitfall: systemd StartLimit Exhaustion — Service Dead for Days

The dashboard service file has:
```ini
StartLimitIntervalSec=600
StartLimitBurst=5
```

After 5 crashes within 10 minutes, systemd stops restarting the service entirely. The service shows `inactive (dead)` and stays dead until manually restarted — even if the root cause is fixed.

**Symptom:** `systemctl --user status hermes-dashboard` shows `inactive (dead) since <date>` with no recent restart attempts. The dashboard was working before, models are loaded, gateway is up.

**Diagnosis:**
```bash
# Check if StartLimit was exhausted
systemctl --user status hermes-dashboard | grep -i 'startlimit\|dead\|failed'

# Check if the service is in a "dead" state (not just "inactive")
systemctl --user is-active hermes-dashboard
# Returns "inactive" — but the real question is: is it dead-dead or just-not-started?
```

**Fix — two options:**

1. **Quick restart** (if service is enabled):
   ```bash
   systemctl --user restart hermes-dashboard
   ```

2. **Increase the limit** (if crashes keep happening):
   ```bash
   systemctl --user edit hermes-dashboard
   # Add:
   [Unit]
   StartLimitIntervalSec=0
   ```
   This disables the start limit entirely. Alternatively, increase `StartLimitBurst` to a higher number (e.g., `20`).

3. **Change Restart policy** (if the service crashes on every start):
   ```bash
   systemctl --user edit hermes-dashboard
   # Add:
   [Service]
   Restart=always
   RestartSec=10
   ```
   `Restart=on-failure` only restarts on non-zero exit codes. `Restart=always` restarts regardless.

**Prevention:** Monitor the dashboard journal for repeated errors. If you see the same error pattern (e.g., model resolution 400s) appearing every ~5 minutes, the service is in a crash loop. Fix the root cause, then restart.
