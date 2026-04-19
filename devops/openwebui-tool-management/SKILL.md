---
name: openwebui-tool-management
description: Install, update, and manage tools (community plugins) on a local Open WebUI instance. Fetch tool source from openwebui.com community posts and install via API.
tags: [openwebui, tools, plugins, management]
---

# Open WebUI Tool Management

Install, update, and manage tools (community plugins) on a local Open WebUI instance.

## Local Setup

- Port: 8088 (avoiding 8080 conflict with llama.cpp router)
- Start script: `~/start-open-webui.sh`
- Data dir: `~/openwebui_data/`
- SQLite DB: `~/openwebui_data/webui.db`
- Venv: `~/open-webui-venv/` (Python 3.11)
- Process user: cricri, admin email: cmarzolin@free.fr

## Fetching Tool Source from openwebui.com

Community posts at `https://openwebui.com/posts/{slug}` embed tool code in SvelteKit SSR HTML.

### Method 1: GitHub raw URL (preferred when available)

The post description usually contains a GitHub link. Fetch the raw file:
```bash
curl -sL 'https://raw.githubusercontent.com/{user}/{repo}/main/tools/{tool_name}.py' -o /tmp/tool.py
```

To find the GitHub URL, grep the page HTML for github.com:
```bash
curl -sL 'https://openwebui.com/posts/{slug}' | grep -oP 'github\.com[^\s"<>]+'
```

GitHub links often 404 (wrong branch, renamed repo, etc.). Fall back to Method 2.

### Method 2: Extract from SvelteKit embedded data (always works)

The tool Python source IS embedded in the page HTML inside `<script>` blocks. Use a Python script to extract it:

```python
import re, json, sys

with open('/tmp/owui_page.html', 'r') as f:
    html = f.read()

scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for s in scripts:
    if 'arxiv' in s.lower() and len(s) > 1000:  # adjust keyword to match tool
        for m in re.finditer(r'\bcontent:\s*"', s):
            value_start = m.end()
            pos = value_start
            chars = []
            while pos < len(s):
                ch = s[pos]
                if ch == '\\':
                    nxt = s[pos+1] if pos+1 < len(s) else ''
                    if nxt == 'n': chars.append('\n'); pos += 2
                    elif nxt == 't': chars.append('\t'); pos += 2
                    elif nxt == '"': chars.append('"'); pos += 2
                    elif nxt == '\\': chars.append('\\'); pos += 2
                    elif nxt == 'u':
                        chars.append(chr(int(s[pos+2:pos+6], 16))); pos += 6
                    else: chars.append(ch); pos += 1
                elif ch == '"': break
                else: chars.append(ch); pos += 1
            content = ''.join(chars)
            if len(content) > 100 and ('class Tools' in content or 'import ' in content):
                with open('/tmp/tool.py', 'w') as f:
                    f.write(content)
                sys.exit(0)
```

Key: the first `content:` field is the short description. The tool Python code is in a LATER `content:` field that contains `class Tools` or `import`. Filter by length (>100 chars) and code patterns.

**Dead ends to avoid**:
- `/api/v1/posts/{id}` returns HTML, not JSON
- `/api/v1/posts/{id}/download` returns 404
- `__data.json` SvelteKit endpoint is complex to parse

## Installing Tools via API

1. **Auth required first.** No API keys exist by default. Need admin password to sign in:
```bash
curl -s -c /tmp/owui_cookies.txt -X POST 'http://localhost:8088/api/v1/auths/signin' \
  -H 'Content-Type: application/json' \
  -d '{"email":"cmarzolin@free.fr","password":"PASSWORD"}'
```

2. **Create tool** using the JWT from signin. **The `meta` field is required** or you get a 422:
```python
import requests
payload = {
    "id": "tool_id",
    "name": "Tool Name",
    "content": "...python code...",
    "meta": {"description": "Short description of the tool"}
}
r = requests.post('http://localhost:8088/api/v1/tools/create',
    headers={"Authorization": f"Bearer {token}"},
    json=payload)
```

**Pitfall**: Shell-based curl with inline JSON fails on large tool files (escaping issues). Use a Python script with `requests` and read the file content directly.

3. Or **generate an API key** first via the UI (Settings > Account > API Keys) for future use.

## Querying Existing Tools

```bash
# List installed tools
sqlite3 ~/openwebui_data/webui.db "SELECT id, name FROM tool;"

# List users
sqlite3 ~/openwebui_data/webui.db "SELECT id, email, role FROM user;"
```

## Fallback: Manual Install

If API auth is not available, the user can install manually:
1. Open http://localhost:8088
2. Go to Workspace > Tools
3. Click + button
4. Paste the Python source code
