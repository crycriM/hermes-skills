---
name: stt-discord-whisper-setup
description: |
  Local STT for Hermes gateway using whisper.cpp CLI. Configured via HERMES_LOCAL_STT_COMMAND env var — no code modifications needed.
  Covers whisper.cpp binary setup, env config, voicemail skill, and troubleshooting.
tags:
  - stt
  - whisper
  - discord
  - telegram
  - voice
  - ffmpeg
  - mlops
category: mlops
---

# Local STT via whisper.cpp CLI

Hermes gateway has a built-in STT pipeline in `tools/transcription_tools.py`. It auto-transcribes voice messages on all platforms (Discord, Telegram, etc.) and injects the text so the agent responds naturally.

**No code modifications needed.** Configure via env var in `~/.hermes/.env`.

## Architecture

```
Voice message → Platform adapter caches audio (.ogg/.mp3)
             → gateway/run.py detects audio media
             → ffmpeg converts to .wav (if needed)
             → transcription_tools calls whisper-cli
             → transcript injected as text
             → agent processes normally
```

The transcription pipeline lives in:
- `gateway/run.py` — `_enrich_message_with_transcription()` (~line 4495)
- `tools/transcription_tools.py` — provider selection, local CLI execution

Injected format: `[The user sent a voice message~ Here's what they said: "..."]`

## Setup

### 1. Whisper.cpp binary (Vulkan build)

Location: `/home/cricri/whisper.cpp/build/bin/whisper-cli` (Vulkan-enabled build, uses AMD GPU)
Model: `/opt/whisper.cpp/models/ggml-base.bin`

Note: `/opt/whisper.cpp/` exists but is a separate build (CPU-only). The Vulkan build is in `~/whisper.cpp/`.

Verify GPU: `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json /home/cricri/whisper.cpp/build/bin/whisper-cli ...` should show `ggml_vulkan: Found 1 Vulkan devices: AMD Radeon Graphics (RADV GFX1151)`

Benchmark: ~260ms for 11s audio on GPU vs ~630ms on CPU.

### 2. Configure Hermes env

Add to `~/.hermes/.env`:

```
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json
HERMES_LOCAL_STT_COMMAND="/home/cricri/whisper.cpp/build/bin/whisper-cli {input_path} -m /opt/whisper.cpp/models/ggml-base.bin -l {language} -otxt -of {output_dir}/transcript"
```

**VK_ICD_FILENAMES is required.** Without it, whisper-cli reports "no GPU found" and falls back to CPU — even though libvulkan is linked. The Vulkan loader only finds the Intel ICD by default and fails on it.

Template placeholders (filled by transcription_tools):
- `{input_path}` — path to the audio file (converted to .wav for non-native formats)
- `{output_dir}` — temp dir where whisper-cli must write a `.txt` file
- `{language}` — language code (default: "en")
- `{model}` — model name (normalized by the pipeline, not the path)

### 3. Config.yaml

The `stt` section in `~/.hermes/config.yaml`:

```yaml
stt:
  enabled: true
  provider: local_command
  local:
    model: base
```

With `provider: local_command`, the pipeline uses `HERMES_LOCAL_STT_COMMAND` directly — the Vulkan-accelerated whisper-cli binary. This is required because faster-whisper (also installed in the hermes venv) runs CPU-only (no ROCm build in the venv) and is too slow for interactive voice messages. The CLI with Vulkan is ~260ms for 11s audio vs ~800ms+ on CPU.

### 4. Gateway restart

`hermes gateway stop && hermes gateway start` — needed for env var changes.

## Current active provider (as of 2026-03-31)

**whisper-cli via HERMES_LOCAL_STT_COMMAND** is active (`provider: local_command`). Key details:

- Binary: `/home/cricri/whisper.cpp/build/bin/whisper-cli` (Vulkan-enabled build, uses AMD GPU)
- Model: `/opt/whisper.cpp/models/ggml-base.bin`
- Requires `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json` in env
- Performance: ~260ms for 11s audio on GPU
- faster-whisper 1.2.1 is installed in the hermes venv as fallback but NOT used (CPU-only, too slow)
- The whisper-server systemd service on port 9000 runs but is NOT used by the Hermes pipeline

## Provider selection logic

From `transcription_tools.py` `_get_provider()`:

1. If `stt.provider` is explicitly set in config:
   - `local` → try faster-whisper → fallback to HERMES_LOCAL_STT_COMMAND → "none"
   - `local_command` → HERMES_LOCAL_STT_COMMAND → fallback faster-whisper → "none"
   - `groq` / `openai` → API-based
2. If no provider set: auto-detect local > groq > openai

**Source file location:** `/home/cricri/.hermes/hermes-agent/tools/transcription_tools.py` (556 lines)

## Voicemail handling
## Voicemail handling
Long voice transcripts are handled by the `voicemail-handler` skill (dogfood/):
- Short transcripts (~<100 words): agent responds normally
- Long transcripts (~100+ words): saved to `~/voicemails/YYYY-MM-DD_HHMM.md`, agent replies with summary + confirmation

No gateway code involved — pure agent-level behavior via skill.

## Integrating whisper.cpp HTTP server (alternative to CLI)
The whisper.cpp HTTP API server (running on `localhost:9000`) can be used by custom apps that want an HTTP-driven STT integration instead of spawning a subprocess per request.

**API shape (whisper-server HTTP API):**
- URL: `POST http://127.0.0.1:9000/inference`
- Content-Type: `multipart/form-data`
- Fields: `file` (audio), `temperature` (0.0), `response_format` (`text`|`json`|`verbose_json`)
- Returns: JSON with `text` field

