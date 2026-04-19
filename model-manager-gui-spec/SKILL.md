---
name: model-manager-gui-spec
description: Web GUI dashboard for model management — GPU monitoring, model load/unload, and memory-aware controls. Implemented as gui_server.py on port 8081.
category: mlops/inference
---

# Model-Manager Web GUI

## Implementation Status: DONE

The GUI has been implemented as a pure-Python HTTP server with a static frontend. No Flask/FastAPI/React dependencies — stdlib only.

## Architecture

- **Backend**: `~/llm-server/gui_server.py` — Python 3 stdlib HTTP server
  - Serves static files from `~/llm-server/gui/`
  - Proxies API calls to llama.cpp router on port 8080
  - Default port: **8081** (configurable via `--port`)
- **Frontend**: `~/llm-server/gui/` — vanilla HTML/CSS/JS
  - `index.html`, `app.js`, `style.css`, `components/`
  - Dark theme (Tokyo Night palette)
  - Auto-refreshes GPU metrics and model status
- **Start script**: `~/llm-server/gui/start.sh` → runs `gui_server.py`

## Ports

| Service | Port | Status |
|---|---|---|
| llama.cpp router | 8080 | m5-router.service |
| model-manager proxy | 8079 | model_manager.py |
| model-manager GUI | 8081 | gui_server.py |
| Open WebUI | 8088 | start-open-webui.sh |

## Starting Services

```bash
# Model manager proxy (foreground)
cd ~/llm-server && python3 model_manager.py

# Model manager GUI (foreground)
cd ~/llm-server && python3 gui_server.py

# Or via start script
cd ~/llm-server/gui && bash start.sh

# Open WebUI
bash ~/llm-server/start-open-webui.sh   # port 8088
```

## API Endpoints (proxied through GUI to router)

- `GET /api/gpu` — GPU metrics (VRAM, temps, utilization)
- `GET /api/models` — Currently loaded models with status
- `POST /api/load` — Load a model: `{"model": "name"}`
- `POST /api/unload` — Unload a model: `{"model": "name"}`

## Notes

- No authentication layer (LAN-only use)
- Lightweight by design — no heavy JS frameworks
- Uses `llama-slot-pinning` skill for multi-model considerations
