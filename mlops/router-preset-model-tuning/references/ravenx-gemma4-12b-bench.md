# ravenx-Gemma4-12B Benchmark Notes

Reference capture from the on-boarding session (2026-06-16). Use as a worked example when
debugging similar MTP-named, dense 12B-class GGUFs on Strix Halo.

## Model facts

| Field | Value |
|---|---|
| Repo | `deadbydawn101/ravenx-Gemma4-12B-MTP-OBLITERATED-OpenMAI-OpenMythos-deep-reasoning-GGUF` |
| File | `ravenx-Gemma4-12B-MTP-F16.gguf` (23.8 GB, single shard) |
| Architecture (GGUF) | `gemma4` (dense) |
| Layers | 48 (blk.0 through blk.47) |
| Context | 131072 (native) |
| MTP head present? | **NO** — "MTP" is a finetune tag in `general.finetune = 'MTP-deep-reasoning'`. The GGUF has 48 standard transformer blocks, no draft head. |
| Tokenizer | `gemma4` (262144 vocab) |
| Baked-in sampling | temp=1.0, top_p=0.95, top_k=64 |

## Preset (working config on Strix Halo)

```ini
[ravenx-gemma4-12b]
load-on-startup = 0
model = /mnt/data1/cricri/models/ravenx-gemma4-12b-mtp-gguf/ravenx-Gemma4-12B-MTP-F16.gguf
ctx-size = 131072
cache-type-k = q8_0
cache-type-v = q8_0
n-gpu-layers = 999
flash-attn = on
mmap = true
jinja = true
temp = 0.7
top-p = 0.95
min-p = 0.01
repeat-penalty = 1.0
batch-size = 2048
ubatch-size = 1024
threads = 8
```

## Performance (Strix Halo APU, Vulkan, unified memory)

| Workload | Speed | Notes |
|---|---|---|
| Prompt processing | **~108 tok/s** | 35-token prompt, 316ms |
| Generation (factual, 32 tok, temp=0.1) | **~8.3 tok/s** | 3845ms total |
| Generation (creative, 128 tok) | intermittent 500s | Gemma 4 template `<channel|>` parsing bug |
| Model load time on router | ~15s | Spawned on port 35343 |
| VRAM (incl. cache) | ~27 GB | Unified memory, no OOM |

## What broke and why

### Bug 1: `/api/load` on port 8080 returns 404
- llama-server's router does not expose a load endpoint at `/api/load` on `:8080`.
- All `POST /api/load` calls on 8080 return `{"error": {"code": 404, "message": "File Not Found"}}` regardless of model state.
- The correct endpoint is `:8079/api/load` (model-manager proxy).

### Bug 2: `spec-type = draft-mtp` caused crash
- The model name says "MTP" but the GGUF has no MTP layers.
- llama-server log on load attempt:
  ```
  W llama_init_from_model: context type MTP requested but model doesn't contain MTP layers
  E srv    load_model: failed to create MTP context
  ```
- Fix: removed `spec-type`, `spec-draft-n-max`, `spec-draft-p-min`, `cache-type-k-draft`, `cache-type-v-draft` from preset. Used plain autoregressive decoding.

### Bug 3: Subsequent loads returned "model is already running"
- After the failed MTP init, the model-manager proxy cached the model as "loaded" in its state.
- `POST :8079/api/load` returned `{"error": {"code": 400, "message": "model is already running"}}`.
- Fix: `systemctl --user restart model-manager` to clear the cached state.

### Bug 4: Intermittent HTTP 500 on creative prompts
- Gemma 4's baked-in chat template emits `<|channel|>` tokens during generation.
- llama-server itself produces valid text, but the model-manager proxy's streaming parser chokes on `<channel|>` mid-stream:
  ```
  Failed to parse input at pos N: <channel|>...
  ```
- Workaround for benchmarking: use short factual prompts (≤32 tokens). Permanent fix would be a custom chat template that strips channel tokens.

## Verification commands (recipe)

```bash
# 1. Restart router and model-manager after preset change
systemctl --user restart m5-router
sleep 3
systemctl --user restart model-manager
sleep 3

# 2. Confirm model is in the router's model list
curl -s http://localhost:8080/v1/models | python3 -c "
import json,sys
d = json.load(sys.stdin)
for m in d.get('data', []):
    if 'ravenx' in m.get('id',''):
        print('Found:', m['id'])
"

# 3. Load via the model-manager proxy (NOT port 8080)
curl -s -X POST http://localhost:8079/api/load \
  -H "Content-Type: application/json" \
  -d '{"model":"ravenx-gemma4-12b"}'

# 4. Watch the load in router logs
journalctl --user -u m5-router --no-pager --since "30 seconds ago" | grep -iE "load|loaded|model" | tail -10

# 5. Test with a short factual prompt (avoid the channel-token parser bug)
curl -s http://localhost:8079/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ravenx-gemma4-12b",
    "messages": [{"role":"user","content":"What is 2+2?"}],
    "max_tokens": 32,
    "temperature": 0.1
  }' | python3 -m json.tool
```

## Lessons for similar MTP-named GGUFs

Before adding `spec-type = draft-mtp`:
1. Check `general.finetune` field — many finetunes use "MTP" as a marketing tag
2. Check `general.architecture` — only specific architectures have native MTP support
3. Look for MTP-specific tensor names or extra output projections in `gguf-dump` output
4. If uncertain, just use plain decoding. ~8 tok/s on a 12B F16 is already respectable.
