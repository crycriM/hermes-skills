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
# Quick one-liner (wrapper script at ~/.local/bin/bh)
bh 'goto("https://example.com"); wait_for_load(); print(page_info())'

# Take a screenshot
bh 'goto("https://example.com"); wait_for_load(); screenshot("/tmp/shot.png")'
```

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

## Pitfalls

- **Cloudflare**: headless Chrome still gets detected. For Cloudflare-protected sites, use Hermes built-in Playwright browser tools instead.
- **f-string backslashes**: Python 3.11 disallows backslashes in f-string expressions. Use temp variables.
- **Daemon stale socket**: restart with `cd ~/browser-harness && uv run python -c "from admin import restart_daemon; restart_daemon()"`
- **Chrome profile**: uses /tmp inside distrobox — no persistent cookies. For login-required sites, use a persistent profile dir.
- **WS URL changes**: the UUID in CDP WebSocket URL changes on Chrome restart. Always discover fresh from localhost:9222/json/version.

## When to use vs Hermes Playwright

- **Use browser-harness**: subagent/CLI tasks, parallel browsers needed, coding agents (Claude Code/Codex) need browser access
- **Use Hermes Playwright**: Cloudflare-protected sites, interactive agent-driven browsing, screenshot-based exploration
