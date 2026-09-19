# Speculative Decoding in llama.cpp

llama.cpp supports speculative decoding to accelerate generation by using a smaller "draft" model to predict multiple tokens ahead, verified by the main model in parallel.

## Types of Speculative Decoding

### 1. External Draft Model (SpecDec)

Traditional approach — a separate small GGUF as draft:

```bash
llama-server -m main.gguf -md draft.gguf \
  --spec-draft-n-max 5 -ngld 999
```

Note: `--draft-max` / `--draft-min` are removed; use `--spec-draft-n-max` / `--spec-draft-n-min`.

### 2. MTP (draft-mtp) — PR #24340+

Integrated speculative decoding using the model's own MTP (Multi-Token Prediction) heads. Two layout patterns:

**Pattern A — Embedded MTP** (single GGUF, e.g. Qwen3.6-27B-mtp):
```
n_layer_all > n_layer, has nextn_predict_layers KV
```
```bash
llama-server -m model.gguf -c 2048 -ngl 999 --flash-attn on \
  --spec-type draft-mtp --spec-draft-n-max 3
```

**Pattern B — Separate MTP file** (e.g. Step-3.7-Flash):
```
Trunk GGUF:        n_layer_all == n_layer, no nextn KV
MTP-file GGUF:     has nextn_predict_layers (usually 3), .nextn.* tensors
```
```bash
llama-server -m trunk.gguf -md mtp-file.gguf \
  -c 2048 -ngl 999 --flash-attn on -ngld 999 \
  --spec-type draft-mtp --spec-draft-n-max 3
```

## MTP Head Modes

| Mode | Condition | Architecture | Behavior |
|---|---|---|---|
| Single-head | `n_mtp_layers == 1` | Qwen3.5/3.6 | One trained MTP head, same layer for all draft steps |
| Chain heads | `n_mtp_layers > 1 && !is_mem_shared` | Step3.5/3.7 Flash | Each draft step uses a different MTP decoder layer; cycles via `llama_set_nextn_layer_offset()` |
| Shared memory | `is_mem_shared` | Gemma4 | Shares target KV, runs all heads in one graph |

Chain heads mode is auto-detected from the GGUF — no extra flags needed.

## Verifying MTP is Active

Send any completion and check the response `timings` field:
```json
"timings": {
  "draft_n": 3,
  "draft_n_accepted": 3
}
```
Server log will show: `common_speculative_impl_draft_mtp: adding speculative implementation 'draft-mtp'`.

## Checking Model MTP Metadata
```bash
llama-cli --model model.gguf -c 64 -n 0 -ngl 0 --no-warmup --verbose 2>&1 \
  | grep -E "nextn_predict_layers|n_layer_all|n_layer_nextn"
```
- `n_layer_all > n_layer` → embedded MTP heads present
- `nextn_predict_layers > 0` → number of MTP heads
- No output → MTP layer may be in a separate file (search for `-MTP-` in filename)

## MTP Pitfalls
- **APEX Compact and Unsloth quantized models often strip MTP layers** during compaction. Always check `n_layer_all`.
- Step-3.7-Flash MTP file is ~2 GB Q4_K with 3 chain heads (blk.45-47) at `/mnt/data2/models/step-3.7-flash/Step-3.7-Flash-MTP-Q4_K_M.gguf`.
- The `--spec-draft-p-min` flag from early WIP builds was removed — use only `--spec-draft-n-max`.

## Router Config

```ini
[step37-flash-mtp]
model = /mnt/data2/models/step-3.7-flash/Step-3.7-Flash-APEX-Compact.gguf
model-draft = /mnt/data2/models/step-3.7-flash/Step-3.7-Flash-MTP-Q4_K_M.gguf
spec-type = draft-mtp
spec-draft-n-max = 3
ctx-size = 8192
n-gpu-layers = 999
n-gpu-layers-draft = 999
flash-attn = on
