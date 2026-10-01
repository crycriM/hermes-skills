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
| `/docs-web/` | docs-web (ComfyUI output browser) | :8190 |

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

### Sub-path WITHOUT a rewrite — let the backend detect the prefix

Preferred over `rewrite ^/prefix(/.*)$ $1 break` when the backend generates
absolute links (`href="/file"`): give the backend a `--prefix /name` flag whose
effect is *per request* — if the incoming path carries the prefix, strip it for
lookups and put it back on every generated link/breadcrumb/redirect; if it
doesn't, behave exactly as when mounted at the root. nginx then just forwards:

```nginx
location = /docs-web { return 301 /docs-web/; }
location /docs-web/ {
    proxy_pass http://127.0.0.1:8190;      # no trailing slash, no rewrite
    proxy_set_header X-Real-IP $remote_addr;
    # ...
}
```

Why: the same instance stays usable both through the proxy (`/docs-web/`) and
directly on its port (`:8190/`), and the browser never sees a link pointing
outside the mount. The `location = /docs-web` exact match is required — a
`location /docs-web/` prefix block does **not** catch the slash-less URL, which
then 404s instead of redirecting. Only downside: a top-level entry literally
named like the prefix is shadowed for prefixed requests.

### Client IP behind the proxy

Every request reaching a local backend comes from `127.0.0.1`, so any per-IP
logic (rate limiting, failed-login lockouts) collapses into one shared bucket and
one client's mistakes punish everyone. Have the backend trust `X-Real-IP` **only
when the peer is loopback** (`$remote_addr` set by nginx overwrites whatever the
client sent, so it cannot be spoofed through the proxy), and set
`proxy_set_header X-Real-IP $remote_addr;` in the location block. Log the same
value so access logs show real clients.

## Validating config changes without sudo

The agent cannot run sudo, but a config change can still be fully validated and
exercised before the human reloads: run a throwaway nginx as the normal user on
spare ports, with a copy of the real config included inside a minimal `http {}`.

```bash
T=~/.hermes/cache/scratch/nginxtest; mkdir -p $T/{body,proxy,fcgi,uwsgi,scgi,logs}
SRC=~/projects/pelemello/reverse-proxy/nginx.conf
# remap BOTH the IPv4 and [::] listen lines — the site config has both
sed -e 's/listen 8443/listen 18443/' -e 's/listen 8444/listen 18444/' \
    -e 's/\[::\]:8443/[::]:18443/' -e 's/\[::\]:8444/[::]:18444/' "$SRC" > $T/site.conf
cat > $T/nginx.conf <<EOF
worker_processes 1;
error_log $T/logs/error.log warn;
pid $T/nginx.pid;
events { worker_connections 64; }
http {
    include /etc/nginx/mime.types;
    access_log $T/logs/access.log;
    client_body_temp_path $T/body;  proxy_temp_path $T/proxy;
    fastcgi_temp_path $T/fcgi;      uwsgi_temp_path $T/uwsgi;  scgi_temp_path $T/scgi;
    include $T/site.conf;
}
EOF
nginx -t -c $T/nginx.conf -p $T/          # syntax check, real file content
nginx    -c $T/nginx.conf -p $T/          # start (unprivileged, ports >1024)
curl -sk -u user:pass https://127.0.0.1:18444/docs-web/ -o /dev/null -w '%{http_code}\n'
nginx    -c $T/nginx.conf -p $T/ -s quit  # stop
```

The site config has no `http {}` wrapper of its own, so `include`ing it inside
one reproduces the live context exactly. Temp paths and `pid` must be redirected
to writable dirs or a non-root nginx refuses to start. Skills' known-good copies:
`~/.hermes/cache/scratch/nginx-docsweb-e2e.sh` (docs-web route end to end).

Then the human runs the only privileged step:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

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

**`/tmp` is a tmpfs — the copy dies at every reboot.** Reproduce with a user
oneshot unit (no sudo needed) so the landing page survives:

```ini
# ~/.config/systemd/user/portal-html.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/install -m 644 /home/USER/projects/pelemello/reverse-proxy/services.html /tmp/services.html
[Install]
WantedBy=default.target
```

```
systemctl --user enable --now portal-html.service     # and after editing services.html
```

Do **not** set `PrivateTmp=yes` in that unit — the copy must land in the real
`/tmp`. The landing page is re-read per request, so this needs no nginx reload.
Symptom when it is missing: `https://<ip>:8444/` returns 404 (or the nginx
welcome page) while every `/service/` sub-path keeps working.

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
| `~/projects/pelemello/reverse-proxy/services.html` | Root landing page (copied to `/tmp/services.html` by `portal-html.service`) |
| `~/.config/systemd/user/portal-html.service` | Refresh `/tmp/services.html` at boot (no `PrivateTmp`) |
| `~/projects/docs-web/server.py` | docs-web backend, `--prefix` for the `/docs-web/` mount |
| `~/.config/systemd/user/docs-web.service` | docs-web unit (port 8190, `--prefix /docs-web`) |
| `~/projects/pelemello/reverse-proxy/certs/cert.pem` | Self-signed cert (4096-bit RSA, 10yr) |
| `~/projects/pelemello/reverse-proxy/certs/key.pem` | Private key |
| `~/projects/pelemello/reverse-proxy/setup.sh` | First-time setup script |