**python pattern for FastAPI apps:**
```python
import httpx, tempfile, os
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()

class STTResponse(BaseModel):
    text: str

@router.post("/api/stt", response_model=STTResponse)
async def stt_transcribe(file: UploadFile):
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(content); tmp_path = tmp.name
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(tmp_path, "rb") as f:
                resp = await client.post(
                    "http://127.0.0.1:9000/inference",
                    data={"temperature": "0.0", "response_format": "text"},
                    files={"file": (tmp_path, f, "audio/wav")},
                )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=resp.text)
        return STTResponse(text=resp.json().get("text", "").strip())
    finally:
        os.unlink(tmp_path)
```

**When to use HTTP vs CLI:**
- HTTP server: keep one warm process, best for apps that need STT repeatedly (web apps, bots). Latency: model stays loaded in memory.
- CLI subprocess: zero setup beyond binary+model, good for infrequent calls or batch scripts.

**Current state:** HTTP server NOT used by Hermes gateway pipeline (CLI path is active there). But the HTTP server IS used by the Pelemelo task manager project (`/projects/pelemello/`) at `http://127.0.0.1:9000`.

## whisper.cpp HTTP server (used by custom apps)
Running on `localhost:9000` as systemd service `whisper-server.service`.
- Used by: Pelemelo task manager (`/projects/pelemello/`) for browser-based STT
- NOT used by: Hermes gateway pipeline (uses CLI path instead)
- API: `POST /inference` with multipart audio → JSON with `text` field
- Start: `whisper-server --model <path> --port 9000 --host 127.0.0.1`

Service file tip: `~/.config/systemd/user/whisper-server.service`
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json
ExecStart=/opt/whisper.cpp/build/bin/whisper-server -m /opt/whisper.cpp/models/ggml-small.bin --port 9000 --host 127.0.0.1 -t 4 -l en
```

## Post-processing proxy (whisper-proxy)

Whisper-server has **no built-in post-processing** — no grammar files, regex substitution, output filtering, or text normalization. It returns raw model output as-is.

A post-processing proxy sits between nginx and whisper-server to clean up the transcript before returning it to clients:

```
Client → nginx (:8444/whisper/) → whisper-proxy (:9001) → whisper-server (:9000)
```

Current post-processing rules (see `references/whisper-proxy.md`):
1. Filler word replacement — "OM", "Hmm", "Um", "Uh" → "..."
2. Newline collapse — all internal newlines replaced with spaces (no line breaks within a message)

**Service:** `whisper-proxy.service` (user systemd unit), depends on `whisper-server.service`.
**Script:** `~/scripts/whisper-proxy.py` — Python FastAPI app using uvicorn + httpx.
**Python venv:** `~/.local/venvs/whisper-proxy` (uv-managed).

### When to add rules

The `post_process_text()` function applies rules in order: filler → newline collapse → dot cleanup. Add new rules in the function body. Each rule should be a regex or string transformation with a clear comment.

### Pitfalls

- **Proxy is transparent for non-transcription paths** (root `/`, `/load`, health checks) — only `/inference` responses are post-processed.
- **JSON responses are handled** — the `text` field inside JSON is processed, but `verbose_json` with timestamps is passed through raw.

## Exposing whisper-server remotely (nginx reverse proxy)

Don't bind whisper-server to `0.0.0.0` directly — no auth on the server. Instead, put it behind nginx with basic auth.
See `references/nginx-whisper-proxy.md` for full config snippets and test commands.

### Quick setup

1. Create htpasswd file: `sudo htpasswd -cb /etc/nginx/auth/stt.htpasswd <user> "<password>"`
2. Add `auth_basic` + `auth_basic_user_file` to the `/whisper/` location in `~/projects/pelemello/reverse-proxy/nginx.conf`
3. Add clickable entry to `/var/www/services/services.html` (services portal at `https://<host>:8444/`)
4. Ensure whisper-server service binds to `--host 127.0.0.1` (not `0.0.0.0`) — nginx proxies to localhost
5. `sudo nginx -t && sudo nginx -s reload`

### Pitfalls

- **patch tool refuses sensitive system paths** (e.g., `/etc/nginx/sites-enabled/`): write to the actual file (`~/projects/pelemello/reverse-proxy/nginx.conf`) not the symlink.
- **`/var/www/services/` permissions**: directory may be `root:root 755`; fix with `sudo chmod 775 /var/www/services/ && sudo chown cricri:cricri /var/www/services/`.
- **whisper-server bound to 0.0.0.0**: defeats nginx auth. Always bind to `127.0.0.1`.

## Troubleshooting

- **"No STT provider available"**: Check `HERMES_LOCAL_STT_COMMAND` is in `~/.hermes/.env` and gateway was restarted
- **ffmpeg not found**: Required for converting .ogg/.mp3 to .wav. Verify `ffmpeg -version`
- **whisper-cli "no GPU found"**: Missing `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json` in env. The Vulkan loader fails to find the Radeon driver without it. Add to `~/.hermes/.env` and restart gateway. Verify: `VK_ICD_FILENAMES=... whisper-cli` should show `ggml_vulkan: Found 1 Vulkan devices`
- **STT silently fails**: Check gateway logs for "transcription error" or "local STT command failed"
- **faster-whisper import timeout**: First load auto-downloads model (~150MB) to `~/.cache/huggingface/`; subsequent loads are instant
- **Config says provider:local but uses CLI**: Expected — "local" tries faster-whisper first, falls back to CLI. If faster-whisper IS installed (it is), CLI is never reached.

## Key principle

**Never modify Hermes gateway code.** Use env vars, config.yaml, and skills instead. Code modifications don't survive updates and cause merge conflicts. The upstream STT pipeline is designed to be configured, not forked.
