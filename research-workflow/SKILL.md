---
name: research-workflow
description: "Academic and web research: arXiv search, SSRN search, blog watching, parallel CLI research, domain intelligence, and paper writing."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Research, arXiv, SSRN, Blog, Academic, Paper-Writing, Domain-Intelligence, Web-Research]
    related_skills: [multi-source-event-research, arxiv, ssrn-search, blogwatcher, parallel-cli, domain-intel, research-paper-writing]
---

# Research Workflow

Academic and web research: paper search, blog monitoring, domain intelligence, and paper writing.

## 1. arXiv Search

Search and retrieve papers from arXiv repository.

See: `references/arxiv.md`

## SSRN Search

Use `mcp_jina_reader_search_ssrn` to search SSRN papers.

## PDF Extraction

For local PDFs, use `pdftotext` terminal command. See `references/pdf-extraction-workflow.md` for full workflow, pitfalls (Jina reader doesn't support `file://`, SSRN Cloudflare protection), and fallback strategies.

See: `references/ssrn-search.md`

## 3. Blog Watching

Monitor and track blog posts and news from specific sources.

See: `references/blogwatcher.md`

## 4. Parallel CLI Research

Run multiple research queries in parallel for comprehensive coverage.

See: `references/parallel-cli.md`

## 5. Domain Intelligence

Research and track domain-specific intelligence and trends.

See: `references/domain-intel.md`

## 6. Paper Writing

Structured approach to writing academic papers.

See: `references/research-paper-writing.md`

## 7. Paris Electro/Techno/Experimental Music Research

Weekly cron research on Paris experimental music scene. Uses EtherREAL, IRCAM,
Shotgun, Lylo, and venue direct sites. Source inventory, venue mappings, and
access-method notes in the references below.

### Tool Access Patterns (July 2026, updated 18 July)

**mcp_jina_reader_parallel_read_url** works for these primary sources:
- ✅ Etherreal (rubrique10), IRCAM/fr/events, Kilomètre25 direct site
- ⚠️ Lylo.fr — intermittent (HTTP 503 on 11 Jul, fine on 18 Jul). Always retry.
- ❌ RA.co events (empty content), but RA.co NEWS is accessible
- ❌ Parismix, PAP, Les Arts Décoratifs, Cent Quatre, La Fabrique, Le 106, Graindor — all HTTP 422/400
- ❌ Les Tanneries — wrong venue (holiday rental)
- ⚠️ Secondary/experimental sources may timeout at 30s; use 60s timeout

**Tavily web search** is excellent for festival discovery, artist queries, and filling gaps where scraping fails.
**Shotgun.live** is the most reliable aggregator for club event listings (FVTVR, Rex Club, etc.).
**Shazam venue pages** useful for quick date/artist verification.
**Bandsintown** has good venue data (Nouveau Casino, etc.).
**Songkick** is best for future months (August+); syncs with Ticketmaster.

**Key new venue**: FVTVR (34 quai d'Austerlitz, 13e) is now the most active club in Paris with nightly programming. Source: Shotgun.live.

**Stale event dates**: Previous session's event listings may contain incorrect dates (e.g. Wolfgang Voigt Gas Live was listed as May but confirmed September). Always verify dates from current session's source data before trusting earlier reference entries. Add a ⭐ marker and include a NOTE when correcting a previous session's error.

**Discord delivery**: The cron job is set to deliver via `"deliver": "discord"`. The final response is automatically delivered — no need for send_message or webhook calls. If nothing to report, respond [SILENT]. If content is produced, it is delivered automatically.

See: `references/paris-electro-techno-research-2026.md`
See: `references/etherreal-venue-decoder.md`

## 8. Multi-Source Event Research

Systematic approach to researching events across multiple sources with access challenges.

See: `references/multi-source-event-research.md`
