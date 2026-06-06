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
python3 ~/llm-server/model_manager.py --verbose    # debug logging (recommended: always use this)
python3 ~/llm-server/model_manager.py --no-auto-swap  # passthrough only
python3 ~/llm-server/model_manager.py --poll-interval 30  # custom refresh rate
```

The systemd service (`~/.config/systemd/user/model-manager.service`) now runs with `--verbose` by default. This is required for debugging logit bias application and reasoning enforcement — without it, the most important proxy-level logic is invisible in logs.

No external dependencies. Stdlib only (http.server, http.client, configparser).

## How it works

```
Client → proxy :8079 → router :8080
                │
                ├─ /v1/chat/completions  → intercept, ensure model loaded, auto-swap if needed, then proxy
                ├─ /v1/completions       → same
                ├─ /tokenize             → intercept, ensure model loaded via ensure_loaded (memory-safe swap), then proxy
                ├─ /models/load          → route through ensure_loaded (unloads others first)
                ├─ /models/unload        → passthrough + trigger state refresh
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
- **Known model list is initialized at startup** from the router's response and refreshed every poll, but new `[section]` entries added to `router-preset.ini` are NOT discovered at runtime — only load/unload *status* of already-known models syncs. After adding a new model to the INI, `systemctl --user restart model-manager` is required before the proxy will serve it.

## Key design decisions

1. **Unified memory**: Strix Halo APU has 128 GB unified memory. VRAM/GTT split is meaningless — use `/proc/meminfo` MemAvailable for all capacity checks.

2. **Swap safety**: 4 GB headroom check during swap wait loop. Memory polling retries up to 60s for large model unloads.

3. **Streaming support**: SSE/chunked responses from the router are forwarded in real time. The proxy re-encodes chunked transfer encoding correctly (http.Client decodes, proxy re-encodes). **CRLF must be real bytes** (`\r\n`), not escaped strings (`\\r\\n`). The terminal `0\r\n\r\n` zero-length chunk is required — without it, httpx/OpenAI SDK hangs waiting for more data and throws `APIConnectionError: Connection error.` / `RemoteProtocolError: peer unexpectedly closed connection`.

4. **Serialized swaps**: Only one model swap at a time. Concurrent requests wait and re-check after the swap completes, avoiding redundant swaps.

5. **Connection handling**: ThreadingMixIn with `Connection: close` header. Each request gets its own thread and TCP connection to the router.

## Model Manager API (proxy layer)

The model_manager.py proxy exposes its own load/unload API that handles memory-safe model swapping:

```bash
# Load a model (POST /api/load — memory-safe swap, waits for VRAM cleanup)
curl -s -X POST http://localhost:8079/api/load \
  -H 'Content-Type: application/json' \
  -d '{"model": "model-name"}'
# → {"success": true}  or  {"error": {"message": "...", "code": 404}}

# Unload a model
curl -s -X POST http://localhost:8079/api/unload \
  -H 'Content-Type: application/json' \
  -d '{"model": "model-name"}'
# → {"success": true}

# Check loaded models
curl -s http://localhost:8079/proxy/status | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('Loaded:', d.get('loaded',[]))"
```

**Endpoint summary:**
| Endpoint | Target | Purpose |
|---|---|---|
| `POST /api/load` | model_manager | Memory-safe model load (unloads others first, polls VRAM) |
| `POST /api/unload` | model_manager | Unload specific model |
| `POST /models/load` | router :8080 | Raw router load (no memory guard) |
| `GET /proxy/status` | model_manager | JSON state: loaded models, memory, all model sizes |

**Key insight:** Always use `POST /api/load` on the proxy (8079) for memory-safe swapping. Direct router `/models/load` (8080) bypasses the memory guard and can cause OOM.

## Model Manager GUI (`gui_server.py` + `gui/`)

A standalone HTTP server (port 8081) that serves a web UI for the model manager. Managed by `model-manager-gui.service`.

### Architecture

```
Browser → gui_server.py :8081 → proxies /api/* → model_manager.py :8079 → router :8080
```

The GUI server (`~/llm-server/gui_server.py`) is a stdlib-only ThreadingMixIn HTTP server. It serves static files from `~/llm-server/gui/` and proxies `/api/*` paths directly to model_manager at :8079. Static files are served on all other paths.

### GUI frontend (`gui/index.html`)

Single-page vanilla JS dashboard. Auto-refreshes every 5 seconds. Fetches two API endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/gpu` | GPU metrics (utilization, temperature, power, VRAM/GTT, fans, power mode) |
| `GET /api/models` | Full model list with status, context size, cache type, loaded state, and inference activity |

### Inference activity indicator

The `/api/models` response includes an `inference_active: bool` field per model, set to `true` when the model has at least one router slot with `is_processing: true` (actively decoding tokens). The GUI renders a pulsing green dot (`.inference-dot`) next to the model name when active.

Implementation in `model_manager.py`:
- `get_active_inference()` queries `GET /slots?model=<name>` for each loaded model via the router
- Called inside `_handle_api_models()` on every refresh
- Only loaded models can show as active; unloaded models always return `false`

### Service management

```bash
systemctl --user start model-manager-gui       # port 8081
systemctl --user restart model-manager          # restarts model_manager.py on 8079
```

Restart model-manager (not model-manager-gui) when changing `model_manager.py`. Only model-manager-gui needs restart when editing files in `gui/`.

## Router API endpoints (passthrough)

- `GET /v1/models` — list models with status (`loaded`/`unloaded`/`loading`/`error`), preset args, architecture
- `GET /slots?model=<name>` — per-slot state for a loaded model. Each slot has:
  - `is_processing` (bool) — true when actively decoding tokens (running inference)
  - `id_task` — task identifier
  - `next_token` — array with `n_remain` and `n_decoded` token counts
  - `params` — full sampler/request parameters
  - Use this to detect which models are actively running inference without GPU polling
- `POST /models/load` — load: `{"model": "name"}` → `{"success": true}`
- `POST /models/unload` — unload: `{"model": "name"}` → `{"success": true}`
- `GET /health` — `{"status": "ok"}`
- Node at `http://localhost:8080`

