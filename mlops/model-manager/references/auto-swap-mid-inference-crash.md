# Auto-Swap Mid-Inference Crash — July 9, 2026

## Incident summary

**Models involved:** step37 (97.3 GB), qwen36-35b (35.9 GB)
**Client:** KiloCode 7.4.1 (Bun runtime), request with 4600B system + 1655B user, max_tokens=32000
**Total RAM:** 124.5 GB (Strix Halo APU unified memory)
**Result:** Model-manager crashed after 22s of retry cycling

## Timeline

| Time | Source | Event |
|------|--------|-------|
| 08:45:55 | Model-manager | `Unloading ['step37'] to fit qwen36-35b (keepers: [], est total 35.9/124.5 GB)` |
| 08:45:55 | Router | KiloCode request being proxied to step37 (timestamp confirms active inference) |
| 08:45:59 | Model-manager | `ERROR Failed to load qwen36-35b: {'error': {'code': 400, 'message': 'model is already running'}}` |
| 08:46:02 | Model-manager | `Keeping 0 loaded model(s) + step37 (est total 97.3/124.5 GB)` then load attempt → same error |
| 08:46:03 | Model-manager | `Keeping 0 loaded model(s) + qwen36-35b (est total 35.9/124.5 GB)` then load attempt → same error |
| 08:46:10 | Model-manager | Load step37 → same error |
| 08:46:17 | Model-manager | Service exit (crash) |
| 08:49:46 | systemd | Auto-restart of model-manager.service |

## Full log excerpts

### Model-manager journal (crash window)

```
Jul 09 08:44:07 State refreshed: loaded=[step37]
Jul 09 08:44:07 Slot staleness check step37: shadow count 2/6 (idle 10s)
... (stable for 1.5 minutes) ...
Jul 09 08:45:55 Unloading ['step37'] to fit qwen36-35b (keepers: [], est total 35.9/124.5 GB)
Jul 09 08:45:55 → step37 stream  client=Kilo-Code/7.4.1  sys=4601B  user=1655B  kwargs={"model": "step37", "max_tokens": 32000, ...}
Jul 09 08:45:59 State refreshed: loaded=[none]
Jul 09 08:45:59 Keeping 0 loaded model(s) + qwen36-35b (est total 35.9/124.5 GB)
Jul 09 08:45:59 Loading qwen36-35b (~35.9 GB VRAM incl. cache)...
Jul 09 08:45:59 ERROR Failed to load qwen36-35b: {'error': {'code': 400, 'message': 'model is already running'}}
Jul 09 08:46:01 State refreshed: loaded=[none]
Jul 09 08:46:02 Keeping 0 loaded model(s) + step37 (est total 97.3/124.5 GB)
Jul 09 08:46:02 Loading step37 (~97.3 GB VRAM incl. cache)...
Jul 09 08:46:02 ERROR Failed to load step37: {'error': {'code': 400, 'message': 'model is already running'}}
Jul 09 08:46:03 State refreshed: loaded=[none]
Jul 09 08:46:03 Keeping 0 loaded model(s) + qwen36-35b (est total 35.9/124.5 GB)
Jul 09 08:46:03 Loading qwen36-35b (~35.9 GB VRAM incl. cache)...
Jul 09 08:46:03 ERROR Failed to load qwen36-35b: {'error': {'code': 400, 'message': 'model is already running'}}
Jul 09 08:46:07 State refreshed: loaded=[none]
Jul 09 08:46:10 State refreshed: loaded=[none]
Jul 09 08:46:10 Keeping 0 loaded model(s) + step37 (est total 97.3/124.5 GB)
Jul 09 08:46:10 Loading step37 (~97.3 GB VRAM incl. cache)...
Jul 09 08:46:10 ERROR Failed to load step37: {'error': {'code': 400, 'message': 'model is already running'}}
Jul 09 08:46:17 State refreshed: loaded=[none]
-- Boot e826eb8dc4a94ef9a39c2ae04a1e771a --
Jul 09 08:49:46 Started model-manager.service
```

