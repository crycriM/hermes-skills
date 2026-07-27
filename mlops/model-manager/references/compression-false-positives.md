# Compression false-positives: when "context exceeded" is a slot state, not a real overflow

## Symptoms

- Cron or short-lived task fails with `Context length exceeded: ~N tokens. Cannot compress further.`
- The session in `state.db` has `message_count=1` and `input_tokens=0`
- The estimated token count (e.g. 14,772) is just the prompt size, not accumulated history
- A parallel long-lived session (e.g. `bg-review`) is hammering the same model slot
- Retrying the same cron job 5-10 seconds later succeeds

## Root cause

The llama.cpp backend returns a generic `HTTP 500: Context size has been exceeded` error for at least three distinct conditions:

1. **Real overflow:** `prompt_tokens + max_tokens > n_ctx`
2. **Slot mid-recovery:** a prior partial request left the slot in a state where the next request can't acquire it cleanly
3. **Slot under contention:** a parallel request is in flight; the slot can't accept a new prompt until the current one finishes

Hermes' compression loop (`agent/conversation_loop.py` around line 3035) triggers on **any** "context exceeded" error and tries `_compress_context()`. For a 1-message session, `len(messages) < original_len` is never satisfied, so the loop exits with "Cannot compress further" — which is a **misleading message**: the session never had anything to compress, and the original error was a transient slot state.

## Reproduction (2026-06-16 10:03)

**Setup:**
- Strix Halo APU, model-manager proxy on `:8079` fronting llama.cpp router on `:8080`
- `qwen36-35b` loaded on port 42683, 4 slots, `n_ctx=131072`
- Two concurrent sessions hitting the proxy at the same second

**Timeline (extracted from `errors.log` and `journalctl _PID=$(pgrep -f model_manager.py)`):**

```
10:01:43  ERROR Proxy error: timed out
10:01:45  DEBUG Pipeline starting: 255 messages, 111581 tokens, model=qwen36-35b
10:01:46  INFO  ◈ qwen36-35b compression: 111581 → 49188 tokens (44% saved)
10:01:46  INFO  → qwen36-35b stream
10:03:33.638 WARNING [bg-review session] HTTP 500: Context size has been exceeded.   ← retry from bg-review fails
10:03:33.642 WARNING [cron session]        Context size has been exceeded.            ← cron's first request fails
10:03:33.815 ERROR  [cron session] Context length exceeded: 14,772 tokens. Cannot compress further.
10:03:33.824 ERROR  cron.scheduler: Job 'Error Scanner — Learn from mistakes' failed
10:03:38      DEBUG Pipeline starting: 255 messages, 111581 tokens, model=qwen36-35b   ← bg-review retry succeeds
```

**State.db session check:**

```sql
sqlite3 ~/.hermes/state.db "SELECT id, source, model, message_count, input_tokens FROM sessions WHERE id LIKE '%20260616_100333%'"
-- 20260616_100333_6d1c6b  src=cron  model=qwen36-35b  msgs=1  in_tok=0
```

The cron's session has **1 message and 0 input tokens** — the "14,772 tokens" reported in the error is just the prompt+system+tools estimate, not accumulated history.

**KV cache pressure check:**

```
journalctl _PID=$(pgrep -f model_manager.py) --since "10:01:00" --until "10:04:00" | grep "◈ qwen36-35b context:"
# 09:57:40 ◈ qwen36-35b context: 63005/131072 tokens (prompt_n=1448 cache_n=61449 predicted_n=108)
# 09:57:43 ◈ qwen36-35b context: 63190/131072 tokens (prompt_n=98 cache_n=63006 predicted_n=86)
# 09:57:55 ◈ qwen36-35b context: 63612/131072 tokens (prompt_n=53 cache_n=63189 predicted_n=370)
# ...
# 09:58:37 ◈ qwen36-35b context: 65471/131072 tokens (prompt_n=100 cache_n=64043 predicted_n=1328)
```

The bg-review was filling the slot with `cache_n=64,043` tokens from prompt-cache reuse — near the safety margin. The cron's request hit a slot during this pressure.

## Diagnosis recipe

When a session fails with "Cannot compress further" but the session has very few messages:

```bash
# 1. Check the session is actually fresh
sqlite3 ~/.hermes/state.db "SELECT id, source, model, message_count, input_tokens, started_at FROM sessions WHERE id LIKE '%<sid>%'"

# 2. Check the proxy journal for the failing timestamp
journalctl _PID=$(pgrep -f model_manager.py) --since "<1 min before failure>" --until "<1 min after>" --no-pager \
  | grep -E "Pipeline starting|◈|ERROR Proxy error|Compression"

# 3. Check if other sessions were hammering the same model
journalctl _PID=$(pgrep -f model_manager.py) --since "<ts>" --no-pager | grep -c "Pipeline starting"
# If count > 1 in the same second, you have parallel traffic

# 4. Check KV cache fill on the model
journalctl _PID=$(pgrep -f model_manager.py) --since "<ts>" | grep "◈ <model> context:"
```

If steps 1 and 2 confirm a fresh session with no compression attempt, and step 3 shows parallel traffic, **this is a slot-state issue, not a real overflow.** Just retry.

## Fixes

### Immediate: re-run the failed job

```bash
# Manual retry
hermes cron run <job-name>

# Or wait for next scheduled run if it's a recurring job
```

### Clearing stale state: restart model-manager

```bash
systemctl --user restart model-manager
# Wait for state refresh (10s poll cycle)
journalctl _PID=$(pgrep -f model_manager.py) --since "now" -f
```

This re-fetches the model list and re-establishes connections. Does not interrupt in-flight requests (the OS handles socket handoff during the brief restart window).

### Prevent: avoid running heavy sessions in the same minute as cron jobs

The `bg-review` thread runs continuously and is the primary cause of slot pressure. Options:
- Stagger cron jobs away from heavy manual sessions
- Lower the bg-review's `protect_recent` so it compresses more aggressively (frees slot pressure faster)
- Add cron retry logic in the prompt itself

### At the Hermes loop level (upstream fix, not in this skill's scope)

The compression loop should skip compression for `len(messages) <= 1` sessions since there's nothing to compress. The misleading "Cannot compress further" error masks the real underlying issue. Track this in the `hermes-agent` skill or upstream conversation_compression.py.

## Related references

- `model-manager` SKILL.md pitfall #17b (cross-reference)
- `cron-agent` SKILL.md — cron session constraints and error patterns
- `headroom-ai-integration` SKILL.md — the compression internals that run before the failure
- `references/cron-job-model-selection.md` — qwen35-9b vs qwen36-35b for cron (qwen36-35b is more prone to this because it's the heavy default model)
