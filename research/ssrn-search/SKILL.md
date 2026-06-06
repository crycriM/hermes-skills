---
name: ssrn-search
description: "Search and fetch SSRN papers via Google Scholar, OpenAlex API, and direct cloudscraper v3.0.0 fetch. Full abstracts via MCP web-reader. Cookies at ~/.hermes/.ssrn-cookies.json"
version: 1.3
---

# SSRN Search & Fetch Skill

Two-source strategy for searching SSRN (Social Science Research Network) papers, bypassing SSRN's Cloudflare 403 block.

**Three fetch methods now available:**
1. `search` — discover papers via Google Scholar or OpenAlex
2. `fetch` — metadata + inverted-index abstract via OpenAlex API
3. `fetch-page` — **full abstract page via cloudscraper v3.0.0** (bypasses Cloudflare challenges directly)

**KEY FINDING:** Direct curl to `papers.ssrn.com` returns Cloudflare 403 challenge. ALL direct SSRN scraping returns empty results. Must use proxy sources.

## Quick Usage

```bash
# Search via Google Scholar (has snippets)
python3 ~/.hermes/skills/research/ssrn-search/scripts/ssrn_search.py search "random kernel time series" --backend scholar

# Search via OpenAlex (structured metadata, citations)
python3 ~/.hermes/skills/research/ssrn-search/scripts/ssrn_search.py search "random kernel time series" --backend openalex

# Fetch paper details by SSRN ID
python3 ~/.hermes/skills/research/ssrn-search/scripts/ssrn_search.py fetch 5930257
```

## Two-Backend Strategy

| Feature | Google Scholar | OpenAlex |
|---------|---------------|----------|
| Snippets | Yes (150 chars) | No |
| SSRN IDs | Yes | Yes |
| DOI | Yes | Yes |
| Citation count | No | Yes |
| Authors (structured) | Raw text | Clean names |
| Year | From text | Structured |
| Abstract | No | Rarely (inverted index) |
| Rate limit | ~10/min (CAPTCHA) | 10/s (no key) |

**Recommendation:** Use Scholar for discovery (better relevance ranking + snippets), OpenAlex for metadata enrichment.

## For Benchmark Runner Integration

Replace the old `_condense_ssrn()` with calls to the script:

```python
import subprocess, json

def search_ssrn(query, backend="scholar"):
    result = subprocess.run(
        ["python3", os.path.expanduser("~/.hermes/skills/research/ssrn-search/scripts/ssrn_search.py"),
         "search", query, "--backend", backend],
        capture_output=True, text=True, timeout=20
    )
```

Or import directly:
```python
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/research/ssrn-search/scripts"))
from ssrn_search import search_ssrn, fetch_ssrn
```

## OpenAlex SSRN Source ID

`S4210172589` — 1,575,755 works indexed from SSRN Electronic Journal.

## Authenticated Access

Auth cookies at `~/.hermes/.ssrn-cookies.json` (user: christian.marzolin@normalesup.org, JWT expires ~May 2026).

- `hq.ssrn.com` — Works with cookies via curl (200). User HQ, subscriptions, library.
- The benchmark's `ssrn_via_scholar.py` auto-loads these cookies and tries direct fetch before the Scholar pipeline.

## cloudscraper v3.0.0 Direct SSRN Fetch

**Package:** `cloudscraper` installed in `llm-server/venv/` (Python 3.8+). Upgraded from pip 1.2.71 → sources 3.0.0.

**How it works:**
- Cloudscraper v3.0.0 solves Cloudflare JavaScript VM challenges (v1/v2/v3) internally using js2py interpreter
- Auto 403 recovery: detects stale sessions, clears cookies + rotates fingerprint, retries (up to 3x)
- Session health monitoring: proactive refresh every 30 min to avoid 403s mid-session
- No browser, no CDP, no Obscura — pure Python HTTP with challenge solving

**CLI usage:**
```bash
~/.hermes/skills/research/ssrn-search/scripts/ssrn_search.py fetch-page 4331902
```

**Python import:**
```python
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/research/ssrn-search/scripts"))
from ssrn_search import fetch_ssrn_page
result = fetch_ssrn_page("4331902")
# Returns: {title, authors, abstract, keywords, jel, pubinfo, ssrn_id}
# On CF timeout: {"error": "cloudscraper timeout — SSRN CF challenge not solved", "ssrn_id": "..."}
```

### SSRN Limitation

SSRN uses **Cloudflare Enterprise with a `chl_page` managed challenge variant** (`challenge-platform/h/b/orchestrate/chl_page/v1`) that cloudscraper v3.0.0 handlers do NOT recognize. The detection patterns for v1/v2/v3 all miss this variant. The auto-refresh-on-403 path hangs because `_refresh_session()` itself re-requests the CF-protected domain and blocks.

**Verified behavior:**
- `requests.get()` (no cloudscraper): returns Cloudflare challenge HTML ✅, 403 status ✅
- `cloudscraper.get()`: hangs indefinitely on SSRN (JS solver never completes for this CF variant)
- MCP web-reader (zai/GLM): returns full abstract + metadata ✅

**If `fetch_ssrn_page` returns an error:** fall back to MCP web-reader (see below).

## MCP Web-Reader for Full Summaries

Fallback when cloudscraper cannot solve the challenge (e.g. new Cloudflare variant).

You can also retrieve the full SSRN abstract page via the MCP web‑reader tool, which uses the zai endpoint (GLM API) under the hood.

Example usage (pseudo‑code):

```python
from hermes_tools import mcp_web_reader_webReader

result = mcp_web_reader_webReader({
    "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4331902",
    "timeout": 30
})
# result contains title, description, content (full abstract), metadata, etc.
print(result)
```

The MCP server is configured at `https://api.z.ai/api/mcp/web_reader/mcp` and already authenticated, so no extra API key is needed.

This method bypasses Cloudflare and returns the complete abstract page content, which can be parsed or used directly.

## Pitfalls

- `papers.ssrn.com` — curl/urllib returns Cloudflare 403 challenge page. cloudscraper hangs on SSRN's CF Enterprise `chl_page` variant (not recognized by any handler). **Use MCP web-reader** for full SSRN abstracts
- cloudscraper v3.0.0 works for many other Cloudflare-protected sites — SSRN's Enterprise CF configuration is an edge case
- Google Scholar may CAPTCHA after ~10 rapid requests — add 5s delays
- OpenAlex relevance ranking is poor for niche queries — Scholar is better for discovery
- SSRN DOIs: `10.2139/ssrn.NNNNNN`
- Abstracts almost never available for SSRN papers in OpenAlex

## Note on cloudscraper vs MCP vs Browser Tools

| Method | CF Bypass | Full Abstract | Best For |
|--------|-----------|---------------|----------|
| cloudscraper `fetch-page` | ⚠️ (hangs on SSRN, works elsewhere) | ❌ on SSRN | Other CF-protected sites |
| MCP web-reader | ✅ (zai/GLM) | ✅ | SSRN primary method |
