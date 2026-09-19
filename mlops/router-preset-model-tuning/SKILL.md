---
name: router-preset-model-tuning
description: Onboard a new GGUF model into the llama.cpp router preset INI by translating vendor deployment guides into llama-server INI settings. Covers architecture analysis, memory-aware GPU layer allocation, chat template handling, and sampling parameter selection. For Strix Halo APU (gfx1151, 128GB unified RAM) with Vulkan RADV.
version: 1.4.0
---

# Router Preset Model Tuning

## When to use

Trigger when:
- A new model needs to be downloaded from HuggingFace and configured in `router-preset.ini`
- Performance of an existing model is unexpectedly slow vs comparable architectures
- A model has unusual architecture (MoE with non-standard routing, Mamba SSM, custom chat templates, thinking/reasoning modes)
- The model vendor publishes backend-specific serving configs (vLLM, SGLang, TRT-LLM)

## Prerequisites

- `hf` CLI installed and authenticated (`hf auth whoami`)
- Model files in GGUF format under `~/models/` or `/mnt/data2/models/`
- `router-preset.ini` at `~/llm-server/router-preset.ini`
- `start-native-router.sh` validation script at `~/llm-server/start-native-router.sh` (checks for unknown INI keys)
- `llama-server` binary in the `llama-vulkan-amdvlk` distrobox
- ~200GB free disk space (check with `df -h ~/models/`)
- Vulkan benchmark results at `~/llm-server/vulkan-bench-results.txt` for comparison
- GGUF metadata inspection reference at `references/gguf-metadata-inspection.md`
- E2B + 31B spec dec benchmark at `references/gemma4-31b-e2b-spec-dec-bench.md`
- Spec dec INI settings at `references/spec-dec-ini-settings.md`
- KNOWN_KEYS validator caveat at `references/known-keys-validator.md`
- Thinking suppression reference at `references/thinking-suppression-techniques.md`
- Hermes model catalog provisioning at `references/hermes-model-catalog-provisioning.md`
- Per-model reasoning budget config at `~/llm-server/model-manager-config.yaml`

## 0. Download from HuggingFace

Skip this step if the model is already downloaded.

```bash
# Single-file GGUF with specific quantization
hf download <org>/<repo> <filename>.Q4_K_M.gguf \
  --local-dir ~/models/<short-name>/

# Filter by glob for repos with many files
hf download <org>/<repo> --include "*Q4_K_M*" \
  --local-dir ~/models/<short-name>/
```

**Notes:**
- `hf` replaces the deprecated `huggingface-cli` — never use `huggingface-cli download`
- Use `--revision <branch/tag>` for non-main branches
- Token is cached at `~/.cache/huggingface/token`; verify with `hf auth whoami`
- Re-login if expired: `hf auth login --token $HF_TOKEN`

**Verify the download:**
```bash
ls -lh ~/models/<short-name>/
file ~/models/<short-name>/*.gguf  # should say "GGUF v3" or similar
```

**⚠️ Xet download failures:** The `hf` CLI may fail with `RuntimeError: File reconstruction error: Internal Writer Error: Background writer channel closed` when using Xet-based transfer. Two fallbacks:
1. Disable Xet: `HF_HUB_DISABLE_XET=1 hf download ...`
2. Direct wget (most reliable): `wget -c "https://huggingface.co/<org>/<repo>/resolve/main/<filename>" -O ~/models/<short-name>/<filename>`
   - Use `wget -c` (continue) to resume interrupted downloads
   - Check disk space first: `df -h ~/models/` — GGUF files are 15-90GB

**Check for companion files** — mmproj (vision), chat templates, tokenizer configs:
```bash
ls ~/models/<short-name>/ | grep -iE 'mmproj|chat_template|jinja|tokenizer'
```
If the initial download used `--include` (restrictive), you may need a second pass without the filter to grab these. If you ran a bare `hf download` (no `--include`), they're already there.

## Step-by-step workflow

### 1. Identify model architecture and capabilities

Two paths depending on source:

**A) HuggingFace model page** — for models not yet downloaded:
- **Quick Start / Deployment** — official serving commands for vLLM/SGLang/TRT-LLM
- **Model Architecture** — type (MoE, dense, Mamba+Attention hybrid, LatentMoE), active parameters, layer count
- **Minimum GPU requirement** — determines if VRAM allocation is realistic
- **Sampling parameters** — temperature, top_p (vendors often specify these)
- **Chat template** — look for custom `chat_template.jinja` or reasoning parser files
- **Context length** — max_position_embeddings
- **Vision support** — check for mmproj files, mentioned multimodal capabilities

**B) GGUF metadata inspection** — faster when the model is already downloaded:
- Preferred tool: `gguf-dump <model.gguf>` (smoke-test friendly, dumps all KVs)
- Fallback: Python parser at `references/gguf-metadata-inspection.md`
- Key fields to extract: `general.architecture`, `general.name`, `general.size_label`, `general.description` (provenance — pruning, quant, tuning), `block_count`, `context_length`, `expert_count`, `expert_used_count`, `leading_dense_block_count`, `rope.freq_base`
- **Vision detection signals** (see § Vision model setup below):
  - `tokenizer.ggml.pre = 'pixtral'` — multimodal tokenizer
  - `general.tags` includes `'multimodal'`
  - Separate `mmproj-*.gguf` file in the model directory
- **Baked-in sampling defaults**: check `general.sampling.temp` and `general.sampling.top_p` — use these as baseline rather than guessing

### 2. Analyze memory constraints

**Strix Halo APU uses unified memory (128GB RAM + GPU)** — the "512MB VRAM" figure in older docs is for discrete GPUs and DOES NOT apply here. HSA/Vulkan on APU shares system RAM with the GPU, so a 24GB F16 model can be fully offloaded:

```ini
n-gpu-layers = 999   # all layers to Vulkan; works on Strix Halo unified memory
```

CPU fallback for offloaded weights is acceptable on MoE but **not preferred** for dense models — the user has explicitly stated "no CPU fallback" as a default. Only reduce `n-gpu-layers` below `block_count` if you measure OOM or extreme slowdown.

