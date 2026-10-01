#!/usr/bin/env bash
# nginx-dryrun.sh — validate an nginx site config WITHOUT sudo.
#
# Usage:
#   nginx-dryrun.sh <site.conf> [URL ...]
#
# Why: the live nginx is root-owned (reload needs sudo), but a config change can
# still be proven BEFORE asking the human to reload. This starts a throwaway
# nginx as the current user: the site config is included inside a minimal http{}
# block (its real context) with every `listen <port>` shifted by +10000, so
# nothing collides with the live server. It runs `nginx -t` on the real file
# content, starts the instance, curls the URLs, then quits.
#
# URLs must use the SHIFTED ports (8443 -> 18443, 8444 -> 18444, 80 -> 10080):
#   nginx-dryrun.sh ~/projects/pelemello/reverse-proxy/nginx.conf \
#       https://127.0.0.1:18444/docs-web/ https://127.0.0.1:18444/
#
# Interpret the codes, don't just look for 200: 401 = backend basic auth with no
# credentials, 301 = mount canonicalisation, 404 on a path you just added = the
# location block did not match, 502/504 = backend down (error log tail printed).
#
# Run with bash (process substitution). Exit 0 = config valid and every URL
# answered, 1 = invalid config or unreachable service.
set -uo pipefail

CONF="${1:?usage: nginx-dryrun.sh <site.conf> [URL ...]}"
[ -r "$CONF" ] || { echo "cannot read config: $CONF" >&2; exit 1; }
shift

WORK="$(mktemp -d "${TMPDIR:-/tmp}/nginx-dryrun.XXXXXX")" || exit 1
mkdir -p "$WORK"/{body,proxy,fcgi,uwsgi,scgi,logs}

# Shift every listen port by +10000, keeping any host / [::] prefix.
python3 - "$CONF" "$WORK/site.conf" <<'PY'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
pat = re.compile(r'^(\s*listen\s+)(?:([\[\]0-9a-fA-F:.]+):)?(\d+)(.*)$')
out = []
for line in open(src):
    m = pat.match(line)
    if m:
        host = m.group(2) or ''
        line = f"{m.group(1)}{host + ':' if host else ''}{int(m.group(3)) + 10000}{m.group(4)}\n"
    out.append(line)
open(dst, 'w').writelines(out)
PY

echo "--- remapped listen lines (live port + 10000):"
while read -r l; do printf '  %s\n' "$l"; done < <(grep -n 'listen' "$WORK/site.conf")

MIME=""
[ -f /etc/nginx/mime.types ] && MIME="include /etc/nginx/mime.types;"
cat > "$WORK/nginx.conf" <<EOF
worker_processes 1;
error_log $WORK/logs/error.log warn;
pid $WORK/nginx.pid;
events { worker_connections 128; }
http {
    $MIME
    default_type application/octet-stream;
    access_log $WORK/logs/access.log;
    client_body_temp_path $WORK/body;
    proxy_temp_path $WORK/proxy;
    fastcgi_temp_path $WORK/fcgi;
    uwsgi_temp_path $WORK/uwsgi;
    scgi_temp_path $WORK/scgi;
    include $WORK/site.conf;
}
EOF

# A site config has no http{} wrapper of its own, so including it inside one
# reproduces the live context exactly. Temp paths and pid MUST be redirected to
# writable dirs, or a non-root nginx refuses to start.
echo "--- nginx -t on the real config content:"
if ! nginx -t -c "$WORK/nginx.conf" -p "$WORK/" 2>&1; then
    echo "INVALID: config rejected, nothing was reloaded" >&2
    exit 1
fi

cleanup() { [ -f "$WORK/nginx.pid" ] && nginx -c "$WORK/nginx.conf" -p "$WORK/" -s quit >/dev/null 2>&1; }
trap cleanup EXIT

nginx -c "$WORK/nginx.conf" -p "$WORK/" || exit 1

rc=0
if [ "$#" -gt 0 ]; then
    # curl exits 0 for 401/404 too, so poll until the instance answers at all.
    for _ in $(seq 1 40); do curl -sk -o /dev/null --max-time 2 "$1" && break; sleep 0.25; done
    echo "--- live checks through the throwaway instance:"
    for u in "$@"; do
        out=$(curl -sk -o /dev/null --max-time 20 -w '%{http_code} %{redirect_url}\n' "$u")
        code=${out%% *}
        loc=${out#* }
        printf '  %-58s -> %s %s\n' "$u" "$code" "$loc"
        case "$code" in
            000) rc=1 ;;
            502|504)
                echo '    backend did not answer — last error log lines:'
                tail -n 5 "$WORK/logs/error.log" | sed 's/^/      /'
                rc=1 ;;
        esac
    done
else
    echo "--- no URLs given: syntax/context check only"
fi

echo
exit "$rc"