## Router startup config (`start-native-router.sh`)

```bash
exec /usr/sbin/llama-server \
    --host 0.0.0.0 \
    --port 8080 \
    --models-preset "$PRESET_FILE" \
    --models-max 3 \
    --no-models-autoload \
    --reasoning off
```

The startup script validates the preset INI against known llama.cpp options before launching. If an unknown key is found, it refuses to start (prevents the crash-loop that happens when llama.cpp rejects unknown preset keys).

### Key flags

- `--models-max 3`: Maximum 3 concurrent models. Lower from 4 to prevent VRAM exhaustion.
- `--no-models-autoload`: **Essential.** Without this, any request mentioning a model name triggers auto-loading. The router would stack models until OOM.
- `--reasoning off`: Disables thinking mode globally at the router level.

## Pitfalls

1. **Don't use VRAM/GTT for capacity checks on Strix Halo.** Use system memory (MemAvailable). Also: `/proc/meminfo` reports are unreliable on AMD APU — don't obsess over `free`/`MemAvailable` figures. Trust what llama.cpp reports (`llama_params_fit_impl: projected to use X MiB of device memory vs. Y MiB of free device memory`).

2. **Models > 96 GB spill to system RAM.** Works but slower.

3. **`--no-models-autoload` is critical.** Without it, the router auto-loads models on ANY request that specifies a model name (including `/tokenize`), leading to multiple models loaded simultaneously and VRAM exhaustion crashes. With `--models-max 3` and `--no-models-autoload`, the gateway has full control — models only load via explicit `/models/load` through the gateway's `ensure_loaded` path.

**Effect of `--no-models-autoload`:** All models return HTTP 404 on the raw router (port 8080) until explicitly loaded. Benchmarking against `:8080` directly fails unless models are pre-loaded. Always benchmark against the model-manager proxy (port 8079) which handles loading automatically, or pre-load via `POST /api/load`.

4. **Router preset INI**: `~/llm-server/router-preset.ini` — model names are `[section]` headers. Parsed on startup for model paths and sizes.

5. **Multi-file GGUF**: Automatically detects shard patterns (`-00001-of-00004.gguf`) and sums all shards for total size. Shard 1 is often tiny (metadata-only header, ~8 MB) — this is normal, not corrupt.

6. **Streaming responses**: The proxy strips incoming `Accept-Encoding` (via `_forwardable_headers`) to avoid compressed responses from the router that would need decompression before re-chunking.

7. **Router caches INI at startup** — `models/load` does NOT re-read the INI file. If you change `router-preset.ini`, you must `systemctl --user restart m5-router` for changes to take effect.

8. **Large model loading (>90 GB) on 128 GB Strix Halo**: Must use `mmap = true` (NOT `no-mmap = true`). The Vulkan tensor preallocation with `no-mmap` tries to copy the entire model + KV cache upfront, which exceeds available memory and fails with `vk::CommandBuffer::end: ErrorOutOfHostMemory`. With mmap, only the working set is resident.

9. **10-second force-kill trap**: If a model load fails (zombie child), the router operator() tries to stop the old instance before spawning the new one. If the old instance's cleanup takes >10s (likely for 100GB+ models), the router force-kills the NEW spawn instead. Fix: unload, wait 15-30s for full GPU memory cleanup, then load. Or restart the router service for a clean slate.

10. **Match ctx-size to the actual workload, not the model's native context**: ctx-size drives KV cache allocation linearly. For a dense 9B model with Q4 KV cache (`cache-type-k/v = q4_0`), each token costs roughly `layers x hidden_dim x 2 (K+V) x 0.5 bytes`. At 40 layers x 4096 hidden_dim: ~164 KB per token. Setting ctx-size 262144 allocates ~43 GB of KV cache slots — overkill for auxiliary/compression models that at most process a 64K threshold's worth of input. This wastes memory bandwidth and slows prefill across the whole 128 GB unified memory pool.

    **For auxiliary/compression models specifically**: the compression threshold (`compression.threshold` in config.yaml) sets how many tokens trigger a compaction. The aux model only needs enough ctx to hold that threshold's worth of serialized messages plus the summarization instruction. Sizing ctx-size at 65536 or 98304 is usually sufficient; 262144 is wasteful.

    **KV cache formula**: `layers x hidden_dim x 2 x bytes_per_element x ctx_size`. bytes_per_element: 0.5 for Q4_0, 1 for Q8_0, 2 for FP16. This applies to small models too, not just large ones — a 9B model with 262K ctx wastes more memory on unused KV slots than it uses for model weights.

11. **Load sequence for large models**: unload → wait 15-30s → verify no zombie (`ps aux | grep llama-server`) → load → wait patiently (103 GB copy takes 2-3 min) → check journalctl for success.

12. **INI-to-CLI flag translation**: Boolean INI keys like `no-mmap = true` become bare flags on CLI (`--no-mmap`), NOT `--no-mmap true`. The latter fails with `error: invalid argument: true`. Same for `jinja = true` → `--jinja`, `flash-attn = on` → `--flash-attn on` (this one takes a value). Check llama-server `--help` for which flags accept values.

