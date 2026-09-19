---
name: cron-playwright-scraping
description: "Use Playwright MCP in cron to scrape JS web pages."
version: 1.0.0
author: Hermes Agent
platforms: [linux]
metadata:
  hermes:
    tags: [Cron, Playwright, Scraping, Browser, MCP, Automation]
    related_skills: [devops, research-workflow, error-learning]
---

# Cron Playwright Scraping

Use Playwright MCP browser tools in cron jobs to scrape JS-rendered web pages that return empty content via `jina_reader` or HTTP tools.

## Tools That Work in Cron

### ✅ Verified Working
- `mcp__playwright__browser_navigate` — navigate to a URL, returns page title + snapshot
- `mcp__playwright__browser_snapshot` — read the accessibility snapshot of the current page

### ❌ Not Verified / Not Working in Cron
- `mcp__playwright__browser_click` — not tested in cron context
- Old Hermes core browser tools (`browser_navigate`, `browser_click`, etc.) — **FAIL** because they need Chrome/CDP + X display

## Verified Site Workflow (Paris Music Research)

### Sites That Work With Playwright MCP

| Site | URL | Status | Notes |
|------|-----|--------|-------|
| EtherREAL | etherreal.com/spip.php?rubrique10 | ✅ Works | Date navigation via URL param `?date=YYYY-MM-DD`. Use `mcp__playwright__browser_snapshot` to read agenda. |
| IRCAM | ircam.fr/fr/events | ✅ Works | Cookie wall appears but the snapshot still captures all event content — the `active` dialog overlay does NOT block the accessibility tree. Events are readable. No need to accept cookies. |
| Lylo | lylo.fr/concerts-electro | ✅ Works | Calendar navigation via `?from=YYYY-MM-DD` URL params. In August the default view shows future listings starting from the current week. Use Playwright MCP, not Jina reader — Jina returned HTTP 503 in some sessions. |

### Sites That Still Block

| Site | URL | Block Method | Workaround |
|------|-----|-------------|------------|
| RA.co (events) | fr.ra.co/events/fr/paris/electro | DataDome | Use RA.co NEWS (accessible), Shotgun.live, or Songkick instead |
| PAP | pap.fr/agenda/musique-electronique-paris | Cloudflare | Skip |
| Parismix | parismix.com/concerts-electro/ | HTTP 422 | Skip |
| Centquatre | centquatre.paris/agenda/ | HTTP 422 | Skip |
| La Fabrique | la-fabrique.org/agenda/ | HTTP 422 | Skip |
| Le 106 | le-106.fr/agenda/ | HTTP 422 | Skip |

## Workflow Pattern

```python
# 1. Navigate
mcp__playwright__browser_navigate(url="https://www.etherreal.com/spip.php?rubrique10")

# 2. Snapshot to read content
mcp__playwright__browser_snapshot()

# 3. For pagination, navigate to next date range
mcp__playwright__browser_navigate(url="https://www.etherreal.com/spip.php?rubrique10&date=2026-08-08")
```

## Fallback Strategy

When Playwright MCP fails or returns empty:
1. Try **Tavily web search** for broad discovery (festivals, announcements)
2. Try **Songkick** for future months' listings
3. Try **Shotgun.live** for club-specific events
4. Skip and note the source as blocked

## Tool Selection: Playwright MCP vs Jina Reader

Prefer **Playwright MCP** as the default scraping tool for all sources in cron. It handles:
- JavaScript-rendered pages that Jina reader returns empty
- Cookie consent dialogs (the content is still in the accessibility tree)
- Sites that return HTTP 422/400 to Jina reader

Use **Jina reader** only for confirmed-working plain-text sources (EtherREAL works with both). The Jina reader is faster (one call) but has a higher failure rate on French music/event sites.

## Key Workflow Insight: Parallel Navigation

You cannot navigate Playwright MCP to multiple pages simultaneously — each `browser_navigate` replaces the current page. Batch independent reads via `mcp__jina_reader__parallel_read_url` (for confirmed-working sources) or sequential Playwright navigations.

## Pitfalls

- Playwright MCP browser tools share a single browser instance — concurrent navigation replaces the current page
- Each `browser_navigate` + `browser_snapshot` costs ~2 tool calls per page
- Sites with bot protection (DataDome, Cloudflare) block Playwright just as they block curl — Playwright is not a bypass for anti-bot systems
- The snapshot returns the accessibility tree, not full HTML — some dynamic content may be hidden behind JS interactions
- Cookie consent popups may obscure content — IRCAM's is visible in the snapshot as `active` dialog
- August is summer break in Paris — many venue calendars are empty. This is a reliable yearly pattern.