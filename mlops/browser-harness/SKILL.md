---
name: browser-harness
description: "Thin CDP control layer for direct browser automation. Python snippets executed on Chrome via CDP WebSocket. Installed at ~/browser-harness/, Chrome runs in browser-use distrobox with Xvfb."
version: 1.0
---

# browser-harness

Direct CDP control — write Python, it executes on Chrome. No LLM in the loop, unlike browser-use the library.

## Setup

- **Repo**: `~/browser-harness/` (editable install via `uv tool install -e .`)
- **Chrome**: runs inside `browser-use` distrobox with Xvfb :99, CDP on port 9222
- **Service**: `systemctl --user start/stop browser-harness-chrome.service`
- **Wrapper**: `bh '<python code>'` — auto-discovers CDP WS URL, starts Chrome if needed

## Usage

```bash
# Correct entrypoint: the `bh` wrapper pipes code into stdin, but the CLI reads
# -c only. Export the WS URL and call the CLI directly:
cd ~/browser-harness
export BU_CDP_WS=$(curl -sf http://localhost:9222/json/version \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['webSocketDebuggerUrl'])")
browser-harness -c "$(cat /path/to/script.py)"
```

Helper names are `new_tab/goto_url/js/cdp/click_at_xy/wait/wait_for_load/page_info` —
there is no `goto`, no `screenshot()` (use `capture_screenshot(path)`), no `bh -c`.

## Key Functions (helpers.py)

- `goto(url)` — navigate, auto-loads domain skills if available
- `page_info()` — returns dict with url, title, w, h, sx, sy, pw, ph
- `click(x, y)` — compositor-level click, passes through iframes/shadow DOM
- `type_text(text)` — insert text at cursor
- `press_key(key)` — Enter, Tab, Escape, ArrowUp/Down/Left/Right, etc.
- `scroll(x, y, dy)` — scroll at position (dy=-300 for down)
- `screenshot(path, full)` — capture screenshot to file
- `js(expression)` — run JS in page, return result
- `cdp("Domain.method", params)` — raw CDP call
- `wait_for_load()` — wait for page to finish loading
- `list_tabs()`, `switch_tab(target_id)`, `new_tab(url)`, `ensure_real_tab()`
- `http_get(url)` — HTTP fetch without browser

## Architecture

Chrome (distrobox Xvfb :99) -> CDP WS :9222 -> daemon.py -> Unix socket -> run.py

## Skills directories

- `interaction-skills/`: cookies, iframes, dialogs, downloads, drag-and-drop, dropdowns, shadow-dom, tabs, uploads, viewport, etc.
- `domain-skills/`: site-specific knowledge. Search with: `rg -n "pattern" ~/browser-harness/domain-skills/`

## Testing HTML5 drag-and-drop (real drags, not synthetic events)

A native drag is `Input.dispatchMouseEvent(mousePressed)` → several `mouseMoved`
with `buttons=1` → **dwell on the target** → `mouseReleased`. Recipe that works:

```python
cdp("Network.setCacheDisabled", cacheDisabled=True)   # when re-testing edited js/css
cdp("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)
```

- **Widen the viewport first.** If the drop target is off-screen, `elementFromPoint`
  returns null and CDP mouse events there are discarded — the gesture looks broken
  but nothing reaches the page. Probe with `document.elementFromPoint(x, y)` before dragging.
- **Dwell 1-2s on the target** (jitter moves or stationary time) so Chrome dispatches a
  `dragover` there before the release; a drop needs a preceding dragover whose handler
  called `preventDefault`. Moves 50ms apart then an instant release ⇒ no `drop` event.
- **Instrument, don't guess.** Add capture-phase listeners for
  `dragstart/dragenter/dragover/dragleave/drop/dragend` into a `window.__ev` array and wrap
  `window.fetch` to record the requests the app sends. No `drop` in the log = the drag was
  refused (never reached the handler); a request with the wrong payload = app-side bug.
- **Beware drag ghosts in the page under test:** an insertion indicator/caret that is
  re-created on every `dragover`, or that lacks `pointer-events: none`, becomes the drop
  target itself and Chrome cancels the drop — the symptom is intermittent because it only
  fails when the pointer happens to sit on the indicator.

## Pitfalls

- **Cloudflare**: headless Chrome still gets detected. For Cloudflare-protected sites, use Hermes built-in Playwright browser tools instead.
- **f-string backslashes**: Python 3.11 disallows backslashes in f-string expressions. Use temp variables.
- **Daemon stale socket**: restart with `cd ~/browser-harness && uv run python -c "from admin import restart_daemon; restart_daemon()"`
- **Chrome profile**: uses /tmp inside distrobox — no persistent cookies. For login-required sites, use a persistent profile dir.
- **WS URL changes**: the UUID in CDP WebSocket URL changes on Chrome restart. Always discover fresh from localhost:9222/json/version.
- **localhost targets**: the Hermes `browser_exec` tool refuses private/internal URLs; drive local apps through browser-harness instead.
- **Blank page on shared hosting**: WordPress sites on shared hosting (Infomaniak, etc.) may show blank pages in automated browsers. Mitigations:
  - Add `page.waitForLoadState('networkidle')` before interactions
  - Try `page.waitForTimeout(3000)` for extra load time
  - Check if the page loads in a regular browser first
  - Fall back to REST API or SSH if browser automation fails

## When to use vs Hermes Playwright

- **Use browser-harness**: subagent/CLI tasks, parallel browsers needed, coding agents (Claude Code/Codex) need browser access
- **Use Hermes Playwright**: Cloudflare-protected sites, interactive agent-driven browsing, screenshot-based exploration
