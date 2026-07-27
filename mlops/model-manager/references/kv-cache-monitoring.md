# KV Cache Occupancy Monitoring

Tracking how much of a model's context window is **actually in use** (tokens currently stored in the KV cache), as opposed to the configured maximum (`ctx-size` / `n_ctx`).

## What the HTTP API exposes

| Endpoint | Field | Meaning | Present? |
|----------|-------|---------|----------|
| `/slots?model=X` | `n_ctx` | Per-slot max context window | ✅ |
| `/slots?model=X` | `next_token[0].n_decoded` | Tokens generated so far in current request | ✅ |
| `/slots?model=X` | `next_token[0].n_remain` | Tokens remaining (max_tokens - n_decoded) | ✅ |
| `/slots?model=X` | `n_past` | Tokens currently in KV cache | ❌ |
| `/v1/models` | `meta.n_ctx` | Model's native training context | ✅ |

The critical gap: **`n_past` is not in the HTTP API**. The `/slots` response has no field for KV cache occupancy.

### Slot response shape (documented for reference)

```json
{
  "id": 0,
  "n_ctx": 65536,
  "speculative": true,
  "is_processing": false,
  "id_task": 221,
  "params": { /* full sampler params */ },
  "next_token": [{
    "has_next_token": false,
    "has_new_line": false,
    "n_remain": 1013,
    "n_decoded": 11
  }]
}
```

## Where n_past lives: the journal

The router (llama-server child processes) logs `n_past` during slot updates. These go to the systemd user journal under `m5-router.service`:

```bash
journalctl --user -u m5-router.service --since "5 min ago" --no-pager | grep "n_past"
```

### Log format

```
[34289] 197.20.592.754 W slot update_slots: id  0 | task 221 | n_past = 70, slot.prompt.tokens.size() = 119, seq_id = 0, pos_min = 118, n_swa = 0
```

Key fields:
- `id` — slot number (0-based per model child process)
- `task` — task ID
- `n_past` — **tokens currently in the KV cache for this slot** (the metric we want)
- `slot.prompt.tokens.size()` — total prompt tokens assigned to this slot
- `pos_min` — minimum position in the cache
- `n_swa` — sliding window attention offset (0 = full context)

### Other useful log lines for KV cache tracking

```
# Checkpoint creation shows cache segment sizes
slot create_check: id  0 | task 221 | created context checkpoint 1 of 32 (pos_min = 239, pos_max = 239, n_tokens = 240, size = 50.519 MiB)

# Slot release shows total tokens processed
slot      release: id  0 | task 221 | stop processing: n_tokens = 256, truncated = 0

# Prompt update shows per-prompt memory usage
srv        update:    - prompt 0x287d7be0:     261 tokens, checkpoints:  1,   103.376 MiB
srv        update:    - prompt 0x362bc840:     199 tokens, checkpoints:  1,   102.691 MiB
```

## Router logging architecture

The router (PID as seen by systemd) runs inside a distrobox container:

```
systemd m5-router.service
  └─ distrobox enter llama-vulkan-amdvlk -- start-native-router.sh
       └─ llama-server --host 0.0.0.0 --port 8080 --models-preset ... (router process)
            ├─ llama-server --port 34289 --alias qwen35-9b ... (child/worker)
            └─ llama-server --port 60475 --alias qwen36-35b ... (child/worker)
```

- **Router process** logs to `journalctl --user -u m5-router.service` (via distrobox stdout capture)
- **Child processes** (one per loaded model, on random ports) log to the SAME journal unit — they inherit the distrobox stdout
- PIDs in log lines (e.g. `[34289]`) refer to child transport IDs, not OS PIDs
- Querying by child OS PID (`sudo journalctl _PID=216795`) returns NOTHING — use the unit instead

## How the llama.cpp built-in GUI shows context usage\n\nThe llama.cpp web UI (served by the router on :8080) displays `Context: X/Y (Z%)` during active generation. This is NOT pulled from a polling endpoint — it's computed client-side from the SSE `timings` object in the final chunk of each streaming completion.\n\n### Data flow\n\n```\nSSE stream → final chunk with \"timings\" field\n    ↓ client-side parseTimingData()\ncontextUsed = prompt_n + cache_n + predicted_n\ncontextTotal = n_ctx (from the slot)\n    ↓\nGUI displays: \"Context: 57/65536 (0.1%)\"\n```\n\n### Source: bundle.js reverse-engineering\n\nTraced from the Svelte bundle at `http://localhost:8080/bundle.js`:\n\n```javascript\nparseTimingData(e) {\n    const r = e.prompt_n || 0,        // tokens in prompt\n          a = e.predicted_n || 0,      // tokens generated so far\n          s = e.cache_n || 0,          // cache hits (prompt tokens already in KV)\n          l = this.getContextTotal(),  // n_ctx from slot config\n          d = r + s + a;              // contextUsed = sum of all three\n    return {\n        contextUsed: d,     // prompt_n + cache_n + predicted_n\n        contextTotal: l,    // n_ctx\n        ...\n    }\n}\n```\n\nThe `timings` object appears in the **final SSE chunk** (the one with `finish_reason` or `[DONE]`):\n\n```json\n{\n  \"choices\": [{\"finish_reason\": \"length\", ...}],\n  \"timings\": {\n    \"cache_n\": 0,\n    \"prompt_n\": 13,\n    \"prompt_ms\": 101.571,\n    \"predicted_n\": 5,\n    \"predicted_ms\": 86.909,\n    \"draft_n\": 2,\n    \"draft_n_accepted\": 2\n  }\n}\n```\n\n### Key insight for model_manager proxy\n\nThe proxy forwards every streaming completion and sees every `timings` object. It could extract `prompt_n + cache_n + predicted_n` from the final chunk and expose it in `/api/models` as `context_used` per model, without touching the journal. The limitation: this only updates DURING active generation — between requests, the value goes stale (slots may retain their KV cache between tasks with `n_past > 0`).\n\n### Relationship to n_past\n\n`prompt_n + cache_n + predicted_n` at the END of a request approximates `n_past` at that moment. But `n_past` can persist between requests (slots retain cache for reuse), while the SSE timings only report the final state of one request. For idle-period accuracy, the journal's `n_past` log lines remain the only source.\n\n## Options for surfacing KV cache usage

### 1. Journal parsing (quick, fragile)
Parse `journalctl --user -u m5-router.service` output for the latest `n_past` per slot. Map child port → model name via `ss -tlnp` or known port list. Expose in `/api/models` or a new endpoint.

**Downsides:** Log format could change across llama.cpp versions. No real-time guarantee (slot updates log only on state changes). Must run as the user (journalctl permissions).

### 2. Proxy-side tracking (medium effort)
The model_manager proxy sees every request. After forwarding, it knows how many prompt tokens were sent. With slot tracking, it could estimate per-model cache fullness.

**Downsides:** Multi-slot reuse complicates tracking. Can't see cache eviction from other slots. Proxy doesn't see prompt re-processing events.

### 3. Upstream llama.cpp patch (cleanest, long-term)
Add `n_past` to the `/slots` JSON response. The data is already in memory — just needs serialization. A small C++ patch to `server.cpp`.

**Upside:** No fragile log parsing. Real-time. Survives version upgrades if merged.

### 4. llama.cpp metrics endpoint
The `--metrics` flag is enabled but the `/metrics` endpoint requires a model name parameter and returns 400 without it. Even with a model, it returns sampler metrics, not slot/KV cache stats. Not useful for this purpose.
