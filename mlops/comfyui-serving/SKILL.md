---
name: comfyui-serving
description: Use when installing, serving or wiring models for ComfyUI.
version: 1.0.0
metadata:
  hermes:
    tags: [comfyui, diffusion, rocm, gfx1151, strix-halo, systemd, gguf, text-encoder, image-generation]
---

# ComfyUI serving

Standing up and operating ComfyUI as a service on this box (AMD Strix Halo, gfx1151, ROCm 7.2), wiring its models, and proving that a workflow really runs — not just that the HTTP call returned 200.

## Rules that apply to every instance

1. **Long-running servers go in a systemd `--user` unit, never a background process spawned from an agent session.** Agent-spawned workers live in capped scopes and die with the session/agent restart. Unit files also do **not** inherit the agent's worker memory cap — do not set `MemoryMax` on the unit. Existing pattern on this box: `~/.config/systemd/user/model-manager.service`.
2. **Verify by class/module, not by status code.** `status: success` in `/history` means *a* code path ran, not the intended one. ComfyUI silently substitutes a wrapper when model detection guesses wrong. Read the log line `Requested to load <ClassName>` and assert it is the class you meant. This rule exists because the failure mode is invisible: the graph completes, timings look healthy, the conditioning is wrong. It applies to custom nodes you install yourself too — grep the node's own `print` lines out of the log to confirm it ran; a render can come from a graph whose new branch was silently dropped.
3. **Never trust a `torch` import — assert `torch.version.hip` is set.** A dependency install can silently replace the ROCm build with a PyPI CPU/CUDA wheel, and everything still imports.
4. **Bind deliberately.** `--listen 0.0.0.0` is unauthenticated; ComfyUI expects LAN or a tunnel. Bind the tailscale address instead if it should not be reachable from the LAN.
5. **Readiness is a health check, not a sleep.** Poll `/system_stats` with a bounded loop (~40 × 1 s); ComfyUI is usable in ~5–10 s.
6. **After installing a custom node, force the frontend to re-read its node definitions.** The browser caches node definitions against the ComfyUI version, and that version does not change when you add a node — so a page open across the install does not know the new type. It renders as a placeholder box with **no inputs and no outputs**, and a workflow referencing it loses that branch silently. Fix the frontend state before touching node code: hard reload, then ComfyUI menu → *Refresh Node Definitions* (or from the console: `localStorage.removeItem('Comfy.NodeDefs'); location.reload()`).
7. **Install additively — never delete `output/` or `user/default/workflows/`, and never overwrite an existing workflow file.** This box's renders and saved workflows are production data that outlive every experiment; the user asks for exactly this guarantee whenever a new pack lands. A pack goes in as a fresh `custom_nodes/<repo>` clone, a new workflow is written as a **new** file in `user/default/workflows/`, and a test render sets a distinct `SaveImage` `filename_prefix` so it cannot clobber a prior image. Restart ComfyUI only when the queue is empty (`GET /queue` → both `queue_running` and `queue_pending` empty) — an unnecessary restart is what reads to the user as "you touched my setup". Prove preservation in the report instead of asserting it: cite the file count and mtimes of `output/` and `user/default/workflows/` before and after, and name the files you added.
8. **A delete-anything pass must exclude files written after its own dry run.** ComfyUI writes into `output/` asynchronously, so a scan → approve → delete sequence can eat a render that landed *during* the approval wait (observed: a job finishing 17:48:23 was removed by a delete pass whose dry run started ~17:49, having never appeared in the approved list). Before removing, drop any file whose mtime is newer than the snapshot, or re-derive the keep-set and require an explicit match (same name **and** identical md5/hash) rather than trusting the stale candidate list. Recovery when it still happens: the API graph is in `GET /history/<prompt_id>` (`prompt[2]`) with its own `execution_start` timestamp, so a deleted render is re-runnable — and `GET /history` also tells you whether the file you are about to delete is a fresh job you should leave alone. Confirm a *different* prefix is not `queue_running` before touching `output/` mid-session.
9. **Classify the artifact before planning a replacement: fork, plugin, or weights.** A repo named *accelerator / turbo / enhanced* is usually a custom node that plugs into the ComfyUI already installed, not a ComfyUI fork — read its install section before touching the working stack, because "replace the image gen software" and "add one node" are completely different jobs. For a plugin nothing is replaced: clone into `custom_nodes/`, run the pack's own `tools/doctor.py` (or equivalent) with ComfyUI's venv python, restart, then submit one real graph and assert the pack's own log lines. Report explicitly which existing model files it reuses — the real question behind "can it use my safetensors" is "does my stack and my library survive".

10. **Reports land on Telegram — lead with the outcome, keep the body short.** The user reads these on a phone, and a long multi-section answer gets truncated there (the reply comes back as "show end of msg"). Put the result, the numbers and the numbered options in the first screen, keep the mechanism for when it is asked for, and let a file or a screenshot carry the long evidence.

11. **A verification run is a budget the user grants, not a step you take.** Rendering here is exclusive and expensive, and the user watches the APU — a test sweep that grows past what was approved gets cut off mid-sweep ("do not run or test"), and submitting even one more job after that is the failure. So: fold the whole verification into ONE authorized sweep (baseline + variant, same seed, submitted together), ask before a second sweep, and stop the instant you are told to. When a sweep is cut short, mark in the report exactly what is proven and what is not — files on disk prove the graph *executed*; they do not prove the adapter changed the image or that the setting is sound. Write "loads clean, effect unverified" rather than letting a passing render imply more than it shows.

## Install procedure (order matters)

1. **Clone outside the home partition** — `/mnt/data2/ComfyUI` has the free space. The tree itself is tiny (~60 MB); the venv + torch is the weight.
2. **venv on Python 3.12** — `uv venv --python 3.12 .venv`. Do not use the system 3.14.
3. **Install AMD torch wheels** — see `references/rocm-pytorch-install.md`. The AMD index is a flat file listing, not a PEP 503 index: use `--find-links` or direct wheel URLs, and pass the AMD listing along with the local wheels so the matching `triton` build resolves.
4. **Install the rest of ComfyUI's requirements with the torch lines removed** (`grep -vE '^\s*(torch|torchvision|torchaudio)\s*($|[<>=])' requirements.txt`), then **re-assert the AMD wheels afterwards** — `torchsde`/`kornia`/`spandrel` pull torch and can drag the wrong build in.
5. **Clone custom nodes, then install each pack's `requirements.txt`.** A clone alone leaves the pack dead: ComfyUI-GGUF needs `gguf`, ComfyUI-Manager needs `GitPython`. Symptom is `(IMPORT FAILED)` in the log's `Import times` block, which names the pack and the missing module.
6. **Wire model paths** with `extra_model_paths.yaml` (absolute paths work without `base_path`), pointing at the existing model store rather than duplicating files:

```yaml
cricri_models:
    text_encoders: /mnt/data1/cricri/models
```

Add `diffusion_models`, `vae`, `loras`, `checkpoints` keys as models land. ComfyUI's own `models/` tree keeps working alongside.

7. **Unit + start** (`~/.config/systemd/user/comfyui.service`): `WorkingDirectory` = the clone, `ExecStart` = `<venv>/bin/python main.py --listen 0.0.0.0 --port 8188`, `KillSignal=SIGINT` (ComfyUI wants SIGINT to release VRAM), stdout+stderr appended to a log file, `Restart=on-failure`. Then `systemctl --user daemon-reload && systemctl --user enable --now comfyui`.
8. **Verify** with `scripts/verify-comfyui.sh`.

### Third-party packs that fetch their own models (worked example: ComfyUI-OpenPose)

`custom_nodes/ComfyUI-OpenPose` (node `OpenPose - Get poses`, category `OpenPose`) is installed here and verified end to end.

- **The venv has no `pip`** (it is a `uv venv`). Install pack requirements with `uv pip install --python /mnt/data2/ComfyUI/.venv/bin/python <pkg>`, never `pip install` inside `.venv/bin`. For `cv2`, `opencv-python-headless` is enough and avoids pulling Qt into the venv; re-assert `torch.version.hip` afterwards (rule 3).
- **Model path is derived from `os.getcwd()`, not from the pack's own directory**: the node walks up from cwd to the first `models` folder, so it only finds `models/openpose/` because the unit's `WorkingDirectory` is the ComfyUI clone. Launch ComfyUI from elsewhere and it writes models to the wrong tree.
- **Pre-place and hash-verify the weights instead of letting the node download them.** `alezonta/openpose` holds `body_25.pth` (100 MB) and `body_coco.pth` (200 MB); the node's `os.path.isfile` guard then skips `snapshot_download`. `hf download <repo> <file> --local-dir models/openpose` writes **no** duplicate into `~/.cache/huggingface/hub` when the filenames are given explicitly (passing them via `--include` is ignored — pass them positionally), and only a 28 KB `.cache/` metadata dir lands in the model folder. Compare `sha256sum` against `lfs.sha256` from `https://huggingface.co/api/models/<repo>?blobs=true`.
- **A display-name mapping whose key does not match `NODE_CLASS_MAPPINGS` is harmless** — ComfyUI falls back to the class key. This pack ships exactly that mismatch; it is not the reason a node misbehaves.
- **Verify vision nodes on a neutral image.** This box's own renders are NSFW and `vision_analyze` refuses them, so alignment cannot be checked visually. `input/openpose_test.jpg` (Wikimedia full-length portrait, 1280×1279) is kept as that asset; the pack's own `example/openpose.json` is a UI workflow, not an API graph.
- **Out-of-band harness for a pack whose directory name is not a Python identifier**: `importlib.util.spec_from_file_location("openpose_pack", "<pack>/__init__.py", submodule_search_locations=["<pack>"])`, register in `sys.modules`, then `exec_module` — the pack's relative imports (`from .src import ...`) then resolve. `os.chdir` to the clone first so the node finds `models/`. Running the node directly is the fastest way to test it, but it does not prove ComfyUI loaded it: still submit an API graph (LoadImage → node → SaveImage) and grep the pack's own `print` lines (`checking existence file`, `model alredy downloaded`) out of the log.
- **Behaviour to know**: inputs `input_image` / `typology` (`COCO` 18 joints | `BODY_25` 25 joints) / `transparency`; outputs `image with keypoints`, `keypoints only` (skeleton on black — this is the ControlNet input) and `POSE_KEYPOINT` (dict `{people:[{pose_keypoints_2d:[[x,y,conf],...]}], canvas_height, canvas_width}`). ~2 s per 1024² on the iGPU. A batch >1 silently uses the first image only. Joint coordinates are in pixels of the input canvas.
- **Its `POSE_KEYPOINT` output is NOT the standard ComfyUI shape** — do not wire it into nodes that declare `POSE_KEYPOINT`. The pack returns a bare dict `{people:[{pose_keypoints_2d:[[x,y,conf],…]}], canvas_height, canvas_width}` with **nested triples**; core (`SDPoseDrawKeypoints` does `keypoints[0]["canvas_width"]`) and controlnet_aux expect a **list of frame dicts** whose `pose_keypoints_2d` is **flat** `[x,y,conf,x,y,conf,…]`. Verified: the ultimate-openpose-editor's `pose_normalized` raises `TypeError: '>' not supported between instances of 'list' and 'float'` on the pack's output and succeeds on `np.asarray(kp).reshape(-1)`. Flatten it in an adapter node, or extract with core `SDPoseKeypointExtractor` when the keypoints must feed a pose editor.
- **~1 px joint jitter across processes is normal**: two direct runs are bit-identical, but the same image through the API server can land a joint one pixel off (ROCm conv kernel selection), which shifts the drawn limbs enough to make ~1 % of pixels differ. Do not read that as a broken install.

### Pose control: what a skeleton image still needs

A pose image is inert until a control path exists; `models/controlnet` and `models/model_patches` start empty on this box.

