#!/usr/bin/env python3
"""Stored ComfyUI workflow -> API-format prompt, for a validation submit.

Why this exists
---------------
A file under `user/default/workflows/` is in *stored* shape: `nodes` + `links` arrays,
key `type`, and widget values flattened into `widgets_values`. `POST /prompt` wants the
id-keyed dict with `class_type` and real input values. Converting by hand goes wrong in
two silent ways: wired inputs need the `links` array walked, and widget values must be
mapped against the node's *input order* (which differs per node and per pack).

The widget order is read from the live server's `/object_info`, so third-party nodes and
optional widgets resolve too, instead of hard-coding a per-node table.

Usage
-----
  gui_workflow_to_api.py <workflow.json> [options]

  --server HOST:PORT     /object_info source (default 127.0.0.1:8188)
  --object-info FILE     use a saved /object_info dump instead of the server
  --set NODE.INPUT=VAL   override one input (repeatable); wins over everything
  --drop-class CLASS     drop these node classes (repeatable)
  --keep-dangling        do not prune nodes that reach no output node
  --out FILE             write the API dict to FILE (default: stdout)
  --summary              print per-node warnings only, not the JSON

Every node whose widgets_values cannot be reconciled with its schema prints a WARNING;
fix those with --set rather than trusting a guessed mapping.

Feed the result to `scripts/run_api_graph.py`, which submits it, tags the render and
prints the log lines that appeared during the run.
"""

import argparse
import json
import sys
import urllib.request

# Types that are always a socket, never a widget row in the GUI.
SOCKET_ONLY = {
    "MODEL", "CLIP", "VAE", "IMAGE", "LATENT", "CONDITIONING", "MASK", "SIGMAS",
    "GUIDER", "SAMPLER", "NOISE", "CONTROL_NET", "STYLE_MODEL", "CLIP_VISION",
    "AUDIO", "WAVEFORM", "POSE_KEYPOINT", "UPSCALE_MODEL", "MODEL_PATCH", "HIDDEN",
    "CLIP_VISION_OUTPUT", "TRANSFORMER", "LORA_MODEL", "HOOKS", "ANY",
}

# Widgets that serialise an extra value right after themselves (the
# *control_after_generate* dropdown), which shifts every later value by one.
SEED_WIDGETS = {"seed", "noise_seed"}


def load_object_info(args):
    if args.object_info:
        return json.load(open(args.object_info))
    url = "http://%s/object_info" % args.server
    return json.load(urllib.request.urlopen(url, timeout=30))


def widget_names(schema):
    """Widget inputs of a node schema, in the order widgets_values is serialised."""
    names = []
    for sec in ("required", "optional"):
        for nm, spec in (schema.get("input", {}).get(sec) or {}).items():
            t = spec[0] if isinstance(spec, list) and spec else None
            if isinstance(t, list):            # COMBO enum -> widget
                names.append(nm)
                continue
            if not isinstance(t, str):
                continue
            if t in SOCKET_ONLY or t.startswith("COMFY_AUTOGROW"):
                continue
            names.append(nm)
    return names


def map_widgets(names, vals):
    """Positional widgets_values -> {name: value}; None when it does not reconcile."""
    if len(vals) == len(names):
        return dict(zip(names, vals))
    if len(vals) < len(names):
        return None                        # optional widget never serialised
    extra, out, vi = len(vals) - len(names), {}, 0
    for nm in names:
        if vi >= len(vals):
            return None
        out[nm] = vals[vi]
        vi += 1
        if extra and nm in SEED_WIDGETS and vi < len(vals):
            vi += 1                        # skip the control_after_generate value
            extra -= 1
    return out if extra == 0 else None


def build(wf, oi, overrides, drop_classes, prune=True, warn=lambda m: print(m, file=sys.stderr)):
    linkmap = {l[0]: l for l in wf.get("links", [])}
    nodes = {n["id"]: n for n in wf["nodes"]}

    # Keep real sinks (schema says output_node) or anything feeding something else,
    # then walk backwards so a parked, unwired node (an idle rewriter on the canvas)
    # does not end up in the prompt referring to ids that are not there.
    keep = set()
    for n in wf["nodes"]:
        if n["type"] in drop_classes:
            continue
        wired = any((o.get("links") for o in (n.get("outputs") or [])))
        if wired or oi.get(n["type"], {}).get("output_node"):
            keep.add(n["id"])
    if prune:
        frontier = set(keep)
        while frontier:
            nid = frontier.pop()
            for i in nodes[nid].get("inputs") or []:
                lid = i.get("link")
                if lid in linkmap:
                    src = linkmap[lid][1]
                    if src not in keep:
                        keep.add(src)
                        frontier.add(src)

    api = {}
    for n in wf["nodes"]:
        nid, t = n["id"], n["type"]
        if nid not in keep:
            continue
        schema = oi.get(t)
        if schema is None:
            warn("WARNING: node %s (%s) is not in object_info - pack not loaded? skipped" % (nid, t))
            continue
        inp = {}
        for i in n.get("inputs") or []:
            if i.get("link") is None:
                continue
            l = linkmap.get(i["link"])
            if l is None:
                warn("WARNING: node %s input %s references missing link %s" % (nid, i["name"], i["link"]))
                continue
            inp[i["name"]] = [str(l[1]), l[2]]          # [upstream node id, output slot]

        names = widget_names(schema)
        named = n.get("widgets_values_named") or {}
        if names and all(nm in named for nm in names):
            inp.update({nm: named[nm] for nm in names})
        else:
            m = map_widgets(names, n.get("widgets_values") or [])
            if m is None:
                warn("WARNING: node %s (%s) widgets_values %r do not reconcile with %r - set them with --set"
                     % (nid, t, n.get("widgets_values"), names))
            else:
                inp.update(m)
        api[str(nid)] = {"class_type": t, "inputs": inp}

    for key, val in overrides.items():
        nid, _, field = key.partition(".")
        if nid in api:
            api[nid]["inputs"][field] = val
        else:
            warn("WARNING: --set %s targets node %s, which is not in the converted graph" % (key, nid))
    return api


def parse_value(raw):
    try:
        return json.loads(raw)
    except Exception:
        return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--server", default="127.0.0.1:8188")
    ap.add_argument("--object-info")
    ap.add_argument("--set", action="append", default=[], dest="sets")
    ap.add_argument("--drop-class", action="append", default=[], dest="drops")
    ap.add_argument("--keep-dangling", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    wf = json.load(open(args.workflow))
    oi = load_object_info(args)
    overrides = {}
    for s in args.sets:
        key, _, val = s.partition("=")
        overrides[key] = parse_value(val)

    api = build(wf, oi, overrides, set(args.drops), prune=not args.keep_dangling)
    print("converted %d of %d nodes" % (len(api), len(wf["nodes"])), file=sys.stderr)
    for nid in sorted(api, key=int):
        print("  %s %s" % (nid, api[nid]["class_type"]), file=sys.stderr)
    body = json.dumps(api)
    if args.out:
        open(args.out, "w").write(body)
        print("written %s" % args.out, file=sys.stderr)
    elif not args.summary:
        print(body)


if __name__ == "__main__":
    main()
