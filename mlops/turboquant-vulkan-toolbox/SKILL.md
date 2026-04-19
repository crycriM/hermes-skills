---
name: turboquant-vulkan-toolbox
description: Build TurboQuant KV cache compression llama.cpp toolbox for AMD Strix Halo (gfx1151). Covers Vulkan fork (broken on gfx1151), HIP fork (working), Dockerfile patterns, and container setup.
version: 2.0
---

# TurboQuant Toolbox for AMD Strix Halo

Build llama.cpp toolbox containers with TurboQuant KV cache compression for AMD RDNA3.5 / gfx1151.

## Fork Landscape

| Fork | Backend | API Style | Status on gfx1151 |
|------|---------|-----------|-------------------|
| `AmesianX/TurboQuant` (35★) | CUDA only | `--cache-type-k turbo4` | N/A (CUDA) |
| `jimliddle/turboquant-amd-vulkan` (3★) | Vulkan | `--kv-codec turboquant --kv-tq-runtime vulkan` | BROKEN — shader workgroup assertion crash |
| `domvox/llama.cpp-turboquant-hip` (4★) | ROCm HIP | `--cache-type-k turbo4` | Working (AmesianX API) |

**Use `domvox/llama.cpp-turboquant-hip` for Strix Halo.**

## HIP Fork (Recommended)

Dockerfile: `~/sources/amd-strix-halo-toolboxes/toolboxes/Dockerfile.hip-turboquant`

```bash
cd ~/sources/amd-strix-halo-toolboxes/toolboxes
podman build --no-cache -t kyuz0/amd-strix-halo-toolboxes:hip-turboquant \
  -f Dockerfile.hip-turboquant .
```

The HIP fork has a complete repo (vendor/, cmake/, examples/ all present), so no cmake scaffolding needed. Uses the same Fedora ROCm toolchain as the standard HIP build (`Dockerfile.rocm-6.4.4`).

### Build Fix: RPC Opcount Mismatch

The fork adds `GGML_OP_TURBO_WHT` etc., bumping `GGML_OP_COUNT` from 96 to 97. This breaks the static assertion in `ggml-rpc.h`. Fix with sed in the Dockerfile before cmake:

```dockerfile
RUN ... \
  && sed -i 's/RPC_PROTO_PATCH_VERSION    1/RPC_PROTO_PATCH_VERSION    2/' ggml/include/ggml-rpc.h \
  && sed -i 's/GGML_OP_COUNT == 96/GGML_OP_COUNT == 97/' ggml/include/ggml-rpc.h \
  && HIPCXX="..." cmake ...
```

A traditional patch file won't work — the hunk fails due to whitespace differences in the Dockerfile COPY context. Inline sed is reliable.

### Key cmake flags

```
-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1151 -DLLAMA_HIP_UMA=ON
```

### Usage with llama-server

```bash
llama-server \
  -m /path/to/model.gguf \
  --mmproj /path/to/mmproj.gguf \
  -ngl 999 -c 262144 \
  --cache-type-k turbo4 --cache-type-v turbo4 \
  --flash-attn on --fit on --jinja \
  --reasoning-format auto \
  --host 0.0.0.0 --port 8085
```

Available cache types: `turbo2`, `turbo3`, `turbo4` (maps to GGML_TYPE_TURBO2_0/3_0/4_0).

## Vulkan Fork (BROKEN on gfx1151)

Dockerfile: `~/sources/amd-strix-halo-toolboxes/toolboxes/Dockerfile.vulkan-amdvlk-turboquant`

The Vulkan fork crashes at `ggml-vulkan.cpp:6685` with a workgroup count assertion during TurboQuant shadow sync. This happens regardless of `--kv-tq-qjl`, `--kv-tq-fallback`, or `--kv-tq-group-size` settings. The fork's Vulkan shaders have dispatch math incompatible with RADV gfx1151 limits.

The Vulkan fork image still works for standard (non-TurboQuant) inference.

### Vulkan Fork Dockerfile Pitfalls

If you ever need to rebuild the Vulkan image, the fork (`jimliddle/turboquant-amd-vulkan`) has a broken repo layout requiring extensive cmake scaffolding:

- Source lives under `source/` subdirectory, not at repo root
- Missing `vendor/`, `examples/`, `pocs/`, cmake templates — must clone mainline as donor
- `cmake/git-vars.cmake` (must have `.cmake` extension — CMake's `include()` appends it)
- `cmake/common.cmake` needs `llama_add_compile_flags()` stub function that includes `ggml/cmake/common.cmake`
- `cmake/license.cmake` must generate a real `license.cpp` with `const char* LICENSES[] = { nullptr };` — empty stub causes linker error
- `cmake/build-info.cmake` with BUILD_NUMBER/COMMIT/COMPILER/TARGET
- `cmake/llama-config.cmake.in` and `cmake/llama.pc.in` copied from mainline
- `convert_hf_to_gguf.py` stub (touched empty — install step expects it)
- All cmake prep must be in a single RUN step (layer boundary issues with separate steps)

## Container Setup

### Pitfall: Distrobox drops `--device` flags with host networking

`distrobox create --additional-flags "--device /dev/dri --group-add video"` silently ignores the device flags when host networking is used (which is the default). The container starts but `llama-cli --list-devices` shows nothing. Use `--privileged` or create the container directly with podman instead.

### Option A: Raw podman (recommended for GPU toolboxes)

```bash
podman run -d \
  --name llama-vulkan-radv \
  --privileged \
  --security-opt seccomp=unconfined \
  --network host \
  -v /home/cricri:/home/cricri \
  -v /mnt/data2:/mnt/data2 \
  localhost/vulkan-radv-latest \
  sleep infinity

# Verify GPU access
podman exec llama-vulkan-radv llama-cli --list-devices

# Run server
podman exec llama-vulkan-radv llama-server \
  -m /path/to/model.gguf \
  --host 0.0.0.0 --port 8099 \
  -c 8192 -ngl 999 -fa 1 --no-mmap -t 8
```

### Option B: Distrobox (for interactive use)

```bash
# Create HIP TurboQuant toolbox
distrobox create --name llama-hip-turboquant \
  --image localhost/kyuz0/amd-strix-halo-toolboxes:hip-turboquant \
  --additional-flags "--device /dev/kfd --device /dev/dri --group-add video --group-add render" \
  --yes

# If no local registry, pipe through podman save:
# podman save localhost/kyuz0/...:hip-turboquant | distrobox create --name llama-hip-turboquant \
#   --image localhost/kyuz0/...:hip-turboquant --additional-flags "..." --yes --import-archive -
```

## Start Script Template

```bash
#!/bin/bash
# ~/llm-server/start-hip-turboquant-ornstein.sh
exec /usr/local/bin/llama-server \
  -m /home/cricri/models/Ornstein-27B-Q4_K_M.gguf \
  --mmproj /home/cricri/models/mmproj-Qwen3.5-27B-F16.gguf \
  -ngl 999 -c 65536 \
  --cache-type-k turbo4 --cache-type-v turbo4 \
  --flash-attn on --fit on --jinja \
  --reasoning-format auto \
  --host 0.0.0.0 --port 8085 \
  -t 8 -b 2048 -ub 1024 \
  --temp 0.6 --top-p 0.95 --min-p 0.01 --repeat-penalty 1.0
```

Note: Ornstein-27B is Qwen3.5 27B based, uses `mmproj-Qwen3.5-27B-F16.gguf` for vision (separate file, not embedded).

## General Dockerfile Pitfalls (podman imagebuilder)

- NO heredocs in RUN commands — imagebuilder splits them into separate steps. Use `printf` with `\n` instead.
- podman truncates build output in notifications — use `process log` with offset to see full output.
- `cmake --install` may fail on missing files — check what the fork expects vs what it provides.
- With `-j$(nproc)` parallel HIP builds, OOM can cause silent failures. Use `-j4` for safety on 32-thread machines.

## Performance on Strix Halo (gfx1151)

Benchmarks with Ornstein-27B (Qwen3.5 27B dense Q4_K_M), 64k context, sharing GPU with router + 2 models:

| Build | Backend | TurboQuant | Speed |
|-------|---------|------------|-------|
| Vulkan (amdvlk) | Vulkan | No | 12 t/s |
| HIP (ROCm) | ROCm | No | 10.5 t/s |
| HIP (ROCm) | ROCm | turbo4 | 10 t/s |

HIP is ~15% slower than Vulkan across the board on gfx1151. TurboQuant adds ~0.5 t/s decompression overhead. The tradeoff: HIP+TQ enables 128k+ context without OOM (33% KV cache reduction observed: 990 MiB compute buffer vs 1474 MiB Vulkan). Use Vulkan for short-context speed, HIP+TQ for long-context capacity.

## Architecture Support

The HIP fork supports gemma4 architecture (`llm_build_gemma4_iswa`). Tested with `gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf` (MoE).

### Gemma 4 26B-A4B `<unused24>` Bug (gfx1151)

Known issue (GitHub #21321, #21416, #21425, #21516): Gemma 4 26B MoE generates `<unused24>` tokens in infinite loop. Affects Unsloth Dynamic quants (`UD-*`) specifically. The 31B dense works fine.

**Status as of April 2026 (latest llama.cpp master):**
- **Vulkan RADV**: FIXED — works correctly with full GPU offload (`-ngl 999`). ~49 t/s decode on Strix Halo. Chat template triggers a compatibility workaround warning but works fine.
- **ROCm/gfx1151**: Still broken. Deterministic failure with full GPU offload.

Workarounds for ROCm:
- `--reasoning-budget 0` helps some setups but not gfx1151
- Partial GPU offload (`-ngl 40` instead of 999) reportedly works around the issue
- Use official `ggml-org` quants instead of Unsloth Dynamic
- The bug is in ROCm kernel behavior with MoE routing, not a sampling or template issue

## What TurboQuant Actually Does

- Near-lossless KV cache compression (~4-5x memory reduction)
- Helps most with long-context generation (decode speed), not prefill
- Does NOT reduce model weight size — only KV cache
- Based on Google DeepMind paper (ICLR 2026): Walsh-Hadamard Transform + Lloyd-Max quantization with QJL correction
- `turbo4` = 4-bit (3-bit PolarQuant + 1-bit QJL), `turbo3` = 3-bit, `turbo2` = 2-bit (no QJL)