For other hardware (discrete GPU, small VRAM):
```
# Layer VRAM budget estimation
# Each layer needs:
#   - model weights: varies by quantization and layer size
#   - Mamba SSM state: 128 (ssm_state_size) × float32 × num_layers
#     Example: 88 layers × 128 × 4 = ~45KB per layer just for SSM state
#
# Rule: n-gpu-layers should leave ~100MB headroom for KV cache and Vulkan overhead
```

**For MoE models** with large total but small active parameters:
- Only attention layers and routed expert weights are compute-critical
- On Strix Halo, `n-gpu-layers = total_layers` is fine — unified memory handles the rest
- On discrete GPUs with limited VRAM, expert weights dispatch from CPU (acceptable for MoE)

**For models with Mamba/SSM layers:**
- SSM state (128×float32 per layer) should stay in fast memory
- For 88-layer LatentMoE on Strix Halo, `n-gpu-layers = 999` is fine; on discrete GPUs `n-gpu-layers = 64` is the empirical ceiling

### 3. Map vendor serving flags to llama-server INI keys

Not all vLLM/SGLang flags map to llama-server. Common mappings:

| Vendor flag | llama-server INI key | Notes |
|---|---|---|
| `--tensor-parallel-size N` | not applicable | single-GPU only on APU |
| `--kv-cache-dtype fp8` | `kv-cache-type` (llama-server uses type, not dtype) | |
| `--enable-chunked-prefill` | `chunked-prefill = true` | |
| `--mamba-ssm-cache-dtype float16` | `cache-type-k`, `cache-type-v` | per-tensor quantization |
| `--max-model-len N` | `ctx-size = N` | |
| `--trust-remote-code` | implied (model loaded from local GGUF) | |
| `--reasoning-parser` | **not supported in llama.cpp** | document as gap |
| `chat_template_kwargs = {enable_thinking: True}` | `chat-template-kwargs` | JSON string |
| reasoning budget | `reasoning-budget` | llama-server supports this |

### 3b. Vision model setup (mmproj)

When the GGUF metadata or model card indicates multimodal/vision capabilities:

1. **Confirm vision support** via GGUF metadata flags:
   - `tokenizer.ggml.pre = 'pixtral'` — multimodal tokenizer
   - `general.tags` includes `'multimodal'`
   - A separate `mmproj-*.gguf` file exists alongside the model

2. **Add the following key** to the preset:
   ```ini
   mmproj = /path/to/mmproj-model-name-version.gguf
   ```
   The `mmproj` key is in the router's KNOWN_KEYS list.

3. **No separate `mmproj` config is needed** in the model path — the router passes `--mmproj` to llama-server automatically based on this INI key.

4. **Sampling and thinking**: Vision models often share the same `chat-template-kwargs` and sampling as their text-only counterparts. The same thinking-off-by-default rule applies unless vision-specific prompting requires it.

5. **VRAM considerations**: The mmproj file (typically 1–2GB F16) loads into VRAM alongside model layers. Reduce `n-gpu-layers` by 8–16 if VRAM-constrained.

### 4. Handle chat templates

**If model provides a custom `.jinja` template:**
```ini
jinja = true
chat-template-file = /path/to/model/chat_template.jinja
```

**If model has thinking/reasoning modes:**
- Extract `enable_thinking` flag from template variables
- Default thinking OFF for performance; make it opt-in via `chat-template-kwargs`
```ini
chat-template-kwargs = {"enable_thinking":false}
```

