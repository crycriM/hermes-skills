# Playwright MCP for Hermes

Installing and configuring Microsoft's `@playwright/mcp` as a Hermes MCP server for browser automation.

## Quick Install

```bash
# 1. Install the package permanently (not via npx — faster startup)
mkdir -p ~/.local/share/playwright-mcp
cd ~/.local/share/playwright-mcp
npm init -y
npm install @playwright/mcp@latest

# 2. Install Chromium (uses the package's bundled playwright version)
# On unsupported OS versions (e.g. Ubuntu 26.04), the system playwright install
# fails — use the package's own playwright-core instead:
cd ~/.local/share/playwright-mcp
npx playwright install chromium
# The browser lands in ~/.cache/ms-playwright/chromium-XXXX

# 3. Verify it works
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | \
  timeout 5 node node_modules/.bin/playwright-mcp --caps=core
# Should return a JSON-RPC response with tool list
```

## Hermes Config

Add to `~/.hermes/config.yaml` under `mcp_servers:`:

```yaml
mcp_servers:
  playwright:
    command: node
    args:
      - "/home/user/.local/share/playwright-mcp/node_modules/.bin/playwright-mcp"
      - "--caps=core,network,storage,testing,vision,pdf,devtools"
      - "--executable-path=/home/user/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome"
      - "--headless"
      - "--no-sandbox"
    enabled: true
    timeout: 120
    connect_timeout: 10
    supports_parallel_tool_calls: true
```

**Important:** Use absolute paths — `$HOME` does NOT expand in YAML.

### Why the extra flags

- `--executable-path`: Points directly to the cached Playwright Chromium. Required because the MCP server defaults to `--browser chrome` which looks for Chrome channels at standard OS paths (`/opt/google/chrome/chrome`). On headless servers or systems where system Chrome was removed, the MCP fails with "Chromium distribution 'chrome' is not found" unless you explicitly point it at the cached binary.
- `--headless`: Required on headless servers with no X display. Without this, Playwright tries to open a headed window and fails.
- `--no-sandbox`: Needed when running as non-root on Linux without a configured user namespace sandbox. Safe in a single-user dev environment but don't use in multi-tenant production.

To find the correct path for `--executable-path`: `ls -d ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome`

### Updating config via CLI (safer than YAML editing)

```bash
hermes config set mcp.playwright.args '[
  "/home/user/.local/share/playwright-mcp/node_modules/.bin/playwright-mcp",
  "--caps=core,network,storage,testing,vision,pdf,devtools",
  "--executable-path=/home/user/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome",
  "--headless",
  "--no-sandbox"
]'
```

Then restart the gateway for the change to take effect:
```bash
systemctl --user restart hermes-gateway.service
```

**Pitfall — stale watchdog args:** The MCP watchdog processes cache the command line at gateway startup. Changing config via `hermes config set` updates the YAML on disk but the running watchdog won't pick it up. A gateway restart via `systemctl --user restart` may also not be sufficient if the old watchdog processes persist (they can re-spawn with stale args). Verify after restart with:
```bash
ps aux | grep playwright-mcp | grep -v grep
# The args should show --executable-path, --headless, --no-sandbox
```
If the flags are missing, kill all `playwright-mcp` and `mcp_stdio_watchdog` processes, then restart the gateway again.

**Pitfall — `patch` is blocked on `~/.hermes/config.yaml`:** The `patch` tool refuses to edit Hermes' own config. Use `hermes config set` (as above) for structured keys, or `sed`/`python3` for complex edits after a backup: `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak`.

**Pitfall — `mcp:` vs `mcp_servers:` YAML sections don't merge:** Hermes config has TWO separate sections: `mcp_servers:` (under the root key, used by the MCP server process) and `mcp:` (a top-level key used by Hermes' own MCP integration layer). When you have correct args in the `mcp:` section but missing/truncated args in `mcp_servers:`, the running MCP process uses `mcp_servers:` only — it never sees the `mcp:` override. Always verify that `mcp_servers.playwright.args` has the complete flag list. Symptoms: config looks right at `hermes config get mcp.playwright.args` but the MCP watchdog launches `playwright-mcp` without `--executable-path`, `--headless`, or `--no-sandbox`.

## Capability Flags

Playwright MCP uses capability groups to control which tools are exposed. Fewer caps = fewer tokens in the tool schema.

| Flag | Tools | When to use |
|------|-------|-------------|
| `core` (default) | navigate, click, type, snapshot, screenshot, tabs, console, evaluate, etc. (24 tools) | Basic browsing |
| `network` | route mocking, online/offline state (6 tools) | Testing with network control |
| `storage` | cookies, localStorage, sessionStorage (17 tools) | Auth persistence |
| `testing` | assertions, locator generation (5 tools) | Test automation |
| `vision` | mouse move/click/drag by coordinates (6 tools) | Screenshot-driven workflows |
| `pdf` | export page as PDF (1 tool) | Page saving |
| `devtools` | tracing, video recording (8 tools) | Debugging |
| `config` | get resolved config (1 tool) | Introspection |

## Ubuntu 26.04 Workaround

Playwright 1.59.1 does not support Ubuntu 26.04 (resolute). The fix is to use the `@playwright/mcp` package's bundled playwright (1.61.0-alpha which supports it):

- `npx playwright install chromium` from the package directory works
- `--with-deps` flag fails because it requires sudo (which needs a TTY). System Chromium dependencies are usually already present on a dev machine.
- On systems where system Chrome was removed (e.g. Ubuntu upgrade removed `/opt/google/chrome/`), you must pass `--executable-path` pointing to the cached Chromium, plus `--headless` and `--no-sandbox` (see Hermes Config section above).
- Verify with a quick Node.js test:
  ```js
  const { chromium } = require('playwright');
  (async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto('about:blank');
    console.log('OK');
    await browser.close();
  })();
  ```

## Kilo Code and Claude Code Config

These tools need their OWN MCP config separate from Hermes. Add the same `mcpServers` block to:

- **Kilo Code:** `~/.config/kilo/kilo.jsonc` (or `kilo.json`)
- **Claude Code:** `~/.claude.json`

```jsonc
{
  "mcpServers": {
    "playwright": {
      "command": "node",
      "args": [
        "/home/user/.local/share/playwright-mcp/node_modules/.bin/playwright-mcp",
        "--caps=core,network,storage,testing,vision,pdf,devtools"
      ]
    }
  }
}
```

Note: Kilo's config is JSONC (supports comments), Claude's is plain JSON.

## Browser Toolkit Distinction: Old vs. New

Two separate browser toolkits exist on this system:

**1. Playwright MCP (`mcp_playwright_browser_*`)** — WORKS. Installed at `~/.cache/ms-playwright/chromium-1226/chrome-linux64/chrome`. Runs headless without needing DISPLAY. This is the toolkit to use for scraping, browsing, and interaction.

**2. Old Hermes core browser tools (`browser_navigate`, `browser_click`, `browser_console`, `browser_vision`, etc.)** — FAIL. These expect a system Chrome/CDP installation with a running X display. No X server is available on this headless system. The error "no Chrome/CDP installed" is correct for these legacy tools.

**When to use each**: Always `mcp_playwright_browser_*`. The old tools are the ones producing the error counters in the error scanner. If a cron job (like Paris music research) triggers browser errors, update its prompt to use `mcp_playwright_browser_navigate` + `mcp_playwright_browser_snapshot` instead of the old tools.
