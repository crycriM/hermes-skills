# Prefix-aware backend — same instance at `/` and under `/name/`

How to make a directory-listing style server (Python stdlib, but the shape
applies to any language) survive being mounted on a reverse-proxy sub-path
*without* nginx rewriting the path, while keeping direct port access intact.

## Why per-request and not a start flag

A global "base URL" flag forces a choice: either the proxy works and direct access
on the port breaks (links point at a prefix the bare port does not serve), or the
proxy serves links that escape the mount. Per-request detection gives both: the
prefix is applied only when the request actually carried it.

```python
prefix = "/docs-web"        # "" = no fixed mount, served at the URL root

    def mount_point(self):
        """Prefix for generated links/redirects, decided per request."""
        p = self.prefix
        if p and (self.path == p or self.path.startswith(p + "/")):
            return p
        return ""

    def stripped_path(self):
        """Request path with the mount prefix removed, when it carries one."""
        p = self.mount_point()
        if not p:
            return self.path
        rest = self.path[len(p):]
        return rest if rest.startswith("/") else "/"     # "/name" -> "/"

    def rel_url(self, path, is_dir=False):
        # ... unchanged path maths ...
        return self.mount_point() + out          # root -> "/name/"
```

Normalise the CLI/env value once at startup: `""` stays `""`, `docs-web` and
`/docs-web/` both become `/docs-web`.

## Call-site checklist (the ones that get missed)

The rule is: **every place a URL is produced** gets `mount_point()` prepended, and
**every place a request path is used** goes through `stripped_path()`.

1. request path → filesystem/business lookup (the obvious one);
2. links to child entries in a listing;
3. breadcrumbs — the root crumb is the classic miss when it is a hardcoded
   `href="/"`;
4. the directory canonical redirect: `Location` must carry the prefix, otherwise
   the browser leaves the mount on the first click;
5. any inline HTML/JS with absolute asset or endpoint paths;
6. anything derived from the path in responses (self-links, ETags keyed on path).

## Edge cases

* `/name` (no trailing slash) must redirect to `/name/`, i.e. the directory
  redirect uses `mount_point() + "/"` — not a bare `"/"`.
* Query strings must survive the strip (`/name/?q=x` → `/?q=x` for lookup).
* A path that does *not* start with the prefix must never be stripped: a direct
  `/` request has to stay the root listing.
* A top-level entry literally named like the mount is shadowed for prefixed
  requests. Accept it knowingly or rename the file/folder.
* Traversal defence is unchanged but re-check it after the strip: resolve the
  stripped path, `realpath` it, and refuse anything outside the root (403).

## Interacting rule: client IP behind the proxy

Same pass, because a mounted service usually protects itself. Every proxied
request arrives from `127.0.0.1`, so a failed-login throttle or rate limiter keyed
on the peer address becomes global: ten typos from anyone lock out everyone.

```python
    def client_ip(self):
        peer = self.client_address[0]
        if peer in ("127.0.0.1", "::1"):                 # trusted proxy only
            fwd = self.headers.get("X-Real-IP", "").split(",")[0].strip()
            if fwd:
                return fwd
        return peer
```

Use it for the throttle buckets **and** the access log. Rationale for trusting the
header from loopback only: nginx sets `X-Real-IP $remote_addr`, overwriting
anything the client sent, so it cannot be spoofed *through the proxy* — a direct
caller could forge it, which is why the peer check matters.

## Verification (both sides, with the concrete assertions)

Direct on the port (`:PORT`), then through the proxy:

```bash
# link prefixing and parity with the direct listing
curl -s -u u:p http://127.0.0.1:PORT/name/ | grep -o 'href="/[^"]*"' | sort -u | head
curl -s -u u:p http://127.0.0.1:PORT/         # same entries, links WITHOUT the prefix

# canonical redirect keeps the mount
curl -s -o /dev/null -D - -u u:p http://127.0.0.1:PORT/name     # 301 Location: /name/

# byte-identical file direct vs mounted; range support survives
curl -s -o /dev/null -w '%{size_download}\n' -u u:p http://127.0.0.1:PORT/name/<file>
curl -s -o /dev/null -w '%{http_code}\n' -r 0-1023 -u u:p http://127.0.0.1:PORT/name/<file>   # 206

# auth + traversal still enforced on both paths
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:PORT/name/                # 401 + WWW-Authenticate
curl -s -o /dev/null -w '%{http_code}\n' -u u:p http://127.0.0.1:PORT/name/../../etc/passwd  # 403/404
```

Couple the assertions to both endpoints on purpose: "every link carries the
prefix" AND "the direct listing is unprefixed", "same entry count direct vs
mounted". A one-sided check passes for a broken build that only ever emits one of
the two shapes.

Then the proxy side: `scripts/nginx-dryrun.sh <site.conf> https://127.0.0.1:18444/name/`
for the real config, and after the human's `sudo nginx -t && sudo systemctl reload nginx`
repeat the same checks against the live portal URL.
