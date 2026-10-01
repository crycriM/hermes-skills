#!/usr/bin/env python3
"""Ask ComfyUI itself which text-encoder class a GGUF will resolve to.

Why: ComfyUI detects the architecture from the state dict, and a text-only
encoder file (vision tower living in a separate mmproj) can be classified as a
different, wrong model family. The graph still runs and reports success while
producing invalid conditioning. Check here first, then confirm with a real load
(assert the log's "Requested to load <Class>" line).

Usage:
    <comfyui>/venv/bin/python probe_te_model.py <text_encoder.gguf> [comfyui_dir]

Run it with the ComfyUI venv so comfy/* and the custom node's deps import.
"""
import importlib.util
import sys

if len(sys.argv) < 2:
    sys.exit(__doc__)

TE_PATH = sys.argv[1]
COMFY = sys.argv[2] if len(sys.argv) > 2 else "/mnt/data2/ComfyUI"
sys.path.insert(0, COMFY)

import comfy.sd as S  # noqa: E402

# Load the custom node pack under an alias: its own module names contain a dash
# and it uses relative imports, so a plain sys.path entry will not work.
NODE_DIR = f"{COMFY}/custom_nodes/ComfyUI-GGUF"
spec = importlib.util.spec_from_file_location(
    "cgguf", f"{NODE_DIR}/__init__.py", submodule_search_locations=[NODE_DIR]
)
pkg = importlib.util.module_from_spec(spec)
sys.modules["cgguf"] = pkg
spec.loader.exec_module(pkg)
import cgguf.loader as L  # noqa: E402

loader = getattr(L, "gguf_clip_loader", None) or L.gguf_sd_loader
sd = loader(TE_PATH)
if isinstance(sd, tuple):
    sd = sd[0]

detected = S.detect_te_model(sd)
print(f"file             : {TE_PATH}")
print(f"tensors          : {len(sd)}")
vision = [k for k in sd if ".visual" in k or k.startswith("visual")]
print(f"vision tensors   : {len(vision)}")
print(f"detect_te_model  : {detected}")

# ComfyUI recognises Qwen3-VL by the vision tower; without it the encoder is
# indistinguishable from plain Qwen3 and gets the wrong wrapper.
KEY = "model.visual.deepstack_merger_list.0.norm.weight"
print(f"{KEY}: {'YES' if KEY in sd else 'NO'}")
if "Qwen3VL" not in str(detected):
    print("\nWARNING: not detected as Qwen3-VL. For a Qwen-Image text encoder this means")
    print("         ComfyUI will pick the Flux2-Klein wrapper (3-layer tap, 12288 dims,")
    print("         wrong tokenizer) and still report success. Use the single-file")
    print("         Comfy-Org-shaped encoder with the vision tower included.")
