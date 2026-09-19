---
name: distrobox-vulkan-llama-bench
description: Benchmark GGUF models in distrobox RADV/AMDVLK containers via llama-cli. Handles GPU memory management and AMDVLK distrobox quoting workaround.
triggers:
  - benchmark llama-cli distrobox
  - distrobox vulkan token speed test
  - amdvlk exit 125 distrobox-enter
---

# Distrobox Vulkan llama-cli Benchmark

Benchmark GGUF models in distrobox containers (RADV and AMDVLK) using llama-cli.

## When to Use
Benchmark prefill/output token speeds across distrobox Vulkan containers using llama-cli.
Use instead of router/API when you need direct llama-cli measurement.

## Drivers & Containers
- **RADV**: `llama-vulkan-radv` (radv open-source driver, fast prefill)
- **AMDVLK**: `llama-vulkan-amdvlk` (AMDVLK proprietary driver, slower prefill)

## GPU Memory Management — RADV
llama-cli accumulates GPU memory across runs. Restart the container before each run:

```bash
distrobox-stop --name llama-vulkan-radv -y 2>/dev/null || true
sleep 1
distrobox-start --name llama-vulkan-radv -b 2>/dev/null || true
sleep 2
```

## AMDVLK Invocation — Key Trick
Direct `distrobox-enter --additional-flags ... -- llama-cli ...` fails with exit 125.
Use a temp script file in `/tmp/`:

```bash
script_file="/tmp/llama-bench-${driver}-${model_name}.sh"
cat > "$script_file" <<'SCRIPT'
#!/bin/bash
export VK_ICD_FILENAMES=/etc/vulkan/icd.d/amd_icd64.json
llama-cli -m MODEL_PATH --ctx-size CTX --cache-type-k q8_0 --cache-type-v q8_0 \
  --n-gpu-layers 999 --flash-attn on --simple-io --single-turn \
  -n NTOKS PARAMS -p "PROMPT" > LOG 2>&1
SCRIPT
chmod +x "$script_file"
distrobox-enter --name llama-vulkan-amdvlk -- bash -c "$script_file"
rm -f "$script_file"
```

## Timing Extraction
llama-cli prints: `[ Prompt: X t/s | Generation: Y t/s ]`

```bash
timing=$(grep -oP '\[\s*Prompt:\s*[\d.]+\s*t/s\s*\|\s*Generation:\s*[\d.]+\s*t/s\s*\]' "$log" 2>/dev/null || true)
prefill=$(echo "$timing" | grep -oP 'Prompt:\s*\K[\d.]+' || echo "ERR")
output=$(echo "$timing" | grep -oP 'Generation:\s*\K[\d.]+' || echo "ERR")
```

## Container Rebuild (AMDVLK)

AMDVLK distrobox can break silently (missing libs, broken Vulkan layers). Full rebuild procedure:

```bash
# 1. Stop and destroy old container
distrobox-stop --name llama-vulkan-amdvlk -y 2>/dev/null || true
distrobox rm --force llama-vulkan-amdvlk 2>/dev/null || true

# 2. Rebuild from Dockerfile
cd ~/sources/amd-strix-halo-toolboxes/toolboxes
podman build -f Dockerfile.vulkan-amdvlk -t llama-vulkan-amdvlk:latest .
distrobox create --image llama-vulkan-amdvlk:latest --name llama-vulkan-amdvlk-new
# Then migrate router service or rename container
```

## Building llama.cpp from source

**Source location:** `~/sources/llama.cpp` (host) — NOT downloaded tarballs.

```bash
cd ~/sources/llama.cpp
git pull origin master  # or checkout a specific branch/tag
```

**Install to user-local prefix** (when /usr is not writable in the distrobox):
```bash
distrobox enter llama-vulkan-amdvlk -- bash -c '
cd /run/host/home/cricri/sources/llama.cpp && \
cmake -S . -B build -G Ninja \
  -DGGML_VULKAN=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_RPC=ON \
  -DCMAKE_INSTALL_PREFIX=/home/cricri/.local \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=ON \
  -DLLAMA_BUILD_SERVER=ON && \
cmake --build build --config Release -j$(nproc) && \
cmake --install build --config Release
'
```
Then run with `export LD_LIBRARY_PATH=/home/cricri/.local/lib64:$LD_LIBRARY_PATH` to pick up shared libs.

**Discard a fork branch after PR merges:**
```bash
git checkout master
git branch -D pr-<PR_NUMBER>-<name>
git merge --ff-only origin/master
```

**Building from a PR branch:**
```bash
cd ~/sources/llama.cpp
git fetch origin pull/<PR_NUMBER>/head:pr-<PR_NUMBER>-<name>
git checkout pr-<PR_NUMBER>-<name>
# Then run the build command above
```

**CMake flags (from Dockerfile.vulkan-amdvlk):**
- `GGML_VULKAN=ON` — Vulkan backend
- `GGML_RPC=ON` — Remote procedure call support
- `CMAKE_BUILD_TYPE=Release`
- `LLAMA_BUILD_SERVER=ON`
- `LLAMA_BUILD_TESTS=OFF`
- `LLAMA_BUILD_EXAMPLES=ON`

Note: After rebuild, test llama-cli immediately. If it crashes with `GGML_ASSERT(i01 >= 0 && i01 < ne01)`, this is a llama.cpp master regression — version 8920 is known stable, 9210 crashes on RADV. Restart container between runs for clean GPU memory state.

