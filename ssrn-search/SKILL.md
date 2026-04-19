---
name: ssrn-search
description: Search and fetch SSRN papers for research. Two-source strategy: Google Scholar for discovery (with snippets), OpenAlex API for metadata (citations, DOIs). No API keys needed.
version: 1.0
---

# SSRN Search & Fetch

Search SSRN (Social Science Research Network) for academic papers. Two complementary backends:

1. **Google Scholar** — `site:ssrn.com` query for discovery with abstract snippets
2. **OpenAlex API** — `primary_location.source.id:S4210172589` filter for structured metadata (DOI, citations, year, authors)

## Why Two Sources?

- SSRN.com itself is behind Cloudflare (403 to curl) — cannot be scraped directly
- Google Scholar returns SSRN papers with good snippets but no structured metadata
- OpenAlex indexes 1.5M SSRN papers with full metadata but no abstracts
- Together they provide complete coverage

## Search Strategy

### For broad discovery (use Google Scholar):

```bash
QUERY="random kernel convolution time series"
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('site:ssrn.com $QUERY'))")
curl -sL "https://scholar.google.com/scholar?q=${ENCODED}&hl=en&num=10&as_sdt=0,5" \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' \
  -H 'Accept: text/html' \
  --max-time 15 -o /tmp/ssrn_scholar.html
```

Parse with regex:
- Titles: `<h3 class="gs_rt">...<a href="URL">TITLE</a></h3>`
- Authors/venue: `class="gs_a">AUTHORS - VENUE</div>`
- Snippets: `class="gs_rs">SNIPPET</div>`
- SSRN ID from URL: `abstract_id=(\d+)`

### For structured metadata (use OpenAlex):

```bash
QUERY="random kernel convolution time series"
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$QUERY'))")
curl -sL "https://api.openalex.org/works?search=${ENCODED}&filter=primary_location.source.id:S4210172589&per_page=10&select=id,title,authorships,publication_year,doi,cited_by_count" \
  -H 'User-Agent: HermesAgent/1.0' \
  --max-time 15
```

OpenAlex SSRN source ID: `S4210172589` (1,575,755 works indexed)

## Fetch Paper Details

### By DOI (OpenAlex):

```bash
DOI="10.2139/ssrn.4440974"
curl -sL "https://api.openalex.org/works/doi:${DOI}" \
  -H 'User-Agent: HermesAgent/1.0' --max-time 15 | python3 -m json.tool
```

### By SSRN ID (convert to DOI):

```bash
SSRN_ID="4440974"
curl -sL "https://api.openalex.org/works?filter=primary_location.source.id:S4210172589,doi:10.2139/ssrn.${SSRN_ID}" \
  -H 'User-Agent: HermesAgent/1.0' --max-time 15
```

### Reconstruct abstract (OpenAlex inverted index):

OpenAlex stores abstracts as `{word: [positions]}`. Reconstruct:

```python
inv = paper.get("abstract_inverted_index", {})
if inv:
    word_pos = []
    for word, positions in inv.items():
        for pos in positions:
            word_pos.append((pos, word))
    word_pos.sort()
    abstract = " ".join(w for _, w in word_pos)
```

Note: SSRN papers rarely have abstracts in OpenAlex (SSRN locks them). Use Google Scholar snippets instead.

## Python Helper Script

Save to `/tmp/ssrn_search.py` and call:

```python
#!/usr/bin/env python3
"""SSRN search via Google Scholar + OpenAlex. No API keys needed."""
import re, json, sys, urllib.request, urllib.parse

def search_ssrn(query, num_results=10, backend="scholar"):
    """Search SSRN papers.
    
    backend: 'scholar' (Google Scholar, has snippets) or 'openalex' (structured metadata)
    """
    if backend == "scholar":
        return _search_scholar(query, num_results)
    else:
        return _search_openalex(query, num_results)

def _search_scholar(query, num_results):
    params = urllib.parse.urlencode({
        "q": f"site:ssrn.com {query}",
        "hl": "en",
        "num": num_results,
    })
    url = f"https://scholar.google.com/scholar?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    
    results = []
    blocks = re.findall(r'<div class="gs_ri">(.*?)(?=<div class="gs_ri">|<div id="gs_|$)', html, re.DOTALL)
    for block in blocks:
        title_m = re.search(r'<h3[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not title_m:
            continue
        paper_url = title_m.group(1)
        title = re.sub(r"<[^>]+>", "", title_m.group(2)).strip()
        
        author_m = re.search(r'class="gs_a">(.*?)</div>', block, re.DOTALL)
        authors = re.sub(r"<[^>]+>", "", author_m.group(1)).strip() if author_m else ""
        
        snippet_m = re.search(r'class="gs_rs">(.*?)</div>', block, re.DOTALL)
        snippet = re.sub(r"<[^>]+>", "", snippet_m.group(1)).strip() if snippet_m else ""
        
        ssrn_id = None
        id_m = re.search(r"abstract_id=(\d+)", paper_url)
        if id_m:
            ssrn_id = id_m.group(1)
        
        results.append({
            "title": title,
            "url": paper_url,
            "authors": authors,
            "snippet": snippet,
            "ssrn_id": ssrn_id,
            "doi": f"10.2139/ssrn.{ssrn_id}" if ssrn_id else None,
        })
    return results

def _search_openalex(query, num_results):
    params = urllib.parse.urlencode({
        "search": query,
        "filter": "primary_location.source.id:S4210172589",
        "per_page": num_results,
        "select": "id,title,authorships,publication_year,doi,cited_by_count",
    })
    url = f"https://api.openalex.org/works?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "HermesAgent/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    
    results = []
    for r in data.get("results", []):
        authors = ", ".join(
            a["author"]["display_name"] 
            for a in (r.get("authorships") or [])[:5]
        )
        doi = r.get("doi", "") or ""
        ssrn_id = None
        m = re.search(r"ssrn\.?(\d+)", doi)
        if m:
            ssrn_id = m.group(1)
        
        results.append({
            "title": r.get("title", ""),
            "year": r.get("publication_year"),
            "authors": authors,
            "doi": doi.replace("https://doi.org/", "") if doi else None,
            "ssrn_id": ssrn_id,
            "cited_by": r.get("cited_by_count", 0),
            "openalex_id": r.get("id", ""),
        })
    return {"total": data.get("meta", {}).get("count", 0), "results": results}

def fetch_ssrn(ssrn_id):
    """Fetch SSRN paper metadata via OpenAlex."""
    doi = f"10.2139/ssrn.{ssrn_id}"
    params = urllib.parse.urlencode({
        "filter": f"primary_location.source.id:S4210172589,doi:{doi}",
        "select": "id,title,authorships,publication_year,doi,cited_by_count,abstract_inverted_index,biblio,primary_location",
    })
    url = f"https://api.openalex.org/works?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "HermesAgent/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    
    if not data.get("results"):
        return None
    
    paper = data["results"][0]
    # Reconstruct abstract
    inv = paper.get("abstract_inverted_index")
    abstract = ""
    if inv:
        word_pos = []
        for word, positions in inv.items():
            for pos in positions:
                word_pos.append((pos, word))
        word_pos.sort()
        abstract = " ".join(w for _, w in word_pos)
    
    authors = ", ".join(
        a["author"]["display_name"]
        for a in (paper.get("authorships") or [])[:10]
    )
    loc = paper.get("primary_location") or {}
    source = (loc.get("source") or {}).get("display_name", "")
    
    return {
        "title": paper.get("title"),
        "year": paper.get("publication_year"),
        "authors": authors,
        "doi": (paper.get("doi") or "").replace("https://doi.org/", ""),
        "ssrn_id": ssrn_id,
        "cited_by": paper.get("cited_by_count", 0),
        "abstract": abstract,
        "venue": source,
        "biblio": paper.get("biblio"),
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ssrn_search.py <search|fetch> <query|ssrn_id> [--backend scholar|openalex]")
        sys.exit(1)
    
    action = sys.argv[1]
    arg = sys.argv[2]
    backend = "scholar"
    if "--backend" in sys.argv:
        backend = sys.argv[sys.argv.index("--backend") + 1]
    
    if action == "search":
        results = search_ssrn(arg, backend=backend)
        if backend == "scholar":
            for i, r in enumerate(results):
                print(f"[{i+1}] {r['title']}")
                print(f"    Authors: {r['authors'][:80]}")
                print(f"    SSRN: {r['ssrn_id']} | DOI: {r.get('doi','')}")
                print(f"    Snippet: {r['snippet'][:120]}")
                print()
        else:
            print(f"Total: {results['total']}")
            for i, r in enumerate(results['results']):
                print(f"[{i+1}] {r['title']}")
                print(f"    Authors: {r['authors'][:60]} | Year: {r['year']} | Cited: {r['cited_by']}")
                print()
    elif action == "fetch":
        result = fetch_ssrn(arg)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(f"SSRN paper {arg} not found in OpenAlex")
```

