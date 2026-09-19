# Laguna DFlash Decoder Contract

## Status: upstream missing, poolside fork only

The upstream llama.cpp (at `1f66c3ce1`, which includes PR #25165 for Laguna target model support) does NOT support the Laguna-specific DFlash decoder contract. The poolsideai `laguna` branch has these changes in a squashed merge commit.

The HuggingFace model card for `poolside/Laguna-S-2.1-DFlash` confirms:
> "Requires Poolside's llama.cpp fork, branch `laguna`. Upstream llama.cpp ships the generic DFlash framework but not the Laguna decoder contract this draft model needs, and upstream PR ggml-org/llama.cpp#25165 covers the target architecture only."

No PR has been submitted upstream for the laguna-dflash changes as of 2026-07-31.

## What's missing upstream

### 1. `dflash.decoder_arch = "laguna"` metadata handling

The Laguna DFlash draft GGUF embeds `dflash.decoder_arch = laguna` in its metadata. The poolside fork reads this and sets `causal=true` on the drafter's attention. Upstream hardcodes `llama_set_causal_attn(ctx_dft, false)` — Laguna drafters are trained with a causal noise block, so the upstream's non-causal assumption is wrong for them.

**Upstream code** (common/speculative.cpp, ~line 990):
```cpp
llama_set_causal_attn(ctx_dft, false); // DFlash needs non-causal attention
```

**Poolside fork** (common/speculative.cpp):
```cpp
bool causal = false;
{
    char buf[32] = {};
    if (llama_model_meta_val_str(model_dft, "dflash.decoder_arch", buf, sizeof(buf)) >= 0) {
        causal = strcmp(buf, "laguna") == 0;
    }
}
llama_set_causal_attn(ctx_dft, causal);
```

### 2. `aux_norm` — per-aux-feature RMSNorm

Laguna drafters RMS-norm each captured target feature before concat + fc. The poolside fork adds `aux_norm` weights (stacked to `[n_embd, n_aux]`) to the dflash model and applies them in the encoder graph:

```cpp
if (model_df.aux_norm != nullptr) {
    const int64_t n_aux  = model_df.aux_norm->ne[1];
    const int64_t n_feat = hparams.n_embd_inp_enc() / n_aux;
    cur = ggml_reshape_3d(ctx0, cur, n_feat, n_aux, n_tokens);
    cur = ggml_rms_norm(ctx0, cur, hparams.f_norm_rms_eps);
    cur = ggml_mul(ctx0, cur, model_df.aux_norm);
    cur = ggml_reshape_2d(ctx0, cur, n_feat * n_aux, n_tokens);
    cb(cur, "enc_aux_norm", -1);
}
```

### 3. Attention gate (`wqkv_gate`) in dflash draft layers

When `decoder_laguna == true`, the poolside fork loads an optional `ATTN_GATE` tensor per layer:

```cpp
if (decoder_laguna) {
    const ggml_tensor * gate_meta = ml.get_tensor_meta(tn(LLM_TENSOR_ATTN_GATE, "weight", i).str().c_str());
    if (gate_meta != nullptr) {
        // ... load wqkv_gate tensor
    }
}
```

### 4. Pre-final-norm state capture (`h_nextn`) in laguna.cpp

The poolside fork captures the residual stream before the final norm (the DFlash drafter's last capture point, "input of layer n_layer" in training convention):

```cpp
// pre-final-norm residual stream: the DFlash drafter's last capture point
cb(cur, "h_nextn", -1);
res->t_h_nextn = cur;
```

Upstream's laguna.cpp doesn't emit this.

### 5. Non-finite feature sanitization on Metal

The poolside fork clamps f16-overflowing activations (|x| > 65504) to prevent NaN poisoning of the drafter KV cache. This is Metal-specific (f16 matmul overflow with massive activations like attention-sink tokens). Less relevant on AMD Vulkan but still a correctness issue.

## What upstream already has

- **Generic DFlash** (`--dflash`, `draft-dflash` spec type, `dflash.block_size` metadata) — works for Qwen3, DeepSeek, etc.
- **Laguna target model** (PR #25165, at commit `1f66c3ce1`) — architecture, graph, conversion script, chat template
- **`h_nextn` staging API** in `llama-ext.h` — used by MTP and generic DFlash, but not wired into laguna.cpp

## How to get laguna-dflash working

Two options ranked by maintainability:

### Option A: Build from poolsideai fork (recommended until upstream merges)

```bash
git clone https://github.com/poolsideai/llama.cpp.git -b laguna
cd llama.cpp
# Build inside distrobox with Vulkan (see custom-llama-cpp-build skill)
distrobox enter llama-vulkan-amdvlk -- bash -c '
  cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON
  cmake --build build -j --target llama-server
'
```

**Caveat:** The poolsideai fork ships Vulkan v0.16 which may not detect Strix Halo (gfx1151). If it falls back to CPU, try:
```bash
export VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/radeon_icd.x86_64.json"
```

### Option B: Cherry-pick the diff onto upstream

The poolside branch is a squashed commit on top of upstream master. The diff covers:
- `common/speculative.cpp` — decoder_arch metadata, causal attention, nextn extraction, sanitization
- `src/models/dflash.cpp` — aux_norm + attention gate + decoder_laguna flag
- `src/models/models.h` — decoder_laguna + aux_norm fields
- `src/models/laguna.cpp` — h_nextn capture + unmasked nextn path

Apply via `git diff` or manual patch. Watch for conflicts with upstream's evolving speculative.cpp.

## Running the Laguna DFlash draft

If you have a poolside-fork-built binary:

```bash
# Start the Laguna target + DFlash draft in one server
llama-server \
  -m laguna-s-2.1-UD-Q4_K_M.gguf \
  -md laguna-s-2.1-DFlash-Q4_K_M.gguf \
  --spec-type draft-dflash \
  --draft 7 \
  -c 16384 \
  --n-gpu-layers 999 \
  --flash-attn on \
  --jinja
```

The `dflash.decoder_arch = laguna` metadata is embedded in the DFlash GGUF — the server reads it automatically. No special flags needed beyond the fork.