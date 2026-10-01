#!/usr/bin/env python3
"""Pass-through logging proxy: capture what an LLM client ACTUALLY sends.

Some client knobs (a reasoning-effort / variant picker, a limit, a header) are
computed from client-side model metadata and are silently dropped for a model the
client knows nothing about. Reading the client's bundled code answers this slowly
and ambiguously; capturing one request body answers it exactly.

    python3 api-logging-proxy.py --listen 8742 --upstream http://127.0.0.1:8741 \
        --log ./captured.jsonl --tag kilo
    # point a SCRATCH client config at http://127.0.0.1:8742/v1, drive the client,
    # then read --log

Each request body becomes one JSON line holding the top-level key set plus every
field EXCEPT the bulky payload keys (messages / input / tools) - which is exactly
what shows whether a knob reached the wire. Long values are truncated.

Operational notes:
  * Stop it with a BRACKET pattern: pkill -f "[a]pi-logging-proxy.py". A plain
    pkill -f "api-logging-proxy.py" also matches the command line of the shell
    running it (the pattern sits inside that command line) and kills that shell.
  * Responses are buffered (Content-Length, not chunked) so the body can be
    logged whole. Fine for CLI clients; do not leave this in the path as a proxy.
  * Drive long client runs from a shell rather than an execute_code cell: that
    tool's kernel is killed at 5 minutes and takes the call with it.
"""
import argparse
import http.client
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BULK = ("messages", "input", "tools", "prompt")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = ("127.0.0.1", 8741)
    log_path = "captured.jsonl"
    tag = "unlabeled"

    def log_message(self, *a):
        pass

    def _proxy(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        if body:
            try:
                d = json.loads(body)
                rec = {
                    "tag": self.tag,
                    "path": self.path,
                    "top_keys": sorted(d.keys()),
                    "params": {
                        k: (v if not isinstance(v, str) or len(v) < 200 else v[:200] + "...")
                        for k, v in d.items() if k not in BULK
                    },
                }
            except Exception as e:
                rec = {"tag": self.tag, "path": self.path, "err": str(e),
                       "raw": body[:300].decode("utf-8", "replace")}
            with open(self.log_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
        hdrs = {k: v for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length", "connection")}
        conn = http.client.HTTPConnection(*self.upstream, timeout=3600)
        try:
            conn.request(self.command, self.path, body=body, headers=hdrs)
            r = conn.getresponse()
            data = r.read()
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() in ("transfer-encoding", "connection", "content-length"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            msg = json.dumps({"proxy_error": str(e)}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _proxy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=8742)
    ap.add_argument("--upstream", default="http://127.0.0.1:8741")
    ap.add_argument("--log", default="captured.jsonl")
    ap.add_argument("--tag", default="unlabeled")
    a = ap.parse_args()
    u = urllib.parse.urlsplit(a.upstream)
    Handler.upstream = (u.hostname, u.port or (443 if u.scheme == "https" else 80))
    Handler.log_path = a.log
    Handler.tag = a.tag
    print(f"logging {a.listen} -> {a.upstream} into {a.log} (tag={a.tag})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.listen), Handler).serve_forever()


if __name__ == "__main__":
    main()