### KiloCode request (from model-manager request log just before crash)

```
→ step37 stream  client=Kilo-Code/7.4.1 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14
  sys=4601B  user=1655B
  kwargs={"model": "step37", "max_tokens": 32000,
    "tools": [{"type": "function", "function": {"name": "bash", ...}},
              {"type": "function", "function": {"name": "edit", ...}},
              {"type": "function", "function": {"name": "glob", ...}},
              {"type": "function", "function": {"name": "grep", ...}},
              {"type": "function", "function": {"name": "read", ...}},
              {"type": "function", "function": {"name": "write", ...}},
              ...]}
```

The request had `max_tokens=32000` and a full set of tool schemas (~8 tools). The model-manager logged the request at **the same second** (08:45:55) as the `Unloading ['step37']` line — confirming the swap triggered while the request was mid-proxy.

### Router journal (subsequent boot)

The router itself didn't crash — it continued operating normally. After the model-manager exited, the router still showed no loaded models. At the next boot (08:49:54), all four models loaded cleanly:

```
Jul 09 08:49:54 Router starting: listening on http://0.0.0.0:8080
Jul 09 08:49:54 Loading qwen36-35b, qwen35-9b, llama3-8b, qwen36-27b
Jul 09 08:51:06 All four models loaded and ready
```

## Root cause analysis

### What triggered the auto-swap?

The `ensure_loaded("qwen36-35b")` was called — it does NOT fire spontaneously from a "preferred model list." The trigger was an explicit load request for qwen36-35b (via model-manager GUI load button, a client request, or an API call). **There is no "default model list" that the model-manager auto-loads from.** The `model-manager-config.yaml` contains only per-model **reasoning tuning parameters** (`max_reasoning_tokens`, `logit_bias_strength`, `target_thinking_tokens`) — it is NOT a load-on-startup or preferred-model list.

### Why did the swap execute despite an active request?

The `ensure_loaded()` algorithm has three bugs:

**Bug 1 — No active-slot check before unload (Critical):** Never queries `GET /slots?model=step37` for `is_processing: true`. A model with active inference should never be unloaded.

**Bug 2 — No "does target alone fit in free memory?" pre-check:** The algorithm starts from `currently_loaded` and packs `keepers + target + 6 GB headroom` within `total_mem`. It never asks "does the target alone fit in the available free memory without unloading anything?"

**Bug 3 — No retry backoff (fatal exhaust):** After `400: model is already running`, retries are immediate (~1s), cycling between two models both stuck in teardown. No exponential backoff.

### The swap was unnecessary

step37 at 97.3 GB fits comfortably on 124.5 GB total. The swap was triggered by a NEW load request for qwen36-35b (not a background preference). Correct behavior: either reject ("35.9 GB does not fit in 27 GB free") or load alongside if headroom permits.

### Design principle: model-manager-config.yaml is NOT a load list

The user's explicit design: **the only default models are the ones loaded at startup via `load-on-startup = 1` in `router-preset.ini`**. The `model-manager-config.yaml` exists solely for per-model tuning parameters. It must never be interpreted as a load-on-startup list, preferred-model ranking, or "should be loaded" target list.

Auto-swap in `ensure_loaded()` responds only to:
1. **Explicit client requests** — a chat completion/tokenize targeting a model not currently loaded
2. **GUI-driven loads** — the user clicking "load" in the model-manager dashboard

It never proactively loads models at startup or on poll cycles. No "primary model" concept exists or should be added.

### The retry death spiral

After the first `"model is already running"` error, the model-manager:
1. Does a state refresh (`loaded=[none]`)
2. Tries the other model
3. Gets the same error
4. No delay between attempts
5. Repeats indefinitely until crash

A proper fix would add:
- **Active slot check**: query `/slots?model=<name>` before any unload, skip if inference active
- **Memory headroom pre-check**: if current model + target fits, don't unload
- **Exponential backoff**: 1s/2s/4s/8s/16s/30s max after "model is already running" errors
- **Load alongside**: when headroom exists, load the target without unloading the current model
