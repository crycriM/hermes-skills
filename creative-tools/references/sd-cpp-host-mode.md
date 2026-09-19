# sd-cpp Host Mode (Outside Container)

Running `sd-server` directly on the host using system Vulkan driver.

## Vulkan Setup

The Vulkan loader looks for ICD files in `/etc/vulkan/icd.d/`, but the system
installs them to `/usr/share/vulkan/icd.d/`. Two options:

```bash
# Option 1: Symlink (requires sudo)
sudo ln -sf /usr/share/vulkan/icd.d/radeon_icd.json /etc/vulkan/icd.d/radeon_icd.json

# Option 2: Environment variable at runtime
export VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json
```

Verify with: `vulkaninfo --summary`

## Model Configuration for Sulphur-2-base

Sulphur-2 ships as a **combined safetensors** containing ALL components:
`diffusion_model`, `vae`, `audio_vae`, `vocoder`, `text_embedding_projection`.
Use ONE model file, not separate component paths.

| Component | Path |
|-----------|------|
| Combined model | `~/models/sulphur-2-base/sulphur_dev_fp8mixed.safetensors` |
| LLM (text encoder) | `~/models/sulphur-2-base/model_cache/LTX-Video-0.9.7-dev/llm/gemma-3-12b-it-UD-Q4_K_XL.gguf` |

### Critical: Do NOT use --vae with the combined model

The external VAE file `ltx-2.3-22b-dev_video_vae.safetensors` triggers a **VAE version detection crash** during model load:

```
ERROR: vae version detection failed: unknown tensor format
first_stage_model.encoder.down_blocks.1.conv.conv.bias not found
...
Error: encoder is only implemented for version >= 2
```

The version probe checks for `first_stage_model.` keys which the separate VAE
doesn't use — it uses flat `decoder.*` keys. This causes the encoder init to
fail with "encoder is only implemented for version >= 2".

**Fix**: Pass only `--model` (the combined file). The combined model's internal
`vae` component is loaded automatically and the decoder path works correctly.

For legacy models with separate safetensors files, you may need:
- `--vae-decode-only` — skip encoder init if you only need generation, not encoding
- `--vae-version 1` — if auto-detection fails and you know the VAE is v1

## Command

```bash
cd ~/sources/stable-diffusion.cpp/build_vulkan/bin

# Run as root to avoid /run/udev permission denied errors
# (cricri cannot read /run/udev/watch/ which sd-server iterates during generation)
sudo VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.json ./sd-server \
  --listen-ip 0.0.0.0 \
  --listen-port 7860 \
  --backend vulkan \
  --offload-to-cpu \
  --max-vram 4 \
  --model /home/cricri/models/sulphur-2-base/sulphur_dev_fp8mixed.safetensors \
  --llm /home/cricri/models/sulphur-2-base/model_cache/LTX-Video-0.9.7-dev/llm/gemma-3-12b-it-UD-Q4_K_XL.gguf

**Do NOT add `--vae` here.** The combined model already contains the VAE.
Specifying a separate VAE triggers version detection which crashes.
```

**Important:** Running as user (without sudo) causes generation to fail with
"permission denied" when sd-server iterates `/run/udev/watch/`. The server
starts and responds to API calls, but crashes during actual generation.
Use `sudo -E` to preserve the VK_DRIVER_FILES env var.

## Key Flags Explained

| Flag | Purpose |
|------|---------|
| `--backend vulkan` | Use GPU for computation |
| `--offload-to-cpu` | Keep weights in RAM, load to GPU as needed (required for limited VRAM) |
| `--max-vram 4` | Limit GPU memory to 4GB (avoids OOM on integrated GPUs) |

## Memory Profile

- Model weights: ~55GB loaded to RAM
- GPU: Handles intermediate activations in chunks (limited by --max-vram)
- Warning: Without --max-vram, generation may crash with "Failed to allocate a buffer"

## /run/udev Permission Issue

When running sd-server as a non-root user (e.g., `cricri`), generation fails with
"permission denied" when the server iterates `/run/udev/watch/` looking for
device files. The server starts fine and responds to API calls, but crashes
during the actual generation step.

**Fix**: Run as root (`sudo`) or grant read access to `/run/udev`.

## Testing Generation

```bash
# Check server is up
curl http://127.0.0.1:7860/v1/models

# Submit video generation job
curl -s -X POST http://127.0.0.1:7860/sdcpp/v1/vid_gen \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a cat walking in the grass",
    "width": 640,
    "height": 352,
    "video_frames": 17,
    "fps": 24,
    "sample_params": {"sample_steps": 20}
  }'
```