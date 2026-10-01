# Text encoder formats: llama.cpp vs ComfyUI

Same model, two incompatible packaging conventions. Picking the wrong one fails silently.

## Decision table

| Consumer | Wanted artifact | Notes |
|---|---|---|
| llama.cpp / `llama-server` | `main.gguf` + `mmproj-*.gguf`, loaded with `--mmproj` | vision tower stays a separate file |
| ComfyUI | **one file with text + vision towers merged** (Comfy-Org layout) | `.safetensors` (bf16 / int8_convrot / w4a8) or a GGUF repack that includes vision |

A community GGUF repo frequently publishes *only* the llama.cpp-shaped pair. Downloading "both files" as instructed satisfies llama.cpp and leaves ComfyUI with a text-only encoder.

## Why the split file breaks ComfyUI (mechanism)

1. ComfyUI identifies the architecture from the state dict, not the filename. Qwen3-VL is recognised by a **vision-tower key**: `model.visual.deepstack_merger_list.0.norm.weight` (the 8B/4B test; the 50-layer 32B variant keys off `visual.deepstack_merger_list.0.norm.weight` plus `model.layers.49.self_attn.q_proj.weight`).
2. A text-only 8B Qwen3-VL state dict carries 36 layers at hidden 4096 with `q_norm` present — which is **the same signature as plain Qwen3-8B**. Detection therefore returns `QWEN3_8B`, not `QWEN3VL_8B`.
3. The dispatcher then takes the `QWEN3_8B` branch of any non-IDEOGRAM clip type, which wraps the encoder in the **Flux2-Klein** text model: a 3-layer tap (layers 9/18/27) concatenated to 12288 dims, with the Klein tokenizer and its own prompt template.
4. Result: the intended path (last hidden state, 4096 dims, Qwen-Image template + its own tokenizer) is never used. The graph still completes and `status: success` is returned. The mismatch only bites when the conditioning reaches the diffusion model.

ComfyUI-GGUF's mmproj pairing does not rescue this: `gguf_mmproj_loader` is called only when the *text encoder's* GGUF architecture is `qwen2vl`, so a `qwen3vl` encoder never gets its sidecar merged. The sidecar's own `general.architecture` is typically `clip`, which is not in the pack's accepted vision types (`clip-vision`, `mmproj`).

## Filename rule (only relevant when pairing does fire)

ComfyUI-GGUF matches a sidecar by name in the same directory: a `.gguf` whose name contains `mmproj` **and** contains the text encoder's stem with the quant suffix stripped. `qwen3vl_8b_heretic-Q4_K_M.gguf` + `mmproj-qwen3vl_8b_heretic-f16.gguf` therefore matches. Select **only the text encoder** in the loader node, never the mmproj; the console prints `Using mmproj '...' for text encoder '...'` when it worked, and an explicit error when it did not.

## Qwen-Image-2.1: what a working ComfyUI install actually needs

All three components are separate downloads; a GGUF diffusion model does not bring an encoder or VAE with it.

| Component | ComfyUI folder | Typical files |
|---|---|---|
| Text encoder | `models/text_encoders/` | `qwen3vl_8b_bf16.safetensors` (16.3 GiB), `qwen3vl_8b_int8_convrot.safetensors` (8.7 GiB), `qwen3vl_8b_w4a8.safetensors` (5.9 GiB) |
| Diffusion model | `models/diffusion_models/` | `qwen_image_2.1_bf16.safetensors` (13.3 GiB), `qwen_image_2.1_int8_convrot.safetensors` (6.8 GiB), or a community GGUF UNet |
| VAE | `models/vae/` | `qwen_image_2.1_vae_bf16.safetensors` (0.6 GiB) |

Load the encoder with the **`qwen_image`** type. Abliterated/uncensored derivatives also ship as single-file ComfyUI-shaped encoders — prefer that form over the GGUF pair when the point of the swap is the ablation.

