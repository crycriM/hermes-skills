# NSFW / abliterated LoRAs for Qwen-Image 2.1 (from wildminder/awesome-qwen-image)

Source list: <https://github.com/wildminder/awesome-qwen-image> — the "LoRA & adapters" table flags
its uncensored/NSFW rows with ⚠️, and the caution note beneath it states those repos are
"uncensored, abliterated, or NSFW". Those six rows are what is inventoried below. Fetched and
verified **2026-09-25**; a raw copy of the README at that date is in
`~/.hermes/cache/scratch/awesome-qwen-image-README.md`.

Everything lands in the ComfyUI lora folder, `models/loras`, i.e.
`/mnt/data2/ComfyUI/models/loras/`. Filenames are kept exactly as upstream (two are in Chinese)
so a row in the upstream table maps 1:1 to a file on disk.

## Inventory

| # | Upstream row | File in `models/loras/` | Bytes | Repo | Rank / tensors | Notes |
|---|---|---|---|---|---|---|
| 1 | Hips / buttocks | `qwen2509臀部放大.safetensors` | 472,047,320 | `RunningHubAI/rh-qwen-image-2.1-lora` | rank 32, 1440 | Body-shape slider, ported from a Qwen-2.5-09 derivative. Largest of the six. Keys: `transformer_blocks.N.attn.add_k_proj.lora_A.default.weight` (`.default.` infix → diffusers/PEFT layout, not kohya). |
| 2 | Breasts and hips | `Qwen Image 2.1大胸大臀.safetensors` | 167,830,384 | `RunningHubAI/rh-qwen-image-2.1-lora` | rank 32, 448 | Combined body-shape adapter from the same pack. Header metadata declares `base_model: Qwen/Qwen-Image-2.1`. |
| 3 | RadianceChrome Voluptuous | `RadianceChromeVoluptuous_QwenImage2.1_v1.0.safetensors` | 167,830,056 | `AIImageStudio/RadianceChromeVoluptuous_QwenImage2.1_v1.0` | rank 32, 448 | Already present locally from an earlier session; its sha256 was re-verified against upstream at inventory time. Character-style LoRA. |
| 4 | NSFW LoRA | `nsfw_qwen_21.safetensors` | 159,436,456 | `Wickedlizerd/NSFW-Qwen-Image-2.1-LoRA` | rank 32, 384 | Civitai original by TheseAlpacas, mirrored unmodified. Trained with ai-toolkit 0.13.19, `ss_base_model_version: qwen_image_2`, trigger tag **`nsfw_qwen_lora`**. Keys are prefixed `diffusion_model.` (kohya/ai-toolkit layout). Upstream asks for **25+ steps, `er_sde`, `beta` scheduler on an INT8 ConvRot base**. |
| 5 | NSFW Image Edit | `Qwen-Image-2.1 NSFW Image Edit.safetensors` | 83,943,552 | `RunningHubAI/rh-qwen-image-2.1-aio-nsfw-lora` | rank 16, 448 | Editing LoRA (needs a reference image to matter). Lowest rank of the pack. |
| 6 | Breasts Slider V1 | `Pornmaster_QI2.1_Breasts_Slider_V1.safetensors` | 3,301,944 | `RunningHubAI/rh-qwen-image-2.1-breasts-slider-lora` | rank 1, 252 | 3 MB slider; rank 1 means it is a single direction per target — expect a narrow, strength-driven effect. Keys prefixed `diffusion_model.`, targets start at `transformer_blocks.10`. |

Pre-existing and unrelated: `qwen-image-2.1-fix-1.0-comfy.safetensors` (the community "Fix" LoRA,
also mirrored in repo 1) and `Qwen Edit 2.1 Optimal Settings.json` / `settings.zip`.

**License / provenance**: all six carry the Qwen Research License like the base weights, plus the
upstream caution that a research license is not permission to use them for anything. They are
DiT-only adapters (no text-encoder tensors), so they go on the `LoraLoader` **model** input; the
`clip` input is harmless and `strength_clip` is ignored (see the skill's "Applying a LoRA to a
generation").

## Also in that README, but NOT LoRAs

The "Heretic & abliterated" section is a different category — text encoders and prompt rewriters
with the refusal direction removed, listed as TE/PE repos, not adapters. Two entries matter here:

- **Heretic TE W4A8** (`Karsus1997/Qwen-Image-2.1-Text-Encoder-Heretic-W4A8`) is the text encoder
  this box already runs (`qwen3vl_8b_w4a8_heretic.safetensors`).
- The GGUF/fp8/NVFP4/int8-ConvRot heretic encoders (`pottokao/...`), the bf16 heretic encoder
  (`kkxao/Qwen-Image-2.1-Text-Encoder-Heretic`) and the abliterated heretic rewriters
  (`darrellbest/...`, `base11231/...`) are **not** downloaded. If one is fetched later, it belongs
  in `models/text_encoders` (encoder) or with the PE-T2I service (rewriter), not `models/loras`.

## Fetch recipe (repeatable)

1. Resolve exact filenames and sizes from the HF API rather than hand-encoding URLs — two names
   contain CJK characters and two contain spaces:
   `HfApi().model_info(repo, files_metadata=True)` → `siblings[]` with `.rfilename`, `.size`,
   `.lfs["sha256"]`. All six repos are public and ungated (verified), so no token is needed.
2. Build the URL with `urllib.parse.quote(filename)` appended to
   `https://huggingface.co/<repo>/resolve/main/`, then download with **`wget -c`** (resumable).
   Gotcha: this box's wget rejects `--no-www-authenticate` ("unrecognized option") — do not use it.
3. Verify before trusting: size == API size, **sha256 == `lfs.sha256`**, and the safetensors header
   parses (8-byte little-endian header length, then JSON; count `lora_A`/`lora_B` pairs). A script
   that does fetch + verify in one pass: see the two scratch scripts named in this file's history
   (`fetch_nsfw_loras.py`, `lora_struct_check.py` under `~/.hermes/cache/scratch/`).
4. ComfyUI picks new files up **without a restart**: `GET /object_info/LoraLoader` listed all six
   immediately (7 entries total in that folder).

All six passed size + sha256 + header validation on 2026-09-25. Key-layout differences matter when
reading a load report: rows 1, 2, 3, 5 use the `.lora_A.default.weight` (diffusers/PEFT) shape,
rows 4 and 6 use `diffusion_model.….lora_A.weight` (kohya/ai-toolkit). Both load in ComfyUI's
`LoraLoader`; do not "fix" either into the other's form.

## Interaction with the Ciru accelerator

The Ciru node's own README lists LoRA use as unqualified, so do not assume the accelerator's
prediction is valid with a LoRA attached — run the LoRA without the `CiruTurboPrediction` node
first, and only then try combining them. Also note the sampler advice for row 4 (`er_sde` / `beta`
/ 25+ steps) collides with the accelerator's constraints: `er_sde` is untested there, prediction
needs ≥20 steps, and a reference-image graph needs `full_evaluations` == steps.

## Evidence kept

Four 1024², 16-step, euler/simple, CFG 1, seed 424242 renders were produced on 2026-09-25 through
the plain graph (no Ciru node, no reference image): baseline plus rows 4, 6 and 5. Files:
`output/LoraTest_A_00001_.png` … `LoraTest_D_00001_.png`, ~51 s each, all `status=success`. The
LoRA-vs-baseline pixel comparison was **not** run (testing was stopped by request), so "loads
without error" is proven and "visibly changes the image" is not — diff them before relying on any
of these adapters.
