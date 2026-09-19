# Qwen3.8-Flash-Next (qwen4exp) + ROCmFP4 quant build & eval

Session-specific detail for building and evaluating the ROCmFP4-fast quant of Qwen3.8-Flash-Next on Strix Halo (2026-08-31). General workflow lives in `../SKILL.md`.

## The fork

- `LaurentZuijdwijk/llama.cpp`, branch `vulkan/qwen4exp-rocmfpx`. Build `3466b4880`.
- Needed for two things upstream (post-ggml/llama.cpp#27742) does not carry: the **ROCmFPx quant types** (Q4_0_ROCMFP4/FAST, Q6/Q8/Q3/Q2_0_ROCMFPX) and the **per-head PLE split** (the 51.2 B-param n-gram table). Upstream reads the PLE joined as one ~20.9 GiB tensor, which exceeds the Vulkan 4 GiB `maxStorageBufferRange` -> swaps on long context.
- The fork's own `ROCMFPX-NOTES.md` in-repo is the authoritative status doc (merge list, kernel perf fixes 2026-08-21, MMVQ-on-by-default for n>1, batched-decode fixes). Check `git log` freshness on the branch before trusting it.

## Build (isolated, bounded)

```bash
distrobox create --name llama-vulkan-qwen4 --image docker.io/kyuz0/amd-strix-halo-toolboxes:vulkan-amdvlk --yes
distrobox enter llama-vulkan-qwen4 -- bash -c '
  git clone --branch vulkan/qwen4exp-rocmfpx --single-branch https://github.com/LaurentZuijdwijk/llama.cpp.git /mnt/data2/sources/llama.cpp-qwen4exp-rocmfpx
  cd /mnt/data2/sources/llama.cpp-qwen4exp-rocmfpx
  cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON
  cmake --build build -j8 --target llama-server llama-cli
'
# verify GPU, NOT --version:
#   LD_LIBRARY_PATH=build/bin VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json \
#   build/bin/llama-cli --list-devices
#   -> Vulkan0: AMD Radeon 8060S (RADV GFX1151)
```

## Model files (agentionai, 96 GiB carve-out targets)

Qwen3.8-Flash-Next = 125 B main + 51.2 B n-gram PLE, 6 B active/token, arch `qwen4exp`. Repos live in `~/models/qwen3.8-flash/` on `/mnt/data1` (~125 GiB free), which holds FAST **or** imatrix (**not both** -- 83.65 + 87.06 GiB):

| file | size | PPL (wikitext-2 raw) | notes |
|---|---|---|---|
| local unsloth `UD-IQ4_XS` (3 shards) | 87.25 GiB | (re-measure locally) | mainstream, upstream-compatible |
| `ROCmFP4-FAST` (5 shards) | 83.65 GiB | 4.6785 +/- 0.02780 | no imatrix; Q4_0_ROCMFP4_FAST experts + Q3_0_ROCMFPX PLE + Q6_K embd/output |
| `ROCmFP4-FAST-imatrix` `-v2-ple16.gguf` + `v2/` | 87.06 GiB | 4.1062 +/- 0.02329 (+2.48%) | **recommended**; root=per-head PLE (VRAM), `v2/`=joined (needs `--ngram-on-disk`); two layouts are same weights |
| `mtp/Qwen3.8-Flash-Next-MTP-ROCmFP4-FAST.gguf` | 2.28 GiB | -- | MTP spec-decoding head |

Card claims it beats AesSedai's AP-IQ4_XS on prefill and generation t/s at every context depth and beats their IQ4_XS quality at 20-30 GiB smaller -- but **those numbers are on AP-IQ4_XS, not our UD-IQ4_XS**, so re-measure on our box rather than trusting them.

## Run (fork, all-on-GPU)

```bash
build/bin/llama-server -m <first-shard-or-single.gguf> -ngl 99 -ctk q8_0 -ctv q8_0 -fa on
# MTP spec decoding:
#   -md <path>/Qwen3.8-Flash-Next-MTP-ROCmFP4-FAST.gguf --spec-type draft-mtp --spec-draft-adaptive \
#     --spec-draft-n-min 2 --spec-draft-n-max 4 --n-gpu-layers-draft 99
```
Quantized KV (`-ctk/-ctv q8_0`) ~= 12.75 KiB/token vs 24 at f16 -- what fits 87 GiB weights + full 262144-token ctx in the 96 GiB carve-out. Vision tower ships separately as `mmproj/mmproj-Qwen3.8-Flash-Next-f16.gguf`.

## Eval battery (axes)

1. Sanity: identical prompts, `--seed`-fixed, ensure GPU offload in load log + no `--ngram-on-disk`.
2. Perplexity: `llama-perplexity` wikitext-2 raw, 145 chunks `-c 2048`, same seed, derive local baselines (don't reuse card PPL).
3. Throughput-vs-depth: `llama-batched-bench` at {512,2048,8192,16384,32768} with q8_0 KV; quadrants {UD-IQ4_XS, ROCmFP4-imatrix} x {fork, upstream} (upstream can't run ROCmFP4 -- that gap is the fork's raison d'etre).
4. Spec decoding: MTP head (accept rate + t/s, prose/code/JSON -- acceptance is content-dependent).
5. VRAM residency: peak VRAM + host RAM with/without MTP at ctx 32k -- verify everything on GPU.
6. One agentic/structured-output spot-check on final two candidates.

Decision: imatrix root (per-head PLE) is the pick -- same size as non-imatrix, ~37% of the PPL gap closed, fully on GPU. Full plan written to `~/models/qwen3.8-flash/RESEARCH-PLAN.md`.
