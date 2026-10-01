#!/usr/bin/env python3
"""Transparent logging proxy: capture what a client SENDS while the REAL server answers.

`echo-openai-server.py` proves what a client sends but answers the request itself (cheap, no GPU,
and it can be the only option when the real endpoint would be paid for). This sibling forwards
every request to the live upstream and streams the reply back, so ONE run proves both halves:
"the client sent field X" AND "the endpoint accepted it". Reach for it whenever the question is
not just what the client does, but whether the value it chose is legal on the far side.

    python3 logging-pass-through-proxy.py <listen_port> <upstream_host:port> [logfile]
    # e.g. python3 logging-pass-through-proxy.py 8742 127.0.0.1:8741 /tmp/captured.jsonl

Then point a THROWAWAY client config at http://127.0.0.1:<listen_port>/v1. For kilo, isolate it
without touching the user's files:

    XDG_CONFIG_HOME=<scratch> KILO_CONFIG_DIR=<scratch>/kilo XDG_DATA_HOME=<scratch-data> \
        kilo run --pure -m <provider>/<model-key> 'say ok'

(`--pure` skips their external plugins; the scratch config dir keeps their kilo.jsonc untouched.)
One JSON line per request is written: the reasoning/thinking family, the model, and the FULL key
list. Set `BODY=1` in the environment to log the entire parsed body.

Why the key list matters: a probe that logs only the fields you already know about will happily
confirm a knob that never arrives in the request. Log the keys, then compare.
"""
import json
import os
import sys
import time
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if len(sys.argv) < 3:
    sys.exit(__doc__)
PORT = int(sys.argv[1])
UP_HOST, UP_PORT = sys.argv[2].split(":")
UP_PORT = int(UP_PORT)
LOG = sys.argv[3] if len(sys.argv) > 3 else os.path.abspath("captured.jsonl")
DUMP_BODY = os.environ.get("BODY") not in (None, "", "0", "false")

REASONING_KEYS = (
    "reasoning_effort", "reasoning", "thinking", "enable_thinking", "preserve_thinking",
    "max_thinking_tokens", "thinking_budget_tokens", "thinking_budget",
    "reasoning_budget_tokens", "chat_template_kwargs",
)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _proxy(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if raw:
            try:
                body = json.loads(raw.decode("utf-8", "replace"))
                rec = {
                    "t": time.time(),
                    "path": self.path,
                    "model": body.get("model"),
                    "keys": sorted(body.keys()),
                    "reasoning": {k: body.get(k) for k in REASONING_KEYS if k in body},
                }
                if DUMP_BODY:
                    rec["body"] = body
            except Exception as exc:
                rec = {"t": time.time(), "path": self.path,
                       "unparsed": raw[:500].decode("utf-8", "replace"), "err": str(exc)}
            with open(LOG, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length", "connection")}
        conn = http.client.HTTPConnection(UP_HOST, UP_PORT, timeout=3600)
        try:
            conn.request(self.command, self.path, body=raw, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in ("transfer-encoding", "connection", "content-length"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            payload = json.dumps({"proxy_error": str(exc)}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _proxy


if __name__ == "__main__":
    print(f"forwarding 127.0.0.1:{PORT} -> {UP_HOST}:{UP_PORT}, logging to {LOG}"
          f"{' (full bodies)' if DUMP_BODY else ''}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
