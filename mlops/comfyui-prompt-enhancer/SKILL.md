---
name: comfyui-prompt-enhancer
description: Use when generating images locally on this box with a prompt enhancer (PE-T2I rewriter) — the full local ComfyUI + Qwen-Image-2.1 workflow, from one-line brief to PNG, with the rewriter service.
version: 1.0.0
metadata:
  hermes:
    tags: [comfyui, prompt-enhancer, pe-t2i, qwen-image-2.1, image-generation, local, amd, strix-halo]
---

# Local ComfyUI image generation with a prompt enhancer

End-to-end workflow for making an image on this box (AMD Strix Halo, gfx1151) when the brief needs enhancing first: one-line prompt → PE-T2I rewriter → Qwen-Image-2.1 DiT → PNG. This is the *image-generation* workflow; the companion `comfyui-serving` skill covers installing/serving ComfyUI and the models. Read this one to actually produce an image with enhancement.

## The three moving parts

1. **ComfyUI** — `/mnt/data2/ComfyUI`, venv `.venv` (Python 3.12), unit `comfyui.service` (systemd --user), port 8188. Log `~/.local/share/comfyui/comfyui.log`.
2. **Prompt rewriter (PE-T2I)** — a served LLM that rewrites a one-line brief into a full DiT prompt. Two options, mutually exclusive in memory (never run both):
   - **9B PE Heretic** — `~/models/pe/pe_t2i_heretic-Q4_K_M.gguf`, unit `pe-t2i.service`, port **8090**. ~5.5 GiB resident.
   - **35B Heretic** — `Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved.i1-Q4_K_M.gguf` (21.7 GB, arch `qwen35moe`), under `/mnt/data1/cricri/models/Qwen3.6-35B-A3B-heretic-Native-MTP-i1-Q4_K_M/`, unit `pe-t2i-35b.service`, port **8091**, started by `~/models/pe/start-pe-heretic35b.sh`. Better fidelity, slower load. Switched from Q8_K_XL (39 GB) to i1-Q4_K_M on 2026-09-23; swap log + restore instructions in `~/models/pe/MODEL_SWAP_2026-09-23.md`.
3. **Headless client** — `run_qwen21_t2i.py` in the ComfyUI dir (stdlib only). `--enhance` runs the rewriter before rendering.

## The one command that does it all

```bash
cd /mnt/data2/ComfyUI
.venv/bin/python run_qwen21_t2i.py "<your brief>" \
  --enhance --no-think \
  --pe-url http://127.0.0.1:8091 \
  --pe-system /home/cricri/models/pe/system_prompt_additive.txt \
  --width 832 --height 1280 --seed 1234 \
  --out /tmp/out.png
```

