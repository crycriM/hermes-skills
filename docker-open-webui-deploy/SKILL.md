---
name: docker-open-webui-deploy
description: Deploy Open-WebUI via Docker or Python venv with correct port mapping, API-based configuration, and troubleshooting.
category: docker
---

# Deploy Open‑WebUI

This skill covers two deployment methods: Docker and Python venv. It also covers API-based configuration when browser automation is unavailable (e.g. Playwright broken on Ubuntu 26).

---

## Method A: Python venv Install

Use this when a systemd user service (`~/.config/systemd/user/open-webui.service`) already exists.

### Prerequisites

- **Python 3.11 or 3.12 required.** Open-WebUI does not support Python 3.13+ yet.
- On Ubuntu 26, system Python is 3.14. Check for older versions: `python3.11 --version`.
- If `python3.11` is available, it can create venvs without needing `python3.11-venv` package (unlike python3.14 which needs `python3.14-venv`).

### Steps

1. **Create the venv with Python 3.11:**
   ```bash
   python3.11 -m venv ~/open-webui-venv
   ```

2. **Install open-webui:**
   ```bash
   source ~/open-webui-venv/bin/activate
   pip install --upgrade pip
   pip install open-webui
   ```

3. **Create the launcher script** (`~/start-open-webui.sh`):
   ```bash
   #!/bin/bash
   cd ~
   source ~/open-webui-venv/bin/activate
   open-webui serve --port 8088
   ```
   `chmod +x ~/start-open-webui.sh`

4. **Start/enable the service:**
   ```bash
   systemctl --user restart open-webui
   systemctl --user enable open-webui
   ```

### Pitfalls

- **Python 3.14 incompatibility**: `pip install open-webui` fails silently — "No matching distribution found" because all versions require Python <3.13. Must use 3.11 or 3.12 explicitly.
- **Missing venv**: If the venv directory is deleted, the service crash-loops with exit code 127 (command not found in the dead venv).

---

## Method B: Docker Deploy

This skill shows a reliable, repeatable way to run the Open‑WebUI container and get it reachable on host port **3000**. It includes the trial‑and‑error that was needed to discover the correct port mapping and how to verify the service is ready.

## Steps

1. **Stop any stale container**
   ```bash
   docker stop open-webui && docker rm open-webui
   ```

2. **Run the container, mapping host 3000 → container 8080** (the app listens on 8080, not 8088):
   ```bash
   docker run -d \
     -p 3000:8080 \
     -v open-webui:/app/backend/data \
     --name open-webui \
     --restart always \
     ghcr.io/open-webui/open-webui:main
   ```

3. **Wait for the DB migrations to finish**
   - Watch the logs:
     ```bash
     docker logs -f open-webui
     ```
   - Look for the line:
     ```
     INFO  uvicorn.main:startup - Application startup complete.
     ```

4. **Verify the service**
   ```bash
   curl -v http://localhost:3000
   ```
   You should receive the HTML splash page (status 200). Opening `http://localhost:3000` in a browser will load the UI.

5. **Confirm the port mapping**
   ```bash
   docker ps --filter "name=open-webui" --format "table {{.Names}}\t{{.Ports}}"
   ```
   Output should show `0.0.0.0:3000->8080/tcp`.

## Common Pitfalls & Troubleshooting

- **Wrong port mapping** – The image defaults to `uvicorn ... --port 8080`. Mapping `-p 3000:8088` (as in the original command) never reaches the web UI, leading to a connection reset.
- **Premature request** – The container health check runs before migrations finish. Wait for the "Application startup complete" log before testing.
- **Volume permission errors** – Ensure the named volume `open-webui` exists or pre‑create it with `docker volume create open-webui`. The container will create it automatically if missing.
- **Firewall / SELinux** – On some hosts, inbound connections to the mapped port may be blocked. Verify with `sudo ufw status` or equivalent.

## Verification Checklist

- [ ] `docker ps` shows `0.0.0.0:3000->8080/tcp`.
- [ ] Logs contain `Application startup complete`.
- [ ] `curl http://localhost:3000` returns HTML, not connection reset.

## Method 2: Python Venv Install

Useful when Docker is overkill or unavailable.

1. **Create venv with Python 3.11** (open-webui requires 3.11-3.12, NOT 3.14):
   ```bash
   python3.11 -m venv ~/open-webui-venv
   source ~/open-webui-venv/bin/activate
   pip install open-webui
   ```

2. **Set DATA_DIR** to persist data (defaults to `./data` relative to cwd):
   ```bash
   export DATA_DIR=/home/cricri/openwebui_data
   open-webui serve --port 8088
   ```

3. **Systemd user service** (`~/.config/systemd/user/open-webui.service`):
   ```ini
   [Unit]
   Description=Open WebUI (LLM frontend)
   After=network.target m5-router.service

   [Service]
   Type=simple
   WorkingDirectory=/home/cricri
   ExecStart=/home/cricri/start-open-webui.sh
   Restart=on-failure
   RestartSec=10

   [Install]
   WantedBy=default.target
   ```

