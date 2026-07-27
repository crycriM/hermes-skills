---
category: mlops
name: router-troubleshooting
description: Fix m5-router.service issues - orphaned INI entries, rogue llama-server processes blocking port 8080
---

# Router Troubleshooting

## When router won't start or GUI shows no models

### Quick diagnostics
```bash
# Check service status
systemctl status m5-router.service

# Find what's on port 8080
lsof -i :8080
# Also check router port 8079 for alternative config
lsof -i :8079
```

### Common issues & fixes

**1. Unrecognized INI options (most common crash cause)**
llama.cpp router **strictly validates** preset options. Any unknown `key = value` line causes immediate crash with:
```
main: failed to initialize router models: option 'X' not recognized in preset 'Y'
```
This puts the service in a crash loop (systemd restarts it repeatedly).

**How to diagnose:**
```bash
journalctl --user -u m5-router.service --since "10 min ago" --no-pager | grep "not recognized"
```

**Valid preset options** (as of llama.cpp b8920): model, ctx-size, cache-type-k, cache-type-v, n-gpu-layers, n-gpu-layers-draft, flash-attn, no-mmap, mmap, jinja, chat-template-kwargs, chat-template-file, temp, top-p, top-k, min-p, repeat-penalty, presence-penalty, batch-size, ubatch-size, threads, mmproj, kv-unified, no-warmup, load-on-startup, draft-max, draft-min, draft-p-min, model-draft, cache-type-k-draft, cache-type-v-draft, rope-scale, rope-freq-base, reasoning, reasoning-budget.

**⚠️ Custom/approximate options like `max-reasoning-tokens`, `draft-context` are NOT valid and will crash the router.** Any dynamic tuning must be done in the gateway proxy (model_manager.py on :8079), not in the preset INI.

**⚠️ `start-native-router.sh` validator is stricter than llama-server:** The script has a hardcoded `KNOWN_KEYS` list that can lag behind llama-server's actual supported flags. If validation fails with "Unknown preset keys" but the key is valid (check `llama-server --help`), add it to `KNOWN_KEYS` in the script. Example: `n-gpu-layers-draft` was missing despite being a valid flag.

**Specific pitfall — reasoning options**
The router uses `reasoning` and `reasoning-budget` to control CoT output. Common incorrect variants:
- `max-reasoning-tokens` → use `reasoning-budget`
- `draft-context` → use `draft-max` and `draft-min` for speculative decoding
If you're copying options from other contexts (OpenWebUI, llama-server CLI), double-check they match the preset schema above.

**2. Orphaned INI entries**
The router-preset.ini can accumulate bare filenames without `key = value` pairs.

```bash
# Check for orphan lines
grep -v '^#' /home/cricri/llm-server/router-preset.ini | grep -v '=' | head
```

**Fix:** Remove any line that's just a filename (no equals sign). The router only recognizes `key = value` format.

**2. Rogue llama-server process hogging port 8080**
A standalone server can block the router from binding.

```bash
# Kill all llama-server processes and free port
pkill -f "llama-server" && lsof -ti:8080 | xargs kill -9
```

**3. Port 8079 conflict (secondary router)**
Sometimes a secondary router instance runs on 8079, causing duplicate model loads.

```bash
# Identify and kill rogue processes
lsof -ti:8079 | xargs kill -9
```

### Full recovery sequence
```bash
# 1. Stop everything
systemctl stop m5-router.service
lsof -ti:8080 | xargs kill -9
lsof -ti:8079 | xargs kill -9

# 2. Fix INI if needed (see above)

# 3. Start fresh
systemctl start m5-router.service
sleep 5
systemctl status m5-router.service
```

### Model backend stuck in thinking loop

Models with thinking mode (e.g., qwen36-35b with `enable_thinking: true`) can get stuck — all slots show `is_processing: true` with ~190 tokens decoded but ~9800 remaining. The model appears "loaded" but requests hang.

### Model backend stuck after large-context request (silent hang)

