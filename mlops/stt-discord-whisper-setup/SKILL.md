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

Long voice transcripts are handled by the `voicemail-handler` skill (dogfood/):
- Short transcripts (~<100 words): agent responds normally
- Long transcripts (~100+ words): saved to `~/voicemails/YYYY-MM-DD_HHMM.md`, agent replies with summary + confirmation

No gateway code involved — pure agent-level behavior via skill.

## Whisper-server (optional, not used by pipeline)

A whisper.cpp HTTP server may still run on `localhost:9000` as systemd service `whisper-server.service`. This is NOT used by the Hermes STT pipeline (which uses CLI, not HTTP). It may be used by other tools.

Service file: `~/.config/systemd/user/whisper-server.service`

```
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json
ExecStart=/opt/whisper.cpp/build/bin/whisper-server -m /opt/whisper.cpp/models/ggml-base.bin --port 9000 --host 127.0.0.1 -t 4 -l en
```

## Troubleshooting

- **"No STT provider available"**: Check `HERMES_LOCAL_STT_COMMAND` is in `~/.hermes/.env` and gateway was restarted
- **ffmpeg not found**: Required for converting .ogg/.mp3 to .wav. Verify `ffmpeg -version`
- **whisper-cli "no GPU found"**: Missing `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.json` in env. The Vulkan loader fails to find the Radeon driver without it. Add to `~/.hermes/.env` and restart gateway. Verify: `VK_ICD_FILENAMES=... whisper-cli` should show `ggml_vulkan: Found 1 Vulkan devices`
- **STT silently fails**: Check gateway logs for "transcription error" or "local STT command failed"
- **faster-whisper import timeout**: First load auto-downloads model (~150MB) to `~/.cache/huggingface/`; subsequent loads are instant
- **Config says provider:local but uses CLI**: Expected — "local" tries faster-whisper first, falls back to CLI. If faster-whisper IS installed (it is), CLI is never reached.

## Key principle

**Never modify Hermes gateway code.** Use env vars, config.yaml, and skills instead. Code modifications don't survive updates and cause merge conflicts. The upstream STT pipeline is designed to be configured, not forked.
