# Installing AMD ROCm PyTorch wheels (the part that fights back)

Goal: a venv where `torch.cuda.is_available()` is True on an AMD GPU (`gfx1151`, Radeon 8060S / Ryzen AI MAX+ 395 class) with `torch.version.hip` populated.

## The index is a flat listing, not a PEP 503 index

`https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2/` serves a plain directory listing. Its project pages 404 (`/torch/` → 404), so:

- `uv pip install --index-url <amd-index> torch` fails with `torch was not found in the package registry`.
- Use **`--find-links <amd-index>`** instead, or download the wheel URLs directly. The `href` values are percent-encoded (`torch-2.9.1%2Brocm7.2.0...whl`) — pass them through `urllib.parse.unquote` when printing, keep them encoded when fetching.

## The triton dependency

ROCm torch wheels depend on a matching `triton==<x>+rocm7.2.0.git<hash>` that exists **only** in the AMD listing. Installing the local torch wheel without it fails resolution (`we can conclude that torch==... cannot be used`). Always pass both:

```bash
uv pip install --python <venv>/bin/python \
  --find-links https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2/ \
  /path/to/torch-<ver>+rocm7.2.0*.whl /path/to/torchvision-<ver>+rocm7.2.0*.whl
```

## Working combination (validated on gfx1151, ROCm 7.2.1 host runtime)

| Piece | Version |
|---|---|
| `torch` | `2.9.1+rocm7.2.0.lw.git7e1940d4` (cp312) |
| `torchvision` | `0.24.0+rocm7.2.0.gitb919bd0c` (cp312) |
| `triton` | `3.5.1+rocm7.2.0.gita272dfa8` (auto, cp312) |
| Python | 3.12 (uv-managed) |

Available siblings in the same listing: torch 2.7.1 / 2.8.0 / 2.9.1 / 2.10.0, each with a matching torchvision and `whl` size ~1.6 GB.

## Recipe: keep the AMD build from being clobbered

A project's `requirements.txt` listing bare `torch` will happily resolve an upstream build. Strip those lines, install the rest, then re-assert:

```bash
PY=<venv>/bin/python; UV=$(command -v uv); IDX=https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2/
$UV pip install --python $PY --find-links $IDX /path/to/torch*.whl /path/to/torchvision*.whl
$UV pip install --python $PY -r requirements.notorch.txt
$UV pip install --python $PY --find-links $IDX --reinstall-package torch --reinstall-package torchvision /path/to/*.whl
```

## Fallback indexes

- `https://rocm.nightlies.amd.com/v2/gfx1151/` — wheels built specifically for this chip (alpha ROCm 7.13 nightlies seen there, cp310–cp313). Use when the release wheels report no device.
- `https://download.pytorch.org/whl/rocm6.4/` — upstream ROCm 6.4 wheels (includes gfx1151 in recent torch).
- `https://repo.radeon.com/rocm/manylinux/rocm-rel-6.4/` — older official release train.

## Verification (always run this before trusting the venv)

```python
import torch, torchvision
print(torch.__version__, torch.version.hip, torch.cuda.is_available())
p = torch.cuda.get_device_properties(0)
print(torch.cuda.get_device_name(0), getattr(p, "gcnArchName", "?"), round(p.total_memory/1024**3, 1))
for dt in (torch.float32, torch.float16, torch.bfloat16):
    x = torch.randn(1024, 1024, device="cuda", dtype=dt)
    (x @ x); torch.cuda.synchronize(); print(dt, "ok")
```

Expect `hip` non-None, `gcnArchName` == `gfx1151`, ~124 GiB unified VRAM reported, and all three dtypes passing. On gfx1151 no `HSA_OVERRIDE_GFX_VERSION` is needed — the chip is natively supported.

## Quant kernels on ROCm

ComfyUI's accelerated quant kernels (w4a8 int8, nvfp4) are CUDA-oriented and reported disabled on ROCm; the model then **dequantizes and computes** instead. That is functional, just not accelerated: a W4A8 text encoder loaded and encoded fine. Do not treat a W4A8/NVFP4 file as unusable on AMD — test it.
