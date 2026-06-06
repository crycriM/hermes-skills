# start-native-router.sh KNOWN_KEYS Validator

The `start-native-router.sh` script has a hardcoded `KNOWN_KEYS` list that validates INI keys before starting the router. This list can lag behind llama-server's actual supported flags.

## Current KNOWN_KEYS (as of llama-server with MTP support)

```
model|ctx-size|cache-type-k|cache-type-v|n-gpu-layers|n-gpu-layers-draft|flash-attn|no-mmap|mmap|jinja|temp|top-p|top-k|min-p|repeat-penalty|presence-penalty|batch-size|ubatch-size|threads|mmproj|chat-template-kwargs|chat-template-file|load-on-startup|draft-max|draft-min|draft-p-min|model-draft|cache-type-k-draft|cache-type-v-draft|rope-scale|rope-freq-base|reasoning|kv-unified|no-warmup|reasoning-budget|spec-type|spec-draft-p-min|spec-draft-n-max
```

## Adding missing keys

If validation fails with "Unknown preset keys" but the key is valid per `llama-server --help`, add it to `KNOWN_KEYS` in `start-native-router.sh`:

```bash
KNOWN_KEYS="...|NEW_KEY|..."
```

## Known missing keys (historical)

- `n-gpu-layers-draft` — added May 2026, was missing despite being a valid llama-server flag since at least v8920
- `spec-type`, `spec-draft-p-min`, `spec-draft-n-max` — MTP (Mixture of Thoughts Pathway) keys added June 2026