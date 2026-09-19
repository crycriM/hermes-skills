---
name: cloud-share-bulk-download
description: "Fetch all files from a cloud-share link in one pass."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Download, Cloud, pCloud, Publink, Share, Bulk, Playwright, Parquet]
    related_skills: [cron-playwright-scraping, blocked-page-recovery, data-pipeline-apis]
---

# Cloud-Share Bulk Download

Task: "fetch all files from this share link into <dir>". Cloud-storage share
pages (pCloud publinks, Dropbox shares, Box, etc.) are SPA front-ends over a
developer API. Don't click through the UI and don't fetch files one-by-one —
each provider's page or API exposes a **whole-folder bulk endpoint** plus an
**embedded manifest**. Find both and you turn an N-file click-fest into two
HTTP calls.

## General method (provider-agnostic)

1. **List first, download after.** Get the true manifest of names + sizes
   BEFORE downloading. Cloud UIs truncate names (`okx_btc_fut...arquet`) and
   paginate. You need the real count to verify the download afterwards.
2. **Mine the page for its data.** These share pages embed the folder state in
   a JS string/`<script>` blob (`var publinkData = {...};`, `bootstrappedData`,
   `window.__INITIAL_STATE__`, etc.) or expose a JSON API endpoint. Extract the
   manifest from there in one `browser_evaluate`, not by scraping DOM nodes.
3. **Find the bulk download.** Read the same blob for a download link that
   zips / streams the whole folder (e.g. pCloud's `getpubzip`). One resumable
   download beats N file requests.
4. **Resumable download** (`wget -c -t 5 -O out.zip "<url>"`), then
   **verify** the zip integrity (`unzip -t`) and **prove the count**:
   `unzip -l | wc -l` and extracted `*.ext | wc -l` must both equal the manifest
   count. If they don't match, go back — missing files are failures.
5. **Flatten if asked.** Zips usually nest under a `<folder>/` prefix; `mv`
   them up if the target dir expects flat files.

## Browser of choice: Playwright MCP

These share pages are JS-only; plain `curl` returns an empty shell. Use the
Playwright MCP tools (`mcp__playwright__browser_navigate` /
`browser_evaluate`) — they launch their own headless chromium from
`~/.cache/ms-playwright/` and do not depend on `google-chrome` being on
`PATH`. (The browser-use `browser_exec` harness locates Chrome via
`find_chrome_executable()`, which on Linux only checks PATH for named chrome
binaries; without one it fails with `chrome-not-running` — that's when you
fall back to Playwright MCP rather than fighting the harness.)

## Provider references

- `references/pcloud-publink.md` — pCloud publink: `publinkData` JSON,
  `getpubzip` endpoint, and the exact 5-step recipe.
- (Add `references/<provider>.md` per provider as you encounter them.)

## Pitfalls

- URLs ending `#/login` do NOT necessarily gate the content — the folder may
  still be readable without a password. Confirm via snapshot before asking the
  user for credentials.
- Do not trust the UI's displayed name count; always source the count from the
  embedded manifest and cross-check after extraction.
- Respect the share's download permission (e.g. pCloud `candownload`:false
  means the owner disabled it — no technique will work then).
- Spot-check binary format when it matters (e.g. parquet files must start with
  the 4-byte magic `PAR1`): `head -c 4 file | xxd`.
