# sd.cpp Troubleshooting

## `/run/udev` Filesystem Loop — Job Submission Fails

### Symptoms

```
{"error":"server_error","message":"filesystem error: too many levels of symbolic links [./run/udev/watch/NN]"}
```
or
```
{"error":"server_error","message":"filesystem error: cannot increment recursive directory iterator: Permission denied"}
```

### Root Cause

sd-server uses `std::filesystem::recursive_directory_iterator` to scan the job output directory. Inside the `llama-vulkan-radv` container, `/run/udev/watch/` contains device symlinks that form circular references:

```
/run/udev/watch/83 -> b7:22
/run/udev/watch/b7:22 -> 83
```

This loop defeats the recursive iterator, throwing `too many levels of symbolic links`. The `Permission denied` variant occurs in container recreations where the namespace is different.

### Fix Options

**Option A — Recreate container with tmpfs mount:**
```bash
podman stop llama-vulkan-radv && podman rm llama-vulkan-radv

mkdir -p /tmp/sd-jobs
podman run -d \
  --name llama-vulkan-radv \
  --device /dev/kfd --device /dev/dri \
  --group-add video --group-add audio \
  --network host --restart unless-stopped \
  --mount type=tmpfs,destination=/run/udev \
  -v /tmp/sd-jobs:/tmp/jobs:rw \
  -v /mnt/data2/models:/mnt/data2/models:ro \
  -v /mnt/data2/sources:/mnt/data2/sources:ro \
  localhost/llama-vulkan-radv:latest \
  sleep infinity
```

**Option B — Investigate container uid/group mismatch:**
The original container image worked as uid 0 with `cricri` group. A recreated container may run differently. Check inside:
```bash
podman exec llama-vulkan-radv bash -c "id && cat /proc/self/uid_map"
```
Compare with a known-working baseline.

**Option C — Bind mount tmpfs over udev path:**
```
-v tmpfs:/run/udev:rw
```

## Model Loaded But img_gen Not Supported

### Symptom

`POST /sdcpp/v1/img_gen` returns error or the WebUI only shows Video Generation tab.

### Root Cause

The Sulphur/LTX-Video model is video-only. The server correctly reports this in its capabilities.

### Fix

Use `POST /sdcpp/v1/vid_gen` for generation, or load a different model that supports image generation.

Check capabilities:
```bash
curl http://127.0.0.1:7860/sdcpp/v1/capabilities
# Look for: supports_img: true/false, supports_vid: true/false
```

## API Returns 404

### Root Cause

Wrong endpoint path. sd.cpp uses `/sdcpp/v1/` prefix, NOT OpenAI-style `/v1/`.

### Fix

| Wrong | Correct |
|-------|---------|
| `POST /v1/generate` | `POST /sdcpp/v1/vid_gen` |
| `POST /v1/progress` | `GET /sdcpp/v1/jobs/{id}` |
| `GET /v1/config` | `GET /sdcpp/v1/capabilities` |

## Server Not Listening on Port 7860

### Diagnosis
```bash
ss -tlnp | grep 7860
podman exec llama-vulkan-radv ps aux | grep sd-server
podman logs llama-vulkan-radv --tail 30
```

### Fix
Kill any existing sd-server and restart:
```bash
podman exec llama-vulkan-radv pkill -f sd-server
# Then re-run the start command from SKILL.md
```

## Model Load Takes Very Long / OOM

- Sulphur model uses ~55GB RSS at full load
- Ensure host has adequate free RAM before starting
- Monitor with: `podman exec llama-vulkan-radv bash -c "ps aux | grep sd-server | grep -v grep | awk '{print \$6/1024\"MB\"}'"`

## Container Image Pull Fails

```bash
Error: unable to copy from source docker://ghcr.io/ggerganov/llama.cpp:server-vulkan
```
Use the local image, not the remote:
```bash
localhost/llama-vulkan-radv:latest   # NOT ghcr.io/ggerganov/llama.cpp:server-vulkan
```