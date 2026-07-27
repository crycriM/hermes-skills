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
| `qwen35-9b` | ❌ off | 65k | Fastest (~2-7s/API call, 95-100% cache) | ✅ **BEST** — handles full research/scraping jobs, never hits proxy timeout |
| `qwen36-27b` | ❌ off | 131k | Fast (~10-40s/API call) | ⚠️ Use for low-context tasks only — hits proxy 502 at ~60k ctx |
| `qwen36-35b` | ⚠️ auto | 131k | Slow | ❌ Avoid — thinking hangs compression and auxiliary calls |
| `qwen36-35b-crown` | ❌ off | 131k | Fast | ✅ Good but must be loaded separately |

**qwen35-9b is now the go-to for automated jobs.** It successfully ran the full Paris music research pipeline (browser scraping 6+ websites, jina_reader extraction, web search, report generation) in 22 API calls with context peaking at 50k — well under the 65k limit. No timeouts, no compression needed, no thinking-mode hangs. The 9B model is fast enough that cache hits stay at 95-100%, keeping latency under 10 seconds per call.

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

**Mitigation:** Use `qwen35-9b` (65k ctx, fast) for all cron jobs. Its per-call latency is 2-7 seconds with 95-100% cache hits, keeping well under the proxy timeout even as context grows.

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

### Real-world monitoring example (qwen35-9b, successful run)

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
