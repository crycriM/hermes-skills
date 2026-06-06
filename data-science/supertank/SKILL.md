---
name: supertank
description: Ingest research articles, PDFs, posts into Supertank knowledge reservoir. SQLite + KeyBERT + ChromaDB. Used by Algo Trading Agent Army.
triggers:
  - /st command
  - supertank ingest
  - add to supertank
---

# Supertank — Knowledge Reservoir

## Overview
Ingest research articles, PDFs, posts into a searchable knowledge base. Used by Algo Trading Agent Army (August queries it).

## Location
- `~/supertank/` — project root
- `~/supertank/raw/` — original files
- `~/supertank/index.db` — SQLite index (filepath, title, source_url, keywords, summary, date_added, doc_type, content_hash)
- ChromaDB `supertank` collection via RAG service :8001

## Dependencies
All in `llm-server/venv` (py3.14): keybert, pymupdf, pdfplumber, pytesseract, sentence-transformers, chromadb, beautifulsoup4, httpx

## Ingest Pipeline
```bash
cd ~/supertank && llm-server/venv/bin/python3 scripts/add.py <url|file> [--keywords kw1,kw2] [--stdin]
```
1. Extract content (PyMuPDF for PDF, curl+BS4 for URL, stdin for text)
2. SHA-256 dedup — if exists, merges keywords/references
3. KeyBERT auto-keywords (all-MiniLM-L6-v2) merged with manual keywords
4. Generate summary (first 200 chars of content)
5. Store raw file, insert SQLite row
6. Embed into ChromaDB `supertank` collection via RAG :8001 `/add` endpoint

## Search
```bash
cd ~/supertank && llm-server/venv/bin/python3 scripts/add.py --search "query"
```
Semantic search: POST to RAG :8001 `/search` with `collection: "supertank"`

## Telegram Workflow (active — option 3)

### Trigger patterns
Match ANY of these:
- `/st <url|file>` — explicit ingest command
- `/st search <query>` — keyword search via SQLite
- `/st find <query>` — semantic search via ChromaDB
- `/st kw:kw1,kw2 <url|file>` — ingest with manual keywords
- `/st <url> title:"Custom Title"` — ingest with custom title
- A message containing "st" or "supertank" alongside a URL, PDF attachment, or research link
- A forwarded PDF with "st" or "supertank" in the caption

**Do NOT auto-trigger** if user sends a PDF/URL without "st" signal.

### Command parsing
```
/st <url|filepath>                     → ingest with auto-keywords
/st kw:kw1,kw2,kw3 <url|filepath>      → ingest with manual + auto keywords
/st search <query>                     → keyword search via SQLite
/st find <query>                       → semantic search via ChromaDB
/st <url> title:"Custom Title"         → ingest with custom title
```

Loose "st" detection: if message contains "st" AND a URL (http...) OR a file path, treat as ingest.

### Telegram attachments
When user sends a file (PDF, txt) with "st" trigger:
1. Download to `/tmp/` (or use local path if platform delivers it)
2. Run `add.py /tmp/downloaded_file.pdf`
3. Clean up `/tmp/` file after

### Response format (terse, no spam)
- **Ingest success:** `✓ Supertank: "{title}" — {chars} chars, {chunks} chunks, kw: {top 5 keywords}`
- **Dedup:** `⏭ Already indexed: "{title}"`
- **Error:** `✗ Supertank: {error message}`
- **Search results:** Numbered list with title, keywords, summary snippet (2-3 lines each)

### Implementation
The skill handler should:
1. Parse the message for trigger pattern
2. Extract URL, filepath, keywords, title from the message
3. Run the appropriate `add.py` command via terminal
4. Parse output and reply with terse confirmation

## Twitter/X Ingestion

X API requires paid credits (CreditsDepleted error). Use MCP web-reader instead:

1. Fetch tweet content: `mcp_web_reader_webReader(url="https://x.com/i/status/...", retain_images=false)`
2. Extract the content from the returned JSON (under `content` key)
3. Clean up escaped characters and write to temp file
4. Ingest: `cd ~/supertank && ~/llm-server/venv/bin/python3 scripts/add.py /tmp/tweet_<id>.txt --keywords kw1,kw2`

The MCP web-reader bypasses both the X API paywall and client-side rendering. Returns full article/thread text in a single call. Works for threads and long-form tweets.

xurl is installed (`~/.local/bin/xurl`, v1.1.0) with OAuth2 token stored in `~/.xurl` but xurl binary can't read manually-injected tokens. Workaround: `~/.local/bin/xurl-read` wrapper uses curl directly. See `social-media/xurl` skill for headless OAuth setup notes.

## Known Issues
- SSRN blocks curl (Cloudflare). User downloads PDFs manually.
- RAG service patched: `~/llm-server/rag_service.py` now supports `collection` param on `/add` and `/search`.
- OCR for scanned PDFs: tesseract installed but not yet wired into extractor.
- Figure/chart extraction + vision model analysis: phase 2, not yet implemented.
- xurl token stored in `~/.xurl` but xurl binary can't read manually-injected OAuth2 tokens — use `xurl-read` wrapper or curl directly.

## Twitter/X ingestion

Due to client‑side rendering, the default `curl+BS4` extractor cannot retrieve tweet text. Use the official `xurl` CLI to fetch the tweet and pipe it into Supertank:

```bash
# 1. Ensure xurl is installed and authenticated (see the xurl skill)
# 2. Fetch tweet text (replace <TWEET_URL> with the actual tweet URL)
xurl read <TWEET_URL> | jq -r '.data.text' | \
  ~/supertank/scripts/add.py --stdin --keywords twitter,<topic>
```

Notes:
- The `--stdin` flag tells `add.py` to read from standard input.
- You can add additional keywords as needed.
- If you only need the tweet ID, you can also use `xurl read <TWEET_URL>` and extract the `id` field for metadata.

This workflow bypasses the JS limitation and stores the tweet as a regular Supertank entry.

## First Entry
Dean 2026 "Scale Invariant Dynamics in Market Price Momentum" — 24pp, 63 chunks in ChromaDB.