**⚠️ When `enable_thinking:false` doesn't work** (DeepSeek-architecture models like Step 3.7 Flash):
- Some models have a chat template that **unconditionally** prepends `<think>\n` to every assistant response, ignoring the `enable_thinking` flag
- The `<think>` (token 128798) and `<think>` (token 128799) are **special architectural tokens**, not regular sampled tokens — `logit_bias` on them has NO effect on preventing thinking from starting
- **Before choosing approach**: check the token type in GGUF metadata. If the thinking tokens are type 3 (special), `logit_bias` will corrupt the sampler — only approach A (chat template override) works. See `references/thinking-suppression-techniques.md` for the token type check command.
- Two approaches to force thinking OFF:

  **A) Chat template override (clean, eliminates thinking entirely):**
  1. Extract the baked-in template via `gguf-dump` (see `references/gguf-metadata-inspection.md` to find `tokenizer.chat_template`)
  2. Copy it to a `.jinja` file, removing `<think>\n` from the generation prompt (the final `{% if add_generation_prompt %}{{ '<|im_start|>assistant\n<think>\n' }}{% endif %}` block)
  3. Add to the preset:
     ```ini
     jinja = true
     chat-template-file = /home/cricri/llm-server/modelname-no-think.jinja
     ```
  4. Restart the model instance to pick up the new template

  **B) Model manager reasoning budget (caps thinking, doesn't eliminate):**
  The `model-manager-config.yaml` (`~/llm-server/model-manager-config.yaml`) supports per-model parameters that inject `logit_bias` on the `</think>` token to close thinking early:
  ```yaml
  models:
    modelname:
      max_reasoning_tokens: 128       # Hard cap on reasoning tokens
      logit_bias_strength: 15.0       # 13+ = strong suppression, 15+ = near-complete
      target_thinking_tokens: 50      # Token count around which bias targets
  ```
  - No restart needed — model_manager reloads config on each request
  - The model will still generate a few tokens of reasoning before closing
  - See `references/thinking-suppression-techniques.md` for token ID discovery

**If model has a reasoning parser (e.g. `super_v3_reasoning_parser.py`):**
- llama-server does NOT support custom reasoning parsers
- Document as backend limitation; use thinking mode only if llama-server handles it natively
- The thinking content will appear in `content` as raw text

**If GGUF has no baked-in `tokenizer.chat_template`:**
- Check if llama.cpp has native architecture-level template support (e.g., `step35`, `mistral4`, `qwen3.5`). These architectures have built-in templates that activate with just `jinja = true` — no separate template file needed.
- To verify: inspect the GGUF metadata for `tokenizer.chat_template` (see `references/gguf-metadata-inspection.md`). If absent and the architecture is recent, it likely has built-in support.
- Fall back to a chat-template-file only if the architecture is unknown to llama.cpp AND no template is baked in.

### 5. Set sampling parameters

**General rule:** Temperature and top_p should match what the vendor used for benchmarking.

For models with thinking/reasoning modes:
- NVIDIA Nemotron: `temp = 1.0, top_p = 0.95` (official recommendation)
- DeepSeek R1/R1-distill: `temp = 0.6, top_p = 0.95`
- Qwen QwQ: `temp = 0.6, top_p = 0.95`

**For non-thinking models:**
- Use `temp = 0.6–0.8, top_p = 0.95` as default
- `top_p = 1.0` with `temp = 1.0` produces flat-line sampling — only use if vendor specifies it

### 6. Memory-optimized INI settings for 512MB VRAM

**Single-shard vs multi-shard detection:**
- `ls -lh <model.gguf>` — if the file is >40GB as a single file, it's single-shard
- Multi-shard files have `-00001-of-N.gguf` naming pattern
- Single-shard: `mmap = true` for memory-mapped I/O (avoids 68GB pre-load into RAM)
- Multi-shard: also `mmap = true` — demand paging handles even 82GB splits without pre-loading
- `no-mmap = true` is only safe for models <32GB where full RAM load is acceptable

For large models (>40GB total):
```ini
mmap = true          # Memory-mapped I/O. DO NOT use no-mmap for models >40GB.
                    # Demand paging handles 68GB+ models without pre-loading everything.
n-gpu-layers = 64    # adjust per actual VRAM usage; 64 is starting point for
                    # 88-layer LatentMoE on 512MB VRAM
batch-size = 512     # smaller batch reduces per-batch memory overhead
ubatch-size = 512
ctx-size = 32768     # reduce from 131072 if most tasks don't need full ctx;
                    # smaller = less KV cache pressure
cache-type-k = q8_0  # KV cache in Q8_0 balances quality and memory
cache-type-v = q8_0
```

**Note on KV cache choice for MTP models:** Models using `spec-type = draft-mtp` should use `f16/f16` (not `q8_0`) for both main and draft KV caches. The MTP acceptance matrix was built with f16 KV — switching to q8_0 degrades draft acceptance. See § Native MTP below for the full settings block.

### KV cache eviction (n-keep / n-discard)

By default, llama.cpp slots never evict their KV cache — `n_discard=0` in the per-slot `params` means every token processed through a slot stays in its K and V tensors permanently. Over hours of operation, stale KV cache from past requests accumulates in VRAM and never gets freed.

**How to verify accumulation:**
```bash
# Check a model's slots — observe n_prompt_tokens growing across requests
curl -s 'http://localhost:8080/slots?model=<model>' | python3 -c "
import sys, json
slots = json.load(sys.stdin)
for s in slots:
    print(f\"Slot {s['id']}: n_prompt_tokens={s['n_prompt_tokens']}, n_prompt_tokens_processed={s['n_prompt_tokens_processed']}\")
    p = s['params']
    print(f\"  n_keep={p['n_keep']}, n_discard={p['n_discard']}\")
"
```

`n_prompt_tokens` is the **cumulative total** of tokens processed through that slot since creation. `n_discard=0` → no eviction. Even `n_prompt_tokens_cache=0` (cache never reused — router cycles slots between conversations) doesn't free the VRAM; stale cache stays allocated.

**The fix:** add `n-keep` and `n-discard` to the preset section:

```ini
n-keep = 4      # tokens preserved from the start of context when eviction fires. 0 = keep nothing.
n-discard = 512 # when context fills, discard this many tokens. -1 = discard ALL.
```

These are per-slot params that control llama.cpp's KV cache eviction algorithm:
- **n-keep**: Anchor tokens preserved on eviction. 4 holds the system-prompt prefix. 0 means no anchor.
- **n-discard**: Tokens evicted per eviction step. Higher values free more VRAM but lose more cache.

**Recommendation by use case:**

| Use case | n-keep | n-discard | Rationale |
|---|---|---|---|
| Stateless API (typical requests) | 0 | -1 | Full slot reset between requests — safest, no stale cache |
| Agentic sessions (same slot reused) | 4 | 512 | Keep system anchor, shed old cache gradually |
| Long-context single-session | 64 | 256 | Keep more context, evict conservatively |

**`n_discard=-1`** is the nuclear option — clears the *entire* KV cache on eviction. Use for stateless proxies where each request is independent. Less VRAM-efficient than partial discard but simpler to reason about.

**Important:** These are standard `llama-server` native flags. Verify they're in the `KNOWN_KEYS` regex in `start-native-router.sh` before adding to the INI. They should already be covered since they've been in llama.cpp for years.

**Verification after adding:**
```bash
systemctl --user restart m5-router
systemctl --user restart model-manager
sleep 5
curl -s 'http://localhost:8080/slots?model=<model>' | python3 -c "
import sys, json
slots = json.load(sys.stdin)
for s in slots:
    p = s['params']
    print(f\"Slot {s['id']}: n_keep={p['n_keep']}, n_discard={p['n_discard']}\")
"
```

### 7. Speculative decoding INI settings

**DSpark drafter (draft-dspark) — DFlash + Markov head:**
Separate draft model that carries a Markov head and uses an anchor-first block layout. GGUF `general.architecture = 'dflash'` (block_count=3, `dflash.target_layers = [41,42,43]`, optional `dflash.block_size`). Distinguish from the plain DFlash (dflash2) engine: **`--spec-draft-p-min` is a real, active param for dspark** (confidence truncation gated on `is_dspark`) but is a **silent no-op for dflash**. `is_dspark` yields a full `block_size` draft tokens vs `block_size-1` for dflash.

Example (DeepSeek-V4-Flash-0731 target + Q2_K_S DSpark drafter):
```ini
spec-type = draft-dspark
spec-draft-n-max = 3        # vendor benchmark sweet spot; n_max>=5 hurts prose/translate/dialog
n-gpu-layers-draft = 999
```
- Drafter file naming: `-dflash` suffix in the filename refers to the GGUF **dflash architecture**, NOT the spec-type — the spec-type is `draft-dspark` when the drafter has the Markov head.
- Q2_K_S drafter (~6.5GB) matches Q8_0 within noise while 36% smaller — a good drop-in for a 90GB+ target.
- KV: f16 main (draft-decode depth cost), q8_0 draft cache (established DFlash2 pattern on this box).
- Always confirm against the vendor's own benchmark card when available (sampling, n_max sweep, KV type) instead of defaulting to generic values.

**Important — `mmap` vs `no-mmap` on huge (>90GB) models is model/board-specific, verify per model.**
A prior rule ("96GB on 128GB unified → must use mmap=true to avoid ErrorOutOfHostMemory") proved **wrong for DeepSeek-V4-Flash-0731 (96GB) on this same Strix Halo box**: running `mmap=true` demand-pages weights from disk during decode, causing constant page faults that dropped generation to **~6 t/s** (I/O bound) vs the Reddit/reference measurement of 20-28 t/s with `--no-mmap`. `no-mmap` keeps all 96GB resident in the 128GB unified pool and is the working config for this model. Always cross-check against an actual working measurement for the exact model (the qwen38 case that motivated the mmap rule had a different failure mode). Latest llama.cpp deprecates `--mmap/--no-mmap` in favour of `--load-mode mmap` (both still function).

**`spec-type` can stack engines**: the DeepSeek daily recipe uses `spec-type = ngram-mod,draft-dspark` (comma list) — ngram-mod on top of the dspark drafter. Also add `no-warmup = true` and `cache-ram = 2048` (needs `cache-ram` added to KNOWN_KEYS).

**v0.6.6 strix-halo-llamacpp qualification (2026-08-20, pe puscz/strix-halo-deepseek-v4-flash, same M5/AXB35 box):**
Pull from the GitHub **release** tarball, not ghcr (ghcr `vulkan` tag = v0.6.5/0b0f35d; v0.6.6 is only a release asset: `Nathanw1014/strix-halo-llamacpp` release v0.6.6, build `b10569-7b6c6133`, source `7b6c61330` "dequantise the cache for the DeepSeek V4 sparse prefill"). Extract into `~/sources/strix-halo-llamacpp/vulkan/`, build `strix-halo-llamacpp:vulkan` via `build-images.sh`. The `_run` launcher exports the full perf env (GGML_VK_MMID_ROWLISTS/SMALLN/BM64/WAVE32/F16B/M128 + GGML_VK_FA_WAVE32) and points VK_ICD_FILENAMES at the bundled `libvulkan_radeon.so` — verified working on-host (Vulkan0 Radeon 8060S detected, all fused ops incl Lightning Indexer + DSV4 HC resolved).
Qualified server shape (matched on this box): `-ngl/-ngld 999 -fa on -ctk q8_0 -ctv q8_0 -c 524288 -np 1 -b 2048 -ub 1024 -fit off --spec-type draft-dspark --spec-draft-n-max 4`. Results: prefill 218 t/s @122k (+67.5% vs 0.6.4), gen stable ~30.5 t/s, no OOM at 524288 ctx (9.5 GiB MemAvailable retained); 1M ctx OOMs. Target = 4-file split `*-0000X-of-00004.gguf` (104.2GB), point `model=` at shard 1.

For E2B + 31B setup on Strix Halo (draft-max=5 sweet spot):
```ini
model-draft = /mnt/data2/models/tiny/gemma-4-E2B-it-UD-Q8_K_XL.gguf
n-gpu-layers-draft = 999
draft-max = 5
cache-type-k = q8_0
cache-type-v = q8_0
```

For Qwen3.5-122B + Qwen3.5-0.8B draft (draft-max=5):
```ini
model-draft = /home/cricri/models/Qwen3.5-0.8B-Q4_K_M.gguf
n-gpu-layers-draft = 999
draft-max = 5
```

For smaller draft setups (holo3-35b + Qwen3-1.7B, where spec dec doesn't help):
```ini
# Comment out draft parameters — spec dec provides zero improvement
# model-draft = /path/to/draft-model.gguf
# draft-max = 16
# draft-n-min = 4
# draft-p-min = 0.5
```

**Important:** The correct argument for separate draft models is `--draft` (or `--draft-max`), NOT `--spec-draft-n-max`.

### Native MTP (built-in head or companion file)

Models with MTP (Multi-Token Prediction) heads use `spec-type = draft-mtp`. Two layout patterns:

**Pattern A — Embedded MTP:** MTP head(s) baked into the same GGUF as the trunk (e.g., Qwen3.6, Crown Dynamic). No `model-draft` needed.

**Pattern B — Separate companion MTP file:** The trunk GGUF has no MTP layers (quantized away during APEX/Unsloth compaction). A separate small GGUF contains the MTP head(s) with its own `nextn_predict_layers` KV. Load both via `model` + `model-draft` with `spec-type = draft-mtp`. Example: Step-3.7-Flash-APEX-Compact.gguf + Step-3.7-Flash-MTP-Q4_K_M.gguf (2 GB, 3 heads).

For Pattern B:
```ini
model = /path/to/trunk.gguf
model-draft = /path/to/mtp-heads.gguf    # NOT a standard draft model — it's the MTP file
spec-type = draft-mtp
n-gpu-layers-draft = 999                 # MTP head file is small (1-2 GB), fully offload
```

**How to detect the pattern:**
```
# Pattern A (embedded): the trunk GGUF has nextn_predict_layers KV
llama-cli --model trunk.gguf -c 64 -n 0 -ngl 0 --no-warmup --verbose 2>&1 | grep nextn_predict_layers

# Pattern B (separate): trunk has NO nextn KV, but the companion MTP file has it
llama-cli --model mtp-file.gguf -c 64 -n 0 -ngl 0 --no-warmup --verbose 2>&1 | grep -iE "nextn_predict_layers|n_layer_all|blk\.\d+\.nextn"

# Key signals:
#   "nextn_predict_layers u32 = 3"  → 3 MTP heads (positive int = MTP exists)
#   "n_layer_all = 48" when "n_layer = 45"  → 3 extra layers beyond trunk
#   "blk.45.nextn.eh_proj.weight"  → MTP tensor loaded
```

**⚠️ False positive trap:** Model name containing "MTP" does NOT prove MTP heads exist — it can be a finetune tag (`general.finetune`), a marketing name, or description. Verify via metadata as above. See `references/mtp-detection.md` for the ravenx-Gemma4-12B-MTP case (48 vanilla blocks, "MTP" in name, no MTP heads).

**Failure on load:**
```
W llama_init_from_model: context type MTP requested but model doesn't contain MTP layers
E srv    load_model: failed to create MTP context
```
Fix: remove `spec-type = draft-mtp` (and `model-draft` if it was the sole reason) from the preset, then restart model-manager to clear the cached failure: `systemctl --user restart model-manager`.

**Step35-specific: chain_heads mode** — When MTP has multiple heads (`n_layer_nextn > 1`) and is not Gemma4 shared-memory, the speculative driver auto-detects `chain_heads = true` and iterates heads per draft step via `set_nextn_layer_offset()`. No special INI flags needed.

**Pattern A detection (embedded) — same quant family nuance:** A single GGUF can switch from Pattern B to Pattern A (or vice versa) across its quant variants. Verify EVERY new file via `qwen35.nextn_predict_layers` / `block_count`:
- `block_count` equals trunk layers (e.g. 64) + no `nextn` key → no MTP → need companion file (Pattern B), add `model-draft` + `n-gpu-layers-draft`.
- `block_count` equals trunk+1 (e.g. 65) AND `nextn_predict_layers = 1` AND `blk.NEXT.nextn.*` tensors exist → MTP embedded (Pattern A) → use `spec-type = draft-mtp` with NO `model-draft`.
- Example: on a `qwen35` 27B, the `Q4_K_M.gguf` had `block_count=64` (no MTP, companion `mtp-*-Q4_0.gguf` had `nextn=1`) while `Q5_K_S.gguf` had `block_count=65` + `nextn=1` + `blk.64.nextn.*` (embedded). The model card's "MTP included at Q4_0" referred to the companion; only metadata inspection tells you which variant you actually have.

**Reasoning budget with MTP/thinking models:** `reasoning-budget = N` is a top-level llama-server flag (`--reasoning-budget`), NOT a chat-template-kwargs field. It only takes effect when thinking is actually enabled — you must coordinate three keys:
```ini
reasoning = on                          # enables thinking token accounting
reasoning-budget = 16384                # cap on thinking tokens (-1 unrestricted, 0 immediate end)
reasoning-budget-message = "..."        # optional: injected before end-of-thinking tag when budget hit
reasoning-format = deepseek             # surface thoughts in message.reasoning_content
chat-template-kwargs = {"enable_thinking":true}   # template must open <think>
```
`reasoning-budget-message` (`--reasoning-budget-message`) is injected by llama-server right before the end-of-thinking tag when the budget is exhausted, prompting the model to close thinking. Both `reasoning-budget` and `reasoning-budget-message` and `reasoning-format` were missing from the default KNOWN_KEYS — `reasoning-format` and `reasoning-budget-message` had to be added manually (2026-08-18).

**`reasoning-format` vs web-UI thinking rendering:** llama-server emits thinking into `reasoning_content` in the OpenAI streaming chat API REGARDLESS of `--reasoning-format` (`none`/`deepseek`/`deepseek-legacy`) whenever `reasoning = on` — the format only controls whether the thinking tags are also LEFTe in `message.content`. Web UIs that render thoughts (Open WebUI "Show thought in progress"/"Render thinking as Markdown", llama-webui) read `reasoning_content` from the stream, so changing `reasoning-format` does NOT fix "no thinking shown." The actual cause of "model doesn't reason at all" for a particular preset is usually a **stale loaded instance**: a model loaded BEFORE an INI edit keeps the old `--chat-template-kwargs {"enable_thinking":false}` / no-reasoning flags until the ROUTER (m5-router) is restarted — an unload/reload via the :8079 proxy is NOT enough because the router holds preset definitions. Symptom: `curl :8080/v1/models` for the model shows stale args (enable_thinking:false, no `--reasoning`). Fix: `systemctl --user restart m5-router` then reload the model, and confirm `reasoning_content` streams via `curl -sN :8080/v1/chat/completions ... stream:true`.
If `chat-template-kwargs` has `enable_thinking:false`, the budget never fires (no thinking tokens to count). llama.cpp 10087+ warns `Setting 'enable_thinking' via --chat-template-kwargs is deprecated. Use --reasoning on/off instead` — the top-level `reasoning` flag is the canonical toggle now, but keep `enable_thinking` in chat-template-kwargs for templates that read it directly (e.g. the Qwen36 froggeric template). `reasoning-format` (values: `none`/`deepseek`) must be added to KNOWN_KEYS manually — it was NOT in the default list (added 2026-08-18).

**Post-deployment verification:**
```bash
# After a test request, check the response for MTP activity:
# timings.draft_n > 0 confirms MTP is active
# timings.draft_n == draft_n_accepted → 100% accept rate
```

Essential settings:
```ini
spec-type = draft-mtp
spec-draft-n-max = 4          # MTP depth; 2-4 typical, 4 is strongest for structured decode
spec-draft-p-min = 0.5        # Minimum acceptance probability per draft token
cache-type-k = f16            # f16 KV for MTP models — benchmark-recommended
cache-type-v = f16
cache-type-k-draft = f16      # Draft head KV cache type (use f16 to match main)
cache-type-v-draft = f16
```

**MTP polling flags (critical for throughput):** These are NOT in the default KNOWN_KEYS — you MUST add them to `start-native-router.sh` before adding to the INI. Add these to the KNOWN_KEYS regex:
```
poll|poll-batch|spec-draft-poll|spec-draft-poll-batch
```

INI values (from Strix Halo MTP benchmarks):
```ini
poll = 100              # Main slot poll rate in μs (default: 50; 100 reduces contention)
poll-batch = 1          # Main slot batch poll rate
spec-draft-poll = 1     # Draft model poll rate in μs (1 = aggressive polling)
spec-draft-poll-batch = 1
```

Without these polling flags, MTP draft generation polls at default conservative rates and throughput drops significantly (observed: ~65 t/s → ~87 t/s on structured decode after adding them).

MTP KV cache choice: f16/f16 is the recommended Strix Halo setting (not q8_0). The model card's acceptance matrix was built with f16 KV; using q8_0 may degrade acceptance rates. Larger batch (b2048/u512) is the sweet spot — b8192 doesn't improve acceptance and adds latency.

Reference profile (Crown Dynamic MTP v7 on Strix Halo):
| setting | workload | gen t/s | MTP acceptance |
|---|---|---|---|
| MTP depth 4, b2048/u512, f16 KV | JSON | 105.79 | 97.6% |
| MTP depth 4, b2048/u512, f16 KV | code | 106.13 | 99.5% |
| MTP depth 2, b2048/u512, f16 KV | JSON | 91.08 | 100.0% |

### 7. Test in Isolation (NEVER on production port 8080)

Write a benchmark script first — don't try to run `llama-server` interactively in a `distrobox enter` chain. The terminal session will SIGTERM the process when the timeout fires, even with `&` backgrounding.

**Step 1: Create the benchmark script** (write to `~/llm-server/bench-<model>.sh`):
```bash
#!/bin/bash
set -e

# Kill any existing test instance on this port
pkill -f "llama-server.*--port 8090" 2>/dev/null || true
sleep 2

# Start llama-server (binary lives inside the distrobox, not on host)
nohup /usr/sbin/llama-server \
  --host 0.0.0.0 \
  --port 8090 \
  --model /home/cricri/models/<short-name>/<filename>.gguf \
  --ctx-size 4096 \
  --n-gpu-layers 999 \
  --flash-attn on \
  --mmap \
  --jinja \
  --temp 0.7 \
  --top-p 0.95 \
  --min-p 0.01 \
  --repeat-penalty 1.0 \
  --batch-size 2048 \
  --ubatch-size 1024 \
  --threads 8 \
  --metrics \
  > /tmp/llama-server-<model>.log 2>&1 &

SERVER_PID=$!
echo "Server PID: $SERVER_PID"

# Wait for readiness
for i in $(seq 1 120); do
  if curl -s http://localhost:8090/health > /dev/null 2>&1; then
    echo "Server ready after ${i}s"
    break
  fi
  sleep 1
done

# Test prompts — start with short factual to verify basic correctness
echo "=== Test 1: Factual (32 tokens) ==="
curl -s http://localhost:8090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":32,"temperature":0.1}' \
  | python3 -m json.tool

echo "=== Test 2: Speed (128 tokens) ==="
curl -s http://localhost:8090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Write a short poem about the moon."}],"max_tokens":128,"temperature":0.7}' \
  | python3 -c "
import json,sys
d = json.load(sys.stdin)
t = d.get('timings',{})
if t and t.get('predicted_n'):
    print(f\"gen {t.get('predicted_per_second',0):.1f} tok/s | {t.get('predicted_n')} tokens in {t.get('predicted_ms',0):.0f}ms\")
else:
    print(f'Error: {d.get(\"error\",{}).get(\"message\",\"unknown\")[:200]}')
"

# Cleanup
kill $SERVER_PID 2>/dev/null || true
sleep 2
echo "Done"
```

**Step 2: Run the script from inside the distrobox in background mode**:
```bash
distrobox enter llama-vulkan-amdvlk -- bash ~/llm-server/bench-<model>.sh > /tmp/bench-output.txt 2>&1
```
Wrap this in a `terminal(background=true, notify_on_complete=true)` call. Use `process(action='wait')` or `process(action='poll')` to monitor. The output goes to `/tmp/bench-output.txt`.

**Step 3: Verify the result**:
```bash
cat /tmp/bench-output.txt
```

**Verify:**
- Response has `choices[0].message.content` with valid text
- No OOM, no crash, no garbled tokens
- Generation speed in the `timings.predicted_per_second` field

> **Port conflict?** `ss -tlnp | grep 809` shows used ports. Avoid 8080, 8081, 8088, 8642 (Hermes gateway).

### 8. Validate the preset

```bash
bash /mnt/data1/cricri/tools/llm-server/start-native-router.sh --help 2>&1 | head -5
# If it prints "ERROR: Unknown preset keys", the INI has invalid keys
# If it exits 0 silently, the preset is valid
```

**⚠️ Validator caveat:** The script's `KNOWN_KEYS` list can lag behind llama-server's actual flags. If validation fails but the key is valid (check `llama-server --help`), add it to `KNOWN_KEYS` in the script. See `references/known-keys-validator.md` for details.

Then restart and benchmark:
```bash
systemctl --user restart m5-router
sleep 5
systemctl status m5-router.service --no-pager | head -5
curl -s http://localhost:8080/health 2>/dev/null || \
  journalctl -u m5-router.service --since "1 minute ago" --no-pager | tail -10
# Compare output speed against similar-sized model in vulkan-bench-results.txt
```

## Common pitfalls

**`no-mmap = true` on large multi-shard models**
- Forces 82GB pre-load into RAM — slow, may OOM
- Use `mmap = true` instead for memory-mapped I/O

**Copying sampling params between models**
- Each architecture has vendor-recommended values
- Wrong params cause degraded output quality or repetitive loops

**Thinking mode enabled by default**\n- Generates extensive CoT tokens before final answer\n- Output speed drops 30-50% vs non-thinking mode\n- Enable only when needed per-request, not in the preset default\n\n**`chat-template-kwargs` must be explicit in every preset section**\n- Thin ACP clients (Kilo Code, Claude Code, Copilot) send NO parameter overrides — they rely entirely on the router preset defaults. If their model block has empty `options: {}`, every sampling parameter comes from llama-server's preset-level defaults.\n- If `chat-template-kwargs` is absent from a preset section, the model's chat template default behavior applies. This means thinking mode may activate even if `reasoning = off` is set — because the template unconditionally prepends `<think>\\n` regardless of the `reasoning` flag.\n- Always add `chat-template-kwargs = {"enable_thinking":false}` to EVERY preset section as a hygiene rule, including models that don't have thinking by default. The only exception is a model specifically configured for thinking (e.g., a "[modelname]-think" variant with `{"enable_thinking":true}`).\n- **Concrete case:** the `[qwen36-35b]` preset section was found missing this key while all others had it. Thin ACP clients send no parameter overrides, so the model ran with whatever chat-template default applied — potentially thinking despite `reasoning = off`. Verify coverage across all presets:
  ```bash
  total=$(grep -c '^\[' ~/llm-server/router-preset.ini)
  covered=$(grep -c 'chat-template-kwargs' ~/llm-server/router-preset.ini)
  echo "$covered / $total presets have chat-template-kwargs"
  ```
- To verify whether a running preset has it set, check the llama-server args: `curl -s http://localhost:8080/v1/models | python3 -c "import json,sys; data=json.load(sys.stdin); [print(m['id'], '→', '--chat-template-kwargs' in ' '.join(m['status']['args'])) for m in data['data']]"`

**`enable_thinking:false` silently ignored by some templates**
- DeepSeek-architecture models (Step 3.7 Flash, DeepSeek R1 derivatives) have a `<think>\n` prefix hardcoded in their chat template
- The `enable_thinking` flag is only honored if the template has a conditional `{% if enable_thinking %}...{% endif %}` block
- Verify by extracting the template with `gguf-dump` and checking the generation prompt section
- Fix: override the template with a modified copy that removes `<think>\n` from `{% if add_generation_prompt %}`

**Dual-entry preset strategy for per-task thinking switching:**
When a model needs thinking ON for some tasks and OFF for others (e.g., research needs thinking, coding doesn't), maintain TWO preset entries pointing at the same GGUF file but with different chat templates:

```ini
[model-name]           # Default: thinking ON (native template)
load-on-startup = 0
model = /path/to/model.gguf
# No chat-template-file → uses baked-in GGUF template (thinking enabled)

[model-name-nothink]   # Override: thinking OFF
load-on-startup = 0
model = /path/to/model.gguf
# Same model path, different chat template
chat-template-file = /home/cricri/llm-server/modelname-no-think.jinja
```

Then load the variant you need per task. See `step37-thinking-suppression` skill for a worked example.

**Logit bias on `<think>` does not suppress thinking**
- `<think>` tokens (128798 for many DeepSeek models) are special architectural tokens, not sampled tokens
- `logit_bias: {128798: -100}` has zero effect on preventing thinking from starting
- The correct technique is a positive bias on `</think>` (128799) to close thinking early, or a chat template override
- See `references/thinking-suppression-techniques.md` for token ID discovery per model

**Custom chat template not loaded**
- Both `jinja = true` AND `chat-template-file = /path/to/template.jinja` are required
- Without `jinja = true`, the template engine is not activated

**GGUF has no baked-in chat template — still works with `jinja = true`**
- Many architectures (step35, mistral4, qwen3.5) have built-in templates in llama.cpp
- Verify by checking GGUF metadata for `tokenizer.chat_template` key
- If absent but architecture is recent, just `jinja = true` is enough — no separate file needed
- Panic only if the architecture is custom/experimental AND no template is in GGUF

**Mamba SSM state overflow**
- SSM state per layer: 128 (ssm_state_size) × float32 × num_layers
- If VRAM runs out mid-inference, reduce `n-gpu-layers` by 8-16 layers
- llama-server will CPU-fallback for the rest

**Speculative decoding argument is `--draft`, not `--spec-draft-n-max`**
- The correct llama-server argument is `--draft` (or `--draft-max`), NOT `--spec-draft-n-max`
- Using `--spec-draft-n-max` causes "invalid argument" error
- For E2B + 31B setup on Strix Halo, `--draft 5` is the sweet spot (7.9 tps, 69% accept rate)
- See `references/gemma4-31b-e2b-spec-dec-bench.md` for detailed benchmark data

**`start-native-router.sh` validator is stricter than llama-server**
- The script has a hardcoded `KNOWN_KEYS` list that can lag behind llama-server's actual supported flags
- If validation fails with "Unknown preset keys" but the key is valid (check `llama-server --help`), add it to `KNOWN_KEYS` in `start-native-router.sh`
- Common keys that need addition: `poll`, `poll-batch`, `spec-draft-poll`, `spec-draft-poll-batch` (MTP polling), `n-gpu-layers-draft` (separate draft model), `repeat-last-n` (paired with `repeat-penalty`), `reasoning-format` (paired with `reasoning-budget`/`reasoning`)
- Example: `n-gpu-layers-draft` was missing from `KNOWN_KEYS` despite being a valid llama-server flag; the four MTP polling flags were added 2026-06-02 when on-boarding Crown Dynamic MTP v7
- Always validate with `bash ~/llm-server/start-native-router.sh --help 2>&1 | head -5` before restarting the router

**`huggingface-cli` is deprecated**
- Always use `hf download` instead
- `huggingface-cli download` no longer works and prints a deprecation warning instructing you to switch

**Don't test on port 8080**
- That's the production router — don't interrupt live inference
- Use a separate port (e.g. 8090) with a standalone llama-server inside the distrobox

**GGUF swap invalidates preset assumptions**
- When replacing a GGUF file for an existing preset slot, re-verify all architecture-dependent settings: MTP heads, chat template, vision support
- A preset that worked with the previous GGUF may crash with the new one (e.g., MTP layers stripped during quantization)
- The error `context type MTP requested but model doesn't contain MTP layers` after a GGUF swap is the classic symptom
- Fix: remove the offending keys (spec-type, spec-draft-*) and reload

**Models without flash-attn support can't use quantized KV cache**
- Some architectures (phi-2, older dense models) do not support flash-attention in llama.cpp
- Setting `cache-type-k = q8_0` or `cache-type-v = q8_0` on these models produces: `V cache quantization requires flash_attn` and the model fails to load
- Fix: omit `cache-type-k`, `cache-type-v`, and `flash-attn` entirely — the model uses default f16 KV cache which works fine for small models
- Detection: the model's small size (2GB for phi-2) and lack of flash-attn architecture support means default caching is sufficient — no need for advanced caching at all
- When in doubt about a small/old model, try loading with just the essential keys first (model, ctx-size, n-gpu-layers, mmap) and add cache opts only if performance requires it

**`/api/load` on port 8080 always returns 404**
- The llama-server router (`:8080`) does NOT expose a load endpoint. `POST /api/load` on 8080 returns `{"error": {"code": 404, "message": "File Not Found"}}` regardless of whether the model is in the preset.
- The correct load endpoint is the model-manager proxy at `:8079`: `POST /api/load` with `{"model": "MODEL_ID"}` body.
- Don't waste time debugging the preset when you see a 404 on 8080 — go straight to `:8079/api/load`.
- After a failed load (e.g. MTP init error), subsequent `POST /api/load` calls on `:8079` may return `model is already running` because the model-manager cached the failed state. Restart model-manager to clear: `systemctl --user restart model-manager`

**Qwen template raise_exception on system message position** (`references/qwen-system-position-validation.md`)
- Some Qwen-based GGUFs (especially Coder variants from third-party quantizers) have a baked-in `raise_exception('System message must be at the beginning.')` in their chat template that fires at generation time, rejecting any request where `messages[0].role != "system"`.
- This kills thin ACP clients (Kilo Code, Claude Code, Copilot) which may send system prompts in non-first positions.
- The error comes back as HTTP 400: `"Unable to generate parser for this template... Jinja Exception: System message must be at the beginning."`
- **Fix:** extract the template via raw byte search (gguf-dump truncates long strings), replace the `raise_exception` block with normal `im_start` rendering, save as `chat-template-file`, and point the preset at it.
- The 27B variant of the same model family often lacks this validation — it's a per-quantizer choice, not a Qwen architecture requirement.
- See `references/qwen-system-position-validation.md` for the full extraction recipe, patch, and verification.

**Gemma 4 chat template emits `<channel|>` tokens during generation**
- The baked-in Gemma 4 template (tokenizer.ggml.model = 'gemma4') injects `<|channel|>thought` into the generation prompt and uses `<channel|>` as a special token in output
- llama-server itself handles this fine — the model produces valid text
- BUT the model-manager proxy's streaming parser can choke on `<channel|>` mid-stream, returning HTTP 500: `Failed to parse input at pos N: <channel|>...`
- Workaround for benchmarking: use short, factual prompts (≤32 tokens output) — the parser handles these cleanly
- Permanent fix: extract the template, remove the channel/think tokens from the generation prompt, save as `chat-template-file = /home/cricri/llm-server/<model>-no-think.jinja` and reference in preset
- Symptom: factual prompts work, creative/long prompts intermittently return 500

**llama-server in distrobox**
- The binary lives inside `llama-vulkan-amdvlk`; always run via `distrobox enter llama-vulkan-amdvlk -- llama-server ...`
- The host-side binary at `~/bin/llama-server` may have library linking issues — use the distrobox one

**Zombie llama processes from killed `distrobox-enter` sessions**
- When a `distrobox enter llama-vulkan-amdvlk -- llama-cli ...` session is interrupted (timeout, Ctrl+C, Hermes tool timeout), the `distrobox-enter` wrapper may die but the **child llama process inside the container can survive**, still holding model weights in memory and pegging a CPU core at 98-99%.
- The conmon/podman wrapper also survives, making the zombie invisible to `pkill -f distrobox`.
- Symptom: APU/GPU at 100% with no obvious llama process in `ps aux | grep llama` (or many llama-cli processes that the user can see).
- Fix: `pkill -9 llama-cli && pkill -9 llama-server` from the host kills all child processes inside the distrobox. Always run this cleanup after interrupted distrobox testing sessions with large models (>40 GB).

**Model-manager proxy doesn't auto-discover new INI models**
- The model_manager proxy (`:8079`) initializes its model list at startup by reading the router's `/v1/models`. Adding a new `[section]` to `router-preset.ini` and restarting only the router makes the model visible to `:8080` but NOT to the proxy (`:8079`).
- **Symptom:** `POST /api/load` returns `{"error": {"code": 400, "message": "model is already running"}}` on a model that has never been loaded. This means the model_manager doesn't know about the model — not that it's loaded.
- **Fix:** After adding a new model to the INI and restarting the router, also restart model-manager:
  ```bash
  systemctl --user restart m5-router       # picks up new INI sections
  systemctl --user restart model-manager   # re-fetches model list from router
  ```
- The proxy's background poll (every 10s) syncs load/unload *status* of known models but does NOT discover new model entries.

## Verification

1. Restart router: `systemctl --user restart m5-router`
2. Also restart model-manager so it picks up the new model: `systemctl --user restart model-manager`
3. Verify model appears in proxy's model list: `curl -s http://localhost:8079/proxy/status | python3 -c "import json,sys; d=json.load(sys.stdin); print([m['name'] for m in d.get('models',[])])"`
4. Load through the proxy: `curl -s -X POST http://localhost:8079/api/load -H 'Content-Type: application/json' -d '{"model":"MODEL_ID"}'`
5. Send test request:
   ```bash
   curl -s http://localhost:8079/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"MODEL_ID","messages":[{"role":"user","content":"Hello"}],"max_tokens":50}'
   ```
6. Check MTP performance in response `timings` field (draft_n/draft_n_accepted ratio)
7. Compare output speed against baseline in `vulkan-bench-results.txt`

## Architecture-specific notes

**nemotron_h_moe (LatentMoE / Nemotron 3)**: Hybrid Mamba-2 + MoE + Attention architecture used by NVIDIA Nemotron 3 family. GGUF architecture key is literally `nemotron_h_moe`. Features SSM layers (conv_kernel=4, state_size=128, group_count=8, inner_size=4096, time_step_rank=64) interleaved with MoE FFN layers. 52 layers typical (nano) to 88 layers (120B super). `feed_forward_length` array signals which layers are MoE (non-zero) vs SSM (zero). Tokenizer is GPT-2 based with optional pixtral (multimodal) pre-tokenizer. Context length ranges from 128K to 1M. VRAM: SSM state overhead same as standard LatentMoE; `n-gpu-layers=64` empirical ceiling for 512MB VRAM on large variants, but smaller variants (30B A3B) can offload more layers.

**MoE with standard routing (Qwen3.5, DeepSeek)**: Expert weights dispatched from CPU — VRAM mainly holds attention layers and active expert weights. `n-gpu-layers` can be higher than dense models of same total size.

**Dense models**: All parameters in VRAM. `n-gpu-layers` = total layers if VRAM allows, otherwise split.

**Mistral/MoE+MLA (Mistral 4 architecture)**: `rope_theta` baked into GGUF. No `rope-freq-base` or `rope-scale` needed. Context length is native 128K.

**Step35 (Step-3.5-Flash, REAP variants)**: Sparse MoE with fine-grained experts. 45 layers (3 leading dense blocks), 173–288 experts (Top-8), single shared expert. Native 256K context via 3:1 SWA ratio (3 sliding-window layers per full-attention layer, sliding_window=512). Rope freq_base = 5,000,000 (full-attn) / 10,000 (SWA). REAP variants document expert pruning in `general.description`. No baked-in chat template in GGUF — use `jinja = true` alone (architecture has built-in template in llama.cpp). Recommended: temp=0.6, top_p=0.95 (chat) / temp=1.0, top_p=0.95 (agent).
