---
name: compression-error-diagnosis
description: Diagnose Hermes context-length-exceeded errors by correlating proxy logs, session DB, and slot state. Trigger when a cron job or background thread fails with a Context length exceeded error and the actual session or token size is small.
version: 1.0.0
author: Hermes Agent
license: MIT
---

# Diagnosing Context length exceeded Errors

## When to use

A cron job or background thread fails with errors like:
```
ERROR agent.conversation_loop: Context length exceeded: 14,772 tokens. Cannot compress further.
ERROR cron.scheduler: Job 'X' failed: RuntimeError: Context length exceeded (14,772 tokens). Cannot compress further.
```

But the actual session/token size is small (the 14,772 is just `system_prompt + tools + prompt`). The failure is a **stale slot state** in the proxy, not a real overflow.

## Diagnosis steps

### 1. Locate the failing session in state.db

```python
import sqlite3
conn = sqlite3.connect('/home/cricri/.hermes/state.db')
conn.row_factory = sqlite3.Row
# Get the cron session (id pattern: YYYYMMDD_HHMMSS_*)
for r in conn.execute("SELECT id, source, model, message_count, input_tokens, started_at, end_reason FROM sessions WHERE id LIKE '%YYYYMMDD_HHMMSS%'"):
    print(dict(r))
```

Check `message_count` — if it's 1-2 and `input_tokens` is small, the failure is not a real context overflow.

### 2. Read system_prompt length

```python
r = conn.execute("SELECT system_prompt FROM sessions WHERE id = '...'").fetchone()
print('len:', len(r['system_prompt']), 'rough_tokens:', len(r['system_prompt'])//4)
```

If system_prompt is ~4-15K tokens, the cron prompt itself is not the problem.

### 3. Check proxy state

```bash
curl -s http://localhost:8079/health
curl -s http://localhost:8079/v1/models | python3 -c "import json,sys; d=json.load(sys.stdin); [print(m['id'], m.get('status',{}).get('value','?')) for m in d.get('data',[])]"
```

Look for `loaded` models and their port numbers. Then:

```bash
curl -s http://localhost:<port>/slots | python3 -c "import json,sys; [print(s) for s in json.load(sys.stdin) if isinstance(s, dict)]"
```

Verify `n_ctx` matches the preset (e.g., 131072 for `qwen36-35b`). If slots are stuck `is_processing: true`, that is the smoking gun.

### 4. Find the actual error in journalctl and agent.log

Proxy-level errors:
```bash
journalctl --user -u model-manager --since "YYYY-MM-DD HH:MM:SS" --until "YYYY-MM-DD HH:MM:SS" --no-pager | grep -E "Pipeline|stream|error|Context|context"
```

Hermes-side errors (compression pipeline, bg-review retries, fallback chain):
```bash
grep -E 'compress|summary|fallback|context_overflow|timed out' ~/.hermes/logs/agent.log | tail -30
```

Look for:
- "Pipeline starting: N messages, M tokens" — actual request size after headroom compression
- "-> <model> stream" — request forwarded
- "ERROR Proxy error: timed out" or "ERROR Proxy error" — actual proxy failure
- "Auxiliary compression: using openrouter (google/gemini-2.5-flash)" — compression routed to cloud (good)
- "context compression started ... messages=N tokens=~M" then "context compression done: messages=N->K" — check delta N-K; if tiny, compression didn't help
- Multiple "API call failed (attempt N/3) ... HTTP 502: timed out" — bg-review or main thread retrying against blown context, NOT compression itself

### 5. Check agent.log for compression delta (real overflow diagnosis)

When GPU is at 100% and compression seems slow, check whether compression actually *helped*:

```bash
grep -E 'context compression (started|done)' ~/.hermes/logs/agent.log | tail -10
```

Look for the message count delta: `messages=56->54` means only 2 messages were dropped. If `protect_last_n` (default 20) + `protect_first_n` (default 3) = 23 protected messages, and the session has large tool outputs in those protected messages, compression cannot reduce context enough. The GPU spike is from the main conversation thread and bg-review daemon retrying against the blown context, not from compression itself.

### 6. Common findings

| Symptom | Cause | Fix |
|---|---|---|
| Request fits in window but Context size has been exceeded | Stale slot state, concurrent bg-review | Restart model-manager.service |
| len(messages) < original_len returns False | Empty 1-message session | Add retry logic in cron prompt |
| Cron fails with error format mentioning 14K-50K tokens | Slot accounting error from concurrent requests | Retry transient errors in cron prompt |
| Compression done in seconds but GPU still 100%, context still exceeds | Compression dropped too few messages (e.g. 56→54); protected messages hold huge tool outputs | Lower `protect_last_n` from 20 to 10, `protect_first_n` from 3 to 1 in config |
| `~34K tokens` in compression log but real context is way larger | Token estimate in compression log is a rough heuristic, not actual | Trust the proxy's `Context size has been exceeded` error, not the log estimate |

## Quick fix

```bash
# Clear stale slot state
systemctl --user restart model-manager
sleep 3
curl -s http://localhost:8079/health
```

## Add resilience to the cron job prompt

Append this resilience section to any cron job that calls the proxy:

```
Resilience: if the first LLM call returns a transient error like 'Context size has been exceeded' or 'HTTP 500' on a small request (your context is well under 131K tokens), retry up to 2 times with a 10s sleep. The proxy at :8079 occasionally returns stale slot errors during concurrent load - they are transient, not real overflows.
```

## Pitfalls

- Do NOT trust the 14,772 token number in the error message — it is a rough estimate, not the actual size that caused overflow.
- Do NOT look at `input_tokens` in the sessions table for cron jobs — it is cumulative across the agent lifetime, not per-request.
- The bg-review daemon and cron jobs can hit the proxy simultaneously. The slot state can become inconsistent. Restarting model-manager.service is the canonical fix.
- system_prompt length is in the `sessions` table, not the `messages` table.
- **GPU at 100% during "slow compression" is usually NOT compression.** Check `agent.log` for the compression delta (messages N→K). If compression dropped only 2-5 messages in 4 seconds, the GPU spike is from the main thread and bg-review retrying against blown context. Compression used a cloud model (Gemini Flash), not the local GPU.
- **Default `protect_last_n: 20` + `protect_first_n: 3` = 23 messages protected from compression.** If those messages contain huge tool outputs, compression cannot reduce context enough. Lower to `protect_last_n: 10, protect_first_n: 1` for sessions with heavy tool usage.
- **Token estimates in compression logs (`~34K tokens`) are rough heuristics.** The real context may be 5-10x larger. Trust the proxy's "Context size has been exceeded" error, not the log estimate.