## Rate Limits

- **Google Scholar**: No official API. ~10 requests/minute before CAPTCHA. Add 5s delays between calls.
- **OpenAlex**: 10 requests/second, no API key needed. 100K+ with free API key. Very reliable.

## Pitfalls

- SSRN.com returns 403 (Cloudflare) for all curl requests — never use it directly
- **Headless browsers vs SSRN Cloudflare** — browser-use (CDP Chrome) = blocked. Camoufox (Firefox fork, Docker :9377) = blocked (even with auth cookies injected via POST /cookies). Hermes Playwright browser = WORKS (shows "Just a moment..." briefly, then resolves). Authenticated sessions pass through. Verified Apr 2026.
- **Camoufox Docker** — deployed as `camoufox-browser` container, `--restart unless-stopped`, port 9377. Built from `~/.hermes/hermes-agent/node_modules/@askjo/camoufox-browser/Dockerfile.camoufox` (patches: port 9377, copy lib/, POST /cookies endpoint added). API tab lookups need `?userId=openclaw`. Cookie injection works but doesn't bypass SSRN Cloudflare.
- **SSRN authenticated access via browser tools** — Login at hq.ssrn.com/pubsigninjoin.cfm via browser_navigate → browser_type email → browser_type password → browser_click Sign in. Extract cookies via browser_console. SSRN_TOKEN is httpOnly (only visible on hq.ssrn.com). JWT is short-lived (~24h). Save to `~/.hermes/.ssrn-cookies.json` (chmod 600). Credentials: christian.marzolin@normalesup.org / PID 3825130.
- Google Scholar may show CAPTCHA if you make too many rapid requests (add 5s delays)
- OpenAlex SSRN papers rarely have abstracts — rely on Google Scholar snippets for content
- SSRN DOIs follow format `10.2139/ssrn.NNNNNN` — use this to cross-reference between sources
- Google Scholar results include papers *about* SSRN topics, not just *on* SSRN — always filter by `site:ssrn.com`
- If full SSRN abstracts are truly needed, only option is a **non-headless browser on a real desktop** (X11/Wayland display), not a Docker container
- The research benchmark (`~/llm-server/research_agent_bench/`) has been patched (Apr 2026) to use `ssrn_via_scholar.py` instead of direct curl. The module provides `fetch_ssrn(query, max_chars)` as drop-in replacement for the broken `_condense_ssrn()` + curl approach
- Semantic Scholar API also works for enrichment (full abstracts for some SSRN papers) — `ssrn_via_scholar.py` tries SemanticScholar first, then OpenAlex, then falls back to Scholar snippets
