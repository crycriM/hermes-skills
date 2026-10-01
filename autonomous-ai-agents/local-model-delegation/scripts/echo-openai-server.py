#!/usr/bin/env python3
"""Dummy OpenAI-compatible endpoint that LOGS what a client actually sends.

Use it to replace the real endpoint under an agent client (kilo, aider, any
OpenAI-compatible tool) and read the request parameters it really sends --
`max_tokens`, message count, model id, stream flag -- instead of inferring them
from the client's docs or from the server's error message.

    python3 echo-openai-server.py [port] [logfile]
    # default port 8799, default log ./echo-openai-requests.jsonl

Then point a THROWAWAY copy of the client's config at it, e.g. for kilo:

    KILO_CONFIG=/path/to/throwaway-kilo.jsonc kilo run --pure -m <provider>/<model-key> 'say ok'
    cat echo-openai-requests.jsonl

Companion: `scripts/logging-pass-through-proxy.py` sends the same capture to the REAL endpoint
and streams the reply back. Use this echo server when the real endpoint is expensive (GPU, quota)
or when the field's legality on the far side is not the question.

Notes that cost time when forgotten:
- **The log carries the client's FULL key list** (`keys`) plus the reasoning/behavioural family by
  name, and dumps the entire body when `BODY=1` is set. Keep it that way: a fixed field list only
  ever answers questions you already thought to ask, and will confirm a knob that never arrives.
  Real case: an effort picker whose value appeared in NO request looked like it worked until the
  key list showed the field was absent at every level.
- `kilo run` needs the model KEY (`-m local/<entry-key>`); a display-name alias from
  `agent.*`/`"model"` fails with 'Model not found' in the non-interactive path.
- A copied kilo.jsonc is JSONC: its `$schema` line contains `//`, so a naive
  comment-strip regex corrupts the URL, and it may carry trailing commas. Strip the
  `$schema` line and trailing commas before json.loads, or hand-write a minimal config.
- Isolate the throwaway config from the user's setup with `XDG_CONFIG_HOME` + `KILO_CONFIG_DIR`
  (and a scratch `XDG_DATA_HOME`), plus `--pure` to skip their external plugins.
- The reply below is deliberately minimal; a client that needs tool calls or several
  turns may error after the first exchange. One logged request is enough for sizing.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
LOG = sys.argv[2] if len(sys.argv) > 2 else os.path.abspath("echo-openai-requests.jsonl")
DUMP_BODY = os.environ.get("BODY") not in (None, "", "0", "false")

# Knobs that change model behaviour or billing shape, logged by name so a request that has them
# can be told apart from one that does not. Absent means absent -- do not read a default in.
TRACKED_KEYS = (
    "reasoning_effort", "reasoning", "thinking", "enable_thinking", "preserve_thinking",
    "max_thinking_tokens", "thinking_budget_tokens", "thinking_budget",
    "reasoning_budget_tokens", "chat_template_kwargs", "temperature", "top_p",
    "response_format", "tool_choice",
)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            body = {"_raw": raw[:500].decode("utf-8", "replace")}
        rec = {
            "t": time.time(),
            "path": self.path,
            "model": body.get("model"),
            "max_tokens": body.get("max_tokens"),
            "max_completion_tokens": body.get("max_completion_tokens"),
            "stream": body.get("stream"),
            "n_messages": len(body.get("messages") or []),
            "n_tools": len(body.get("tools") or []),
            "keys": sorted(body.keys()),
            "tracked": {k: body.get(k) for k in TRACKED_KEYS if k in body},
        }
        if DUMP_BODY:
            rec["body"] = body
        with open(LOG, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def frame(delta, finish=None):
                return "data: " + json.dumps({
                    "id": "chatcmpl-probe", "object": "chat.completion.chunk",
                    "created": int(time.time()), "model": body.get("model") or "probe",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                    "usage": None}) + "\n\n"

            self.wfile.write(frame({"role": "assistant"}).encode())
            self.wfile.write(frame({"content": "ok"}).encode())
            self.wfile.write(frame({}, "stop").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        payload = json.dumps({
            "id": "chatcmpl-probe", "object": "chat.completion",
            "created": int(time.time()), "model": body.get("model") or "probe",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        """Answer /v1/models the way a vLLM/llama.cpp-style server does, so a client that
        probes for limits sees a plausible window."""
        payload = json.dumps({"object": "list", "data": [{
            "id": os.environ.get("ECHO_MODEL_ID", "probe-model"),
            "object": "model", "owned_by": "probe",
            "max_model_len": int(os.environ.get("ECHO_CONTEXT", "131072")),
            "context_length": int(os.environ.get("ECHO_CONTEXT", "131072")),
            "max_tokens_cap": int(os.environ.get("ECHO_MAX_TOKENS_CAP", "65536")),
            "max_tokens_default": int(os.environ.get("ECHO_MAX_TOKENS_DEFAULT", "8192")),
        }]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    print(f"echo-openai-server on http://127.0.0.1:{PORT}/v1 -> logging to {LOG}"
          f"{' (full bodies)' if DUMP_BODY else ''}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
