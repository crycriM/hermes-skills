#!/usr/bin/env python3
"""Logging forward proxy for the halogen lane: 127.0.0.1:8742 -> 127.0.0.1:8741.

Logs every request body (one JSON object per line, with a sorted key list) to
bodies.jsonl next to this file and streams the upstream response back verbatim.
This is how the per-client wire facts in references/clients.md were captured.

Usage:
    python3 client-logging-proxy.py [port]   # default 8742, upstream fixed 8741
    tail -f bodies.jsonl

Point a SCRATCH client config at it (never the real one):
  - opencode: XDG_CONFIG_HOME=<scratch dir holding opencode/opencode.jsonc> and a
    provider whose baseURL is http://127.0.0.1:8742/v1. NOTE: OPENCODE_CONFIG and
    OPENCODE_CONFIG_CONTENT are merged, not substituted -- XDG_CONFIG_HOME is the
    only reliable way to run opencode on a throwaway config (verified 1.18.34).
  - Kilo: KILO_CONFIG=<scratch kilo.jsonc>.

Kill it by PID: `pkill -f "client-logging-proxy"` also matches the shell that ran
it, so prefer `kill <pid>`.
"""
import http.client
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = ("127.0.0.1", 8741)
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bodies.jsonl")
_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _relay(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if body:
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"_raw": body[:2000].decode("utf-8", "replace")}
            keys = sorted(parsed.keys()) if isinstance(parsed, dict) else None
            with _lock, open(LOG, "a") as fh:
                fh.write(json.dumps({"path": self.path, "keys": keys,
                                     "body": parsed}) + "\n")
        conn = http.client.HTTPConnection(*UPSTREAM, timeout=600)
        hdrs = {k: v for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length", "connection",
                                     "accept-encoding")}
        hdrs["Content-Length"] = str(len(body))
        hdrs["Accept-Encoding"] = "identity"
        conn.request(method, self.path, body=body, headers=hdrs)
        resp = conn.getresponse()
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() in ("transfer-encoding", "connection", "content-length"):
                continue
            self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            self.wfile.write(chunk)
            self.wfile.flush()

    def do_POST(self):
        self._relay("POST")

    def do_GET(self):
        self._relay("GET")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8742
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
