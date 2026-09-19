# MTP Head Detection in GGUF Files

The model name or `general.finetune` field can claim "MTP" without the GGUF having a real Multi-Token Prediction head. Setting `spec-type = draft-mtp` on a model without one is a fatal load error.

## Symptom of false-positive MTP

```
W llama_init_from_model: context type MTP requested but model doesn't contain MTP layers
E srv    load_model: failed to create MTP context
E srv          main: exiting due to model loading error
```

Side effect: model-manager proxy returns `'model is already running'` on subsequent retries because the failed slot doesn't release. Restart model-manager to clear the lock.

## Verified case 1: ravenx-Gemma4-12B-MTP (false positive)

Repo: `deadbydawn101/ravenx-Gemma4-12B-MTP-OBLITERATED-OpenMAI-OpenMythos-deep-reasoning-GGUF`

| KV field | Value | Real MTP? |
|---|---|---|
| `general.name` | `Ravenx Gemma4 12b MTP Deep Reasoning` | Claims yes |
| `general.finetune` | `MTP-deep-reasoning` | Claims yes |
| `gemma4.block_count` | 48 | Standard transformer blocks only |
| Tensor names | `blk.0..47.attn_*.weight`, `blk.0..47.ffn_*.weight` | No `mtp.*` / `output_shifts*` / `*_draft.*` |
| `gemma4.expert_count` | (absent) | Dense, not MoE |
| `*output_shifts*` in any tensor | No | — |
| Real MTP layers | **None** | Confirmed by absence of draft head |

**Conclusion:** "MTP" is a finetune/training-method tag, not a baked-in MTP head. Use standard autoregressive (or pair with a separate draft model).

## Verified case 2: Step-3.7-Flash — separate MTP file pattern (2026-06-22)

Step-3.7-Flash ships MTP layers as a **separate GGUF file**, not embedded in the trunk.

| File | `n_layer` | `n_layer_all` | `nextn_predict_layers` | MTP tensors |
|---|---|---|---|---|
| `Step-3.7-Flash-APEX-Compact.gguf` (trunk, 84GB) | 45 | 45 | absent | none |
| `Step-3.7-Flash-MTP-Q4_K_M.gguf` (MTP, 2GB) | 45 | 48 | 3 | `blk.45-47.nextn.eh_proj/enorm/hnorm/shared_head_*` |

Usage with `-md` (model-draft) pointing to the MTP file:
```ini
[step37]
model = /path/to/Step-3.7-Flash-APEX-Compact.gguf
model-draft = /path/to/Step-3.7-Flash-MTP-Q4_K_M.gguf
spec-type = draft-mtp
spec-draft-n-max = 3
n-gpu-layers-draft = 999
```

The `chain_heads` mode auto-activates when `n_mtp_layers > 1` and the model is NOT Gemma4 shared-memory: each MTP head runs sequentially per draft step via `set_nextn_layer_offset()`. No extra flags needed.

**Lesson:** "No MTP in trunk GGUF" does NOT mean the model lacks MTP — check for a companion `-MTP-` file. The trunk-only quantizations (APEX Compact, Unsloth UD) strip MTP layers to save space, but the original MTP heads may be available as a separate download.

## Verified case 3: Qwopus3.6-27B-Coder-Compat-MTP (embedded MTP)

File: `Qwopus3.6-27B-Coder-Compat-MTP-Q4_K_M.gguf` (16GB, qwen35 arch)

| KV field | Value |
|---|---|
| `qwen35.nextn_predict_layers` | 1 |
| `n_layer` | 64 |
| `n_layer_all` | 65 |
| MTP tensors | `blk.64.nextn.eh_proj/enorm/hnorm/shared_head_*` |

Single embedded MTP head, `spec-draft-n-max = 2`, 76.81% acceptance rate. No separate file needed — `spec-type = draft-mtp` works directly.

## Detection checklist

Run before enabling `spec-type = draft-mtp`:

```bash
# Quick check via llama-cli (loads metadata only, no GPU needed)
distrobox enter llama-vulkan-amdvlk -- bash -c '
export LD_LIBRARY_PATH=/home/cricri/.local/lib64:/home/cricri/.local/lib:$LD_LIBRARY_PATH
timeout 30 llama-cli --model /path/to/model.gguf -c 64 -n 0 -ngl 0 --no-warmup --verbose 2>&1 \
  | grep -E "nextn|n_layer_all|n_layer |arch "
'
```

**Signals:**
- `n_layer_all > n_layer` → has extra blocks (likely MTP)
- `nextn_predict_layers` KV present → confirmed MTP
- `blk.N.nextn.*` tensor names → MTP head identified
- All three absent in trunk → check for companion `-MTP-` file before giving up

If only `general.name` / `general.finetune` mention "mtp" but no tensor name does → fake MTP. Use plain autoregressive or `model-draft = ...` with a real separate draft model.

## Architectures and MTP support

| Architecture | Embedded MTP | Separate MTP file | Notes |
|---|---|---|---|
| `qwen3.6` / `qwen35` | Yes (when preserved) | N/A | `nextn_predict_layers` in KV, `blk.N.nextn.*` tensors |
| `step35` | Stripped by quantizers | Yes (companion file) | Trunk has `n_layer_all == n_layer`; MTP file adds blocks 45-47 |
| `gemma4` | No | No | "MTP" in name is always a finetune tag |
| `llama`, `mistral`, `qwen3.5` | No | No | Use separate draft model for spec dec |
