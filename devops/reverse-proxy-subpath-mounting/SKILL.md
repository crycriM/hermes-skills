---
name: reverse-proxy-subpath-mounting
description: "Use when wiring a service into a reverse proxy sub-path."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [nginx, reverse-proxy, sub-path, homelab, systemd]
    related_skills: [devops, tailscale-ingress, model-manager-gui-spec]
---

# Mounting a service on a reverse-proxy sub-path

Class of task: "there is a service on port N, wire it into the reverse proxy as
well" — a local HTTP backend that serves at `/` on its own port must also be
reachable as `https://<host>/<name>/` through an existing nginx site. Applies to
stdlib Python servers, Go binaries, framework apps alike.

## When to Use

* the user says a service on port N should also be reachable through the reverse
  proxy ("wire it in as well", "put it behind the proxy");
* a service that works on `http://<host>:<port>/` must appear under
  `https://<host>/<name>/`;
* an existing sub-path mount 404s, emits links that escape the mount, or
  redirects out of it;
* you publish a local HTTP service and want it reachable over the portal's TLS
  instead of on a bare port.

Not for: writing the service itself, or picking a reverse proxy — this is the
mount, publish and verify procedure.

Host specifics for this box (site config path, service map, landing page, which
ports are taken) live in the `devops` skill's nginx reverse-proxy reference; this
skill is the procedure and the rules that hold anywhere.

## Order of work

1. Read the live site config and find the right server block. A portal often has
   more than one listener (different services on different ports): identify the
   block whose `location = /` serves the landing page and whose sub-paths match
   the URL the user quoted. Adding the location to the wrong block changes
   nothing for that URL and looks like a broken config.
2. Confirm the backend port and that it is the service, not a neighbour
   (`ss -ltnp`, the unit's `ExecStart`, one `curl`). Service maps in READMEs drift
   (they claim one port for everything) — trust the curl.
3. Pick the mount strategy and commit to it before editing:
   * **backend made prefix-aware** (preferred, see the contract below) when you
     control the code — no rewrite, direct port access keeps working;
   * **prefix strip + `sub_filter`** for frameworks with hardcoded absolute paths
     (`location /prefix/ { rewrite ^/prefix(/.*)$ $1 break; proxy_pass ...; }`),
     adding one location per absolute prefix the app emits;
   * **plain strip** only when the app is happy behind a prefix and nobody needs
     direct-port access.
4. Implement the backend side of the contract, restart the backend
   (`systemctl --user daemon-reload && systemctl --user restart <unit>` — for a
   stdlib service the unit's `ExecStart` is the only state).
5. Add the nginx locations, then the entry in the landing page.
6. Verify against the real config with `scripts/nginx-dryrun.sh` (unprivileged,
   shifted ports), then hand the human the privileged reload. Never report the
   route as working before that reload: the file on disk being new is not the
   served config, and until then the new path 404s.
7. When sudo is unavailable (the normal case for a root-owned system nginx), do
   not chase workarounds to publish the route yourself — no loosening `$HOME`
   permissions, no second copy of the site config on privileged ports. Stage the
   change, prove it with the dry run, and give the human the exact two commands
   plus what stays pending until they run them.

## The prefix-aware backend contract

Detection is **per request**, never a global start flag. Requests arriving with
the prefix are stripped for filesystem/business lookup and have the prefix
prepended to every generated URL; requests without it behave exactly as when
mounted at root. Invariant to hold: the same instance answers both `/` on its own
port and `/name/` through the proxy, and no generated link ever points outside the
mount. Implementation checklist, code sketch and edge cases:
`references/prefix-aware-backend.md`.

## nginx rules

```nginx
location = /name { return 301 /name/; }      # required, see below
location /name/ {
    proxy_pass http://127.0.0.1:PORT;        # NO trailing slash, no rewrite
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

* `proxy_pass` **without** a URI part (no trailing `/`) forwards the original
  path; a trailing slash or explicit URI silently strips the prefix, which breaks
  a prefix-aware backend that expects to see it.
* The slash-less URL is **not** matched by a `location /name/` prefix block and
  would 404; the exact-match `location = /name { return 301 /name/; }` is what
  makes `/name` work. Prefix matching picks the longest match, so ordering is
  irrelevant unless paths nest.
* Keep authentication in the backend: nginx forwards the `Authorization` header
  untouched, so the browser prompt comes from the service. Do not duplicate the
  credentials in an nginx `auth_basic` unless you mean to replace it.
* WebSocket/SSE services need the `Upgrade`/`Connection` headers (map
  `$http_upgrade` to `$connection_upgrade` once at `http` level).

## Per-IP logic behind a proxy (do this in the same pass)

Every proxied request reaches a local backend from `127.0.0.1`, so any per-IP
state — failed-login throttles, rate limits, audit buckets — collapses into one
shared bucket and one client's mistakes punish everybody. Rules:

* nginx: `proxy_set_header X-Real-IP $remote_addr;` in the location block.
* backend: trust that header **only when the peer address is loopback**;
  nginx overwrites whatever the client sent, so it cannot be spoofed through the
  proxy, but a direct caller could spoof it if you trust it blindly.
* use the resolved value for throttling *and* in access logs, or the logs lose the
  real client the moment the proxy appears.

## Verify, then hand off

Run `scripts/nginx-dryrun.sh <site.conf> [URL ...]`: it includes the real site
config inside a minimal `http {}` block with every `listen` port shifted +10000,
so a throwaway nginx as the current user proves syntax, context and routing
without sudo and without touching the live server. Then the only privileged step
is the human's:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Assertions worth making before claiming success (see the reference for the exact
commands): mounted root 200 with **every** link prefixed and the same entry count
as direct root; `/name` → 301 `/name/` with the prefix in `Location`; a real file
byte-identical direct vs mounted; `Range: bytes=0-1023` → 206; no credentials →
401 with `WWW-Authenticate`; `/name/../../etc/passwd` → 403/404.

Keep reusable harnesses in this skill's `scripts/`, not in the scratch dir —
scratch is pruned after a day and the next session inherits nothing.

## Pitfalls

* **A static landing page served from a world-readable copy dies on reboot.** If
  nginx workers cannot read the source (they run as `www-data` and cannot
  traverse `$HOME`), the page is copied to `/tmp` — a tmpfs. Add a user oneshot
  unit (`install -m 644 <src> /tmp/<name>`, **no `PrivateTmp`**, `WantedBy=default.target`)
  or the portal root 404s after every boot while all sub-paths keep working. That
  page is read per request, so it needs no nginx reload.
* **Prefix collision:** a top-level entry literally named like the mount (`/name`
  folder) is shadowed for prefixed requests. Rename one of them or accept it —
  decide consciously.
* **Two things to restart, and they are different:** the backend unit for code/flag
  changes, nginx for location changes. Restarting the backend never publishes a
  new location; reloading nginx never picks up a new `ExecStart`.
* **Don't leave the mount half-documented:** update the project README's service
  map and the reverse-proxy README in the same pass, or the next session trusts
  a table that was already wrong.
* When the request is only "wire it in", do not silently re-scope the other
  services' ports in the README — fix inaccuracies you must touch, mention the
  rest.

## Support files

* `scripts/nginx-dryrun.sh` — validate any nginx site config without sudo
  (`nginx -t` on the real content + live curls through a throwaway instance).
* `references/prefix-aware-backend.md` — implementing the per-request mount in a
  stdlib server: call-site checklist, code sketch, edge cases.