A failure mode distinct from the thinking loop, caused by a **sync request with a long prompt context** (3000+ prompt tokens). The model generates at ~20 t/s but takes minutes, saturating the GPU at 100%. Model-manager's retry logic compounds the problem.

**Root cause — OpenWebUI "Suggested Questions" feature:**

After every assistant response, OpenWebUI's frontend automatically sends a sync request to generate 3-4 follow-up questions using the **full conversation history as prompt** (typically 3000-5000+ prompt tokens). This is a client-side setting stored in browser localStorage:

- OpenWebUI UI: **Settings → Interface → "Show suggested questions after chat response"**
- No server-side config toggle — must be unchecked in each browser

When disabled, OpenWebUI stops sending these post-response requests entirely.

**Symptom sequence:**
1. User's task completes fine (stream or sync)
2. OpenWebUI frontend sends a new sync request with the full conversation history (~3455 prompt tokens) for follow-up question generation
3. Backend starts a massive generation — slot shows `n_decoded` climbing past 5000-8000 tokens
4. GPU pegs at 100%, request takes 2+ minutes
5. Model-manager hits `Proxy error: timed out` after 2 minutes
6. Model-manager enters a **retry loop** — sends a new request every ~5 seconds, all pile up behind the stuck slot
7. After 6+ minutes, model-manager logs: `Unloading X for swap → Y` and force-kills the backend
8. Router logs: `force-killing model instance name=X after 10 seconds timeout` then `exited with status 1`

**Diagnosis — trace the chain:**

```bash
# 1. Check model-manager for the timeout + retry + swap pattern
journalctl --user -u model-manager.service --since "30 min ago" --no-pager | grep -E "Proxy error|timed out|Unloading"

# 2. Check model-manager for request activity — look for "→ model sync" followed by timeout
#    The sync after a "◆ model reasoning:" line is the follow-up question request
journalctl --user -u model-manager.service --since "30 min ago" --no-pager | grep -v "State refreshed"

# 3. Check router for proxy_reques frequency (5s intervals = retry loop, 50-100+ = stuck)
journalctl --user -u m5-router.service --since "30 min ago" --no-pager | grep "proxy_reques" | grep -o "model [a-z0-9-]*" | sort | uniq -c | sort -rn

# 4. Check backend slots for the stuck task
# Find the backend port:
ps aux | grep llama-server | grep "alias <model-name>"
# Check slots — look for is_processing=true with large n_decoded:
curl -s http://<backend-port>/slots | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'slot {s[\"id\"]}: processing={s[\"is_processing\"]}, decoded={s[\"next_token\"][0][\"n_decoded\"]}') for s in d]"

# 5. Verify VRAM saturation
cat /sys/class/drm/card*/device/mem_info_vram_used
# Total VRAM (128GB unified on Strix Halo — rocm-smi VRAM field underreports):
cat /sys/class/drm/card*/device/mem_info_vram_total
```

**The retry loop pattern:** ~60 proxy requests in ~6 minutes (~5s intervals) to the stuck model, plus 30+ simultaneous requests to another model as model-manager tries to swap.

**Recovery:**
```bash
# Kill the stuck backend process by alias
ps aux | grep llama-server | grep "alias <model-name>" | awk '{print $2}' | xargs kill -9

# Or restart the router to clear all backends
systemctl --user restart m5-router.service
```

**Prevention:**
- Disable "Suggested Questions" in OpenWebUI: Settings → Interface → uncheck "Show suggested questions after chat response"
- The `reasoning_budget` and `max_tokens` injections in model-manager don't prevent this — the hang is from large-prompt prefill time, not generation length
- Follow-up question requests should ideally use streaming (not sync) to avoid blocking slots
- The specific sync-after-completion signature (`→ model sync` immediately after `◆ model reasoning:`) is the hallmark of OpenWebUI follow-up generation

**Reference:** `references/openwebui-followup-request-flood.md` — full log signatures and timeline from an observed incident on step37.

### Model stuck in "loading" state (zombie child process)

The router reports a model as `"loading"` in `/v1/models` but the child llama-server died immediately. The router never clears the state, leaving a zombie process.