## MTP Speculative Decoding Verification

After building, verify `--spec-type draft-mtp` works:

### 1. Check flag availability
```bash
llama-server --help 2>&1 | grep "spec-type"
# Must show draft-mtp in the value list
```

### 2. Determine MTP model layout — two patterns:

**Embedded MTP** (single GGUF, e.g. Qwen3.6-27B-mtp):
```
n_layer_all > n_layer, has nextn_predict_layers KV
```
Usage:
```bash
llama-server --model model.gguf -c 2048 -ngl 999 --flash-attn on \
  --spec-type draft-mtp --spec-draft-n-max 3
```

**Separate MTP file** (e.g. Step-3.7-Flash trunk + Step-3.7-Flash-MTP):
```
Trunk: n_layer_all == n_layer, no nextn KV
MTP file: has nextn_predict_layers (often 3), contains blk.45-47.nextn.* tensors
```
Usage:
```bash
llama-server \
  --model trunk.gguf -md mtp-file.gguf \
  -c 2048 -ngl 999 --flash-attn on -ngld 999 \
  --spec-type draft-mtp --spec-draft-n-max 3
```

### 3. Verify MTP is active
Send a completion and check response `timings` for `draft_n` / `draft_n_accepted` fields.
Server log should show: `"adding speculative implementation 'draft-mtp'"`.

### 4. Chain heads mode (step35 multi-block MTP)
Auto-detected when `n_mtp_layers > 1` and NOT Gemma4 shared-memory. The driver cycles through MTP heads sequentially per draft step via `set_nextn_layer_offset()`. No special flags needed.

### MTP pitfalls
- **APEX Compact and Unsloth quantized models often strip MTP layers** — check that `n_layer_all > n_layer` or that a separate `-MTP-` file exists.
- **`--flash-attn on` (not `--fa on`)** — newer builds (b9756+) use `--flash-attn on` with a space; `--fa on` gives `invalid argument`.
- **`--simple-io` flag** — without it, `llama-cli` enters interactive mode and floods output with `> ` prompts when piping or timing out. Always add `--simple-io` for scripted tests.

## Zombie Process Cleanup (critical)

`distrobox enter` sessions that time out or are killed leave orphaned `llama-cli`/`llama-server` processes inside the container. These hold the model in memory, peg CPU at 98%, and consume GPU — the user will see 100% APU usage with no obvious cause.

**Symptom:** `ps aux | grep llama` shows multiple processes at 98% CPU, each holding 10-20GB RAM, from previous test sessions.

**Fix:**
```bash
pkill -9 llama-cli
pkill -9 llama-server
# Verify GPU is released
cat /sys/class/drm/card*/device/gpu_busy_percent  # should be 0
```

**Prevention:** Always kill test servers explicitly after testing:
```bash
kill $(ps aux | grep "llama-server.*PORT" | grep -v grep | awk '{print $2}') 2>/dev/null
```

## Post-Rebuild Host Library Sync

After rebuilding llama.cpp inside the distrobox, the host-side router binary (`~/.local/bin/llama-server`) still needs the new shared libraries. The router script sets `LD_LIBRARY_PATH=/tmp/llama.cpp-update/build/bin`.

**Copy new libs from build dir to router's expected path:**
```bash
mkdir -p /tmp/llama.cpp-update/build/bin
cp ~/sources/llama.cpp/build/bin/libllama-server-impl.so /tmp/llama.cpp-update/build/bin/
cp ~/sources/llama.cpp/build/bin/libllama-common.so* /tmp/llama.cpp-update/build/bin/
cp ~/sources/llama.cpp/build/bin/libmtmd.so* /tmp/llama.cpp-update/build/bin/
cp ~/sources/llama.cpp/build/bin/libllama.so* /tmp/llama.cpp-update/build/bin/
cp ~/sources/llama.cpp/build/bin/libggml*.so* /tmp/llama.cpp-update/build/bin/
# Verify resolution
LD_LIBRARY_PATH=/tmp/llama.cpp-update/build/bin ldd ~/.local/bin/llama-server | grep "not found"
# Empty output = all resolved
```

## Common Failures
| Exit | Cause | Fix |
|---|---|---|
| 1 | OOM / GPU memory exhausted | Restart RADV container before run |
| 125 | distrobox-enter quoting bug | Use script-file approach above |
| 1 | `failed to create MTP context` | Model lacks MTP layers OR missing `-md` for separate MTP file |
| abort | HTTP bind error (port in use) | Pick a different port |
| 124 | Interactive mode flood (timeout) | Add `--simple-io` flag to `llama-cli` |
| 98% CPU | Zombie llama processes from timed-out distrobox sessions | `pkill -9 llama-cli llama-server` |

## llama.cpp Version Notes
- **b9756+** (2026-06-22): Has PR #24340 (Step3.5/3.7 flash mtp3 with chain_heads). Does NOT support `deepseek4` architecture.
- **b9741** (2026-06-20): No multi-block MTP chain. Does NOT support `deepseek4`.
- **b9205** (2026-05-18): Missing newer architectures.
- **b8920**: Known stable for benchmarking.
- Master builds can crash with `GGML_ASSERT(i01 >= 0 && i01 < ne01)` on Vulkan — benchmark after each major update.