13. **Zombie loading state**: If a model load fails (wrong path, corrupt file, OOM, invalid CLI flag), the router may leave the entry stuck at `status: loading` forever. No logs will appear in the model-manager's journal because the child process already died. Fix: `systemctl --user restart m5-router` to clear the stuck state. Simply retrying `/models/load` won't work — the router thinks it's already loading.

    **How to find the actual error:** The router runs inside the distrobox container. Its error messages are NOT in `journalctl --user -u m5-router` (which just shows systemd start/stop). Find them with:
    ```bash
    sudo journalctl --since "5 min ago" --no-pager | grep "distrobox\|llama-server\|error\|failed"
    ```
    Look for lines like `error while handling argument "--X": the argument has been removed` or `cannot stat` or `exited with status 1`. The distrobox prefix in the log line identifies which process the message comes from. Once you find the actual error, fix the INI, then restart the router.

14. **/tokenize triggers auto-load without --no-models-autoload**: The gateway intercepts `/tokenize` and routes it through `ensure_loaded`, which unloads existing models before loading the requested one. Without this intercept (or without `--no-models-autoload` on the router), a tokenize request bypasses the gateway's memory guard and the router loads models on demand until OOM.

15. **Unknown preset keys cause crash-loops**: llama.cpp rejects unknown keys in router-preset.ini with `failed to initialize router models: option X not recognized in preset Y` and exits with code 1. If you add custom keys (like `max-reasoning-tokens`), the router will crash-loop on every systemd restart. The startup script's validation catches this before launch, but if you edit the INI after startup, the next restart will fail. Only use llama.cpp-native keys in the INI.

16. **Router preset INI known keys**: When adding new options to router-preset.ini, update the `KNOWN_KEYS` regex in `start-native-router.sh` too. Current list: `model|ctx-size|cache-type-k|cache-type-v|n-gpu-layers|n-gpu-layers-draft|flash-attn|no-mmap|mmap|jinja|temp|top-p|top-k|min-p|repeat-penalty|presence-penalty|batch-size|ubatch-size|threads|threads-batch|numa|mmproj|chat-template-kwargs|chat-template-file|load-on-startup|draft-max|draft-min|draft-p-min|model-draft|cache-type-k-draft|cache-type-v-draft|rope-scale|rope-freq-base|reasoning|kv-unified|no-warmup|reasoning-budget|spec-type|spec-draft-p-min|spec-draft-n-max`

17. **Chunked proxy bug pattern**: If the OpenAI SDK throws `APIConnectionError: Connection error` when hitting the proxy, but `curl` to the backend llama-server works fine, the issue is in the proxy's chunked transfer encoding. Check `_proxy_bytes()` for: (a) escaped CRLF strings (backslash-r-backslash-n produces literal backslash chars instead of CR+LF bytes), and (b) missing terminal `0 CRLF CRLF` chunk. Both cause the client to hang and then fail when the connection closes.

18. **model_manager is a systemd user service** at `~/.config/systemd/user/model-manager.service`. Managed with `systemctl --user start/stop/restart model-manager`. Logs via `journalctl _PID=$(pgrep -f model_manager.py) --since "..."` or `systemctl --user status model-manager`. The router (llama-server) runs inside the distrobox container — use `sudo journalctl --since "..." --no-pager | grep "distrobox|reasoning-budget"` for router-level events. Confusing the two log sources leads to wasted time.

18b. **Startup race condition with router.** If model-manager logs `Router POST /tokenize failed: [Errno 111] Connection refused` at startup, the thinking token ID cache is empty and logit bias will never fire. The lazy-load fallback resolves this at runtime; the systemd `After=m5-router.service` ordering prevents it on clean starts.

19. **`POST /api/load` returns 400 "model is already running" on unknown models.** If the model was just added to `router-preset.ini` and the router was restarted but model-manager was NOT restarted, the proxy's internal model list is stale. The error message is misleading — the model isn't loaded but simply unknown to the proxy. Fix: `systemctl --user restart model-manager` to re-fetch the model list from the router at startup.

20. **Reasoning-budget logs lack slot IDs.** The `reasoning-budget: activated/deactivated/exhausted` messages from llama-server's sampler do NOT include the slot ID. Cross-reference timestamps with slot-tagged `init_sampler` logs: `grep "init_sampler|reasoning-budget"`.

20. **model_manager logit bias always fires for thinking models.** Three paths: (a) `max_tokens == 0` — enforces `max_tokens = max_reasoning_tokens + 512`; (b) `max_tokens <= budget` — progressive bias; (c) `max_tokens > budget` — scaled bias. See the Bias formula section for details.

21. **Bias applies to both stream and sync requests.** The injection happens in `_handle_completion()` before the stream/sync dispatch. If you see `model stream` without `Applied reasoning bias`, check: (a) is the model in `model-manager-config.yaml`? (b) does it have `max_reasoning_tokens` set? (c) is the token ID cached?

