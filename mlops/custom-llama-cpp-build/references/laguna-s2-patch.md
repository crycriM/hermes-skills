# Laguna S 2.1 (48-layer / 118B-A8B) Patch for llama.cpp b10087

Upstream b10087 (commit 1f66c3ce1) supports Laguna XS.2 (40-layer, 30B-A3B) and M.1 (70-layer, 230B-A10B) but NOT S 2.1 (48-layer, 118B-A8B). The S 2.1 GGUF fails with:

```
error loading model: done_getting_tensors: wrong number of tensors; expected 76, got 69
```

## Patch: 3 files

### 1. `src/models/laguna.cpp` — Add 48-layer type mapping

In `load_arch_hparams()`, add `case 48`:

```diff
     switch (hparams.n_layer()) {
         case 40: type = LLM_TYPE_30B_A3B;   break;  // Laguna-XS.2
+        case 48: type = LLM_TYPE_118B_A8B;  break;  // Laguna-S.2
         case 70: type = LLM_TYPE_230B_A10B; break;  // Laguna-M.1
         default: type = LLM_TYPE_UNKNOWN;
     }
```

### 2. `src/llama-model.h` — Add `LLM_TYPE_118B_A8B` enum value

Insert after `LLM_TYPE_122B_A10B` (near line 133):

```diff
     LLM_TYPE_122B_A10B, // Qwen3.5
+    LLM_TYPE_118B_A8B,  // Laguna-S.2
     LLM_TYPE_196B_A11B, // Step3.5-Flash
```

### 3. `src/llama-model.cpp` — Add string return for new type

In `llm_type_name()`:

```diff
         case LLM_TYPE_122B_A10B:     return "122B.A10B";
+        case LLM_TYPE_118B_A8B:      return "118B.A8B";
         case LLM_TYPE_196B_A11B:     return "196B.A11B";
```

## After patching

Rebuild:

```bash
distrobox enter llama-vulkan-amdvlk -- bash -c '
  cd ~/sources/llama.cpp
  cmake --build build -j --config Release --target llama-server
'
```

## Verify

```bash
distrobox enter llama-vulkan-amdvlk -- \
  env LD_LIBRARY_PATH=/home/cricri/sources/llama.cpp/build/bin \
  "/home/cricri/sources/llama.cpp/build/bin/llama-server" \
  --host 0.0.0.0 --port 8090 \
  --model /home/cricri/models/laguna/UD-Q4_K_M/Laguna-S-2.1-UD-Q4_K_M-00001-of-00003.gguf \
  --n-gpu-layers 999 --flash-attn on --ctx-size 4096 \
  --jinja --mmap --metrics --threads 8
```

If the model loads without errors (allow ~40s for 69GB via mmap), the patch works.

## DFlash note

The DFlash draft model (`laguna-s-2.1-DFlash-Q4_K_M.gguf`, 622MB) requires `--spec-type draft-dflash` support NOT present in upstream b10087. poolsideai's fork has it, but its Vulkan v0.16 backend doesn't detect Strix Halo GPU. For now, run base inference without speculative decoding (~32 tok/s on 118B-A8B MoE).
