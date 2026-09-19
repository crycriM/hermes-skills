# Nginx Reverse Proxy — LAN Services

Config lives at `~/projects/pelemello/reverse-proxy/nginx.conf`, symlinked to `/etc/nginx/sites-enabled/pelemello`. HTTPS on port 8443 with self-signed cert.

## Service Map

| Path | Backend | Port |
|------|---------|------|
| `/` (exact) | Static listing page | `services.html` |
| `/open-webui/` | Open-WebUI | :8088 |
| `/rag/` | RAG API proxy | :8002 |
| `/dashboard/` | Hermes Dashboard | :9119 |
| `/pelemello/` | Pelemello SPA+API | :3000 |
| `/v1/` | Model Manager API | :8079 |
| `/model-manager/` | Model Manager GUI | :8081 |
| `/llama/` | Llama.cpp server | :8080 |
| `/whisper/` | Whisper STT | :9000 |

## Common Patterns

### Static landing page at root

```nginx
location = / {
    root /path/to/static/dir;
    try_files /services.html =404;
}
```

Use `location = /` (exact match) so it only matches `/` not every request.

### Moving a service from root to sub-path

```nginx
location /service-name/ {
    rewrite ^/service-name(/.*)$ $1 break;
    proxy_pass http://127.0.0.1:PORT;
    # ... standard proxy headers ...
}
```

The `rewrite ... break` strips the prefix before forwarding. Without it the backend sees `/service-name/whatever` instead of `/whatever`.

### Service that uses absolute paths in its JS

For SPAs that hardcode paths like `/api/` or `/static/`, use `sub_filter`:

```nginx
location /prefix/ {
    rewrite ^/prefix(/.*)$ $1 break;
    proxy_pass http://127.0.0.1:PORT;
    sub_filter_once off;
    sub_filter_types text/javascript;   # text/html is default, don't repeat
    sub_filter "'/api/" "'/prefix/api/";
    sub_filter '"/api/' '"/prefix/api/';
}
```

**When sub_filter isn't enough** (heavy SPAs like Open-WebUI, SvelteKit apps), add explicit catch-all locations for every absolute path the SPA references. Find them with:

```bash
curl -s http://127.0.0.1:PORT/ | grep -oP '(src|href)=["\x27](/[^"\x27 ]+)' | sort -u
```

Then add one location per absolute path prefix:

```nginx
# Open-WebUI uses: /static/, /_app/, /manifest.json, /api/
location /static/    { proxy_pass http://127.0.0.1:8088; ... }
location /_app/      { proxy_pass http://127.0.0.1:8088; ... }
location = /manifest.json { proxy_pass http://127.0.0.1:8088; ... }
location /api/       { proxy_pass http://127.0.0.1:8088; ... }

# Dashboard uses: /assets/, /favicon.ico
location /assets/    { proxy_pass http://127.0.0.1:9119; ... }
location = /favicon.ico { proxy_pass http://127.0.0.1:9119; ... }
```

These must appear BEFORE the sub-path locations like `/open-webui/` and `/dashboard/` in the config. Nginx prefix matching picks the longest match, so `/open-webui/static/foo` correctly matches `/open-webui/` (longer than `/static/`), while `/static/foo` (from Open-WebUI root) matches `/static/`.

**Only link user-facing services.** API-only endpoints (model-manager `/v1/`, RAG `/rag/`, Whisper `/whisper/`) should appear in the listing page but NOT be clickable links — they return JSON/404 on root, confusing users.

## Pitfalls

### nginx worker can't read from /home/

The nginx worker runs as `www-data`. Home directories are `rwxr-x---` (750), so the worker can't traverse `/home/cricri/` to reach config-proxied files. Files served via `root` or `try_files` must live somewhere world-readable.

**Symptoms:** nginx welcome page appears instead of your static file; 404 on `try_files`.

**Fix:** Serve from `/tmp/` (world-readable, no PrivateTmp on this system) or `/var/www/html/`:

```bash
cp services.html /tmp/services.html && chmod 644 /tmp/services.html
```

```nginx
location = / {
    root /tmp;
    try_files /services.html =404;
}
```

Verify: `sudo -u www-data cat /tmp/services.html` should work. If it doesn't, check for PrivateTmp (`systemctl cat nginx | grep PrivateTmp`).

### `sub_filter_types` duplicate MIME type warning

```
[warn] duplicate MIME type "text/html" in /etc/nginx/sites-enabled/pelemello:70
```

**Cause:** `sub_filter_types text/html text/javascript;` — `text/html` is already the nginx default for `sub_filter`. The directive *adds* to the default, it doesn't replace it.

**Fix:** Use only the non-default types: `sub_filter_types text/javascript;`

### Sudo required for syntax check + reload

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Without sudo, `nginx -t` can check syntax but fails on pid file access.

### Open-WebUI sub-path limitations

Open-WebUI is designed to run at root. Sub-path proxying (`/open-webui/`) may break some features. Direct HTTP on port 8088 is the fallback.

## File Locations

| File | Purpose |
|------|---------|
| `~/projects/pelemello/reverse-proxy/nginx.conf` | Main config |
| `~/projects/pelemello/reverse-proxy/services.html` | Root landing page |
| `~/projects/pelemello/reverse-proxy/certs/cert.pem` | Self-signed cert (4096-bit RSA, 10yr) |
| `~/projects/pelemello/reverse-proxy/certs/key.pem` | Private key |
| `~/projects/pelemello/reverse-proxy/setup.sh` | First-time setup script |
