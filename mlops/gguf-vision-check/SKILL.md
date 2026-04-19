---
name: gguf-vision-check
description: Check if GGUF model files support image input, and find vision-enabled GGUF models with mmproj files on HuggingFace. Use when setting up multimodal inference with llama.cpp.
version: 1.0.0
metadata:
  hermes:
    tags: [GGUF, vision, multimodal, llama.cpp, mmproj, image-input]

---

# GGUF Vision Support Check

Most GGUF files are text-only. Vision/multimodal support in llama.cpp requires either:
1. A separate **mmproj GGUF** file (vision encoder, typically CLIP/Siglip-based), loaded with `--mmproj`
2. Vision encoder weights **baked into** the main GGUF (rare, newer approach)

## Step 1: Check if a GGUF has vision support

Use this Python script to inspect a GGUF file:

```python
import sys
from gguf import GGUFReader

path = sys.argv[1]
reader = GGUFReader(path)

# List all metadata keys
for k in sorted(reader.fields.keys()):
    kl = k.lower()
    marker = ""
    if any(x in kl for x in ["vision", "image", "clip", "mmproj", "multimodal", "encoder", "proj"]):
        marker = " <-- VISION"
    print(f"  {k}{marker}")

# Check tensors for vision-related names
vision_tensors = [t.name for t in reader.tensors
    if any(x in t.name.lower() for x in ["vision", "image", "clip", "mmproj", "encoder", "visual"])]
if vision_tensors:
    print(f"VISION TENSORS ({len(vision_tensors)}):")
    for t in vision_tensors[:10]:
        print(f"  {t}")
else:
    print("No vision tensors found -- text-only GGUF.")
```

Pitfall: The `gguf` library's `ReaderField` objects are opaque; don't try to extract string values directly. Just check key names and tensor names -- that's enough to determine vision support.

## Step 1.5: Check HF repo for companion mmproj files

**Critical:** Many VL models store the vision encoder in a **separate mmproj GGUF file** in the same HuggingFace repo. The main GGUF shards will show ZERO vision tensors — that's normal, not a "text-only" verdict. Always check the repo file listing before concluding a model lacks vision.

Look for files matching `*mmproj*.gguf` in the repo tree. If present, the model is VL-capable and needs `--mmproj <path>` at serving time. The mmproj file is typically 0.5–2 GB.

This is especially true for REAP-pruned or quantized community GGUFs (e.g., OpenMOSE repos) where the model card says "VL support kept intact" — the vision encoder survived pruning but lives in the mmproj, not the main shards.

## Step 2: Verify HuggingFace repos have mmproj files

Many HF repos are **gated** (401 without auth). Use `curl -sL` (follow redirects) and handle 401 gracefully:

```python
import subprocess, json

def check_repo(repo):
    url = f"https://huggingface.co/api/models/{repo}"
    r = subprocess.run(["curl", "-sL", "-m", "10", url],
                       capture_output=True, text=True, timeout=15)
    if not r.stdout.strip():
        return None, "empty response"
    try:
        d = json.loads(r.stdout)
    except:
        return None, f"parse error: {r.stdout[:100]}"
    if "error" in d:
        return None, d.get("error", "?")
    siblings = [s["rfilename"] for s in d.get("siblings", [])]
    mmproj = [f for f in siblings if "mmproj" in f.lower()]
    main = [f for f in siblings if f.endswith(".gguf") and "mmproj" not in f.lower()]
    return {"mmproj": mmproj, "main": main}, "ok"
```

Pitfall: Case-sensitive repo names matter. `ggml-org/pixtral-12B-GGUF` redirects to `ggml-org/pixtral-12b-GGUF` -- use `-L` flag.

## Step 3: Serving a vision model

With llama-server, load both files:

```bash
llama-server -m model-Q4_K_M.gguf --mmproj mmproj-model-f16.gguf -ngl 99 -c 4096
```

Then send images via the OpenAI-compatible API using base64 or URL in the message content array.

## Known vision GGUF repos (public, no auth needed)

| Model | Params | Repo | mmproj |
|-------|--------|------|--------|
| Qwen2.5-VL-32B-Instruct | 32B | ggml-org/Qwen2.5-VL-32B-Instruct-GGUF, unsloth/Qwen2.5-VL-32B-Instruct-GGUF | yes (Q8_0, f16) |
| Qwen2.5-VL-7B-Instruct | 7B | ggml-org/Qwen2.5-VL-7B-Instruct-GGUF, unsloth/Qwen2.5-VL-7B-Instruct-GGUF | yes (Q8_0, f16) |
| Qwen2.5-VL-72B-Instruct | 72B | unsloth/Qwen2.5-VL-72B-Instruct-GGUF | yes (BF16, F16, F32) |
| Qwen2-VL-7B-Instruct | 7B | ggml-org/Qwen2-VL-7B-Instruct-GGUF | yes (Q8_0, f16) |
| Mistral-Small-3.1-24B (Pixtral) | 24B | unsloth/Mistral-Small-3.1-24B-Instruct-2503-GGUF | yes (BF16, F16, F32) |
| Pixtral-12B | 12B | ggml-org/pixtral-12b-GGUF | yes (Q8_0, f16) |
| MiniCPM-V-2.6 | 8B | openbmb/MiniCPM-V-2_6-gguf | yes (f16) |
| MiniCPM-o-2.6 (vision+audio) | 8B | openbmb/MiniCPM-o-2_6-gguf | yes (f16) |

Gated (need HF login + license acceptance): Llama-3.2-11B/90B-Vision, LLaVA variants, Phi-4-multimodal.

## Step 0: Important — check the repo for a separate mmproj file first

Before scanning GGUF tensors, check the HF repo file listing. Many VL models store the vision encoder as a **separate mmproj GGUF** (typically 0.5–2 GB) alongside the main shards. If a mmproj file exists, the model supports vision regardless of what's in the main GGUF tensors.

Look for files named like `*-mmproj.gguf` or `mmproj-*.gguf` in the repo root or alongside the quantized shards.

## Common pitfalls

- **"No vision tensors" doesn't mean "not a vision model"** — the VL encoder is almost always in a separate mmproj file. Check the repo listing before concluding text-only.
- **mmproj is separate** -- you must download both the main GGUF and the mmproj GGUF. The mmproj file is typically 0.5-2GB.
- **Architecture mismatch** -- just because a model family has a VL variant doesn't mean every GGUF of that family has vision. E.g. `gemma4` architecture in GGUF doesn't mean the specific GGUF file has vision tensors.
- **Gated repos** -- many popular models (Llama Vision, LLaVA) require HF login. Set `HF_TOKEN` env var or use `huggingface-cli login`.
- **HF API redirects** -- repo names are case-sensitive; pixtral-12B redirects to pixtral-12b. Always use `-L` with curl.