22. **DeepSeek-distilled models output think tokens despite reasoning=off.** Models like `Qwen3.5-9B-DeepSeek-V4-Flash-MTP` are fine-tuned to always emit `<think>` blocks. Setting `reasoning = off` in router-preset.ini and `chat-template-kwargs = {"enable_thinking":false}` is not sufficient — the model's weights produce thinking tokens regardless of template flags.

    **Symptom:** `_proxy_sync_with_reasoning_trace()` logs `thinking: X chars, Y lines` via journalctl, and responses always contain `<think>` blocks even with reasoning explicitly disabled.

    **Detection:**
    ```
    journalctl _PID=$(pgrep -f model_manager.py) -f | grep "thinking"
    ```

    **Fix:** Add the model to `~/llm-server/model-manager-config.yaml` so the proxy injects `reasoning_budget` + logit bias:
    ```yaml
    models:
      qwen35-9b:
        max_reasoning_tokens: 512
        logit_bias_strength: 10.0
        target_thinking_tokens: 200
    ```
    Then `systemctl --user restart model-manager`.

    **Why this works:** `reasoning = off` only disables the template's thinking tags and the engine's reasoning-content parsing — it does not stop a model from generating thinking tokens if they are naturally part of its output distribution (as they are in DeepSeek-distilled models). The proxy-level `reasoning_budget` API parameter and `logit_bias` on the close token work at the sampler level, actively steering token selection regardless of template. Only models registered in `model-manager-config.yaml` receive this treatment.

    **⚠️ Known exception: Step 3.7 Flash (and models where the thinking close token is a special type-3 token).** The logit_bias approach assumes the close token responds to bias as a regular token would. For Step 3.7 Flash:
    - `</think>` = token 128799, **type 3 (special/control)** in the GGUF tokenizer
    - Applying `logit_bias` on a type-3 token **corrupts the sampler** — output becomes "128128128..." instead of proper text
    - The model_manager's `</think_>` and `</thinking>` search patterns don't match `</think>` (128799) anyway, so the bias never fires
    - `reasoning_budget` API parameter is also ineffective — the model ignores it
    - **Chat template override is the only working approach** — see `router-preset-model-tuning` skill's `references/thinking-suppression-techniques.md`
    - Check token type: `gguf-dump model.gguf --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['metadata'].get('tokenizer.ggml.token_type',{}).get('value',[])[TOKEN_ID])"`

