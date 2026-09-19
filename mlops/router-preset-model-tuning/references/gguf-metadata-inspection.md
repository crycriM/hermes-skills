# GGUF Metadata Inspection

## Primary tool: gguf-dump (preferred)

If `gguf-dump` is installed (via `pip install gguf`), use it directly:

```bash
gguf-dump /path/to/model.gguf 2>&1 | head -80
```

This dumps all metadata key-value pairs, tensor count, and tensor list. The `head -80` limits output to metadata + first few tensors. Key fields to scan:

```
general.architecture         # Architecture key (e.g. nemotron_h_moe, step35, qwen3)
general.name                 # Full model name
general.size_label           # Size label like "128x2.4B"
general.description          # Provenance info (REAP pruning, base model)
general.sampling.temp        # Baked-in sampling temperature
general.sampling.top_p       # Baked-in top-p
general.tags                 # Tags array — check for 'multimodal'
general.base_model.0.name    # Base model name for fine-tunes
{arch}.block_count           # Number of transformer blocks
{arch}.context_length        # Maximum context length
{arch}.expert_count          # Total experts (MoE)
{arch}.expert_used_count     # Active experts per forward pass
{arch}.embedding_length      # Hidden dimension size
{arch}.attention.head_count  # Number of attention heads
{arch}.rope.freq_base        # RoPE frequency base
tokenizer.ggml.model         # Tokenizer model type (e.g. gpt2, llama)
tokenizer.ggml.pre           # Pre-tokenizer type — 'pixtral' = multimodal!
tokenizer.chat_template      # Baked-in chat template (may be long)
```

## Python fallback (when gguf-dump unavailable)

```python
import struct

def read_gguf_metadata(path, show_all=False):
    with open(path, "rb") as f:
        magic = f.read(4)
        version = struct.unpack("<I", f.read(4))[0]
        tensor_count = struct.unpack("<Q", f.read(8))[0]
        metadata_kv_count = struct.unpack("<Q", f.read(8))[0]
        print(f"GGUF v{version}, tensors: {tensor_count}, metadata KVs: {metadata_kv_count}\n")

        for i in range(metadata_kv_count):
            key_len_bytes = f.read(8)
            if len(key_len_bytes) < 8:
                break
            key_len = struct.unpack("<Q", key_len_bytes)[0]

            # Sanity: GGUF v3 metadata keys are short strings
            if key_len > 1000:
                break
            key = f.read(key_len).decode("utf-8", errors="replace")

            val_type = struct.unpack("<I", f.read(4))[0]

            if val_type == 8:  # string
                s_len = struct.unpack("<Q", f.read(8))[0]
                if s_len > 50000:
                    continue
                val = f.read(s_len).decode("utf-8", errors="replace")
            elif val_type == 4:  # uint32
                val = struct.unpack("<I", f.read(4))[0]
            elif val_type == 5:  # int32
                val = struct.unpack("<i", f.read(4))[0]
            elif val_type == 6:  # float32
                val = struct.unpack("<f", f.read(4))[0]
            elif val_type == 7:  # bool
                val = bool(struct.unpack("<B", f.read(1))[0])
            elif val_type in (0, 1):  # uint8 / int8
                f.read(1); continue
            elif val_type == 9:  # array
                arr_type = struct.unpack("<I", f.read(4))[0]
                arr_len = struct.unpack("<Q", f.read(8))[0]
                if arr_type == 8:
                    for _ in range(arr_len):
                        sl = struct.unpack("<Q", f.read(8))[0]
                        f.read(min(sl, 1000000))
                elif arr_type in (4, 5):
                    f.read(4 * arr_len)
                elif arr_type == 0:
                    f.read(arr_len)
                val = f"[array {arr_len} items]"
            else:
                # skip unknown types
                continue

            if show_all or key in (
                "general.architecture", "general.name", "general.description",
                "general.size_label", "general.base_model.0.name",
                "general.base_model.0.organization",
                "tokenizer.chat_template",
                f"{arch}.block_count", f"{arch}.context_length",
                f"{arch}.embedding_length", f"{arch}.expert_count",
                f"{arch}.expert_used_count", f"{arch}.leading_dense_block_count",
                f"{arch}.rope.freq_base", f"{arch}.attention.sliding_window",
                f"{arch}.feed_forward_length",
                f"{arch}.expert_feed_forward_length",
            ):
                if isinstance(val, str) and len(val) > 200:
                    val = val[:200] + "..."
                print(f"  [{i}] {key} = {val}")
```

## Key fields to extract per architecture

| Architecture | Fields | Notes |
|---|---|---|
| `step35` | `block_count`, `context_length`, `expert_count`, `expert_used_count`, `leading_dense_block_count`, `rope.freq_base`, `attention.sliding_window`, `general.description` | REAP pruning info in `general.description`. SWA ratio is 3:1 (3 SWA per full-attn layer). Default freq_base = 5,000,000. |
| `qwen3`, `qwen3.5` | `block_count`, `context_length`, `expert_count`, `expert_used_count` | No leading dense blocks. Use vendor HF page for template. |
| `llama`, `gemma4` | `block_count`, `context_length` | Dense models. Template usually baked in. |

## Common pitfalls

- **GGUF v3 boundary bug**: metadata keys near the end of the header can have corrupted length values (falsely huge). The parser above breaks when key_len > 1000 — this is expected for v3 GGUFs; the remaining metadata is not recoverable via this method.
- **No `tokenizer.chat_template` found**: Many architectures (step35, mistral4) have built-in templates in llama.cpp. `jinja = true` alone suffices. No need for a separate template file.
- **`general.description` is important**: It contains model provenance like "pruned 40% of experts using REAP method" or "quantized with Q4_K_M". Don't skip it.
- **Single-shard vs multi-shard**: The metadata only tells architecture; check file size to determine if single (.gguf) or multi (-00001-of-N.gguf). Multi-shard models need `no-mmap` decisions handled per the main skill.