- **Qwen-Image (the base model used here) gets pose through the union DiffSynth control LoRA** `qwen_image_union_diffsynth_lora.safetensors`, applied with `LoraLoaderModelOnly` on the MODEL, with the control image injected as `VAEEncode → ReferenceLatent` (not through a ControlNet node). Confirmed against the official template `image_qwen_image_union_control_lora.json`. The union file covers canny, depth, pose, lineart, softedge, normal, openpose.
- **The DiffSynth model patches do not cover pose**: `qwen_image_{canny,depth,inpaint}_diffsynth_controlnet.safetensors` (loaded by `ModelPatchLoader` → `QwenImageDiffsynthControlnet`, template `image_qwen_image_controlnet_patch.json`). Reaching for those for an OpenPose skeleton is the wrong file.
- **Pose editors are optional and orthogonal to detection.** Detector = photo → skeleton. Editor = author/fix a skeleton with no photo. `huchenlei/ComfyUI-openpose-editor` is the older upstream (needs `comfyui_controlnet_aux`, its only node is `LoadOpenposeJSONNode`, its iframe `postMessage` handling was reported to skip origin validation) — use the local fork instead.

#### westNeighbor/ComfyUI-ultimate-openpose-editor (installed here)

Fully local, no internet at runtime. Nodes in category `ultimate-openpose`: `OpenposeEditorNode` ("Openpose Editor Node") and `AppendageEditorNode` ("Appendage Editor").

- **Clone it manually with the exact folder name `ComfyUI-ultimate-openpose-editor`.** `js/openpose_editor.js` hardcodes `extensions/ComfyUI-ultimate-openpose-editor/ui/OpenposeEditor.html` as its iframe src; a Manager install that renames the folder silently breaks the editor window.
- **`requirements.txt` over-declares: the code imports only torch, numpy, matplotlib, cv2 and `comfy.utils`.** `polygraphy` is dead weight (and drags onnx/protobuf); matplotlib was the only genuinely missing dep here. Install with `uv pip install --python .venv/bin/python matplotlib` and re-assert `torch.version.hip`.
- **Extension URLs come from `WEB_DIRECTORY = "js"`**, so the js is served at `/extensions/ComfyUI-ultimate-openpose-editor/openpose_editor.js` and the modal at `/extensions/ComfyUI-ultimate-openpose-editor/ui/OpenposeEditor.html`. Checking the served 200s is a fast proof the wiring survived the install (a wrong URL shape 404s and reads like a broken pack).
- **The renderer assumes the COCO-18 body layout.** `util.py` carries a 1-indexed `limbSeq` over 18 joints, identical to the OpenPose pack's COCO limb sequence — but **BODY_25 data renders wrong limbs** (verified: a standing subject came out with the legs splayed apart). Feed it `COCO`, never `BODY_25`.
- **Input priority**: `POSE_JSON` (STRING) wins for output, `POSE_KEYPOINT` (socket) wins for editing; both are in the `optional` dict. Outputs `POSE_IMAGE` (rendered skeleton → your control image), `POSE_KEYPOINT`, `POSE_JSON` (coordinates normalised to 0..1).
- **`load_pose()` requires every widget positionally.** A hand-written API graph that passes only `POSE_JSON` or only `POSE_KEYPOINT` dies with `missing 14 required positional arguments` — and `POSE_JSON` must be present (empty string) even when the socket is wired. The UI always sends them, so this only bites headless callers.
- **`AppendageEditorNode` is the genuinely useful part**: pivot at the joint nearest the torso, with `scale`/`x_offset`/`y_offset`/`rotation` and `appendage_type` from `left_upper_arm` … `right_foot`, `torso`, `shoulders`. Verified: `left_full_arm` at scale 1.4 / rotation −25° left the shoulder fixed and moved exactly the elbow and wrist, and the render changed only inside the arm bbox.
- **Feeding it from the OpenPose pack needs an adapter**: the pack's `POSE_KEYPOINT` is the non-standard nested/bare-dict shape (see above), so a direct socket link fails in-graph with `TypeError: '>' not supported between instances of 'list' and 'float'`. Flatten with `np.asarray(kp).reshape(-1)`, wrap the frame dict in a list, and pass it as `POSE_JSON` (or build a two-line adapter node — same bridge pattern as `ComfyUI-PE-T2I`).

## Text encoders: the format trap

A text-encoder **GGUF split into `main.gguf` + `mmproj-*.gguf` is the llama.cpp artifact and is the wrong shape for ComfyUI.** ComfyUI needs the single file with the vision tower merged in (the Comfy-Org format). A text-only encoder file gets **misdetected** and silently routed to the wrong wrapper, producing invalid conditioning while the graph still reports success. Full mechanism, detection keys and the download table: `references/text-encoder-formats.md`. Read it before wiring any Qwen-VL-derived text encoder.

