# PDF Extraction Workflow

When reading research papers (PDFs) in Hermes sessions.

## Quick Reference

**For local PDFs:**
```bash
pdftotext /path/to/file.pdf /tmp/extracted.txt
wc -l /tmp/extracted.txt  # check size
head -50 /tmp/extracted.txt  # preview
```

**For web-hosted PDFs:**
```bash
curl -sL -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "https://example.com/paper.pdf" -o /tmp/paper.pdf
pdftotext /tmp/paper.pdf /tmp/extracted.txt
```

## Pitfalls

1. **`mcp_jina_reader_read_url` does NOT support `file://` URLs** — only HTTP(S). Use `pdftotext` terminal for local files.
2. **SSRN pages are behind Cloudflare bot detection** — `curl` and `mcp_tavily_search_tavily_extract` often return "Just a moment..." HTML. Use the direct PDF download link pattern: `https://papers.ssrn.com/sol3/Delivery.cfm/<hash>-MECA.pdf?abstractid=<ID>&mirid=1`
3. **Extracted text can be large** (2000+ lines). Always check `wc -l` before reading. Use `head`/`sed`/`grep` for targeted extraction.
4. **`pdftotext` may produce garbled output** for complex layouts. Check first 50 lines for readability. If broken, try `pdftotext -layout` or `pdfplumber`/`PyMuPDF` (if installed).
5. **SSRN abstract pages** (`papers.ssrn.com/sol3/papers.cfm?abstract_id=XXXX`) are Cloudflare-protected. Use the direct PDF delivery URL or `curl -A "Mozilla/..."` with user-agent spoofing.

## SSRN Paper Discovery

To find a paper by abstract ID:
1. Search web: `mcp_tavily_search_tavily_search(query="SSRN <abstract_id>")`
2. Look for `Delivery.cfm` URL in results (direct PDF link)
3. Extract with `curl` + `pdftotext`

## When Jina Reader Works

- `mcp_jina_reader_read_url` works for **HTTP(S)** URLs to PDFs
- `mcp_jina_reader_extract_pdf` works for arXiv IDs and direct HTTP(S) PDF URLs
- Both fail for local `file://` paths
