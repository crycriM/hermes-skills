#!/usr/bin/env python3
"""Submit an API-format ComfyUI graph and report what really ran. Stdlib only.

Exit 0 only when the graph finishes with status_str == "success". Prints the
output node results, a sha256 for every image written, and the log lines that
appeared DURING the run - so the class/`Requested to load` assertion costs no
extra step.

    run_api_graph.py graph.json \
        --set 4.clip_name=qwen3vl_8b_w4a8_heretic.safetensors \
        --prefix smoke --grep Ciru

The model filenames in a vendored api_example rarely match this box's store;
`--set <node>.<input>=<value>` is the supported way to repoint them instead of
editing the example in place. Values are parsed as JSON when possible, else
kept as strings.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid


def post(server, path, body, timeout=30):
    req = urllib.request.Request(server + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def log_offset(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def log_delta(path, start, patterns):
    try:
        with open(path, "r", errors="replace") as fh:
            fh.seek(start)
            lines = fh.read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        if any(p.lower() in line.lower() for p in patterns):
            out.append(line.rstrip())
    return out


def apply_set(graph, spec):
    """`4.clip_name=value` or `4.inputs.clip_name=value`."""
    node, _, rest = spec.partition(".")
    if not rest:
        raise SystemExit(f"--set needs <node_id>.<input>=<value>, got {spec!r}")
    key, _, value = rest.partition("=")
    key = key.split("inputs.", 1)[-1]
    if node not in graph:
        raise SystemExit(f"--set: no node {node!r} in the graph")
    try:
        value = json.loads(value)
    except json.JSONDecodeError:
        pass
    graph[node].setdefault("inputs", {})[key] = value
    return node, key, value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph", help="API-format graph JSON ({node: {class_type, inputs}})")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--set", action="append", default=[], metavar="NODE.INPUT=VALUE")
    ap.add_argument("--prefix", help="overwrite every SaveImage filename_prefix")
    ap.add_argument("--output", default="/mnt/data2/ComfyUI/output")
    ap.add_argument("--log", default=os.path.expanduser("~/.local/share/comfyui/comfyui.log"))
    ap.add_argument("--grep", action="append", default=[], metavar="PATTERN")
    ap.add_argument("--timeout", type=float, default=2400)
    ap.add_argument("--poll", type=float, default=5)
    args = ap.parse_args()

    graph = json.load(open(args.graph))
    if not all(isinstance(v, dict) and "class_type" in v for v in graph.values()):
        raise SystemExit("not an API-format graph (every top-level value needs class_type); "
                         "see references/submitted-workflow-format.md for the conversion")

    for spec in args.set:
        node, key, value = apply_set(graph, spec)
        print(f"override: node {node} . {key} = {value!r}")
    if args.prefix:
        for nid, node in graph.items():
            if node["class_type"] in ("SaveImage", "PreviewImage"):
                node["inputs"]["filename_prefix"] = args.prefix
        print(f"filename_prefix -> {args.prefix!r} (test renders stay distinguishable)")

    patterns = ["Requested to load", "Prompt executed", "IMPORT FAILED", "error"] + args.grep
    start = log_offset(args.log)

    res = post(args.server, "/prompt", {"prompt": graph, "client_id": str(uuid.uuid4())})
    pid = res["prompt_id"]
    print(f"submitted {pid} (queue number {res.get('number')})", flush=True)

    t0 = time.time()
    while time.time() - t0 < args.timeout:
        try:
            hist = json.load(urllib.request.urlopen(f"{args.server}/history/{pid}", timeout=15))
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"poll error: {exc}", flush=True)
            time.sleep(args.poll)
            continue
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            ok = status.get("status_str") == "success"
            print(f"elapsed {time.time() - t0:.1f}s status={status.get('status_str')} "
                  f"completed={status.get('completed')}", flush=True)
            for msg in status.get("messages", []):
                print("  msg:", json.dumps(msg)[:400], flush=True)
            for nid, out in (entry.get("outputs") or {}).items():
                print(f"  output node {nid}: {json.dumps(out)[:600]}", flush=True)
                for img in out.get("images", []) or []:
                    path = os.path.join(args.output, img.get("subfolder", ""), img["filename"])
                    if os.path.exists(path):
                        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
                        print(f"  IMAGE {path} {os.path.getsize(path)}B sha256={digest}", flush=True)
                    else:
                        print(f"  IMAGE missing on disk: {path}", flush=True)
            lines = log_delta(args.log, start, patterns)
            print(f"--- log during run ({len(lines)} matching lines) ---")
            for line in lines[-25:]:
                print("   ", line)
            return 0 if ok else 2
        time.sleep(args.poll)
    print(f"TIMEOUT after {args.timeout}s; the job may still be queued", flush=True)
    return 3


if __name__ == "__main__":
    sys.exit(main())
