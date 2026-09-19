---
name: custom-llama-cpp-build
description: Build llama.cpp from a vendor fork or unreleased PR for model architectures not yet supported by the installed router binary. Covers fork selection, cmake setup, Vulkan/RADV support for Strix Halo, compile-error patching, and standalone server setup alongside the existing router.
version: 1.3.0---
---

# Custom llama.cpp Build

## When to use

- A model's GGUF architecture (e.g. `laguna`, unreleased MoE) is not recognized by the installed distrobox llama-server — `Unknown model architecture` on load
- The model card says "llama.cpp support is in PR #N" or points to a vendor fork
- You need to serve the model standalone without modifying the existing router/service deployment

## Workflow

See `references/laguna-s2-patch.md` for a worked example of patching upstream b10087 to support a model variant not included in the merged PR.

See `references/laguna-dflash-decoder-contract.md` for the Laguna DFlash speculative-decoding situation: upstream's merged PR #25165 covers the target architecture **only**; the Laguna-specific DFlash decoder contract (causal attention, per-aux norms, attention gate, pre-norm state capture) lives only on poolside's `laguna` fork and has no upstream PR yet. If your draft GGUF embeds `dflash.decoder_arch = laguna`, you need the fork — generic upstream DFlash runs it with wrong (non-causal) attention.

See `references/qwen4exp-rocmfpx-build.md` for the worked Qwen3.8-Flash-Next (qwen4exp) case: the ROCmFP4 quant fork build (dedicated `llama-vulkan-qwen4` distrobox, `-j8`), the ROCmFP4-fast vs UD-IQ4_XS model files and sizes, MTP spec decoding, and the 6-axis eval battery (perplexity / throughput-vs-depth / VRAM residency / MTP / sanity / agentic).

### 1. Find the right source

Check the model card's "Usage → llama.cpp" section. Prioritize in this order:

