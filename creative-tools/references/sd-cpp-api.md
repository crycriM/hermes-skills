# sd.cpp API Reference

## Endpoint Summary

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | WebUI (Vue.js) |
| GET | `/v1/models` | Server info |
| GET | `/sdcpp/v1/capabilities` | Full schema, available options |
| POST | `/sdcpp/v1/img_gen` | Image generation |
| POST | `/sdcpp/v1/vid_gen` | Video generation |
| GET | `/sdcpp/v1/jobs/{id}` | Job status + results |
| POST | `/sdcpp/v1/jobs/{id}/cancel` | Cancel job |

## Video Generation — `/sdcpp/v1/vid_gen`

### Request

```json
{
  "prompt": "string (required)",
  "negative_prompt": "string",
  "width": 640,
  "height": 352,
  "video_frames": 17,
  "fps": 24,
  "seed": -1,
  "clip_skip": -1,
  "strength": 0.75,
  "moe_boundary": 0.875,
  "vace_strength": 1.0,
  "output_format": "webm",
  "output_compression": 100,
  "sample_params": {
    "scheduler": "default",
    "sample_method": "default",
    "sample_steps": 20,
    "eta": "",
    "flow_shift": "",
    "shifted_timestep": 0,
    "guidance": {
      "txt_cfg": 7,
      "img_cfg": "",
      "distilled_guidance": 3.5,
      "slg_layers": "7,8,9",
      "layer_start": 0.01,
      "layer_end": 0.2,
      "scale": 0
    }
  },
  "high_noise_sample_params": {
    "scheduler": "default",
    "sample_method": "default",
    "sample_steps": -1,
    "eta": "",
    "flow_shift": "",
    "shifted_timestep": 0,
    "guidance": {
      "txt_cfg": 7,
      "img_cfg": "",
      "distilled_guidance": 3.5,
      "slg_layers": "7,8,9",
      "layer_start": 0.01,
      "layer_end": 0.2,
      "scale": 0
    }
  },
  "init_image": "data:image/...;base64,...",
  "end_image": "data:image/...;base64,...",
  "control_frames": ["data:image/...;base64,..."],
  "lora": [
    {"path": "string", "multiplier": 1.0, "is_high_noise": false}
  ],
  "vae_tiling_params": {
    "enabled": false,
    "tile_size_x": 0,
    "tile_size_y": 0,
    "target_overlap": 0.5,
    "rel_size_x": 0,
    "rel_size_y": 0
  },
  "cache": {
    "mode": "disabled",
    "option": "",
    "scm_mask": "",
    "scm_policy_dynamic": true
  }
}
```

### Response

```json
{
  "id": "job-uuid",
  "status": "queued",
  "queue_position": 1,
  "created": 1716000000,
  "kind": "vid_gen"
}
```

## Image Generation — `/sdcpp/v1/img_gen`

Same structure as vid_gen but `width`/`height` map to image dimensions and
`batch_count` replaces `video_frames`/`fps`. No `high_noise_sample_params`.

## Job Status — `GET /sdcpp/v1/jobs/{id}`

### Queued/Generating state

```json
{
  "id": "job-uuid",
  "status": "generating",
  "queue_position": 0,
  "kind": "vid_gen",
  "timing": {
    "created": 1716000000,
    "started": 1716000005,
    "completed": null
  }
}
```

### Completed state

```json
{
  "id": "job-uuid",
  "status": "completed",
  "kind": "vid_gen",
  "timing": {
    "created": 1716000000,
    "started": 1716000005,
    "completed": 1716000120
  },
  "result": {
    "images": [
      {
        "index": 0,
        "b64_json": "..."
      }
    ],
    "output_format": "webm",
    "fps": 24,
    "total_frames": 17
  }
}
```

### Error state

```json
{
  "id": "job-uuid",
  "status": "failed",
  "error": {
    "message": "error description"
  }
}
```

## Job States

- `queued` — waiting in queue
- `generating` — actively processing
- `completed` — done, results available in `result`
- `failed` — error, check `error.message`
- `cancelled` — user cancelled

## Polling Strategy

```bash
# Submit
JOB_ID=$(curl -s -X POST http://127.0.0.1:7860/sdcpp/v1/vid_gen \
  -H "Content-Type: application/json" \
  -d '{"prompt": "...", ...}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Poll
while true; do
  STATUS=$(curl -s "http://127.0.0.1:7860/sdcpp/v1/jobs/$JOB_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "Status: $STATUS"
  [ "$STATUS" = "completed" ] && break
  [ "$STATUS" = "failed" ] && echo "Error" && break
  sleep 5
done
```

## Output Formats

- **Video:** `webm`, `mp4`, `avi` (codec support varies by browser)
- **Image:** `png`, `jpg`, `webp`

## Cache Modes

Available modes: `disabled`, `easycache`, `ucache`, `dbcache`, `taylorseer`,
`cache-dit`, `spectrum`

## Image Inputs

Image parameters accept base64 data URLs:
```
data:image/png;base64,<base64_encoded_image>
```

Supported input targets for vid_gen:
- `init_image` — start frame
- `end_image` — end frame (interpolation)
- `control_frames` — ordered array of conditioning frames

For img_gen:
- `init_image` — seed image
- `mask_image` — inpainting mask
- `control_image` — ControlNet guidance
- `ref_images` — reference images array