23. **`--draft-max` removed in newer llama-server — use `spec-draft-n-max`.** The `draft-max` INI key (which maps to `--draft-max N` on the llama-server CLI) has been removed from current llama-server builds. Using it causes a silent loading failure:

    ```
    error while handling argument "--draft-max": the argument has been removed.
    use --spec-draft-n-max or --spec-ngram-mod-n-max
    ```

    The router stays in `status: loading` forever because the child process crashes before it can report the error through the normal channel. The fix is to replace `draft-max` with `spec-draft-n-max` in the INI, then restart the router.

    **Two speculative decoding patterns:**

    - **Built-in MTP** (`spec-type = draft-mtp`): The model has multi-token prediction heads baked in. Uses `spec-draft-n-max` and `spec-draft-p-min`. No `model-draft` needed. Common on Qwen3.6+ and fine-tuned variants with "MTP" in the filename.

    - **Separate draft model** (`model-draft = <path>` + `spec-draft-n-max`): A smaller model generates draft tokens that the main model verifies. Use for models without MTP heads. Requires `n-gpu-layers-draft = 999` to fully offload the draft model to GPU. Example:
      ```ini
      model-draft = /mnt/data2/models/tiny/Qwen3.5-4B.Q4_K_M.gguf
      spec-draft-n-max = 5
      n-gpu-layers-draft = 999
      ```

    The separate-draft pattern accepts fewer tokens per step (~5 vs MTP's ~2-3) but works with any model pair where the draft is smaller than the main. MTP is faster (~81-91% acceptance) but only works with models specifically trained with MTP heads.

    **Detecting CLI flag errors at load time:** Router spawn errors are NOT visible in `journalctl --user -u m5-router` or the model-manager journal. Look in the system journal with:
    ```bash
    sudo journalctl --since "5 min ago" --no-pager | grep "distrobox" | grep -i "error\|argument\|removed"
    ```
    The `distrobox` prefix in the log line identifies the router's child process. This catches every boot argument error the underlying llama-server emits before crashing.

## Structured CoT (Chain-of-Thought) Grammar Injection

The proxy injects GBNF grammar constraints into `<think/>` blocks for `-cot` model variants. This forces models to produce structured reasoning (GOAL/APPROACH/EDGE or GOAL/STATE/ALGO/EDGE/VERIFY) in ~100-300 tokens instead of free-form rambling that burns thousands of tokens.

### Architecture

```
Grammar files (~/llm-server/grammars/*.gbnf)
    ↓ loaded at startup into COT_GRAMMARS dict
Client requests "qwen36-35b-cot"
    ↓ proxy _handle_completion() intercepts
Injects "grammar" + "reasoning_budget" into JSON body
    ↓ forwarded to router
Router serves with enable_thinking:true (from INI preset)
    ↓ model outputs structured <think/> + free-form answer
```

### Components

- **Grammar files**: `~/llm-server/grammars/structured-cot-coding.gbnf` (GOAL/STATE/ALGO/EDGE/VERIFY) and `structured-cot-general.gbnf` (GOAL/APPROACH/EDGE)
- **COT_GRAMMARS dict**: Maps model name → grammar string, loaded by `preload_cot_grammars()` at startup
- **Injection point**: `_handle_completion()` checks if requested model is in COT_GRAMMARS, injects `grammar` and `reasoning_budget: 512` into the request JSON body before proxying
- **Preset entries**: Duplicate model configs with `-cot` suffix, `enable_thinking:true`, and `chat-template-kwargs = {"enable_thinking":true}`

### Adding a new -cot variant

1. Create grammar file in `~/llm-server/grammars/`
2. Add mapping in `preload_cot_grammars()` grammar_map dict (or rely on auto-scan by model base name)
3. Add `[model-name-cot]` section to `router-preset.ini` with `enable_thinking:true`
4. Restart both `m5-router` and `model-manager` services

### Grammar format (GBNF)

```gbnf
root ::= think answer
think ::= "<think\>\n" "GOAL: " line "APPROACH: " line "EDGE: " line "</think\>\n\n"
line ::= [^\n]+ "\n"
answer ::= [\x09\x0A\x0D\x20-\x7E]+
```

The grammar only constrains the `<think/>` block. The answer channel stays permissive — model writes free-form after the structured scratchpad.

### Key principle

Never put custom keys in `router-preset.ini` (crash loop risk). The proxy layer is the right place for per-request modifications like grammar injection, logit_bias, and reasoning_budget overrides. The router INI should only contain llama.cpp-native keys.

## Debugging Auxiliary Task "Connection Error" Failures

Hermes auxiliary tasks (title_generation, flush_memories, etc.) use the same model-manager proxy chain. When you see "Auxiliary title generation failed: Connection error" (or similar for other auxiliary tasks):

**The chain to trace:**
```
Hermes gateway → custom aux provider → m5:8079 (model_manager) → llama-server backend (port N)
```

**Step 1: Check aux config in `~/.hermes/config.yaml`** — find the `title_generation` (or other) section:
```yaml
title_generation:
  provider: custom
  model: qwen36-35b
  base_url: m5:8079/v1
  api_key: ''
```

**Step 2: Test the proxy endpoint (m5:8079) directly:**
```bash
curl -s --max-time 20 http://localhost:8079/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen36-35b","messages":[{"role":"user","content":"Say hello in 2 words"}],"max_tokens":10}'
```

**Step 3: If proxy fails, find the backend port and test direct:**
```bash
# Find backend llama-server ports (one per loaded model)
ss -tlnp | grep llama-server

# Test backend directly (e.g. port 41707)
curl -s --max-time 20 http://127.0.0.1:41707/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen36-35b","messages":[{"role":"user","content":"Say hello"}],"max_tokens":10}'
```

**Common failure causes:**
- **Proxy chunked encoding bug** — `APIConnectionError: Connection error` from the OpenAI SDK while `curl` to the backend works. The proxy's `_proxy_bytes()` has broken chunk framing (escaped CRLF or missing terminal chunk). See Pitfall #17.
- Backend llama-server still `loading` the model (wait 10-30s for large models)
- Model status check: `curl -s http://localhost:8080/v1/models | python3 -c "import json,sys; ..."` to poll `status.value`
- Transient network/load issue — retry after confirming backend is `loaded`
- DNS resolution for hostname like `m5` (use `localhost` if hostname fails)

**Key insight:** If the direct backend works but the proxy fails, the issue is in model_manager.py proxy layer. If both fail, the backend llama-server itself has a problem (still loading, crashed, wrong port).

17. **Chunked proxy bug pattern**: If the OpenAI SDK throws `APIConnectionError: Connection error` / `RemoteProtocolError: peer unexpectedly closed connection` when hitting the proxy, but `curl` to the backend llama-server works fine, the issue is in the proxy's chunked transfer encoding. Check `_proxy_bytes()` for: (a) escaped CRLF strings (`\\\\r\\\\n` produces literal backslash chars instead of CR+LF bytes — need `\\r\\n`), and (b) missing terminal `0\\r\\n\\r\\n` chunk. Both cause the client to hang and then fail when the connection closes. Test with the Python OpenAI client directly: `OpenAI(api_key='no-key-required', base_url='http://localhost:8079/v1').chat.completions.create(...)` — curl alone isn't sufficient because it tolerates broken chunked encoding.

18. **model_manager is a systemd user service** at `~/.config/systemd/user/model-manager.service`. Managed with `systemctl --user start/stop/restart model-manager`. Logs via `journalctl _PID=$(pgrep -f model_manager.py) --since "..."` or `systemctl --user status model-manager`. The router (llama-server) runs inside the distrobox container and logs via distrobox journal — use `sudo journalctl --since "..." --no-pager | grep "distrobox\|reasoning-budget"` for router-level events. Confusing the two log sources leads to "No entries" and wasted time.

18b. **Startup race condition with router.** If model-manager logs `Router POST /tokenize failed: [Errno 111] Connection refused` at startup, the thinking token ID cache is empty and logit bias will never fire. See "Startup race condition" section above. The lazy-load fallback (added 2026-05-05) resolves this at runtime; the systemd `After=m5-router.service` ordering prevents it on clean starts.

19. **Reasoning-budget logs lack slot IDs.** The `reasoning-budget: activated/deactivated/exhausted` messages from llama-server's sampler do NOT include the slot ID. To attribute them to specific slots, cross-reference timestamps with slot-tagged `init_sampler` logs: `grep "init_sampler\|reasoning-budget"`. Each `init_sampler: id N | task T` event happens at the same second as the corresponding `reasoning-budget: activated` for that slot. This is critical for multi-slot debugging — without cross-referencing, it appears that some slots bypass the budget entirely when they actually don't.

20. **model_manager logit bias always fires for thinking models.** Three paths: (a) `max_tokens == 0` — enforces `max_tokens = max_reasoning_tokens + 512` and applies full strength; (b) `max_tokens <= budget` — progressive bias `(1 - max_tokens/budget) * strength`; (c) `max_tokens > budget` — scaled bias `max(strength * 0.35, strength * target_thinking_tokens / max_tokens)`. Path (c) uses `target_thinking_tokens` (default 800, ~40s at 20 tok/s) and a 35% floor so bias never vanishes even for huge hardcaps. The bias also handles `logit_bias` in both dict and list format (converts list to dict internally to merge correctly).

21. **Bias applies to both stream and sync requests.** The injection happens in `_handle_completion()` before the stream/sync dispatch at lines 662-665. If you see `→ model stream` without `Applied reasoning bias`, check: (a) is the model in `model-manager-config.yaml`? (b) does it have `max_reasoning_tokens` set? (c) is the token ID cached? Run `journalctl _PID=$(pgrep -f model_manager.py) --since "1 min ago" | grep "bias\|Token ID"`.

## External Provider Configuration Issues

When fallback models work but main models fail (e.g., GLM models failing on zai provider), check external configuration:

### API Key Configuration Pitfalls

**Symptom**: Main model (glm-5.1) fails consistently but fallback models work fine.

**Root Cause**: API key configuration mismatch and model name incompatibility.

**Diagnosis Pattern**:

1. **Check API Key Location**:
   - `config.yaml`: `api_key: ''` (empty)
   - `.env`: `GLM_API_KEY=bdf0ab...NGtM` (actual key)
   - **Fix**: Use environment variable in config.yaml: `api_key: ${GLM_API_KEY}`

2. **Model Name Validation**:
   - Requested model: `glm-5.1` 
   - Provider's default: `glm-5`
   - API error: `{"error":{"code":"401","message":"token expired or incorrect"}}`
   - **Fix**: Use model names that your API key actually supports (often the base model names like `glm-5`, `glm-4.5-air`)

**Verification Steps**:

```bash
# Test API key directly
curl -s -X POST https://api.z.ai/api/coding/paas/v4/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GLM_API_KEY" \
  -d '{"model": "glm-5", "messages": [{"role": "user", "content": "test"}], "max_tokens": 10}'

# Check fallback provider configuration
grep -A3 -B1 "fallback_providers:" ~/.hermes/config.yaml
```

**Configuration Best Practices**:

1. **Always validate API keys** with direct curl tests before blaming model names
2. **Use environment variables** for sensitive credentials in config.yaml
3. **Test model names** with your specific API key - some providers return 401 for invalid model names that look valid
4. **Check fallback_providers** for working model names as hints about supported models

See [Zai Provider Configuration Pitfalls](references/zai-provider-configuration-pitfalls.md) for detailed troubleshooting guide.

## Reasoning Token Tracing

Non-streaming completions through the proxy are intercepted by `_proxy_sync_with_reasoning_trace()`. After receiving the response from the backend llama-server, it parses the JSON, extracts `reasoning_content` from each choice, and logs a trace line:

```
◆ qwen35-4b reasoning: 218 chars, 7 lines | tokens: 60 completion, 17 prompt
```

This only fires when `reasoning_content` is non-empty (i.e. the model is a thinking model and `enable_thinking` is true). Use `journalctl _PID=$(pgrep -f model_manager.py) -f | grep "◆"` to watch reasoning usage in real time. The char/line counts help tune `max-reasoning-tokens` per model — once you see typical reasoning output sizes, set the INI key accordingly and the logit-bias mechanism will nudge models to close their thinking blocks before hitting the limit.

### enable_thinking in API responses

The `/api/models` and `/api/available` endpoints now include an `enable_thinking` field per model, parsed from the `chat-template-kwargs` JSON in the preset INI:

- `true` — model has `{"enable_thinking":true}` in preset (e.g. `qwen36-35b-cot`)
- `false` — model has `{"enable_thinking":false}` in preset (e.g. `qwen36-35b`)
- `null` — no `chat-template-kwargs` in preset (model's default behavior)

## Debugging Reasoning Infinite Loops

Three separate mechanisms control reasoning output (two active, one disabled):

1. **llama-server native `reasoning_budget`** (per-request API parameter, injected by model_manager — active). Progressive sampler that increasingly forces the `</think>` end sequence as the budget approaches. Configured by `max_reasoning_tokens` in `model-manager-config.yaml`. Logs: `reasoning-budget: activated, budget=N tokens`, `reasoning-budget: deactivated (natural end)`, `reasoning-budget: budget exhausted, forcing end sequence`.

2. **model_manager `logit_bias`** (per-request, active). Constant additive bias on `</think>` token as a gentle early nudge. Configured in `~/llm-server/model-manager-config.yaml`. Only visible at DEBUG level (`--verbose` flag).

3. **Router INI `reasoning-budget`** (DISABLED — prefill token bug, see below). Do not enable.

### Where to find logs

### Where to find logs

model_manager is a **systemd user service** (`systemctl --user status model-manager`). Its logs:
```bash
# model_manager logs (PID-based, not unit-based)
sudo journalctl _PID=$(pgrep -f model_manager.py) --since "1 hour ago" --no-pager

# Router/llama-server logs (via distrobox container, user-level systemd unit)
sudo journalctl --user -u m5-router.service --since "1 hour ago" --no-pager

# Reasoning-budget events (from llama-server, via distrobox)
sudo journalctl --since "1 hour ago" --no-pager | grep "reasoning-budget"
```

### Debugging workflow for reasoning loops

1. **Identify the runaway task**: Look for eval times >60s or eval tokens >2000 in slot timing logs.
   ```bash
   sudo journalctl --since "2 hours ago" --no-pager | grep "52943.*eval time"
   ```
2. **Trace the task lifecycle**: Note task ID and slot ID, then grep for all events:
   ```bash
   sudo journalctl --since "2 hours ago" --no-pager | grep "task <ID>"
   ```
3. **Check reasoning-budget activation**: The budget should log "activated" when generation starts. If missing, the slot bypassed the budget gate entirely.
4. **Check model_manager bias application**: Requires `--verbose` flag on model_manager. Without it, bias debug logs are invisible.
5. **Look for "budget exhausted, forcing end sequence"**: This means the hard budget worked — the model was force-stopped at the limit.
6. **Look for "Connection reset by peer"**: Client-side timeout/disconnect from waiting too long.

### Known issue: Reasoning appears to "loop" but is actually budget working

When a model generates 4000+ thinking tokens at ~22 t/s, it takes **186+ seconds** before any text output appears. This looks like an infinite loop but is the `reasoning-budget` working as configured — the model is silently thinking for 3+ minutes. The perception is worse because reasoning-budget logs lack slot IDs, making it seem like some slots bypass the budget entirely (they don't — cross-reference with `init_sampler` timestamps to attribute correctly).

**What was broken (now fixed):** Two bugs:

1. **model_manager logit bias never fired without explicit max_tokens.** The bias logic required `max_tokens > 0`. Most Hermes requests don't set `max_tokens`. Now fixed: when `max_tokens == 0`, the proxy enforces `max_tokens = max_reasoning_tokens + 512` AND applies full bias strength.

2. **llama-server reasoning-budget prefill token consumption.** The sampler processes all prefill tokens, including historical `<think_>` blocks from conversation history. On long conversations, this exhausts the budget before generation starts. Fixed by disabling `reasoning-budget` in the preset entirely and letting model_manager handle limits via `max_tokens` + `logit_bias` (which only affect output tokens, not prefill).

**Current tuning (as of 2026-05-23):**
- `reasoning-budget` **DISABLED** in `router-preset.ini` (commented out — prefill token bug, see below)
- `reasoning_budget` **INJECTED PER-REQUEST** by model_manager.py as API parameter (native progressive sampler, budget=4096)
- `max_reasoning_tokens: 4096` in `model-manager-config.yaml` — sets both the reasoning_budget API parameter and the logit_bias target
- `logit_bias_strength: 11.8` (balanced — gentle early nudge alongside native sampler)
- `target_thinking_tokens: 800` (~40s at 20 tok/s — bias floor kicks in around this mark)
- model_manager enforces `max_tokens = max_reasoning_tokens + 512` (4096 + 512 = 4608 total) when caller omits it
- When caller sets `max_tokens > budget`, bias = `max(11.8 * 0.15, 11.8 * 800 / max_tokens)` — always nudges, never zero
- `model_manager.py` runs with `--verbose` (debug-level bias and injection logs visible)
- Logit bias targets the LAST token of `</think_>` sequence (token 94979 = `_>` for Qwen models), NOT the first (510 = `</` which is too generic)
- `logit_bias` uses **positive** values to PROMOTE the close tag (make it more likely). Negative would suppress it, causing longer thinking.
- systemd unit has `After=m5-router.service` to avoid startup race where `/tokenize` fails with Connection refused
- Lazy-load fallback in bias injection handles cases where startup preload still fails

### Startup race condition: token ID preload fails silently

**Symptom:** Logit bias never fires. No "Applied reasoning bias" or "Enforced max_tokens" debug lines in model-manager logs. Reasoning loops run unchecked. Router shows `reasoning-budget: activated, budget=2147483647 tokens` (INT_MAX — no real limit).

**Root cause:** model-manager and m5-router start in parallel (no systemd ordering). The `/tokenize` preload at model-manager startup fails with `Connection refused` because the router isn't up yet. `THINKING_CLOSE_TOKENS` dict stays empty → `thinking_token_id = THINKING_CLOSE_TOKENS.get(model)` returns `None` → the bias injection block is skipped entirely. No error is raised; bias just silently never applies.

**How to detect:** Check startup logs for:
```
Router POST /tokenize failed: [Errno 111] Connection refused
No thinking token IDs cached (models don't use thinking tags)
```
If you see these, bias is dead. Cross-check with a live request: `journalctl --user -u model-manager -f | grep "bias"` — if no "Applied reasoning bias" lines appear for thinking models, the token IDs weren't resolved.

**Fix (applied 2026-05-05):**
1. **Lazy-load fallback in `model_manager.py`:** When `thinking_token_id` is `None` at bias injection time, calls `get_token_id()` on the spot (router is definitely up by now). Caches the result for subsequent requests. This handles the race condition at runtime.
2. **Systemd ordering:** Added `After=m5-router.service` and `Wants=m5-router.service` to `model-manager.service` so systemd starts model-manager after the router is ready. This fixes the preload on clean restarts.

**Verification after restart:**
```bash
# Should show cached token IDs (not the "don't use thinking tags" message)
journalctl --user -u model-manager --since "just now" | grep "Token IDs cached"
# Should show bias application on requests to thinking models
journalctl --user -u model-manager -f | grep "bias"
```

### Dual mechanism: native reasoning_budget + logit bias

Since 2026-05-23, model_manager injects TWO controls per request for thinking models:

1. **`reasoning_budget` API parameter** — llama-server's native progressive sampler. Monitors thinking tokens and increasingly forces the `</think>` end sequence as the budget approaches. Reaching budget → near-deterministic close. This is per-request, NOT the INI-level `reasoning-budget` which was disabled due to the prefill bug.

2. **`logit_bias` on the close token** — constant additive bias at every step. A gentle early nudge before the native sampler kicks in.

**Key distinction between per-request reasoning_budget and INI reasoning-budget:**

| Aspect | INI `reasoning-budget` (disabled) | API `reasoning_budget` (active) |
|---|---|---|
| Scope | Per-slot default, set at startup | Per-request override |
| Prefill token bug | YES — counts historical `<think_>` in prompt | Same sampler code, same bug risk on long multi-turn chats with `preserve_thinking=true` |
| When it's safe | Never (prefill bug on any multi-turn) | Fresh chats, single-turn, or short conversations where prefill thinking is < budget |
| Configured in | `router-preset.ini` | `model-manager-config.yaml` → injected by model_manager.py |

**How they work together:**

The proxy injects `reasoning_budget = max_reasoning_tokens` then applies the logit_bias on top:

```python
req["reasoning_budget"] = budget  # native progressive sampler
logging.debug(f"Injected reasoning_budget={budget} for {model}")
# ... then existing logit bias logic applies
```

At token 1-~3500: logit bias provides gentle pressure (bias ~4-5).
At token 3500-4096: native sampler progressively increases forcing.
At token 4096: near-deterministic `</think>` emission from the native sampler.
Hard max_tokens catch-all at budget+512 guards against edge cases.

### model-manager-config.yaml tuning

```yaml
# ~/llm-server/model-manager-config.yaml
models:
  qwen36-35b:
    # Native reasoning_budget injected as per-request API parameter.
    # Sampler progressively increases pressure on </think> as the budget
    # approaches, reaching near-deterministic close at ~4096 tokens.
    # Logit bias kept as a gentle early nudge alongside the native mechanism.
    max_reasoning_tokens: 4096    # sets both reasoning_budget (native) and bias target
    logit_bias_strength: 11.8     # 5-8 gentle, 10-12 balanced, 13+ strong suppression
    target_thinking_tokens: 800   # ~40s at 20 tok/s — when logit bias starts nudging (default: 800)
```

### Bias formula (three paths)

**Path A: no caller limit** (`max_tokens == 0`): Enforces `max_tokens = max_reasoning_tokens + 512` (=4608 with budget=4096). Falls into Path C with max_tokens=4608.

**Path B: within budget** (`max_tokens <= max_reasoning_tokens`): Progressive bias `(1 - max_tokens/budget) * strength`. Goes from 0 at `max_tokens == budget` to full strength at `max_tokens == 0`.

**Path C: caller allows more than budget** (`max_tokens > budget`): Scaled bias using `target_thinking_tokens`. Formula: `max(strength * 0.15, strength * target / max_tokens)`. The 15% floor (reduced from 35% on 2026-05-17) ensures bias never vanishes even for generous budgets, without overpowering the native reasoning_budget mechanism.

Example with strength=11.8, target=800, budget=4096:

| max_tokens | bias | path | reasoning_budget active? |
|---|---|---|---|
| 0 (enforced 4608) | 2.05 | C (11.8*800/4608) | Yes, 4096 |
| 1000 | 8.92 | B (1-1000/4096)*11.8 | Yes, 4096 |
| 2048 | 5.90 | B | Yes, 4096 |
| 4096 | ~0.0 | B (boundary) | Yes, 4096 |
| 8192 | 1.77 | C (floor: 11.8*0.15) | Yes, 4096 |

For models that tend to loop, increase `bias_strength` (13-15) or lower `target_thinking_tokens`. For models that cut thinking too short, decrease strength to 5-8 or raise the budget.

### Fixed: bias now fires for all thinking-model requests (2026-05-06)

Previously, callers that set `max_tokens >= max_reasoning_tokens` (e.g. KiloCode sending `max_tokens=4096` against a budget of 1024) got **zero bias**. The model would think unchecked for 100+ seconds (2839 tokens observed in one case). The fix adds Path C to the bias formula: when `max_tokens > budget`, bias = `max(strength * floor%, strength * target / max_tokens)`. The `target_thinking_tokens` parameter (default 800, ~40s at 20 tok/s) controls when the nudge kicks in; the floor (now 15%) prevents it from vanishing on huge hardcaps.

### Why INI reasoning-budget is DISABLED in llama-server (prefill bug)

The INI-level `reasoning-budget` sampler processes ALL prefill tokens (see `references/reasoning-budget-internals.md`). On long conversations where `preserve_thinking=true` embeds previous `<think_>...</think_>` blocks in the prompt, the sampler:

1. Matches historical `<think_>` → enters COUNTING, starts decrementing budget
2. Matches historical `</think_>` → enters DONE
3. Re-arms on the template's trailing `<think_>` → fresh budget
4. BUT: if any historical thinking block is truncated (unclosed, from a previous budget-forced response), the sampler stays in COUNTING and exhausts the budget on historical tokens before generation starts

With `reasoning-budget = 1024`, this fires immediately on any conversation with >1024 thinking tokens in history. The symptom: `reasoning-budget: activated` immediately followed by `budget exhausted, forcing end sequence` at the same timestamp — the model never gets to generate.

**Solution for long multi-turn chats:** Disable `reasoning-budget` in the preset entirely. The per-request `reasoning_budget` API parameter uses the same sampler code so the prefill bug still applies on long conversations. For short/fresh chats it works perfectly. For long chains, model_manager's `max_tokens` (output-only) + `logit_bias` (output-only) remain the bug-free fallback since they only constrain generation tokens, never prefill. The per-request reasoning_budget is the default active mechanism; drop back to bias-only when you see prefill exhaustion on a multi-turn conversation.

## Standalone model load testing

To verify a new model config before relying on the router, spawn a standalone llama-server on a free port inside the vulkan container:

```bash
# Pick a free port (check with: ss -tlnp | grep 80)
distrobox enter llama-vulkan-radv -- bash -c '
export VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/radeon_icd.x86_64.json"
/usr/sbin/llama-server \
    --host 0.0.0.0 --port 8082 \
    --model /home/cricri/models/MODEL.gguf \
    --mmproj /home/cricri/models/mmp-PROJECTOR.gguf \
    --ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0 \
    --n-gpu-layers 999 --flash-attn on --no-mmap --jinja \
    --threads 8 --batch-size 2048 --ubatch-size 1024 \
    --verbose
'
```

Then verify: `curl -s http://localhost:8082/health` and `curl -s http://localhost:8082/v1/models` (check `capabilities` includes `multimodal` for vision). Test inference with a quick chat completion. Kill the test server when done.

Note: Open WebUI may send traffic to any llama-server port it discovers, polluting logs — ignore that noise.
