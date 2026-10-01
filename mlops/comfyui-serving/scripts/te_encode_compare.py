#!/usr/bin/env python3
"""Encode one prompt with two text encoders and compare the conditioning.

The decisive test for "can I swap this encoder": not whether the graph runs,
but whether the tensor handed to the diffusion model is the same one. Encodes
through each encoder's production path (comfy.sd.load_clip for safetensors,
CLIPLoaderGGUF.load_patcher for gguf) and reports wrapper class, shape and, when
shapes agree, cosine similarity.

Usage:
  <comfyui>/venv/bin/python te_encode_compare.py <A.safetensors> <B.gguf> [prompt]

Edit SAFE/GGUF below or pass paths positionally. Run with cwd = the ComfyUI
clone so folder_paths picks up extra_model_paths.yaml; absolute paths still work
without it.
"""
import gc
import importlib.util
import sys

COMFY = "/mnt/data2/ComfyUI"
sys.path.insert(0, COMFY)

import torch  # noqa: E402
import comfy.sd  # noqa: E402
import comfy.model_management as mm  # noqa: E402
import folder_paths  # noqa: E402

if len(sys.argv) < 3:
    sys.exit(__doc__)
SAFE, GGUF = sys.argv[1], sys.argv[2]
PROMPT = sys.argv[3] if len(sys.argv) > 3 else (
    "A photorealistic close-up portrait of a young woman with dark red lips, "
    "one arm raised tucking hair behind her ear, ring-light catchlight in her eyes.")

# The pack's module name contains a dash and it uses relative imports, so a
# plain sys.path entry will not work.
spec = importlib.util.spec_from_file_location(
    "cgguf", f"{COMFY}/custom_nodes/ComfyUI-GGUF/__init__.py",
    submodule_search_locations=[f"{COMFY}/custom_nodes/ComfyUI-GGUF"])
pkg = importlib.util.module_from_spec(spec)
sys.modules["cgguf"] = pkg
spec.loader.exec_module(pkg)
from cgguf.nodes import CLIPLoaderGGUF  # noqa: E402


def encode(clip, label):
    c = clip.encode_from_tokens_scheduled(clip.tokenize(PROMPT))
    t = c[0][0]
    print(f"{label}")
    print(f"   wrapper class : {type(clip.cond_stage_model).__name__}")
    print(f"   cond shape    : {tuple(t.shape)}  dtype={t.dtype}")
    print(f"   finite        : {bool(torch.isfinite(t).all())}   "
          f"mean={t.float().mean().item():+.4f} std={t.float().std().item():.4f}")
    return t.float()


def free():
    mm.unload_all_models()
    mm.soft_empty_cache()
    gc.collect()


print("=== A: safetensors ===")
clipA = comfy.sd.load_clip(ckpt_paths=[SAFE], clip_type=comfy.sd.CLIPType.QWEN_IMAGE,
                           embedding_directory=folder_paths.get_folder_paths("embeddings"))
tA = encode(clipA, f"   {SAFE.split('/')[-1]}")
del clipA
free()

print("\n=== B: gguf via CLIPLoaderGGUF ===")
node = CLIPLoaderGGUF()
sd = pkg.loader.gguf_clip_loader(GGUF)
clipB = node.load_patcher([GGUF], comfy.sd.CLIPType.QWEN_IMAGE, [sd])
tB = encode(clipB, f"   {GGUF.split('/')[-1]}")
del clipB, sd
free()

print("\n=== comparison ===")
if tA.shape == tB.shape:
    a, b = tA.flatten(), tB.flatten()
    print(f"shapes match -> cosine similarity = "
          f"{(torch.dot(a, b) / (a.norm() * b.norm())).item():.6f}")
    per = torch.nn.functional.cosine_similarity(tA[0], tB[0], dim=-1)
    print(f"per-token cos: min={per.min().item():.4f} "
          f"mean={per.mean().item():.4f} max={per.max().item():.4f}")
else:
    print(f"SHAPE MISMATCH: A {tuple(tA.shape)} vs B {tuple(tB.shape)}")
    print("-> conditioning is not interchangeable; the diffusion model would "
          "receive the wrong context width.")
