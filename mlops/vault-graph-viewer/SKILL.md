---
name: vault-graph-viewer
description: Local web app for browsing the memory-index vault as an interactive D3.js force-directed graph. Shows wikilinks, semantic similarity edges, orphans, and full note content in a sidebar.
version: 1.0.0
metadata:
  hermes:
    tags: [vault, graph, visualization, d3, flask, chromadb]
---

# Vault Graph Viewer

Flask + D3.js app at `~/memory-index/viewer/`.

## Start

```bash
cd ~/memory-index/viewer && ~/llm-server/venv/bin/python vault_viewer.py
# Opens http://localhost:8055 (also http://192.168.0.44:8055 on LAN)
```

Cold start takes ~12 seconds (loads sentence-transformers all-MiniLM-L6-v2 for semantic edges).

## Architecture

| File | Purpose |
|------|---------|
| `vault_viewer.py` | Flask backend: scans ~/memory-index/*.md, builds graph from [[wikilinks]] + ChromaDB similarity, serves API |
| `static/index.html` | D3.js force-directed graph, sidebar with markdown renderer, search/filter/orphan controls |

### API Endpoints

- `GET /` — serves index.html
- `GET /api/graph` — returns `{nodes: [...], edges: [...]}` (computed once at startup)
- `GET /api/stats` — note count, edge count, orphan count, edge types
- `GET /api/note/<encoded_id>` — full markdown content + metadata for a note (ID is URL-encoded path like `lessons%2F2026-03-25-router-corruption`)

### Graph Data Sources

1. **Wikilink edges**: parsed from `[[name]]` patterns in markdown files (weight: 2)
2. **Semantic edges**: ChromaDB embedding similarity at distance < 0.6 between vault files (weight: 1, dashed green lines)

### Frontend Features

- Color-coded nodes by category (facts=orange, lessons=purple, models=green, projects=blue, etc.)
- Node size proportional to connection count (degree)
- Click node → sidebar loads full note with clickable [[wikilinks]]
- Search bar filters nodes in real time
- "Show orphans" highlights disconnected nodes
- "Labels" toggles node names, "Reset" resets zoom
- Legend categories are clickable to highlight clusters

## Known Bugs Fixed

- Node IDs with slashes (e.g. `lessons/2026-03-25-router-corruption`) need `encodeURIComponent()` in fetch URLs
- `.dimmed` CSS class was missing — added `opacity: 0.15 !important`; also need `.link.dimmed { opacity: 0.05 !important; }`
- Tooltip position used `offsetX/offsetY` (relative to SVG element) instead of `pageX/pageY` minus container offset
- Edge highlighting must handle both pre-simulation (string IDs) and post-simulation (object references) via `e.source.id || e.source`
- **SVG zero-dimension bug**: `container.clientWidth/Height` returns 0 when fetch callback fires before flex layout computes. Fix: use `style("width","100%").style("height","100%")` with `attr("viewBox", ...)` and fallback to `window.innerWidth - 380` / `window.innerHeight`. Also add `min-width: 0; overflow: hidden` on `#graph-area` CSS.
- **Mobile layout**: 380px fixed sidebar swallows entire phone screen. Add `@media (max-width: 768px) { body { flex-direction: column; } #sidebar { width: 100%; min-width: 0; max-height: 40vh; } #graph-area { min-height: 60vh; } }`
- **D3 CDN blocked**: external CDN (d3js.org) may be blocked by browser extensions or network. Bundle D3 locally: download `d3.v7.min.js` to `static/` and use `<script src="/static/d3.min.js">`.
- **Don't duplicate functions via patches**: when patching JS in inline `<script>` tags, fuzzy matching can produce duplicate function definitions. Always read the full file state before patching, or rewrite the whole script block.
- **Add error visibility**: wrap all fetch calls with `.catch()` that writes a red error div into the graph area. Silent failures in D3 are impossible to debug without a browser console.

## Testing Limitations

No headless browser available on Ubuntu 26:
- Playwright doesn't support Ubuntu 26 (chromium or firefox)
- Firefox snap headless `--screenshot` silently fails to write files
- Selenium not installable (PEP 668 + no venv with it)

Validate via API calls (`/api/graph`, `/api/stats`, `/api/note/...`) and JS syntax checks (`node -e 'new Function(...)'`). Add inline diagnostic divs that report D3 state, SVG element count, and viewBox dimensions after render. For visual testing, user must open in browser manually — always ask them to test on both desktop and mobile.

## Dependencies

Uses the existing venv at `~/llm-server/venv/` (flask, chromadb, sentence-transformers). No separate venv needed.

## Adding a systemd Service (optional)

```ini
# ~/.config/systemd/user/vault-viewer.service
[Unit]
Description=Vault Graph Viewer
After=rag-service.service

[Service]
Type=simple
ExecStart=/home/cricri/llm-server/venv/bin/python /home/cricri/memory-index/viewer/vault_viewer.py
Restart=on-failure

[Install]
WantedBy=default.target
```