Arguments (from `run_qwen21_t2i.py`): `prompt` (positional), `--width/--height`, `--steps` (default 25), `--cfg` (default 1.0), `--seed` (default None = random), `--sampler` (euler), `--scheduler` (simple), `--prefix` (qwen21), `--server` (127.0.0.1:8188), `--out`, `--enhance` (rewrite first), `--pe-url` (llama-server base URL — **must include the scheme**, `http://127.0.0.1:8091`, a bare `host:port` dies with `unknown url type`), `--pe-system` (path to the contract), `--pe-max-tokens` (8192), `--no-think` (disable rewriter thinking), `--scale` (canvas scale vs the DiT's native resolution).

The rewriter contract is read on every call, so you can switch contracts per run by changing `--pe-system` — no service restart.

## Choosing a contract

Three contracts ship in `~/models/pe/`. Pick by what you care about:

- **`system_prompt.txt`** — the trained Qwen PE contract. Full observer-style rewrite, pads with skin/texture detail, ~260-320 tokens. Best-looking output, but it has opinions — historically recodes age/colour/undress. Use when you want the polished "official template" look and trust the model's taste.
- **`system_prompt_additive.txt`** — additive-only. Carries your stated elements verbatim, adds only in the gaps (lighting, surfaces, placement, camera), never chooses a ratio (`wh_ratio` echoes your brief or returns `1:1`, so the canvas stays ComfyUI's business). Use when faithfulness matters more than polish — e.g. NSFW where every stated element must survive. **Failure mode: worst case is a pass-through** (dense brief → model decides nothing is missing → returns brief unchanged, ~1 in 3). The retry guard in the node handles a single no-op; a guaranteed non-empty result needs a caller-side retry when the rewrite is within a few words of the brief.
- **`system_prompt_strict.txt`** — stricter discipline, still 9B-grade retention. Intermediate option.
- **`ernie_pe_system_prompt.txt`** — Baidu ERNIE-Image PE contract (3B Ministral-Instruct, Apache-2.0), a different lineage. Untested here; drop-in if you want to compare.

Language rule that bites people: an additive contract answers in the brief's language unless a language rule is placed at the **top** of the contract as a numbered `## 0. Language — this rule outranks everything below` section. Position and weight of a rule beat wording.

## Proving it really ran (don't trust the 200)

`status: success` in `/history` means *a* code path ran, not the intended one. ComfyUI silently substitutes a wrapper when model detection guesses wrong. Verify by:
1. Reading the log line `Requested to load <ClassName>` and asserting it is the class you meant.
2. For the rewriter: grepping the node's own `[PE-T2I] ...` log line out of the ComfyUI log — a render can come from a graph whose enhanced branch was silently dropped.
3. Reading the PNG's embedded prompt (the client saves `out.png.prompt.txt`) to confirm the rewrite actually reached the text encoder.

## Measuring fidelity, not eyeballing one rewrite

Individual runs swing (the 9B ran 18/19 → 10/19 elements on the same brief). Don't judge a contract on one render. `scripts/pe_fidelity_ab.py` runs the same brief N times against one or two contracts and reports per-element kept/dropped plus sanitizer signals (recoding, clothing, hedges). Run it before recommending a contract.

## The graph (for when you need the node, not the CLI)

- The rewriter is a bridge node, `custom_nodes/ComfyUI-PE-T2I` (`PET2IPromptRewriter`, category `PE-T2I`). It POSTs to the llama-server and returns `prompt` (STRING) → wire to a text encoder, `width`/`height` (INT) → `EmptyLatentImage`, `wh_ratio` (STRING) → a ShowText/PreviewAny to see it.
- **Widget-vs-socket gotcha:** inputs declared without `forceInput` render as widgets with no left-edge socket until a link is dragged on, or right-click → *Convert Widget to Input*. A user reads this as "no inputs" — pre-empt it.
- The node's `pe_url` and `thinking` widgets are the switch between the two rewriters: `pe_url` → `http://127.0.0.1:8091`, `thinking` → False for the 35B.
- **Frontend re-read:** after adding the node, the browser caches node definitions. Hard reload, then ComfyUI menu → *Refresh Node Definitions* (or `localStorage.removeItem('Comfy.NodeDefs'); location.reload()`), or the node renders as an empty placeholder box.

## Known failure modes

- `--pe-url` without `http://` scheme → `unknown url type`.
- Bare `host:port` rewriter URL → dies.
- Additive contract on a dense brief → no-op pass-through (retry-on-no-op guard fires once; a double no-op is logged and the first answer kept, never crashes).
- Additive contract answers in the brief's language unless the language rule is at the top.
- Never run the 9B (8090) and 35B (8091) rewriters at once — both on demand, mutually exclusive in ~22-28 GiB of shared memory.
- Don't stack the rewriter with other big models — this box is OOM-sensitive; free memory first if a large model must load.
- **Hard rule (crashed the box 2026-09-24): ComfyUI rendering is exclusive — never run local inference alongside it.** Loading a router model (`:8079`) while ComfyUI holds the DiT + text encoder rebooted the machine. No local chat model, no second llama-server, no PE rewriter while a render is queued or sampling. Run the orchestrating agent on a cloud model when generating images.
- **`vk::Queue::submit: ErrorDeviceLost`** (`ggml_vulkan: device lost on Vulkan0`) is a GPU-level hang on this Strix Halo box, not a model or config defect. It has hit the 35B rewriter right after heavy GPU churn (a ComfyUI render, a large model unload) and then vanished — 12 consecutive requests passed afterwards. Restart the unit (`systemctl --user restart pe-t2i-35b`) and retry; do not go hunting through quant/context/flag changes.
- The client supports a LoRA: `--lora` adds a `LoraLoader` between UNETLoader+CLIPLoader and the KSampler, applying `qwen-image-2.1-fix-1.0-comfy.safetensors` from `ComfyUI/models/loras/`. Tune with `--lora-strength-model` (default 1.0) and pick another file with `--lora-name`. That LoRA is diffusion-only (no text encoder), targeting `transformer_blocks`/`img_mlp`, so it must be wired on the model path, not the clip path.
- **PE rewriter truncation**: The default `--pe-max-tokens` is 8192. Long input prompts (dense NSFW combos) can expand to 300+ tokens and hit the ceiling, causing mid-word truncation and JSON parse failure. Use `--pe-max-tokens 12000` as a safety margin.
- **Prefer the 9B rewriter (port 8090) for NSFW work**: It is faster (7-12s vs longer), less verbose, and the additive contract already adds sufficient detail. The 35B (8091) is better for complex briefs needing creative elaboration.
- **Use `terminal` with `timeout=600` per render, not `execute_code`**: Each render takes ~270s. The kernel's default 300s timeout kills the cell mid-render. `terminal` with explicit timeout lets each render complete.

## Resolution floor

128×128 is too small for the Qwen-Image-2.1 DiT to maintain structural correctness — faces, anatomy, and details degrade. Use **256×256 as the practical minimum** for recognizable output. The DiT's native resolution scale is 1280 (set via `resolution` in `TextEncodeQwenImage21`); the latent canvas should be at least 12.5% of that (~160px) but 256px gives enough pixels for anatomy to resolve properly.

## Image file lookup

When the user references a batch image by number (e.g. "image 78"), it is **not** in a simple sequential path. Check these locations in order:

1. **Runner output** — `/tmp/nsfw_pipeline/<name>_<seed>.png` (runner.py writes sequentially, so "image N" = the Nth file by timestamp in this dir).
2. **Direct renders** — `/mnt/data2/ComfyUI/output/nsfw_N.png` (N is the number the user gave).
3. **Temp renders** — `/tmp/nsfw_<name>_<seed>.png` (one-shot renders with `--out /tmp/nsfw_...`).

The client script is `run_qwen21_t2i.py` (not `run_qwen_it2i.py`). The PE system prompt lives at `~/models/pe/system_prompt_additive.txt`, which is symlinked to `/mnt/data1/cricri/models/pe/system_prompt_additive.txt` — both paths resolve to the same file.

## NSFW prompting notes

The additive contract preserves stated elements but **still hides genitalia** in the output even when `visible genitalia` appears in the prompt. For reliable results, combine `visible genitalia` with `legs spread` (or an equivalent pose cue) — the pose cue is what makes the DiT expose the area.

**User preference for NSFW**: elegant, tasteful, not vulgar. Graceful arm/head movement, delicate positioning, explicit but not crude. Golden-hour outdoor lighting is preferred. Avoid bed/sheets unless explicitly requested. When iterating, keep the same model ethnicity/setting/lighting and vary only pose/expression — the user will correct "ugly" or "too vulgar" output and wants the aesthetic refined, not randomised.

## Reference

- Companion skill `comfyui-serving` — installing/serving ComfyUI, model wiring, the text-encoder format trap, log lines, machine facts.
- Workflow file: `/mnt/data2/ComfyUI/user/default/workflows/qwen_image_2_1_comfyui_workflow_1.json` (Qwen Image 2.1: UNETLoader qwen_image_2.1_int8_convrot.safetensors, CLIPLoader qwen3vl_8b_w4a8_heretic.safetensors, VAE qwen_image_2.1_vae_bf16.safetensors, KSampler seed/steps/cfg).
- Contracts: `~/models/pe/system_prompt*.txt`, `ernie_pe_system_prompt.txt`.
- Rewriter services: `systemctl --user status pe-t2i pe-t2i-35b`; health at `http://127.0.0.1:8090/health` and `:8091/health`.
