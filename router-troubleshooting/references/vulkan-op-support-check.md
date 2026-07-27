# Vulkan Backend Op Support Verification

When a new model architecture is added to llama.cpp (or when building from a PR), verify that all ggml ops used by the model are supported by the Vulkan backend.

## Technique

### 1. Extract ops used by the model code

```bash
cd ~/sources/llama.cpp

# Get all ggml_* function calls used by the model
grep -oE "ggml_[a-z_]+\(" src/models/<model_name>.cpp | sed 's/(//' | sort -u > /tmp/model_ops.txt
cat /tmp/model_ops.txt

# Also check KV cache code if the model has custom cache
grep -oE "ggml_[a-z_]+\(" src/llama-kv-cache-<variant>.cpp | sed 's/(//' | sort -u >> /tmp/model_ops.txt
sort -u /tmp/model_ops.txt -o /tmp/model_ops.txt
```

### 2. Extract ops supported by Vulkan backend

```bash
grep -oE "GGML_OP_[A-Z_]+" ggml/src/ggml-vulkan/ggml-vulkan.cpp | sort -u > /tmp/vk_ops.txt
wc -l /tmp/vk_ops.txt
```

### 3. Cross-reference to find gaps

```bash
while read op; do
  # Skip non-op functions (builders, utilities)
  case "$op" in
    ggml_build_*|ggml_row_size|ggml_init*) continue ;;
  esac
  
  # Map ggml_* to GGML_OP_*
  upper=$(echo "$op" | sed 's/ggml_/GGML_OP_/' | tr 'a-z' 'A-Z')
  
  # Some ops have different names (ggml_cast → GGML_OP_CPY, ggml_scale_bias → GGML_OP_SCALE)
  case "$op" in
    ggml_cast) upper="GGML_OP_CPY" ;;
    ggml_scale_bias) upper="GGML_OP_SCALE" ;;
    ggml_rope_ext|ggml_rope_ext_back) upper="GGML_OP_ROPE" ;;
  esac
  
  if ! grep -q "$upper" /tmp/vk_ops.txt; then
    echo "MISSING: $op ($upper)"
  fi
done < /tmp/model_ops.txt
```

### 4. Verify false positives

Some "missing" ops are actually supported under different names or as unary ops:

```bash
# Check if op is implemented as GGML_OP_UNARY with a specific sub-op
grep "GGML_UNARY_OP_$(echo $op | sed 's/ggml_//' | tr 'a-z' 'A-Z')" ggml/src/ggml-vulkan/ggml-vulkan.cpp

# Check if op is implemented via GGML_OP_CPY (type conversion)
grep "GGML_OP_CPY" ggml/src/ggml-vulkan/ggml-vulkan.cpp

# Check if op uses GGML_OP_SCALE (ggml_scale_bias is just scale with bias param)
grep "GGML_OP_SCALE" ggml/src/ggml-vulkan/ggml-vulkan.cpp
```

## Known mappings (as of llama.cpp b9741)

| Model op | Vulkan op | Notes |
|----------|-----------|-------|
| `ggml_cast` | `GGML_OP_CPY` | Type conversion via copy |
| `ggml_scale_bias` | `GGML_OP_SCALE` | Scale with bias param stored in op params |
| `ggml_rope_ext` | `GGML_OP_ROPE` | Extended RoPE uses same op |
| `ggml_rope_ext_back` | `GGML_OP_ROPE_BACK` | Backward RoPE |
| `ggml_sigmoid` | `GGML_OP_UNARY` + `GGML_UNARY_OP_SIGMOID` | Unary op |
| `ggml_relu` | `GGML_OP_UNARY` + `GGML_UNARY_OP_RELU` | Unary op |
| `ggml_silu` | `GGML_OP_UNARY` + `GGML_UNARY_OP_SILU` | Unary op |
| `ggml_gelu` | `GGML_OP_UNARY` + `GGML_UNARY_OP_GELU` | Unary op |

## Example: DeepSeek V4 (PR #24162)

Model code: `src/models/deepseek4.cpp` + `src/llama-kv-cache-dsv4.cpp`

Ops used:
- `ggml_add`, `ggml_mul`, `ggml_div`, `ggml_mul_mat` → ✅ Vulkan
- `ggml_concat`, `ggml_cont`, `ggml_permute` → ✅ Vulkan
- `ggml_soft_max`, `ggml_sum_rows`, `ggml_rms_norm` → ✅ Vulkan
- `ggml_get_rows`, `ggml_set_rows`, `ggml_fill` → ✅ Vulkan
- `ggml_rope_ext`, `ggml_rope_ext_back` → ✅ Vulkan (via GGML_OP_ROPE/ROPE_BACK)
- `ggml_sigmoid` → ✅ Vulkan (via GGML_OP_UNARY)
- `ggml_cast` → ✅ Vulkan (via GGML_OP_CPY)
- `ggml_top_k` → ✅ Vulkan
- `ggml_scale`, `ggml_scale_bias` → ✅ Vulkan (via GGML_OP_SCALE)

**Result:** All DeepSeek V4 ops (compressor, lightning indexer, hyper-connections) are supported by Vulkan backend.

## Caveats

- This only checks op-level support, not performance optimization
- Some ops may be supported but slow (fallback to CPU)
- Flash attention support is separate (check `ggml_vk_flash_attn`)
- Cooperative matrix support varies by GPU (check device capabilities)