4. **Start script** (`~/start-open-webui.sh`):
   ```bash
   #!/bin/bash
   export DATA_DIR=/home/cricri/openwebui_data
   source ~/open-webui-venv/bin/activate
   open-webui serve --port 8088
   ```

## API-Based Configuration (No Browser Needed)

When Playwright cannot install (e.g. Ubuntu 26), configure via curl:

1. **Reset admin password** (use Python sqlite3, NOT sqlite3 CLI — `$` in bcrypt hash gets mangled by shell):
   ```bash
   python3.11 -c "
   import bcrypt, sqlite3
   h = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode()
   conn = sqlite3.connect('$DATA_DIR/webui.db')
   conn.execute('UPDATE auth SET password=? WHERE email=?', (h, 'user@example.com'))
   conn.commit()
   conn.close()
   "
   ```

2. **Authenticate** (cookie-based, NOT Bearer-only):
   ```bash
   curl -s -c /tmp/owui_cookie -X POST http://localhost:8088/api/v1/auths/signin \
     -H 'Content-Type: application/json' \
     -d '{"email":"user@example.com","password":"admin123"}'
   ```

3. **Query models** (must use cookie, Bearer alone returns HTML):
   ```bash
   curl -s -b /tmp/owui_cookie http://localhost:8088/api/models
   ```

## Pitfalls

- **Python 3.14**: open-webui has no wheel for 3.14. Use 3.11.
- **sqlite3 CLI + bcrypt**: `$` signs in bcrypt hashes get shell-expanded. Always use Python's sqlite3 module.
- **API auth**: Open WebUI v0.8.x uses cookie-based auth. Bearer token in header returns HTML, not JSON. Use `-c`/`-b` curl flags.
- **DATA_DIR**: If not set, data goes to `./data` relative to WorkingDirectory. Old data in a different dir won't be found.
- **Playwright on Ubuntu 26**: Not supported as of Apr 2026. Use API approach above.
- **IPv6 causing startup hang**: If IPv6 is broken on the network, Open WebUI hangs during init trying to reach Hugging Face CDN (or other external services) via IPv6. The process stays in SYN-SENT and never binds its port. Fix: force Python to IPv4-only via a `sitecustomize.py` hack.

## Troubleshooting: Open WebUI Process Runs But Never Listens

**Symptom**: `ps aux` shows the process, `systemctl status` says active (running), but `ss -tlnp | grep 8088` shows nothing. No "Application startup complete" in logs.

**Diagnosis**:
1. Check for stuck outbound connections: `ss -tnp | grep <PID>`
2. If you see `SYN-SENT` to an IPv6 address (port 443), the process is stuck trying to reach an external service over broken IPv6.

**Root cause**: Python's `socket.getaddrinfo` returns IPv6 addresses first on dual-stack systems. If IPv6 routing is broken (no response to SYN), the TCP handshake hangs for minutes, blocking startup.

**Fix** — Force IPv4-only via Python sitecustomize:
1. Create `/home/cricri/open-webui-ipv4/sitecustomize.py`:
   ```python
   """Force IPv4 for all socket connections."""
   import socket
   import urllib3.util.connection as urllib3_cn

   def _ipv4_only():
       return socket.AF_INET
   urllib3_cn.allowed_gai_family = _ipv4_only

   _orig_getaddrinfo = socket.getaddrinfo
   def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
       return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
   socket.getaddrinfo = _ipv4_getaddrinfo
   ```

2. Add to systemd service:
   ```ini
   [Service]
   Environment="PYTHONPATH=/home/cricri/open-webui-ipv4"
   ```

3. Reload and restart:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart open-webui
   ```

**Verification**: Service should bind port 8088 within ~10-20 seconds instead of hanging forever.

## Troubleshooting: Built-in Web Search "An error occurred"

**Symptom**: The integrated web search (toggle in chat) fails with "An error occurred while searching the web", but a community search tool (e.g. brave-search tool) works fine with the same API key.

**Root cause**: The built-in web search generates multiple queries via LLM call (`generate_queries`), then fires them all in parallel via `asyncio.gather` against the search API. Brave free tier allows 1 req/sec — parallel queries trigger 429 Too Many Requests instantly.

**Diagnosis**:
```bash
journalctl --user -u open-webui --since "10 min ago" | grep -i '429\|search\|error'
```
Look for `429 Client Error: Too Many Requests` in the logs.

**Code path** (for reference):
- `middleware.py` calls `generate_queries()` → LLM decomposes user message into 2-5 search queries
- `retrieval.py` fires all queries via `asyncio.gather(*search_tasks)` (parallel)
- `brave.py` has a single retry-after-1s fallback, but parallel retries also overlap

**Fix**: Set `concurrent_requests` to 1 in Open WebUI admin settings:
- Admin Panel → Settings → Web Search → Concurrent Requests → set to 1
- This serializes the queries, respecting Brave's 1 req/sec limit
- Alternatively, disable the built-in web search and rely on community search tools (which send single requests)

**Config location** (in SQLite): `webui.db` → `config` table → `data` JSON → `rag.web.search.concurrent_requests`

---
*Skill updated to cover venv install and API-based configuration after Ubuntu 26 broke Playwright browser automation.*