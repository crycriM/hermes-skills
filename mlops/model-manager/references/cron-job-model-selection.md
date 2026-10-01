# Model Selection for Cron/Automated Jobs

## Core Pitfall: Thinking Mode Models Hang Automation

**qwen36-35b** with `chat-template-kwargs = {"preserve_thinking":false, "enable_thinking":true}` and `reasoning = auto` is **unusable for cron jobs**. The model generates reasoning tokens before producing any text output — even for system meta-operations like context compression. A compression call that should take 10 seconds instead burns thousands of reasoning tokens and hangs indefinitely.

**Symptom:** Context compression starts (`context compression started: ... tokens=~81,282 model=qwen36-35b`) but never finishes. No errors — just silence.

**Detection:**
```bash
# Test if thinking mode is active
curl -s --max-time 30 http://localhost:8079/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen36-35b","messages":[{"role":"user","content":"Say hello in one word"}],"max_tokens":10}'
# If reasoning_content appears and content is empty, thinking mode is active
```

## Recommended Models for Cron Jobs

| Model | Thinking | Context | Speed | Cron Fit |
|-------|----------|---------|-------|----------|
| `qwen36-35b` | on, capped by the proxy at 4096 reasoning tokens | 262k | moderate (MoE, 3B active) | ✅ the local lane on :8079 and the `load-on-startup` default — keep the thinking levers above in place |
| `qwen36-27b` | ❌ off | 131k | Fast (~10-40s/API call) | ⚠️ Use for low-context tasks only — hits proxy 502 at ~60k ctx |

**The small fast lane is gone.** `qwen35-9b` was removed from `router-preset.ini` on 2026-09-28 (backup: `backups/router-preset.ini.before-9b-removal-20260928-123000`). Its measured record while it existed — the Paris music research pipeline, 22 API calls, context peaking at 50k, 2-7 s per call at 95-100% cache, no compression and no proxy timeout — is the bar any replacement lane has to clear. Automated jobs on the local endpoint now run on `qwen36-35b`.

**qwen36-27b fails above ~60k context.** Real-world threshold confirmed: API call #9 succeeded at 61k ctx (10.5s latency), but API call #10 at similar context timed out 3 times (502 proxy timeout). The model-manager proxy cuts off the backend before llama-server finishes processing the large prompt. Use only for tasks that stay under 40k tokens.

## Proxy Timeout Problem

When context exceeds ~60k tokens, even non-thinking models can hit **proxy timeouts** on the model-manager (`:8079`). The backend llama-server takes >2 minutes to process the prompt, but the proxy returns HTTP 502 after a shorter timeout.

**Confirmed threshold with qwen36-27b:** API call at 61k ctx succeeded (10.5s), but the next call at similar context timed out 3 times consecutively. The failure is not deterministic — it depends on server load and prompt complexity. Safe limit: keep context under 40k tokens for 27B+ models.

**Symptom sequence:**
```
API call failed (attempt 1/3) HTTP 502: timed out
Retrying API call in 2.9s (attempt 1/3)
API call failed (attempt 2/3) HTTP 502: timed out
Retrying API call in 4.6s (attempt 2/3)
API call failed (attempt 3/3) HTTP 502: timed out
Fallback to custom/qwen36-35b  ← makes things WORSE (thinking mode)
```

**Mitigation:** keep automated jobs on `qwen36-35b` with the thinking cap in place, or on `qwen36-27b` for low-context work, and treat context as the other lever (stay under ~40k tokens for 27B-class lanes). A small, fast lane is what made 50k-context cron runs painless here; if that latency is needed again, add a section back to `router-preset.ini` instead of improvising on a heavy lane.

## Monitoring Cron Job Progress

The agent log in `~/.hermes/logs/agent.log` is the primary monitoring surface:

```bash
# Find session ID from cron scheduler start
grep "Running job 'Paris music research'" ~/.hermes/logs/agent.log
# → session=cron_bb1ed2d9c19a_20260608_194402

# Watch progress in real time
grep "cron_bb1ed2d9c19a_20260608_194402" ~/.hermes/logs/agent.log | tail -10

# Track API calls (context growth + cache hits)
grep "API call #" ~/.hermes/logs/agent.log | grep "<session_id>"

# Watch for compression events
grep "compression" ~/.hermes/logs/agent.log | grep "<session_id>"

# Check for errors
grep "<session_id>" ~/.hermes/logs/errors.log
```

**Key metrics to watch:**
- `in=<N>` / `cache=<N>/<total>` — context growth and cache efficiency
- `latency=<seconds>` — per-call time; >90s is warning
- `context compression started/done` — compression events
- `API call failed` — proxy/model timeouts

### Real-world monitoring example (historical: the retired qwen35-9b lane, successful run)

```bash
# Track the run from start to report generation
grep "cron_bb1ed2d9c19a_20260608_222903" ~/.hermes/logs/agent.log | grep -E "API call|write_file|search_web|parallel_read|browser_"
```

**Healthy run signature (22 API calls, 7 minutes):**
```
API call #1:  in=22631 out=92  latency=96.8s   # first call: opencode-go→custom fallback
API call #2:  in=23122 out=144 latency=9.0s  cache=98%
API call #3:  in=29657 out=148 latency=39.9s cache=78%
API call #4:  in=30768 out=172 latency=15.0s cache=97%
API call #9:  in=61034 out=94  latency=10.5s cache=99%
API call #18: in=45370 out=2858 latency=114.8s  # report generation (2858 output tokens)
API call #22: in=50614 out=133 latency=5.4s  cache=99%
```

**Unhealthy run signatures:**
- qwen36-35b (thinking): compression starts at 81k ctx, never finishes — no errors logged
- qwen36-27b (timeout): API calls succeed until ~61k ctx, then 3x 502 → fallback loop

## cronjob Provider Field Quirk

The `cronjob update` tool doesn't reliably accept `provider: "custom"` — it often reverts to `"opencode-go"`. The fallback chain (opencode-go → custom) still works if the `base_url` is set to `http://localhost:8079/v1`. Non-standard model names (like `qwen36-27b`) will fail on opencode-go but succeed on fallback to the local proxy. This adds ~90s to the first API call but subsequent calls use cached routing.