**Symptom:**
```bash
curl -s http://localhost:8080/v1/models | jq '.data[] | select(.status.value == "loading")'
# Shows model with status "loading" but no active child process

ps aux | grep defunct
# Shows zombie: [llama-server] <defunct>
```

**Root cause:** The child llama-server failed to load the model (e.g., unsupported architecture, corrupted GGUF, missing file) and exited immediately, but the router didn't reap the zombie or clear the "loading" state.

**Diagnosis:**
```bash
# 1. Check for zombie child processes
ps aux | grep defunct | grep llama-server

# 2. Get the real error from router logs (DO THIS FIRST)
journalctl --user -u m5-router.service --since "30 min ago" --no-pager | grep -E "error|fail|unknown"

# 3. Look for the specific model's load attempt
journalctl --user -u m5-router.service --since "30 min ago" --no-pager | grep -A 5 "spawning server instance with name=<model-name>"
```

**⚠️ Workflow pitfall:** Always check journal logs BEFORE guessing at VRAM/memory issues. On unified memory systems (128GB Strix Halo), rocm-smi's VRAM field underreports — don't assume OOM when the real error is "unknown model architecture" or similar.

**Common causes:**
- **Unsupported model architecture**: GGUF declares `general.architecture = X` but llama.cpp doesn't support it yet. Example: `deepseek4` (not in llama.cpp b9741, which only supports `deepseek`, `deepseek2`, `deepseek2-ocr`, `deepseek32`). Check for active PRs on llama.cpp GitHub.
- **Corrupted GGUF**: Partial download, checksum mismatch
- **Missing split file**: Multi-part GGUF missing one of the parts

**Checking architecture support:**
```bash
# Check what architectures the current build supports
cd ~/sources/llama.cpp  # Host source, not distrobox
grep "LLM_ARCH_" src/llama-arch.cpp | grep -E "^\s*\{ LLM_ARCH_"

# For unreleased architectures, check PRs
curl -s "https://api.github.com/search/issues?q=repo:ggml-org/llama.cpp+<arch_name>+is:pr&sort=created&order=desc" | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'PR #{i[\"number\"]}: {i[\"title\"]} - {i[\"state\"]}') for i in d.get('items',[])[:5]]"
```

**Building from a PR branch:**
```bash
cd ~/sources/llama.cpp
git fetch origin pull/<PR_NUMBER>/head:pr-<PR_NUMBER>-<name>
git checkout pr-<PR_NUMBER>-<name>
git submodule update --recursive

# Build in distrobox using host source
distrobox enter llama-vulkan-amdvlk -- bash -c '
cd /run/host/home/cricri/sources/llama.cpp && \
cmake -S . -B build -G Ninja \
  -DGGML_VULKAN=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_RPC=ON \
  -DCMAKE_INSTALL_PREFIX=/usr \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=ON \
  -DLLAMA_BUILD_SERVER=ON && \
cmake --build build --config Release && \
cmake --install build --config Release
'
```

**Reference:** `references/vulkan-op-support-check.md` — systematic technique for verifying Vulkan backend support for new model architectures.

**Recovery:**
```bash
# Restart the router to clear zombie and stale loading state
systemctl --user restart m5-router.service

# Verify the model is gone from loading state
curl -s http://localhost:8080/v1/models | jq '.data[] | select(.status.value == "loading")'
```

**Prevention:**
- Check llama.cpp release notes for supported architectures before downloading new models
- Verify GGUF architecture field: `python3 -c "import struct; f=open('<gguf>','rb'); f.read(4); struct.unpack('<I',f.read(4)); struct.unpack('<Q',f.read(8)); n_kv=struct.unpack('<Q',f.read(8))[0]; [print(f.read(struct.unpack('<Q',f.read(8))[0]).decode()) for _ in range(min(n_kv,10))]"`
- For multi-part GGUFs, verify all parts exist before adding to preset

### Verification
- Check logs: `journalctl -u m5-router.service -f`
- Router should show all models in GUI on port 8080
- No duplicate processes on port 8080 (only router, not standalone llama-server)
- Ensure port 8079 is clear if not used