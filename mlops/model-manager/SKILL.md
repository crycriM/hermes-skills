---
name: model-manager
description: HTTP proxy (port 8079) fronting llama.cpp router (port 8080) with auto-swap model management on Strix Halo APU.
tags: [llama-cpp, router, model-management, strix-halo, proxy]
---

# Model Manager Proxy

HTTP proxy at `~/llm-server/model_manager.py` on port 8079 that fronts the llama.cpp router on 8080. Intercepts chat/completion requests to auto-swap models as needed. Background polling keeps model state in sync with the router (catches external load/unload via web UI or direct API).

## Starting the proxy

```bash
python3 ~/llm-server/model_manager.py              # :8079, auto-swap ON
python3 ~/llm-server/model_manager.py --port 8090  # custom port
python3 ~/llm-server/model_manager.py --verbose    # debug logging
python3 ~/llm-server/model_manager.py --no-auto-swap  # passthrough only
python3 ~/llm-server/model_manager.py --poll-interval 30  # custom refresh rate
```

No external dependencies. Stdlib only (http.server, http.client, configparser).

## How it works

```
Client → proxy :8079 → router :8080
                │
                ├─ /v1/chat/completions  → intercept, ensure model loaded, auto-swap if needed, then proxy
                ├─ /v1/completions       → same
                ├─ /models/load|unload   → passthrough + trigger state refresh after 2s
                ├─ /v1/* (everything else) → transparent passthrough
                ├─ /proxy/status         → JSON: loaded models, memory, all model sizes
                └─ /health               → JSON: proxy + router health check
```

### Auto-swap flow

1. Chat/completion request arrives with `model: X`
2. Proxy checks if X is already loaded (fast path, no lock contention)
3. If not loaded: acquires swap lock (serialized — one swap at a time), unloads current model, polls memory until freed, loads X
4. Forwards the original request to router
5. If swap fails, returns 503 to client

### State management

- Background thread polls `GET /v1/models` every 10s (configurable)
- Model state is thread-safe (RLock for reads, Lock for swap serialization)
- External load/unload operations (via web UI or direct API) are detected on next poll cycle

## Key design decisions

1. **Unified memory**: Strix Halo APU has 128 GB unified memory. VRAM/GTT split is meaningless — use `/proc/meminfo` MemAvailable for all capacity checks.

2. **Swap safety**: 4 GB headroom check during swap wait loop. Memory polling retries up to 60s for large model unloads.

3. **Streaming support**: SSE/chunked responses from the router are forwarded in real time. The proxy re-encodes chunked transfer encoding correctly (http.Client decodes, proxy re-encodes).

4. **Serialized swaps**: Only one model swap at a time. Concurrent requests wait and re-check after the swap completes, avoiding redundant swaps.

5. **Connection handling**: ThreadingMixIn with `Connection: close` header. Each request gets its own thread and TCP connection to the router.

## Router API endpoints (passthrough)

- `GET /v1/models` — list models with status
- `POST /models/load` — load: `{"model": "name"}` → `{"success": true}`
- `POST /models/unload` — unload: `{"model": "name"}` → `{"success": true}`
- Router at `http://localhost:8080`

## Pitfalls

1. **Don't use VRAM/GTT for capacity checks on Strix Halo.** Use system memory (MemAvailable). Also: `/proc/meminfo` reports are unreliable on AMD APU — don't obsess over `free`/`MemAvailable` figures. Trust what llama.cpp reports (`llama_params_fit_impl: projected to use X MiB of device memory vs. Y MiB of free device memory`).

2. **Models > 96 GB spill to system RAM.** Works but slower.

3. **Only one model loaded at a time** (current router config). Swap unloads first, waits for memory, then loads.

4. **Router preset INI**: `~/llm-server/router-preset.ini` — model names are `[section]` headers. Parsed on startup for model paths and sizes.

5. **Multi-file GGUF**: Automatically detects shard patterns (`-00001-of-00004.gguf`) and sums all shards for total size. Shard 1 is often tiny (metadata-only header, ~8 MB) — this is normal, not corrupt.

6. **Streaming responses**: The proxy strips incoming `Accept-Encoding` (via `_forwardable_headers`) to avoid compressed responses from the router that would need decompression before re-chunking.

7. **Router caches INI at startup** — `models/load` does NOT re-read the INI file. If you change `router-preset.ini`, you must `systemctl --user restart m5-router` for changes to take effect.

8. **Large model loading (>90 GB) on 128 GB Strix Halo**: Must use `mmap = true` (NOT `no-mmap = true`). The Vulkan tensor preallocation with `no-mmap` tries to copy the entire model + KV cache upfront, which exceeds available memory and fails with `vk::CommandBuffer::end: ErrorOutOfHostMemory`. With mmap, only the working set is resident.

9. **10-second force-kill trap**: If a model load fails (zombie child), the router's `operator()` tries to stop the old instance before spawning the new one. If the old instance's cleanup takes >10s (likely for 100GB+ models), the router force-kills the NEW spawn instead. Fix: unload, wait 15-30s for full GPU memory cleanup, then load. Or restart the router service for a clean slate.

10. **Reduce ctx-size for huge models**: Models >100 GB with 128K ctx won't fit even with mmap. Reduce `ctx-size` to 32768 in the INI — this cuts KV cache allocation significantly. You can always raise it later if memory allows.

11. **Load sequence for large models**: unload → wait 15-30s → verify no zombie (`ps aux | grep llama-server`) → load → wait patiently (103 GB copy takes 2-3 min) → check journalctl for success.