## Measured on this box: safetensors vs the llama.cpp GGUF pair

Same prompt, both encoders through their production load path (`comfy.sd.load_clip` for safetensors, `CLIPLoaderGGUF.load_patcher` for the gguf) — `scripts/te_encode_compare.py`:

| Encoder | Wrapper class | Conditioning shape |
|---|---|---|
| `qwen3vl_8b_w4a8_heretic.safetensors` (Comfy-Org layout) | `QwenImage21TEModel_` | `(1, 42, 4096)` |
| `qwen3vl_8b_heretic-Q6_K.gguf` + its mmproj | `Flux2TEModel_` | `(1, 512, 12288)` |

Not a degraded version of the right tensor — a different tensor, from a different tokenizer and a different tap. Shapes differ, so there is nothing to compare; the DiT cannot consume it. The graph still returns `status: success`. (The three llama.cpp files — `qwen3vl_8b_heretic-Q4_K_M.gguf`, `-Q6_K.gguf`, `mmproj-qwen3vl_8b_heretic-f16.gguf` — were removed from the model store once this was established; `qwen3vl_8b_w4a8_heretic.safetensors` is the only encoder this pipeline needs. Do not re-download the pair "because the repo ships both".)

**A `qwen3vl` GGUF loads silently — it does not error.** `ComfyUI-GGUF`'s `TXT_ARCH_LIST` (`loader.py`) contains `qwen3vl`, so `gguf_clip_loader` takes the `{"llama", "qwen2vl", "qwen3", "qwen3vl", "gemma3"}` branch, applies `LLAMA_SD_MAP`, and returns a text-only state dict. Only the `qwen35`-family arch raises `Unexpected text model architecture type` — that loud failure does not generalise to `qwen3vl`. The mmproj branch is gated on `arch == "qwen2vl"` alone (same file, two lines apart), so a `qwen3vl` encoder never gets its vision tower merged, and detection then lands on `QWEN3_8B` → the Flux2-Klein wrapper.

### So: can a GGUF replace the safetensors encoder?

- **Not a llama.cpp-shaped pair.** `main.gguf` (arch `qwen3vl`, 399 tensors, **zero** `model.visual.*`) + `mmproj-*.gguf` (arch `clip`, vision tensors named `v.blk.*`) is correct for `llama-server`, wrong for ComfyUI. This is what a repo publishes when it ships both consumers; the README that says "add the CLIPLoader and point it at the gguf" is written for a *different* file in the same repo.
- **No ComfyUI-shaped GGUF exists for Qwen-Image 2.1** as of 2026-09 — `Comfy-Org/Qwen-Image-2.1` publishes only `qwen3vl_8b_{bf16,int8_convrot,w4a8}.safetensors`, and `pottokao/Qwen-Image-2.1-Text-Encoder-Heretic-GGUF` pairs its GGUFs with `qwen3vl_8b_bf16_heretic.safetensors` / `qwen3vl_8b_fp8_heretic.safetensors` for ComfyUI. A merged single-file GGUF (text + `model.visual.*` in one file) would work, but nothing ships one.
- **The memory argument is weak anyway**: w4a8 5.9 GiB vs Q4_K_M 4.7 GiB — ~1.2 GiB against a 6.8 GiB DiT, in exchange for invalid conditioning. Keep the single-file safetensors.
- To check a candidate before wiring it: `scripts/probe_te_model.py` for the detection verdict, then `scripts/te_encode_compare.py` for the real conditioning.

## Cheap confirmation before committing to a workflow

- On a `.safetensors` encoder, read the header JSON (first 8 bytes = header length, then JSON) and confirm the vision key above is present; that alone predicts correct detection.
- Run `scripts/probe_te_model.py` against a GGUF to get ComfyUI's own verdict.
- After a real load, the log must say `Requested to load QwenImage21TEModel_`. If it says `Flux2TEModel_`, the encoder is the wrong shape for ComfyUI.