1. **Upstream llama.cpp release tag** — If the model architecture was merged upstream, use the release tag (e.g. `b10087` for Laguna). **Always prefer upstream** — it has the most recent Vulkan backend, fastest bug fixes, and broadest hardware support.
2. **Vendor's official fork** with a dedicated branch — only if the architecture isn't upstream yet.
3. **Upstream PR** (ggml-org/llama.cpp#N) — may need to `gh pr checkout N`
4. A community branch if neither exists (riskier)

**Why upstream first:** Vendor forks often lag on Vulkan backend versions. For example, poolsideai's `laguna` branch ships Vulkan v0.16 which cannot detect Strix Halo GPU (gfx1151), while upstream b10087 has Vulkan v0.17 which works fine. A fork that loads the model on an RTX 2080 Ti may silently fall back to CPU on Strix Halo with "no usable GPU found".

**When upstream needs patches** (common pattern): Upstream may merge support for SOME model variants but not all. E.g., upstream b10087 merged Laguna XS.2 (40-layer) and M.1 (70-layer) but NOT S 2.1 (48-layer). The fix is a small patch, not a fork swap. See `references/laguna-s2-patch.md` for the exact diff.

### 2. Clone and build

```bash
# Inside distrobox (required for Vulkan support on Strix Halo)
distrobox enter llama-vulkan-amdvlk -- bash -c '
  cd ~/sources/llama.cpp && \
  git checkout b10087 && \
  cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON && \
  cmake --build build -j --target llama-server
'

# Verify Vulkan: the binary loads without "no usable GPU found"
distrobox enter llama-vulkan-amdvlk -- bash -c '
  LD_LIBRARY_PATH="$HOME/sources/llama.cpp/build/bin" \
  "$HOME/sources/llama.cpp/build/bin/llama-server" --version
'
```

**Important:** The binary requires `LD_LIBRARY_PATH` set to the build directory at runtime because it depends on `libllama-server-impl.so` and other `.so` files in the same directory. The distrobox's system `llama-server` binary is a thin wrapper that fails without these. Use one of:
- Set `LD_LIBRARY_PATH` in the start script
- Copy the entire `build/bin/` directory to a persistent location and reference it there

### 3. Fix common compile errors

| Error | Fix |
|---|---|
| `'isfinite' is not a member of 'std'` in `common/speculative.cpp` | Add `#include <cmath>` at line ~14, after `#include <algorithm>` |
| `OpenSSL not found, HTTPS support disabled` | Harmless for local serving — ignore |
| `vendor/` not found / cmake scaffolding missing | Clone upstream `ggml-org/llama.cpp` as a donor, copy missing dirs |

### 4. Build inside distrobox with Vulkan\n\n**Always build inside a distrobox** (not the host — the host build sees `no usable GPU found`; Strix Halo requires Vulkan dev headers only available inside a distrobox).

**Use a DEDICATED distrobox, not the production one.** The production container `llama-vulkan-amdvlk` runs model-manager + the router; an experimental/unstable fork build does not belong there (user preference — a build there risks the router and loads shader-compile pressure onto the same VM that serves models). Create a fresh clone of the same toolbox image per fork and build there:

```bash
distrobox create --name llama-vulkan-<fork> --image docker.io/kyuz0/amd-strix-halo-toolboxes:vulkan-amdvlk --yes
# same image == same glslc/cmake/vulkan-headers toolchain
```

The build artifacts live on the host-mount (`/mnt/data2/sources/...`, shared across distroboxes), so a partial build survives across containers — a re-run in the new container resumes where a killed build left off.

```bash
distrobox enter llama-vulkan-amdvlk -- bash -c \
  'cd ~/sources/llama.cpp-<arch> && \
   cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON && \
   cmake --build build -j --target llama-server'
```

**Key env var for Vulkan GPU detection on Strix Halo:**
```bash
export VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/radeon_icd.x86_64.json"
```
Without this, the built binary may see "no usable GPU found" even when Vulkan was enabled at build time. The exact ICD path may differ between the host and the distrobox — check both:
```bash
ls -la /usr/share/vulkan/icd.d/*radeon*   # host
distrobox enter llama-vulkan-amdvlk -- ls /usr/share/vulkan/icd.d/*radeon*  # distrobox
```

**Verify Vulkan works:**
```bash
distrobox enter llama-vulkan-amdvlk -- \
  env LD_LIBRARY_PATH=/home/cricri/sources/llama.cpp/build/bin \
  VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json \
  /home/cricri/sources/llama.cpp/build/bin/llama-server --version
```
```

### 5. Create start script

Write `~/llm-server/start-<arch>.sh`:

```bash
#!/bin/bash
# Start <Model Name> on dedicated port
set -e
PID_FILE="/tmp/llama-server-<arch>.pid"
LOG_FILE="/tmp/llama-server-<arch>.log"

[ -f "$PID_FILE" ] && kill $(cat "$PID_FILE") 2>/dev/null && sleep 2

# Build directory (must be set for LD_LIBRARY_PATH to find .so files)
LLAMA_BUILD_DIR="$HOME/sources/llama.cpp/build/bin"
LLAMA_SERVER="$LLAMA_BUILD_DIR/llama-server"

if [ ! -x "$LLAMA_SERVER" ]; then
    echo "ERROR: $LLAMA_SERVER not found"
    exit 1
fi

export VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/radeon_icd.x86_64.json"

distrobox enter llama-vulkan-amdvlk -- \
  env LD_LIBRARY_PATH="$LLAMA_BUILD_DIR" \
  "$LLAMA_SERVER" \
    --host 0.0.0.0 --port 8082 \
    --model /path/to/model-shard-00001-of-N.gguf \
    --jinja --flash-attn on --n-gpu-layers 999 --ctx-size 16384 \
    --mmap --temp 0.6 --top-p 0.95 --min-p 0.01 \
    --batch-size 2048 --ubatch-size 512 --threads 8 --metrics

# Wait for readiness
echo -n "Waiting for model to load..."
for i in $(seq 1 300); do
    if curl -s http://localhost:8082/health > /dev/null 2>&1; then
        echo " ready after ${i}s!"
        exit 0
    fi
    sleep 1
done
echo " timeout after 300s"
exit 1
```

### 6. Add preset entry (for documentation)

Add a `[model-name]` section to `~/llm-server/router-preset.ini` with `load-on-startup = 0`. The stock router won't load it, but the config block serves as canonical reference. Annotate with comments noting the custom binary path and port.

## Pitfalls

- **LD_LIBRARY_PATH needed at runtime** — The llama-server binary depends on `libllama-server-impl.so`, `libllama.so`, etc. in the same directory. The distrobox's system `llama-server` is a thin wrapper that fails with `error while loading shared libraries: libllama-server-impl.so`. Always set `LD_LIBRARY_PATH` in the start script.

- **VK_ICD_FILENAMES needed on Strix Halo** — Without this env var, the built binary sees "no usable GPU found" and falls back to CPU (too slow for 69GB models). Set to `/usr/share/vulkan/icd.d/radeon_icd.x86_64.json`. The path differs between host (`radeon_icd.json`) and distrobox (`radeon_icd.x86_64.json`).

- **Speculative decoding args renamed in b10087+** — llama.cpp renamed argument names. Catch old names with `--help | grep 'the argument has been removed'`:
  | Old name | New name |
  |---|---|
  | `--draft-max` | `--spec-draft-n-max` |
  | `--draft-min` | `--spec-draft-n-min` |
  | `--draft-p-min` | `--spec-draft-p-min` |
  `--model-draft` still works (aliased to `--spec-draft-model`). This affects launch scripts, router-preset.ini entries, and any saved examples.

- **Never test large models without unloading others first** — Loading a 69GB model alongside other loaded models (even idle ones) may OOM on 128GB unified memory. Before testing on the production distrobox, unload non-essential models through model-manager. Keep small models Hermes relies on (e.g. qwen35-9b at ~9GB) and unload the rest. Or use a dedicated test port (8090) with a standalone server — this avoids touching the router entirely.
- **Kill lingering processes**: After interrupted test sessions, orphan llama-server processes hold the port. Clean up with `pkill -9 -f "llama-server.*port <PORT>"`. A `kill -9` on the tracked background wrapper may NOT kill the detached cmake build — verify with `ps -eo pid,%cpu,comm | grep -E 'cc1plus|cmake|cc1'` and kill the actual compiler PIDs.

- **Use bounded parallelism on the no-swap Strix Halo box** — an unbounded `cmake --build -j` on 32 cores + Vulkan shader compilation (`glslc` spawns)` spiked load to ~85 and **hard-crashed the machine** (no swap, so OOM is fatal — hours of lost work). Always build `-j8` (or fewer) and in the background (`background=true, notify`), watching `free -g` / `/proc/loadavg` during the build. This is true of the production container too — never run `-j` unbounded.

- **Verify GPU detection with `llama-cli --list-devices`, not `--version`** — `llama-server --version` succeeds even if Vulkan silently fell back to CPU. `llama-cli --list-devices` (with `LD_LIBRARY_PATH=build/bin` + `VK_ICD_FILENAMES`) prints the actual adapter, e.g. `Vulkan0: AMD Radeon 8060S (RADV GFX1151) (127488 MiB, ...)`. Fail-fast on this before running any benchmark. Do NOT probe with a `models/*.gguf` vocab file — vocab-only GGUFs are not loadable as models (`failed to load model`).
- **DFlash2 engine is on the strix fork's `strix-halo-vulkan` branch, not upstream** — Upstream has generic DFlash (v1 block-diffusion), but the DFlash2 engine (2-tap grouped depthwise conv + candidate selector, upstream PR #27342 by Jian Chen) is only on `Nathanw1014/llama.cpp` branch `strix-halo-vulkan`. The `Nathanw1014/strix-halo-llamacpp` repo is the *toolbox* (build scripts + benchmark docs), NOT the engine. Clone the fork: `git clone --branch strix-halo-vulkan --single-branch https://github.com/Nathanw1014/llama.cpp.git`. Detect DFlash2 at load: engine sets `is_dflash2` from `dflash.selector_top_k > 0` in the draft GGUF metadata (dflash2 builds also carry `dflash.selector_rank`, `dflash.conv_kernel_size=2`, `dflash.conv_group_size`). Verify with the repo's `gguf-py` reader. `--spec-type draft-dflash --spec-draft-n-max 4`; confirmed active via `draft_n`/`draft_n_accepted` in completion `timings`.
- **A distrobox-built Vulkan binary runs on the host** (like production) — build inside `llama-vulkan-amdvlk` with `-DGGML_VULKAN=ON -DGGML_NATIVE=ON -DBUILD_SHARED_LIBS=ON`, then run on the host with `LD_LIBRARY_PATH=<build>/bin` AND `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json` (the real host RADV ICD; without VK_ICD_FILENAMES it silently falls back to CPU backend). Host-path check: `/home/cricri/sources` is a symlink to `/mnt/data2/sources`, so `/home/cricri/sources/llama.cpp-<branch>/build/bin` works.
- **Laguna DFlash draft needs the poolside fork, not upstream** — Upstream has generic DFlash and the Laguna target model, but the Laguna-specific DFlash decoder contract was never merged upstream. If you load a Laguna DFlash GGUF (with `dflash.decoder_arch = laguna` metadata) on an upstream build, the drafter runs with non-causal attention, no per-aux norms, no attention gate, and no pre-norm state capture. Draft quality is severely degraded. Use the poolsideai `laguna` branch (see `references/laguna-dflash-decoder-contract.md`).
