# Speculative Decoding INI Settings

## E2B + 31B Setup (Strix Halo, draft-max=5 sweet spot)

```ini
[gemma-4-31b]
model = /mnt/data2/models/tiny/gemma-4-31B-it-UD-Q5_K_XL.gguf
model-draft = /mnt/data2/models/tiny/gemma-4-E2B-it-UD-Q8_K_XL.gguf
n-gpu-layers = 999
n-gpu-layers-draft = 999
flash-attn = on
no-mmap = true
batch-size = 512
ubatch-size = 256
cache-type-k = q8_0
cache-type-v = q8_0
draft-max = 5
```

## Qwen3.5-122B + Qwen3.5-0.8B Draft (draft-max=5)

```ini
[qwen35-122b]
model = /home/cricri/models/Qwen3.5-122B-A10B-REAP-20-Q6_K.gguf
model-draft = /home/cricri/models/Qwen3.5-0.8B-Q4_K_M.gguf
n-gpu-layers = 999
n-gpu-layers-draft = 999
flash-attn = on
no-mmap = true
batch-size = 2048
ubatch-size = 1024
cache-type-k = q8_0
cache-type-v = q8_0
draft-max = 5
```

## When NOT to use spec dec (smaller drafts)

For setups like holo3-35b + Qwen3-1.7B where spec dec provides zero improvement:

```ini
# Comment out draft parameters
# model-draft = /path/to/draft-model.gguf
# draft-max = 16
# draft-n-min = 4
# draft-p-min = 0.5
```

## Key arguments

- `--draft` or `--draft-max N` — number of tokens to draft (NOT `--spec-draft-n-max`)
- `--model-draft` — draft model path
- `--n-gpu-layers-draft` — GPU layers for draft model
- `--cache-type-k-draft` — KV cache type for draft (optional)
- `--cache-type-v-draft` — KV cache type for draft (optional)

## Validator caveat

The `start-native-router.sh` script has a hardcoded `KNOWN_KEYS` list that may lag behind llama-server's actual supported flags. If validation fails with "Unknown preset keys" but the key is valid (check `llama-server --help`), add it to `KNOWN_KEYS` in the script. Example: `n-gpu-layers-draft` was missing despite being a valid flag.
