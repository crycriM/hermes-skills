# Cron Job Debugging Reference

## Session: 2026-06-22 - Cron Delivery Failure (Plugin Registration)

### Issue Description
Cron job `bb1ed2d9c19a` "Paris music research" executed and produced output but failed on delivery:
```
delivery error: Discord plugin not registered or missing standalone_sender_fn
```

The job's `last_status` was `error` but it **did** run — the error was purely at delivery time.

### Root Cause
The cron job was created via the `medor` profile (`create_cron_job.py` passed `-p medor`) but runs under the **default** profile at execution time. The default profile had `discord-platform` in its `plugins.disabled` list and an empty `plugins.enabled: []`, so the Discord plugin was never registered in `platform_registry`. Without the plugin's `standalone_sender_fn` hook, cron delivery to Discord fails.

### Investigation Commands
```bash
# List all cron jobs with delivery status
hermes cron list
# or via the cronjob tool:
cronjob action=list

# Check if the platform plugin is registered
# Look at plugins.enabled and plugins.disabled in config.yaml
grep -A 70 '^plugins:' ~/.hermes/config.yaml

# Check if the env var is set
grep 'DISCORD_BOT_TOKEN' ~/.hermes/.env

# Verify the cron job's creation origin
cat ~/.hermes/scripts/paris-music-research/create_cron_job.py
# Look for -p <profile> to see which profile created it
```

### Applied Fix
```bash
# 1. Enable the platform plugin
hermes config set plugins.enabled '["discord-platform"]'

# But: hermes config set stores YAML arrays as strings, not lists.
# Verify the output — if it shows enabled: "'[\"discord-platform\"]'"
# (a quoted string instead of a YAML list), fix with Python:

python3 -c "
import yaml
with open('/home/cricri/.hermes/config.yaml') as f:
    cfg = yaml.safe_load(f)
cfg.setdefault('plugins', {})['enabled'] = ['discord-platform']
if 'discord-platform' in cfg.get('plugins', {}).get('disabled', []):
    cfg['plugins']['disabled'].remove('discord-platform')
with open('/home/cricri/.hermes/config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
"

# 2. Restart gateway to pick up plugin registration
systemctl --user restart hermes-gateway.service

# If restart hangs (distrobox/llama-server processes block shutdown):
systemctl --user kill --signal=SIGKILL hermes-gateway.service
# Then check it auto-restarts (systemd restart policy)
```

