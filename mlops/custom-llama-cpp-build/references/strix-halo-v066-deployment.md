# strix-halo-llamacpp v0.6.6 deployment (BOSGAME M5 / AXB35, Ryzen AI Max+ 395, 128 GiB)

Deployed 2026-08-20 for DeepSeek-V4-Flash-0731 (UD-IQ3_XXS, 4-file split 104.2 GB) + DSpark drafter.

## Getting the release
- v0.6.6 is a **GitHub release tarball**, NOT a ghcr tag. ghcr `vulkan` stable = v0.6.5 (0b0f35d).
- Source: `Nathanw1014/strix-halo-llamacpp` release `v0.6.6`; build string `b10569-7b6c6133`, source commit `7b6c61330` ("dequantise the cache for DeepSeek V4 sparse prefill").
- Asset: `strix-halo-llamacpp-vulkan-portable.tar.gz` (34 MB). Verify with `MANIFEST.txt` (source/mesa/libdrm/glslc pins).
- Extract into `~/sources/strix-halo-llamacpp/vulkan/`; build docker per README: `build-images.sh` → `strix-halo-llamacpp:vulkan` (Dockerfile `COPY vulkan /opt/strix-halo-llamacpp/vulkan`).

## Payload / launcher
- `vulkan/llama-server|llama-cli|llama-bench` are symlinks to `_run` wrapper, which sets the bundled driver + perf env:
  - `VK_ICD_FILENAMES=<payload>/driver/radeon_icd.x86_64.json` (bundled Mesa RADV `libvulkan_radeon.so` + libdrm 2.4.133)
  - `GGML_VK_MMID_ROWLISTS/SMALLN/BM64/WAVE32/F16B/M128=1` and `GGML_VK_FA_WAVE32=1`
- Real binaries in `vulkan/bin/`. `--version` → `build 10569, commit 7b6c6133`.
- Self-contained: runs on host (no host RADV dependency). Verified GPU detect: `Vulkan0 : Radeon 8060S (RADV STRIX_HALO)`, fused ops resolve (Flash Attn, Gated Delta Net, Lightning Indexer, DSV4 HC pre/comb/post).

## Live router cutover
`start-native-router.sh` (exec'd by `m5-router.service` through `distrobox enter llama-vulkan-amdvlk`):
```bash
export STRIX_HALO_VULKAN="/home/cricri/sources/strix-halo-llamacpp/vulkan"
export VK_ICD_FILENAMES="$STRIX_HALO_VULKAN/driver/radeon_icd.x86_64.json"
export VK_DRIVER_FILES="$VK_ICD_FILENAMES"
export LD_LIBRARY_PATH="$STRIX_HALO_VULKAN/driver:$STRIX_HALO_VULKAN/bin"
export GGML_VK_MMID_ROWLISTS=1 ... GGML_VK_FA_WAVE32=1
exec "$STRIX_HALO_VULKAN/llama-server" --host 0.0.0.0 --port 8080 --models-preset ... --models-max 4 --no-models-autoload --metrics
```

## Distrobox container crash → router exit 255
- Symptom: `systemctl --user status m5-router` shows `exit 255/EXCEPTION`, `Mem peak ~31MB` (llama never started). `distrobox enter` errors `OCI runtime error: crun: the container ... is not running`, even though `podman ps` lists it "Up". Root cause: container runtime died (conmon "prematurely exited").
- Fix: `podman stop llama-vulkan-amdvlk && podman start llama-vulkan-amdvlk`, then `systemctl --user restart m5-router`.
- Diagnose order: systemctl status (exit 255 = distrobox layer, not llama) → `distrobox enter` check → container restart.

## Memory contention / OOM on 128 GiB
- `load-on-startup=1` models (qwen36-35b ~35 GB + qwen38-27b-nothink ~27 GB each) drop MemAvailable to ~50 GB quickly, leaving no room for a 96 GB model. **User reports hard PC crash on OOM** → strongly avoid stacking models.
- Qualification runs DSV4 as a **dedicated single-model server** (`-np 1`). When loading ~100 GB model: pre-check `grep MemAvailable /proc/meminfo` (need ≥ model_size + ~10 GB), keep only the target loaded (set other startup models to `load-on-startup=0` or let model-manager auto-swap evict), confirm `curl :8080/v1/models` shows only target + small companions, then load via `:8079/api/load`.
- `mmap=true` on a ~100 GB model demand-pages weights from disk and tanks decode to ~6-8 t/s (I/O bound); use `no-mmap=true` (article/report both use `--no-mmap`).

## Qualified config (from pepuscz/strix-halo-deepseek-v4-flash, same box)
`-ngl 999 -ngld 999 -fa on -ctk q8_0 -ctv q8_0 -c 524288 -np 1 -b 2048 -ub 1024 -fit off --spec-type draft-dspark --spec-draft-n-max 4 --jinja`
- Results: prefill 218 t/s @122k (+67.5% vs 0.6.4), gen stable ~30.5 t/s, no OOM at 524288 ctx (9.5 GiB retained). 1M ctx OOMs. Largest qualified = 524288.
- `fit` key must be added to start-native-router.sh KNOWN_KEYS (was missing).
- Target = 4-file split `*-0000X-of-00004.gguf`; point `model=` at shard 1.
