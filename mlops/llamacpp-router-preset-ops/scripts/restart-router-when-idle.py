#!/usr/bin/env python3
"""Idle-gated llama.cpp router restart - put a router-preset.ini edit live without cutting inference.

Why: the router caches router-preset.ini at boot, so a preset edit is inert until
`systemctl --user restart m5-router`. That restart kills whoever is mid-generation and re-preloads
every `load-on-startup = 1` section (tens of GB), so it must (a) wait for a quiet window and
(b) clean the preloads up afterwards.

Usage (stdlib only, run from anywhere):
    python3 scripts/restart-router-when-idle.py <target-section> --unload <id> --unload <id>

Run it as a background process with completion notification (terminal background=true, notify=true)
and read the log it writes under ~/llm-server/logs/ - especially the CHECK lines, which are the proof
the edited preset reached the child process.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

ROUTER = "http://localhost:8080"
PROXY = "http://localhost:8079"
LOG_DIR = os.path.expanduser("~/llm-server/logs")


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="preset section to reload and verify once the router is back")
    ap.add_argument("--unload", action="append", default=[],
                    help="model id to unload after the restart (repeatable) - use for the big "
                         "load-on-startup sections you do not need resident")
    ap.add_argument("--idle-polls", type=int, default=3, help="consecutive idle polls required (default 3)")
    ap.add_argument("--poll", type=int, default=20, help="seconds between polls (default 20)")
    ap.add_argument("--max-wait", type=int, default=6 * 3600, help="give up after N seconds (default 21600)")
    ap.add_argument("--skip-load", action="store_true", help="do not reload the target at the end")
    return ap.parse_args()


def main():
    args = parse_args()
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "restart-when-idle-%s.log" % datetime.now().strftime("%Y%m%d-%H%M%S"))

    def log(msg):
        line = "%s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        with open(log_path, "a") as fh:
            fh.write(line + "\n")

    def req(url, payload=None, timeout=15):
        data = json.dumps(payload).encode() if payload is not None else None
        r = urllib.request.Request(url, data=data,
                                   headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            body = resp.read().decode()
        return json.loads(body) if body.strip().startswith(("{", "[")) else body

    def ok(url):
        try:
            req(url, timeout=5)
            return True
        except Exception:
            return False

    def loaded():
        try:
            data = req(ROUTER + "/v1/models", timeout=8)
        except Exception as exc:
            return None, str(exc)
        ids = []
        for m in data.get("data", []):
            st = m.get("status") or {}
            if (st.get("value") if isinstance(st, dict) else st) == "loaded":
                ids.append(m["id"])
        return ids, None

    def busy(ids):
        """True if any loaded model has a processing slot. A failed/odd probe counts as busy."""
        for mid in ids:
            try:
                slots = req("%s/slots?model=%s" % (ROUTER, mid), timeout=8)
            except Exception as exc:
                log("  slots probe failed for %s (%s) - treating as busy" % (mid, exc))
                return True
            if not isinstance(slots, list):
                log("  slots probe returned non-list for %s - treating as busy" % mid)
                return True
            if any(s.get("is_processing") for s in slots):
                return True
        return False

    def wait_until(pred, what, timeout_s, every=5):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if pred():
                return True
            time.sleep(every)
        log("  TIMEOUT waiting for %s (%ss)" % (what, timeout_s))
        return False

    log("watcher start - target %s, idle window %d x %ds, max wait %.1fh"
        % (args.target, args.idle_polls, args.poll, args.max_wait / 3600))

    idle = 0
    started = time.time()
    while time.time() - started < args.max_wait:
        ids, err = loaded()
        if err:
            log("router probe error (%s) - retry in %ds" % (err, args.poll))
            idle = 0
            time.sleep(args.poll)
            continue
        if busy(ids):
            idle = 0
            log("busy: loaded=%s - waiting" % ids)
        else:
            idle += 1
            log("idle %d/%d (loaded=%s)" % (idle, args.idle_polls, ids))
            if idle >= args.idle_polls:
                break
        time.sleep(args.poll)
    else:
        log("gave up: router never stayed idle within %.1fh - NO restart performed"
            % (args.max_wait / 3600))
        return 1

    # The unit's ExecStop is `pkill -TERM -f llama-server` inside the distrobox, which also kills
    # hand-started standalone servers (they do not come back on their own) - keep their cmdlines.
    snap = os.path.join(LOG_DIR, "pre-restart-cmdlines-%s.txt" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    with open(snap, "w") as fh:
        fh.write(subprocess.run(["ps", "-eo", "pid,etime,cmd"], capture_output=True, text=True).stdout)
    log("cmdline snapshot -> %s" % snap)

    log("restarting m5-router")
    subprocess.run(["systemctl", "--user", "restart", "m5-router"], check=False)
    if not wait_until(lambda: ok(ROUTER + "/health"), "router /health", 420):
        log("ABORT: router did not come up")
        return 1
    log("router up")

    log("restarting model-manager")
    subprocess.run(["systemctl", "--user", "restart", "model-manager"], check=False)
    wait_until(lambda: ok(PROXY + "/health"), "proxy /health", 120)
    ids, _ = loaded()
    log("post-restart loaded: %s" % ids)

    for mid in args.unload:
        try:
            log("unload %s -> %s" % (mid, req(PROXY + "/api/unload", {"model": mid}, timeout=60)))
        except Exception as exc:
            log("unload %s failed: %s" % (mid, exc))

    if not args.skip_load:
        try:
            log("load %s -> %s" % (args.target, req(PROXY + "/api/load", {"model": args.target}, timeout=300)))
        except Exception as exc:
            log("load %s failed: %s" % (args.target, exc))
        wait_until(lambda: args.target in (loaded()[0] or []), "%s loaded" % args.target, 300)

    # Live argv is the only proof the edited preset reached the child process.
    try:
        for m in req(ROUTER + "/v1/models").get("data", []):
            if m["id"] == args.target:
                a = " ".join((m.get("status") or {}).get("args") or [])
                log("live argv: %s" % a)
                log("CHECK enable_thinking=false kwarg present: %s" % ('{"enable_thinking":false}' in a.replace(" ", "")))
                log("CHECK reasoning-budget absent: %s" % ("--reasoning-budget" not in a))
                log("CHECK reasoning-format deepseek present: %s" % ("--reasoning-format deepseek" in a))
    except Exception as exc:
        log("argv inspection failed: %s" % exc)

    log(subprocess.run(["free", "-g"], capture_output=True, text=True).stdout.strip())
    log("done - behavioural verification (a real chat request) is still a separate step")
    log("log: %s" % log_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
