# amd-strix-halo-toolboxes: choosing the right toolbox tag

Pre-built llama.cpp containers for gfx1151 live in `~/sources/amd-strix-halo-toolboxes/`. The authoritative maps: `README.md` (tag table) and `refresh-toolboxes.sh` (the `TOOLBOXES` dict with exact image refs + `--device /dev/dri --device /dev/kfd --group-add video --group-add render --group-add sudo --security-opt seccomp=unconfined`).

## Qwen3.8-Flash-Next (qwen4exp) ROCm tags

| tag | fork / purpose | notes |
|---|---|---|
| `rocm-10.0-qwen-3.8-flash-next` | drluoto `strix-halo-flash-next` | native MTP, ngram-mod, `GGML_HIP_NO_VMM=ON`, no rocWMMA. NO engram support. |
| `rocm-10.0-engramhalo` | Aristo94 `EngramHalo.cpp:strix-halo-qwen4exp` | sparse QSA gather, SSD-backed engram loading (.hgn), standalone MTP sidecar. This is the ONLY tag that reads engram .hgn files. Needs `-lm mmap --lazy-mode on` (NOT `--no-mmap`), one slot, at most `-c 163840` with external MTP. Validated on ROCm 7.14 upstream; the 10.0 image is experimental. |
| `rocm-10.0` | stable ROCm core | no qwen4exp-specific fork work |
| `rocm-10.0-strix-llama` | halo-box retained-PM4 | measured 1207 t/s pp on Qwen3.8-Flash-Next Q4_K_XL |
| `rocm-10.0-rocmfpx` | ROCmFPX HIP | ROCmI4/W4A4, FP3/4/6/8 weights, MTP |

## Decision rule

- User has `.hgn` engram files in the model dir (e.g. `qwen38-flash-next-w4b.hgn`) → must use `rocm-10.0-engramhalo`, plain `rocm-10.0-qwen-3.8-flash-next` cannot load them.
- Download a Signal/fine-tune GGUF per model card tiers (AP-Q4_K_XL vs AP-IQ4_XS vs Q8_0): pick tier by VRAM fit, the link in the card's Running section gives the launch flags and separate MTP draft repo.
- `distrobox list` returning empty is NOT proof no containers exist — check the podman DB when podman state is broken (see `references/podman-state-repair.md`).

## Downloading the GGUF (with MTP draft)

- `df -h` FIRST — multi-hundred-GB quants on a disk at 88% need old quant shards deleted (ask user first) before there is room.
- Plain `wget -c -O <dir>/<file>.gguf "https://huggingface.co/<org>/<repo>/resolve/main/<subfolder>/<file>.gguf"` beats the hf CLI for one-off large pulls; `-c` resumes. Sustains ~50-60 MB/s; run it background+notify.
- The MTP draft head is usually a SEPARATE HF repo (e.g. `Qwen3.8-Flash-Next-MTP-Q8_0-GGUF`) — read the model card's Running/tier table, not just the repo tree.
- Tiers appear as subfolders (e.g. `AP-Q4_K_XL/Signal-...-AP-Q4_K_XL.gguf`); the repo tree page shows the real layout.
