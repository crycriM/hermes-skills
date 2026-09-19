#!/usr/bin/env python3
"""SSRN search via Google Scholar + OpenAlex + direct cloudscraper fetch."""
import re, json, sys, urllib.request, urllib.parse

# cloudscraper v3.0.0 — Cloudflare v1/v2/v3 + Turnstile bypass with auto 403 recovery
# Installed in llm-server/venv/, use that interpreter
import cloudscraper as _cs

def search_ssrn(query, num_results=10, backend="scholar"):
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


# --------------------------------------------------------------------------- #
# cloudscraper v3.0.0 direct SSRN fetch
# - Handles Cloudflare v1/v2/v3 JavaScript VM challenges automatically
# - Auto 403 recovery: refreshes session + rotates fingerprint on 403s
# - Session health monitoring: proactive refresh before expiry
#
# LIMITATION: SSRN uses Cloudflare Enterprise with a managed challenge variant
# (challenge-platform/h/b/orchestrate/chl_page/v1) that cloudscraper v3.0.0
# does NOT recognize. The auto-refresh path hangs because _refresh_session()
# itself hits the CF challenge. Use MCP web-reader instead (see fetch_ssrn_page).
# --------------------------------------------------------------------------- #

_scraper = None

def _get_scraper():
    global _scraper
    if _scraper is None:
        _scraper = _cs.create_scraper(
            interpreter="js2py",           # v3 challenge solver (js2py is default + most compatible)
            session_refresh_interval=1800,  # 30 min — proactive session refresh
            auto_refresh_on_403=True,      # auto 403 recovery on stale sessions
            max_403_retries=3,             # retry budget before giving up
            debug=False,
        )
    return _scraper

def fetch_ssrn_page(ssrn_id, timeout=30):
    """
    Fetch a SSRN paper page via cloudscraper v3.0.0.

    Cloudscraper handles Cloudflare v1/v2/v3 JavaScript challenges automatically.
    Auto 403 recovery + session health monitoring built in.

    LIMITATION: SSRN's Cloudflare Enterprise uses a 'chl_page' managed challenge
    that cloudscraper's handlers don't recognize. The auto-refresh path hangs.
    If this returns {"error": ...}, use MCP web-reader instead:
        mcp_web_reader_webReader({"url": f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={ssrn_id}"})

    Returns dict with title, authors, abstract, keywords, JEL codes, etc.
    Returns {"error": ...} on failure or timeout.
    """
    scraper = _get_scraper()
    url = f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={ssrn_id}"

    # Run request in a thread so we can enforce a hard timeout
    import threading, queue
    result_queue = queue.Queue()

    def _do_request():
        try:
            resp = scraper.get(url, timeout=timeout)
            result_queue.put(("ok", resp.text))
        except Exception as e:
            result_queue.put(("error", str(e)))

    t = threading.Thread(target=_do_request, daemon=True)
    t.start()
    t.join(timeout=timeout + 5)
    if t.is_alive():
        return {"error": "cloudscraper timeout — SSRN CF challenge not solved", "ssrn_id": ssrn_id}

    status, payload = result_queue.get()
    if status == "error":
        return {"error": payload, "ssrn_id": ssrn_id}

    html = payload
    if not html or len(html) < 200:
        return {"error": "Empty or too-short response", "ssrn_id": ssrn_id}

    # Parse the SSRN abstract page
    title_m = re.search(r'<title>(.*?)</title>', html, re.I)
    title = title_m.group(1).strip() if title_m else ""

    # Authors block
    authors_m = re.search(r'class="authors[\s\S]*?<span[\s\S]*?>(.*?)</span>', html, re.I)
    authors = re.sub(r"<[^>]+>", "", authors_m.group(1)).strip() if authors_m else ""

    # Abstract paragraphs
    abstract_parts = re.findall(r'<p\s+class="abstract[^"]*">(.*?)</p>', html, re.I | re.DOTALL)
    if not abstract_parts:
        abstract_parts = re.findall(r'class="abstract"[\s\S]*?>([\s\S]*?)</div>', html, re.I)
    abstract = re.sub(r"<[^>]+>", " ", " ".join(abstract_parts)).strip()
    abstract = re.sub(r"\s+", " ", abstract).strip()

    # Keywords
    kw_m = re.search(r'Keywords:</span>(.*?)</div>', html, re.I | re.DOTALL)
    keywords = [k.strip() for k in re.findall(r'<a[^>]*>(.*?)</a>', kw_m.group(1), re.I)] if kw_m else []

    # JEL codes
    jel_m = re.search(r'JEL Classification:</span>(.*?)</div>', html, re.I | re.DOTALL)
    jel = [c.strip() for c in re.findall(r'<a[^>]*>(.*?)</a>', jel_m.group(1), re.I)] if jel_m else []

    # Publication info
    pub_m = re.search(r'class="pubinfo"[\s\S]*?>([\s\S]*?)</div>', html, re.I)
    pubinfo = re.sub(r"<[^>]+>", " ", pub_m.group(1)).strip() if pub_m else ""

    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "keywords": keywords,
        "jel": jel,
        "pubinfo": pubinfo,
        "ssrn_id": ssrn_id,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ssrn_search.py <search|fetch|fetch-page> <query|ssrn_id> [--backend scholar|openalex]")
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
    elif action == "fetch-page":
        # Direct fetch via cloudscraper (bypasses Cloudflare challenges)
        result = fetch_ssrn_page(arg)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(f"Failed to fetch SSRN paper {arg} via cloudscraper")