### Key Learnings
- Cron jobs inherit the **running profile's** plugin config at execution time, not the creating profile's config.
- A plugin can be in both `disabled` and `enabled` lists in different profile configs — check which profile the cron scheduler runs under.
- `plugins.enabled` takes precedence over `plugins.disabled` — removing from `disabled` is optional but avoids ambiguity.
- `DISCORD_BOT_TOKEN` in `.env` is necessary but NOT sufficient — the `discord-platform` plugin must be registered (enabled) for cron delivery to work.
- The platform plugin registration provides the `standalone_sender_fn` hook that cron uses for out-of-process delivery.
- `hermes config set` cannot properly handle YAML list values — always verify the output manually or use Python yaml library as a workaround.
- Gateway restart is required after plugin config changes; SIGKILL works when normal stop hangs on long-running children.
- Delivery errors and execution errors are separate failure modes — check `last_status` vs `last_delivery_error` in the cron job list.
- Cron jobs never share the `deliver` route with an active gateway session (they use `standalone_sender_fn`, not the adapter's live connection).

### See Also
- `hermes-agent` bundled skill (protected): docs on plugin management
- The plugin's `register()` function in `plugins/platforms/discord/adapter.py` defines the `standalone_sender_fn` hook

---

## Multi-Step Cron Scripts: Parallelize Long-Running Independent Steps

When a `no_agent` cron script runs multiple independent long-running steps under a fixed script timeout (Hermes caps no_agent scripts at 3600s), run the steps in parallel (`&` + `wait`) so total wall-time ≈ the slowest step, not the sum.

WHY: A serial run of N steps each taking T seconds can exceed the script timeout and drop the last steps entirely — even though the earlier steps' side effects already succeeded. The script times out with empty or partial stdout, so the cron output file shows nothing, but the first steps already completed their real work (e.g. API uploads). The failure is invisible in the output file and only apparent when checking the downstream system. The watchdog that checks the output file then fires a false "nothing happened" alert, because it greps the (empty) output rather than the real target.

Pattern:
- Launch each independent step with `&`, then `wait` for all of them.
- Give each step its own timestamped log file so partial output survives a timeout.
- Total wall-time then scales with the slowest step, not N × step.

Also: `uv run` does NOT source the project `.env` in the cron environment, so credential env vars (e.g. NUMERAI_PUBLIC_ID, NUMERAI_SECRET_KEY) are unset and uploads either fail silently or the script errors. Load them explicitly at the top of the script:
```bash
set -a
[ -f ./.env ] && . ./.env
set +a
```

Verify the parallel pattern before relying on it: the shell tool blocks `&` in foreground calls — run the test script with `background=true` and confirm every step emits its completion line before trusting the design.

---

## Session: 2026-05-06 - Cron Job Model Fallback Investigation

## Session: 2026-05-06 - Cron Job Model Fallback Investigation

### Issue Description
Cron job `bb1ed2d9c19a` "Paris music research" was failing to execute despite `cronjob run` returning success responses. The job was stuck in scheduled state with `last_run_at: null`.

### Root Cause
**Model Configuration Fallback**: The job was configured with:
```json
"model": "{'provider': 'custom', 'base_url': 'http://localhost:8079/v1', 'model': 'qwen36-35b'}"
```

But was falling back to the default provider:
```
Fallback activated: {'provider': 'custom', 'base_url': 'http://localhost:8079/v1', 'model': 'qwen36-35b'} → glm-4.5-air (zai)
```

### Investigation Commands
```bash
# Check if model is actually available
curl -s http://localhost:8079/v1/models | jq '.data[] | select(.id == "qwen36-35b")'

# Test model connectivity
curl -s http://localhost:8079/v1/chat/completions \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen36-35b", "messages": [{"role": "user", "content": "test"}]}'

# Check logs for fallback patterns
grep -A 5 -B 5 "Fallback activated" ~/.hermes/logs/agent.log
```

### Applied Fix
```bash
python3 -c "
import json
with open('/home/cricri/.hermes/cron/jobs.json', 'r') as f:
    data = json.load(f)
for job in data['jobs']:
    if job['id'] == 'bb1ed2d9c19a':
        job['model'] = \"{'provider': 'custom', 'base_url': 'http://localhost:8079/v1', 'model': 'qwen36-35b'}\"
        job['provider'] = None
        job['base_url'] = None
with open('/home/cricri/.hermes/cron/jobs.json', 'w') as f:
    json.dump(data, f, indent=2)
"
```

### Key Learnings
- Cron job API success ≠ actual execution
- Model configurations can fall back silently to default providers
- Always check logs for "Fallback activated" messages when cron jobs don't execute
- Direct model testing helps verify configuration
- Model configuration must be stored as string representation of Python dict, not just the model name

### Prevention
- Verify model availability before setting up cron jobs
- Test custom model configurations directly via API
- Monitor logs for fallback patterns during cron execution
- Use job-specific log traces: `grep -A 10 -B 5 "<job_id>" ~/.hermes/logs/agent.log`

---

## Session Debug: Dashboard Inactive Issue

### Issue
Cron job `bb1ed2d9c19a` "Paris music research" showed successful API response but didn't actually execute (`last_run_at: null`).

### Root Cause
Hermes dashboard service was inactive, which is required for cron job execution despite API responses indicating success.

### Debugging Steps

```bash
# 1. Initial Status Check
cronjob list  # Showed job in scheduled state with no execution

# 2. Dashboard Status
systemctl status --user hermes-dashboard
# Result: inactive (dead)

# 3. Process Check
ps aux | grep -i hermes

# 4. Port Conflict Resolution
lsof -i :9119
# Found: PID 740678 using port 9119
kill 740678  # Killed conflicting process

# 5. Dashboard Restart
hermes dashboard --host 0.0.0.0 --insecure &
```

### Key Learnings
1. **Dashboard Dependency**: Cron jobs cannot execute via API alone - require active dashboard service
2. **Port Conflicts**: Existing processes on port 9119 prevent dashboard startup
3. **Background Process**: Need to use `&` for dashboard but monitor with `ps aux`
4. **Timing**: Allow 2-3 seconds after dashboard start before cron execution