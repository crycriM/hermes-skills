# Sulphur-2-base via Diffusers (Python)

Alternative to sd.cpp C++ server - uses HuggingFace diffusers library.

## Setup

```bash
# Create venv with ROCm-enabled PyTorch (CUDA build won't work on AMD GPU)
uv pip install --python .venv/bin/python3 torch --index-url https://download.pytorch.org/whl/rocm6.2
uv pip install --python .venv/bin/python3 diffusers transformers accelerate safetensors sentencepiece protobuf fastapi uvicorn
```

## Server

```bash
cd ~/models/sulphur-2-base
.venv/bin/python server.py --port 8188
```

Key files:
- `server.py` - FastAPI server with `/generate` endpoint
- `gui.py` - Web GUI on port 9890

## Key Issue: Text Encoder

The model includes a GGUF text encoder (`text_encoders/gemma-3-12b-it-UD-Q4_K_XL.gguf`) which diffusers cannot load directly. 

**Fix**: Load text encoder from HF repo:
```python
from transformers import T5EncoderModel

text_encoder = T5EncoderModel.from_pretrained(
    "SulphurAI/Sulphur-2-base",
    subfolder="text_encoder",
    torch_dtype=torch.float16,
)
```

Then pass to pipeline:
```python
pipe = LTX2Pipeline.from_single_file(
    "sulphur_dev_fp8mixed.safetensors",
    text_encoder=text_encoder,
    torch_dtype=torch.float16,
)
```

## ROCm / AMD GPU

- PyTorch with CUDA build fails on AMD ROCm with "CUDA driver version insufficient"
- Need ROCm-specific PyTorch wheel
- Check with: `python -c "import torch; print(torch.cuda.is_available(), torch.version.hip)"`

## API

```bash
# Health
curl http://127.0.0.1:8188/health

# Generate
curl -X POST http://127.0.0.1:8188/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a cat walking",
    "width": 640,
    "height": 352,
    "num_frames": 33,
    "num_inference_steps": 10
  }'
```

Response includes `video_url` to download the mp4.