Related rules that do hold: ComfyUI-GGUF pairs an mmproj sidecar by *filename* only (a `.gguf` name containing `mmproj` **and** the text encoder's stem, quant suffix stripped, in the same directory), and that pairing only fires when the text encoder's own GGUF architecture is `qwen2vl`.

## Prompt enhancement layer (Qwen-Image-2.1 PE)

Qwen-Image-2.1 has a prompt-enhancer layer that is easy to mistake for a text encoder. `PE-T2I` and `PE-I2I` are fine-tuned **Qwen3.5-VL 9B** models that take a one-liner (any language) and return `{"rewritten_prompt": "...", "wh_ratio": "3:2"}`. The 1000-word prompts in ComfyUI's official Qwen-Image-2.1 templates are this model's *output style* — the stock template is meant to be fed by one.

- **It is an LLM, not a text encoder.** It never goes in `CLIPLoader`; it runs before the prompt reaches the DiT. Serve it as a second llama-server and call it from the client script.
- **`system_prompt.txt` is mandatory** — it *is* the output contract (JSON shape, length discipline, register). Qwen's repo and the community repacks ship it. Without it the model is useless.
- **`wh_ratio` sets the canvas**: `1:1` 2048², `4:3` 2400×1792, `3:2` 2528×1696, `16:9` 2752×1536, `2:3`/`3:4`/`9:16` transposed. Ignore it and you fight the model's own composition.
- Sources: stock encoders are `text_encoders/qwen3.5_9b_qwen_image_2.1_pe_{t2i,i2i}.int8_convrot.safetensors` (8.82 GiB) in `Comfy-Org/Qwen-Image-2.1`; abliterated GGUF is `pottokao/Qwen-Image-2.1-PE-T2I-Heretic-GGUF` (`pe_t2i_heretic-Q4_K_M.gguf`, 5.49 GiB, T2I only). Qwen Research License — non-commercial.
- **Serve it with the self-contained Vulkan build on its own port.** The distrobox `~/.local/bin/llama-server` is a shared-lib stub and dies with `libllama-server-impl.so: cannot open shared object file`; use `/mnt/data2/sources/strix-halo-llamacpp/vulkan/bin`:

```bash
V=/mnt/data2/sources/strix-halo-llamacpp/vulkan
export VK_ICD_FILENAMES=$V/driver/radeon_icd.x86_64.json
export VK_DRIVER_FILES=$VK_ICD_FILENAMES
export LD_LIBRARY_PATH=$V/driver:$V/bin
"$V/bin/llama-server" -m <pe>.gguf --host 127.0.0.1 --port 8090 \
    -ngl 99 -c 16384 --jinja -a pe-t2i
```

Then `POST /v1/chat/completions` with `system_prompt.txt` as the system message, `temperature 1.0 / top_p 0.95 / top_k 20`, and `chat_template_kwargs.enable_thinking`. Parse the **last** JSON object containing `rewritten_prompt` — thinking prose precedes it, so a naive `json.loads` on the whole response fails.
- Measured here: load ~1.5 s, 35–70 s per rewrite (~1150 tokens), 5.5 GiB resident. Keep it **on demand** (`pe-t2i.service`, started/stopped explicitly, never enabled at boot) — it is a second model resident alongside the DiT and text encoder.

### Getting the rewriter into a graph

- **`CLIPLoaderGGUF` cannot load it.** ComfyUI-GGUF's text-model whitelist has no qwen35 branch and fails loudly, which is at least honest: `ValueError: Unexpected text model architecture type in GGUF file: 'qwen35'`. Verify any candidate encoder with `scripts/probe_te_model.py` before building a graph around it.
- **Working route: a bridge node** — `custom_nodes/ComfyUI-PE-T2I` (`PET2IPromptRewriter`, category `PE-T2I`). It POSTs to the llama-server and returns `prompt` (STRING), `width`/`height` (INT) and `wh_ratio` (STRING), so the rewriter's ratio drives `EmptyLatentImage` through real links instead of a hand-typed widget. The 5.5 GiB stays in the service, out of ComfyUI's process. Proven in-graph: `wh_ratio=3:2` → canvas `1280x832` at `canvas_scale 0.5`, node log line `[PE-T2I] rewritten in 30.4s (1070 tokens)`.
- **When handing a custom node over, explain widget-vs-socket up front and give the wiring map.** Inputs declared without `forceInput` render as widgets with no left-edge socket; the socket appears only when a link is dragged onto the widget row, or via right-click → *Convert Widget to Input*. That reads to a user as "this node has no inputs" and is the most likely support question after any node install — pre-empt it, and state which output goes to which target input rather than saying "wire it in". **Name the widget rows in the order they render, top to bottom, with the value the shipped file sets** (e.g. `enabled=true`, `full_evaluations=25`, `attention=auto`, `allow_edit_prediction=false`): the settings live in the file and in that node, not in the conversation, so "is that setting fixed, and where do I change it?" is otherwise the very next message. If the user cannot see the row at all, it is the cached node definitions (rule 6) — say so with the fix instead of re-describing the node.
- **Fully native alternative**: the stock Comfy-Org `qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot.safetensors` (8.82 GiB) loads through core `CLIPLoader` — ComfyUI core *does* know the qwen35 family (see its `llm_qwen3_5_text_gen` template) — then `TextGenerate` (inputs: `clip`, `prompt`, `max_length`, `sampling_mode`, optional `thinking`) returns the rewritten prompt as a STRING. Costs 8.82 GiB, is the non-abliterated model, leaves the canvas manual, and puts the model in ComfyUI's own process.
- **Serving an API-format graph to the UI**: frontend ≥1.53 accepts API-format JSON on drop (`isApiJson` / `loadApiJson` in the bundle). Write the bare `{"<node_id>": {"class_type": ..., "inputs": ...}}` map — no `prompt`/`client_id` wrapper, since detection requires *every* top-level value to carry `class_type` — into `user/default/workflows/` and it appears in the Workflows sidebar.
- **Inspecting the live frontend from a console**: test connectability with `node.connect(outSlot, targetNode, targetSlot)` and read `outputs[i].links` / `inputs[i].link` back to confirm the link stuck. Sockets are drawn on the canvas, so DOM queries for socket elements return nothing, and `outputs[i].pos === null` is normal on built-in nodes too — neither is a defect signal.
- Do not drive the frontend's loader by hand: `loadApiJson(json, workflow, opts)` needs a real workflow object as its second argument and throws `Cannot read properties of undefined (reading 'isFunction')` otherwise. Verify a graph through the API instead.

### Fidelity: what the abliterated rewriter does with a real brief

Measured on `pe_t2i_heretic-Q4_K_M.gguf` (the only quant pottokao ships) against a 107-word, 19-element NSFW portrait brief:

- **Element retention: 74% at temperature 1.0, 65% at 0.7, 53% with a hardened contract.** Individual runs swing from 18/19 to 10/19 elements — the failure is variance on top of a dominant softening tendency, not a fixed loss.
- **When it drops an element it recodes instead of omitting**: `young woman` → `adult woman` (3/3 samples at T=0.7), `dark green-brown eyes` → `dark brown eyes`, and a stated naked subject reframed from the upper chest up so the anatomy is out of frame. Lower temperature makes the recoding *more* consistent — the sanitized continuation is the high-probability one. Abliteration removed refusal, not the softening behaviour.
- The output lands at 280–360 words against the contract's 400–500, and the model emits **no thinking trace at all** — a constant ~43 non-JSON characters per response even with `enable_thinking: true`. The trained reasoning pass is dead in this build.
- **A stricter system prompt makes retention worse, not better.** A longer contract costs instruction-following capacity this model does not have. Do not reach for prompt engineering first; replace the model.
- Measure, don't eyeball one rewrite: `scripts/pe_fidelity_ab.py` runs the same brief N times against one or two system prompts and reports per-element kept/dropped plus sanitizer signals (recoding, clothing, hedges).
- The node reads `system_prompt_path` on every call, so contracts can be A/B'd from the UI with no code change; wire the node's `prompt` output to a ShowText/PreviewAny node to actually see the rewrite inside the graph.

### The fix that works: a bigger abliterated model behind the same contract

- A 35B-A3B heretic MoE (arch `qwen35moe`, 3B active), served by `pe-t2i-35b.service` on port 8091 (`~/models/pe/start-pe-heretic35b.sh`). Same Vulkan build, same Qwen system prompt, thinking off. The artifact was renamed and moved once: it now lives at `/mnt/data1/cricri/models/qwen3.6/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved.i1-Q4_K_M.gguf` (21.7 GiB); the 36.4 GiB `Q8_K_XL` in the old `Qwen3.6-35B-A3B-heretic-MTP-GGUF-Q8/` directory is gone.
- **A live service is not proof its model path is valid.** The running instance keeps its loaded copy after the file is moved, so `/health` returns `ok` while `start-pe-heretic35b.sh` points at a path that no longer exists — the next restart or `systemctl --user restart` dies. Before restarting any llama-server unit, `test -e` the `-m` argument in its start script and fix it. Check with `ps -o cmd -p $(systemctl --user show <unit> -p MainPID --value)` against the script, and `curl /props` for the path the running instance actually loaded.
- **Measured on the same 107-word, 19-element brief: 100% element retention (57/57 across 3 samples), zero sanitizer signals, 5–8 s per rewrite** — against 74% / 65% / 53% and 25–29 s for the 9B PE Heretic. Load ~36 GB, ~46 s to ready.
- Score your own regexes before blaming the model: every apparent miss in the first pass was a pattern artefact — `turned towards` vs `turned to`, `non-joining` vs `not joined`, and `wears a light horny smile` tripping a garment pattern. Read the samples.
- Trade-off: it is terser (174–207 words against the contract's 400–500) and picks `2:3` where the 9B picked `1:1`. Less invented detail is the price of dropping none of the stated detail.
- Never run it alongside the 9B rewriter; both are on demand and mutually exclusive in memory. Node switch is two widgets: `pe_url` → `http://127.0.0.1:8091`, `thinking` → False.
- `run_qwen21_t2i.py --pe-url` needs a full URL with scheme (`http://127.0.0.1:8091`); a bare `host:port` dies with `unknown url type`.
- **Thinking is on by default in this build, and it eats the budget silently.** A probe with `max_tokens` of 12–64 returns `finish_reason: length` with `content: ""` — every token went into `reasoning_content` before any answer was emitted. That is not a broken service. Send `"chat_template_kwargs": {"enable_thinking": false}` for a normal completion (as the node does with its `thinking` widget off), and give any probe a generous `max_tokens` so an empty string cannot be mistaken for a dead model.

### Additive-only contract

`~/models/pe/system_prompt_additive.txt` is a second contract for the same 35B rewriter: carry the user's stated elements **in their own words**, add only in the gaps (lighting, surfaces, placement, camera), and never choose a ratio — `wh_ratio` echoes the user's or returns `1:1`, so the canvas stays ComfyUI's business.

- Measured: the brief travels through **verbatim** (whole sentences unchanged), additions land as extra observer sentences on lighting, fabric texture and camera/DOF. Nothing substituted, nothing dressed, no recoding — the failure mode is inverted from the trained PE contract.
- **Its worst case is a pass-through, not damage**: with a dense brief the model sometimes decides nothing is missing and returns the brief unchanged (~1 sample in 3). A "The floor" clause demanding one lighting sentence and one frame sentence reduces but does not eliminate it. A no-op is harmless; a lossy rewrite is not.
- **Language: an additive contract answers in the brief's language unless a language rule explicitly outranks the carry-through rule.** With a French brief it returned French (40 FR tokens / 0 EN) even after the language clause was strengthened at the *end* of the contract. Moving it to a numbered `## 0. Language — this rule outranks everything below` section at the top fixed it (0 FR / 43 EN) while keeping the translation faithful. Verbatim carry-through and English normalisation are in direct tension; the model resolves that tension by the position and weight of the rule, not by its wording.
- **Retry-on-no-op belongs in the caller.** `ComfyUI-PE-T2I/nodes.py` retries once with a fresh seed when the rewrite comes back within a few words of the brief, keeps whichever answer added detail, and keeps the first answer if the retry fails to parse. Verified by forcing the branch with a deliberately no-op contract: the guard fired, the bad retry was logged and discarded, no exception escaped.
- If a guaranteed non-empty enhancement is needed, verify in the caller (retry when the rewrite is within a few words of the brief) rather than fighting the contract.

### Auditing a past run: which rewriter served it

- **Never infer the backend from the rewriter's log body.** Both rewriters log at nearly the same token rate (~36 t/s — the 35B MoE runs only ~3B active, so it matches the dense 9B), so task counts and per-task timings under `~/.local/share/pe-t2i*/` cannot tell them apart. The decisive evidence is the systemd unit lifecycle: `journalctl --user -u pe-t2i --since <t1> --until <t2> | grep -iE 'Started|Stopped'` — a unit **stopped before** the batch cannot have served it — cross-checked against the `--pe-url` port in the run script that wrote the batch. Answering "which model ran" from log contents alone is a wrong answer waiting to happen.
- **Recover the brief and flags from the run script, not the image.** The `out.png.prompt.txt` written next to a render holds the *rewritten* prompt; feeding it back re-enhances an already-enhanced prompt. Grep the Hermes state for the script that wrote the batch (`grep -r 'BRIEF=' ~/.hermes/`, or search for `--pe-url` / `--out <batch>`). When the user says "don't read the image prompt", this is what they mean.
- **A "same prompt, new seed" rerun needs ONE new seed across the whole batch** (raw reference + each contract), so the variants stay comparable. Leaving `--seed` unset gives every render a different random seed and the images stop being comparable.
- **A raw batch (no `--enhance`) has no PE in the loop at all** — its "resulting prompt" is verbatim the argument passed. State raw-vs-enhanced per image when delivering a batch; "which PE did image N use" is the first question asked and the answer is often "none".

## Throughput: canvas size and rewriter contention

- **Rendering is exclusive on this box: no local inference alongside ComfyUI.** Observed here — loading a model on the llama.cpp router (`:8079`) while ComfyUI held the DiT + text encoder hard-crashed the machine (reboot, no swap). Treat ComfyUI as owning the APU whenever a job is queued or sampling: no local chat model, no second llama-server, no PE rewriter. Orchestrate image work from a cloud model.
- **Canvas size dominates render time superlinearly.** Measured on Qwen-Image 2.1 here: 1024² ≈ 2.5 s/step, but 1792×2400 (4.3× the pixels) ≈ 50–90 s/step — roughly 20× the per-step cost, not 4×. Iterate prompts at 1024²; reserve a native 2K / 3:4 canvas for the final render. A 28-step 1024² job is ~80 s; the same graph at native 3:4 is ~20–25 min.
- **Never sample while a PE rewriter is resident.** The rewriter (9B on 8090 *or* 35B on 8091) shares iGPU bandwidth with the DiT and drags the sampler to ~90 s/step. Stop the rewriter service before queueing the image job — the rewrite is already baked into the graph at submission, so nothing needs the service afterwards.
- **A job that starts degraded stays degraded.** Stopping the rewriter mid-render frees the memory but does **not** restore sampler speed; the running job keeps its bad state. Interrupt and re-submit a clean job. `POST /interrupt` is honoured only between steps, so at ~90 s/step allow up to a step of latency before the queue clears.
- **Reuse a rewrite instead of paying for another.** The already-computed expanded prompt lives in the live graph: `GET /queue` → `queue_running[0][2]` (index 2 is the API graph) → `"4".inputs.prompt`, canvas at `"5".inputs`. Read it out before interrupting, then submit that prompt directly — no second 30–90 s rewrite.
- **Do not combine `--enhance` with generation in one foreground terminal call.** The rewrite alone takes 30–90 s and the whole call can exceed the foreground timeout, orphaning the job in ComfyUI's queue while the poller dies. Run the client as a background terminal with notify, or call the rewriter directly first and submit the returned prompt yourself.

## Running a workflow headlessly

1. `GET /object_info/<Class>` to confirm the node exists and read its real input names/enums before building a graph — do not guess parameter names.
2. `POST /prompt` with `{"prompt": {<api-format graph>}, "client_id": "<uuid>"}`, then poll `GET /history/<prompt_id>` until the id appears. `status.messages` carries `execution_success` or `execution_error`; `outputs` carries the node results.
3. **To execute an encode-only subgraph, terminate it in `PreviewAny`** (core node, accepts `*`, is an output node). Without an output node ComfyUI prunes the branch and executes nothing. `CLIPLoader → CLIPTextEncode → PreviewAny` is the cheapest end-to-end check that a text encoder loads and encodes.
4. Cross-check the run against the log delta, not just the API response.

## Splicing a node into an existing saved workflow

Wiring a new pack into a workflow the user already saved is a file-editing job, not a click job — and it must leave their file untouched (rule 7).

1. **Read the graph first**: per node the `type`, `pos`, `widgets_values`, `inputs[*].link` and `outputs[*].links`, plus the `links` array (`[id, from_node, from_slot, to_node, to_slot, type]`). Which node currently feeds the consumer (usually the KSampler's `model` input) decides where the new chain goes.
2. **Write a NEW file** in `user/default/workflows/` with its own uuid `id` and `revision: 0`, compact single-line JSON as ComfyUI writes it. Leave the source file byte-identical and hash it before and after — cite both hashes in the report.
3. **Re-bookkeep every link you touch.** New node ids from `last_node_id + 1`, link ids from `last_link_id + 1`; append the new links, repoint the downstream node's `inputs[i].link`, and **edit the upstream node's `outputs[i].links` array** — skipping that last half leaves a wire that looks connected in the JSON and is dead in the UI. Delete the superseded link entry and give the new nodes unique `order` values.
4. **Lint the bookkeeping mechanically before installing**: every `inputs[*].link` must exist in `links` and resolve back to that node and slot; every `outputs[*].links` entry must exist and point back; no dangling endpoints.
5. **Carry widget rows for optional inputs** the user may want to flip (`allow_edit_prediction` style). An optional input the file omits has to be re-added by hand or via right-click *Convert Widget to Input* later. Ship defaults that make the file run as opened.
6. **Prove the file by running it.** Convert it to an API graph and submit it once (`scripts/gui_workflow_to_api.py` → `scripts/run_api_graph.py`). A GUI file cannot be validated server-side, so an executed converted run is the only real evidence the wiring is right.
7. **For that validation run, swap in a neutral prompt and a distinct `SaveImage` prefix.** Leave the user's own prompt in the saved file, and never re-render their NSFW prompt just to test wiring.
8. **Bake the pack's constraints into the file, not into a comment.** A graph with a reference image forces full denoiser evaluation, so it ships as `full_evaluations = sampler steps` with the experimental cheaper setting left as a widget the user can A/B themselves.
9. **A constant a UI change can invalidate is a trap — name the pairing in the handover.** `full_evaluations` must track `steps` and nothing links them, so a graph that ships a fixed count next to a variable step count breaks on the user's first step change, with an exception raised from inside the sampler rather than at validation. Either pin both, ship the setting the user cannot invalidate, or state in the report exactly which widget must be re-synced when the other changes. Re-read the pack's own source for the couplings before handing over a file: the error messages differ per coupling (step floor, count-vs-steps range, reference-image equality, multi-call samplers) and each one tells the user something different about what they changed.

## Log lines worth asserting

| Line | Means |
|---|---|
| `Device: cuda:0 <name> : native` + `AMD arch: gfx1151` | GPU offload is real, not CPU fallback |
| `Requested to load <ClassName>` | the wrapper actually used — assert this is the intended one |
| `Found quantization metadata version N` | ComfyUI-native quant format accepted |
| `Import times` → `(IMPORT FAILED)` | that custom node pack is dead; install its `requirements.txt` |
| `To see the GUI go to: http://...` | server bound where you expect |

## Model acquisition

`hf download <repo> --local-dir <dir> --include '<pattern>'` (the HF cache is duplicated otherwise), then **verify the hash before use**: compare `sha256` against `lfs.sha256` from `https://huggingface.co/api/models/<repo>?blobs=true`. Cite the match in the report; a 5–18 GB download that is silently truncated looks identical otherwise.

**`--local-dir` still leaves a full duplicate under `~/.cache/huggingface/hub`** — a 5.5 GB download occupies ~11 GB until it is pruned. Size the entries with `hf cache list` / `du -sh ~/.cache/huggingface/hub/*` and remove just the repo you re-downloaded (`hf cache prune` only drops *detached* revisions, so a live repo needs its cache directory removed). **Never clear the cache wholesale**: on this box it also holds the embedding, compression and whisper models that other pipelines load at runtime.

## Ciru AMD Halo Qwen 2.1 Turbo (third-party custom node, installed here)

`custom_nodes/ComfyUI-CiruImageAccelerator` — prediction scheduling (TaylorSeer-style) plus a Triton packed-attention kernel for gfx1151.

- **It is a custom node, not a ComfyUI fork, and it replaces nothing.** It ships no weights and inserts on the MODEL wire: `UNETLoader → QwenImage21Cache → CiruTurboPrediction → KSampler`. The existing safetensors keep working untouched; no re-download, and `output/` + `user/default/workflows/` are not touched by the install.
- **Prereqs it needs from core**: `TextEncodeQwenImage21` and `QwenImage21Cache` (both present in ComfyUI 0.37.0). No `pip install`, no Torch swap.
- **`tools/doctor.py` reports the three expected model files as "not in default folder" — that is not a failure** when `extra_model_paths.yaml` supplies the directories. It also prints GPU arch, HIP and Triton. Run it with ComfyUI's own venv python.
- **The shipped `api_examples/*.json` name the official encoder (`qwen3vl_8b_int8_convrot.safetensors`); this box runs the community `qwen3vl_8b_w4a8_heretic.safetensors`.** Patch `clip_name` (node 4) or the graph 400s. Denoiser and VAE names already match the store.
- **Verified on this box** (Torch 2.9.1+rocm7.2, HIP 7.2, Triton 3.5.1 — *older* than the 3.8/HIP 7.15 the author validated on): 1024², 30 steps, CFG 1, euler/simple, `12`/`auto` → **45.2 s** whole prompt (416 native attention calls, 12 full / 18 predicted); 2048² same settings → **191.4 s** with `{'native': 32, 'packed': 384}`. The packed Triton kernel compiles and runs on this stack (author's reference: 173.19 s).
- **Assert these log lines, they are the whole proof**: `Requested to load QwenImage21` (right DiT class), `Ciru AMD Halo Qwen 2.1 Turbo: gfx1151 dense attention ready (2048 packed; 1024 native)`, and `Ciru Turbo Prediction: {... 'attention_calls': ... 'branches': {'(0,)': {'full': 12, 'predicted': 18 ...}}}`.
- **Reference-image (edit) graphs are a special case: `full_evaluations` must equal the sampler step count or the node raises.** Verified on this box with a ref image wired into `TextEncodeQwenImage21` → the `reference_latents` reach the sampler and `power=12, steps=25` dies at KSampler with `RuntimeError: Image editing currently requires full_evaluations equal to sampler steps; enable allow_edit_prediction to try experimental predicted edits`; the same graph at 25/25 succeeds and logs `full: 25, predicted: 0`. So on every edit workflow here (all four saved Qwen workflows: `LoadImageOutput` → `images.image_1`), Ciru gives **no prediction speedup** unless `allow_edit_prediction=true` (experimental) — what it still gives at 2048 is the packed attention path.
- **Every failure the node can raise is a config coupling, and the messages are not interchangeable** (all reproduced here):

  | change the user makes | error |
  |---|---|
  | steps ≠ `full_evaluations` **and** a reference image is wired | `RuntimeError: Image editing currently requires full_evaluations equal to sampler steps; enable allow_edit_prediction to try experimental predicted edits` |
  | steps < 20 | `ValueError: Turbo+ requires at least 20 sampler steps` |
  | `full_evaluations` > steps (steps lowered after the node was set) | `ValueError: full evaluations must be between 6 and <steps>` |
  | sampler evaluates the model twice per step (heun family) | `RuntimeError: Turbo Prediction saw more model calls than sampler steps; this sampler is unsupported` |
  | batch > 1, or the latent shape changes mid-pass | `RuntimeError: Turbo Prediction currently supports batch size one` / `input shape changed within a sampling pass` |

  The heun family (`heun`, `heunpp2`, `exp_heun_2_x0`, `dpmpp_2m_sde_heun` — the sampler in saved workflow 3) is unusable with the node at any setting; `euler`, `euler_ancestral` and `dpmpp_2m` are single-call and fine. Note the step count and `full_evaluations` are **not auto-linked**: changing steps or sampler in the UI is what produces most of these, so treat `full_evaluations` as a value to re-check after any step change.
- **Measured cost of the edit path here** (1024², reference image, euler/simple, CFG 1): 28/28 = **146 s** (992 native attention calls, 28 full, 0 predicted); 28 steps at 12 full with `allow_edit_prediction=true` = **46 s** (480 native calls, 12 full, 16 predicted) — ~3.2× faster, and the only way to get prediction on a reference-image graph.
- **Constraints**: prediction needs ≥20 sampler steps (12 full is the default and the best speed/quality point); batch >1 rejected; cannot combine with EasyCache; CFG >1, LoRAs, other samplers, editing-prediction (`allow_edit_prediction`) are unqualified. For edits set `full_evaluations` = sampler steps.
- **Local change**: the ≥20 floor in `schedule.py` is a conservative guard, not an algorithmic limit — the generator handles short runs fine. Raised floor replaced by `MIN_SAMPLER_STEPS = 12` (original kept as `schedule.py.orig`; a future `git pull` on this node will conflict). A `systemctl --user restart comfyui` is required after such an edit; the pack is imported at startup and there is no hot reload. Re-ran the case the guard was *not* protecting: a reference-image graph at 16 steps with `full_evaluations=12` and no opt-in is still refused in 3 s, so the change moved the step floor only.
- **Measured at 16 steps, dpmpp_2m/simple, CFG 1, 1024², reference image, seed 883195680029544**: 16 full = 59.5 s warm / 608 attention calls; 12 full + 4 predicted = 45.4 s / 480 calls (**1.3×**, matching the 16/12 call ratio — fixed costs dominate at short runs). Fidelity vs the no-prediction baseline: PSNR 39.94 dB, SSIM 0.9849, mean |Δ| 1.62/255, p99 9, 2.0 % of pixels >8/255. Two identical-config renders are bit-identical in pixels (PNG hashes differ only via metadata), so pixel diffing against a same-seed baseline is a valid check. Prediction at short step counts approximates a *smaller* share of the run than the stock presets (25 % at 16/12 vs 60 % at 30/12), which is why the short case is the safer one.
- Keep `attention=auto`: at 1024 it keeps native attention (the custom 1024 path can be *slower*), and only 2048-square gets packed.
- Free the APU before submitting (rendering is exclusive here): `POST /api/unload {"model": ...}` on the model-manager proxy for every loaded router model; 2048² DiT + encoder wants ~100 GB resident.

## Machine facts (this box)

- Model store: `~/models` → `/mnt/data1/cricri/models` (Qwen GGUFs, mmproj files, Wan2.2-TI2V-5B). `/mnt/data2/models` is the llama.cpp router store.
- ComfyUI: `/mnt/data2/ComfyUI`, venv `.venv` (Python 3.12), log `~/.local/share/comfyui/comfyui.log`, unit `comfyui.service`, port 8188. Headless client: `run_qwen21_t2i.py` in that directory (stdlib only; `--server`, `--out`, `--enhance`, `--scale`).
- Prompt rewriter: `~/models/pe/` (GGUF + mandatory `system_prompt.txt` + `start-pe-t2i.sh`), unit `pe-t2i.service` (on demand), port 8090, log `~/.local/share/pe-t2i/pe-t2i.log`.
- Remote access: tailnet `m5.tailc651b0.ts.net` (100.101.195.27) or LAN `10.0.10.11`. Neither is authenticated — never port-forward 8188; tailscale ACLs or an SSH tunnel (`ssh -N -L 8188:127.0.0.1:8188 <host>`) only.
- Disk pressure: check `df -h /mnt/data1 /mnt/data2` before adding models — both fill fast.

### Applying a LoRA to a generation

A LoRA is wired with a `LoraLoader` node between the loaders and the KSampler. **Diffusion-model LoRAs** (tensors under `diffusion_model.transformer_blocks.*` / `img_mlp`, no text-encoder tensors) attach to the **model** input; **text-encoder LoRAs** attach to the **clip** input. For a diffusion-model LoRA the clip input is harmless but `strength_clip` is ignored.

- **Input names are `strength_model` / `strength_clip`** (not `lora_strength_model` / `lora_strength_clip`). Confirm real input names with `GET /object_info/LoraLoader` before building the graph.
- `load_mode` = `standard`; connect `model` → UNETLoader output, `clip` → CLIPLoader output.
- In the headless client, `run_qwen21_t2i.py` gained `--lora` (default file `models/loras/qwen-image-2.1-fix-1.0-comfy.safetensors`), `--lora-name`, `--lora-strength-model` (default 1.0), `--lora-strength-clip` (default 1.0). The node is inserted as id `9` and the KSampler's `model` input is pointed at it.

Inspect a candidate LoRA's targets before wiring it: `safetensors.safe_open(path, framework='pt', device='cpu')` handles **LZ4-compressed** safetensors natively (the file starts with `X\xd0\x00\x00`, the LZ4 block magic), then read `f.metadata()` and the tensor key prefixes to decide model-vs-clip. A `.zip` bundled with a LoRA may be a decoy (a different model's workflow), not the LoRA's settings.

**Inventory already on this box**: the six ⚠️ NSFW rows from `wildminder/awesome-qwen-image` live in `models/loras/` (rank 32 body-shape/style adapters, one rank-1 slider, one rank-16 edit LoRA) — sizes, upstream repos, key layouts and the fetch/verify recipe are in `references/qwen-image-loras.md`. Two use the `.lora_A.default.weight` key shape and two use `diffusion_model.….lora_A.weight`; both are normal. ComfyUI lists new files in `/object_info/LoraLoader` without a restart. **A LoRA that loads without error is not yet a LoRA that did anything** — patch success on a quantized DiT is silent, and the render succeeds either way. Diff a LoRA render against a same-seed baseline (`scripts/image_fidelity_ab.py`) before relying on one, and report "loads clean" separately from "changes the image".

## Reference and script files

- `references/rocm-pytorch-install.md` — AMD wheel index mechanics, exact working versions, fallback indexes, GPU verification snippet.
- `references/text-encoder-formats.md` — which encoder file belongs to which consumer, ComfyUI's TE detection keys, Qwen-Image-2.1 component table.
- `references/submitted-workflow-format.md` — converting a stored workflow (`nodes`/`links`, `type` key) to the API prompt shape, and the 500 that fires when you submit the stored form verbatim.
- `references/frontend-and-fidelity-checks.md` — verifying a file or node in the real UI headlessly (load a saved workflow, read its widget rows, screenshot one node) and the pixel-fidelity A/B recipe for a speed/fidelity knob, plus how to patch a third-party pack's guard safely.
- `references/qwen-image-loras.md` — the six NSFW/abliterated LoRAs from `wildminder/awesome-qwen-image`, now resident in `models/loras/` (sizes, HF repos, ranks, key layouts, which are already local), the resumable fetch+sha256-verify recipe, and the note that the README's "Heretic & abliterated" section is text encoders/rewriters, not LoRAs.
- `scripts/verify-comfyui.sh` — service state, readiness, device stats, node/pack health.
- `scripts/run_api_graph.py` — submit any API-format graph, repoint model filenames with `--set <node>.<input>=<value>`, tag test renders with `--prefix`, hash the images, and print the log lines that appeared during the run (the `Requested to load` / pack-specific assertions, for free).
- `scripts/probe_te_model.py` — ask ComfyUI's own detection which text encoder class a GGUF will resolve to, before running a graph.
- `scripts/gui_workflow_to_api.py` — stored workflow (`nodes`/`links`) → API prompt for a validation submit: widget order read from the live `/object_info`, dangling nodes pruned, `--set node.input=value` overrides, loud warnings on any node whose `widgets_values` do not reconcile.
- `scripts/image_fidelity_ab.py` — PSNR/SSIM/pixel-delta comparison of two renders (plus an optional A | B | 6× diff strip) for judging a speed-vs-fidelity knob; run it with the ComfyUI venv python.
