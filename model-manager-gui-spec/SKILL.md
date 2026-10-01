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

## API Endpoints (proxied through GUI → model_manager :8079 → router :8080)

- `GET /api/gpu` — GPU metrics (VRAM, temps, utilization, power mode)
- `GET /api/models` — All configured models with status, size, context, cache type, and **Thinking** column (`enable_thinking` field: Y/N/—)
- `GET /api/available` — Same model list (used by the legacy GUI at `gui/app.js`)
- `POST /api/load` — Load a model: `{"model": "name"}`
- `POST /api/unload` — Unload a model: `{"model": "name"}`
- `POST /api/power-mode` — Set APU power mode: `{"mode": "quiet|balanced|performance"}`

### Thinking column

The models table shows a "Thinking" column derived from the `enable_thinking` field in `/api/models`:
- **Y** (green) — `enable_thinking: true` in preset (thinking model variant)
- **N** (muted) — `enable_thinking: false` in preset (thinking explicitly disabled)
- **—** (gray) — no `chat-template-kwargs` in preset (model default)

## Mobile / small-screen layout

The GUI is used from an Android phone at ~360-412 CSS px. Rules that keep it inside the frame:

- `.header` and `.header-right` must both be `flex-wrap:wrap` — without wrapping the 723px-wide control row forces the whole document wider than the viewport, so the banner looks oversized and the page scrolls sideways.
- The table lives in `<div class="table-wrap">` (`overflow-x:auto`), so a wide table scrolls inside the card instead of pushing the page wide.
- `@media(max-width:768px)` turns the models table into one stacked card per model: `thead` hidden, `tr/td` set to `display:block/flex`, and every `<td>` carries `data-label` so `td::before{content:attr(data-label)}` supplies the column name. Adding a column means adding its `data-label` in the row template in `index.html` (render loop, `m-actions`/`m-name` classes mark the special cells).
- Verify with playwright at 360/412: assert `documentElement.scrollWidth === clientWidth` and that no `tbody td` right edge exceeds the models `.card` right edge.

## Services

`model-manager-gui.service` runs `gui_server.py` (:8081) and is independent of `model-manager.service`, which runs `model_manager.py` (:8079). Restart only the GUI unit for dashboard changes — restarting the proxy/router pair activates staged preset config the user may be holding back.

`gui_server.py` `_send_file()` sends `Cache-Control: no-store`, so edits to `gui/` show up on the next reload without cache clearing.

## Notes

- No authentication layer (LAN-only use)
- Lightweight by design — no heavy JS frameworks
- Uses `llama-slot-pinning` skill for multi-model considerations
