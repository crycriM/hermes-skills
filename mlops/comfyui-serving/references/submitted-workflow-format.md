# Submitting a stored workflow file to the API

A saved workflow (`.json` under `user/default/workflows/`) is **not** directly submittable to `POST /prompt`. The two shapes differ, and the difference is the common cause of a silent 500.

## The two formats

**Stored file** — top-level `nodes` and `links` arrays. Each node uses the key `type`, not `class_type`:

```json
{ "nodes": [ { "id": 1, "type": "UNETLoader", "inputs": {...} } ], "links": [[...]] }
```

**API prompt** — a dict keyed by node id, each value carrying `class_type`:

```json
{ "prompt": { "1": { "class_type": "UNETLoader", "inputs": {...} }, ... }, "client_id": "<uuid>" }
```

The `links` array is ignored by the API — links are carried inside each node's `inputs` as `[link_id, node_id, slot]`.

## The conversion

**Canonical implementation: `scripts/gui_workflow_to_api.py`** — it reads each node's widget order from the live server's `/object_info` (so third-party and optional widgets resolve too), prunes nodes that reach no output node, and takes `--set node.input=value` overrides for anything the schema cannot resolve. Use it for real files; the excerpt below is the core of its mapping loop.

The naive rename is **not enough on its own**: in a stored workflow `inputs` is a *list of input descriptors* (`{name, type, widget?, link}`) whose values live in the parallel `widgets_values` array, not a value map. Converting a real, linked graph correctly means walking `links` for the wired inputs and `widgets_values` for the rest:

```python
def gui_to_api(wf, widget_names, linkmap=None):
    linkmap = linkmap or {l[0]: l for l in wf["links"]}      # id, from_node, from_slot, to_node, to_slot, type
    api = {}
    for n in wf["nodes"]:
        t = n["type"]
        if t not in widget_names:                            # a dangling node (no consumer) is pruned anyway
            continue
        inp = {}
        for i in n.get("inputs") or []:
            if i.get("link") is not None:                    # wired input
                l = linkmap[i["link"]]
                inp[i["name"]] = [str(l[1]), l[2]]           # [upstream_node_id, output_slot]
        named, vals = n.get("widgets_values_named") or {}, n.get("widgets_values") or []
        for idx, nm in enumerate(widget_names[t]):           # order = the node's widget order
            if nm in inp:
                continue
            if nm in named:
                inp[nm] = named[nm]                          # frontends that write the named form
            else:
                pos = idx + (1 if nm in {"seed", "noise_seed"} else 0)   # only the seed row carries a control value
                if pos < len(vals):
                    inp[nm] = vals[pos]
        api[str(n["id"])] = {"class_type": t, "inputs": inp}
    return api
```

Two things that bite:

- **`control_after_generate` shifts the whole value list.** A GUI KSampler serialises `[seed, "fixed", steps, cfg, sampler, scheduler, denoise]` — seven values for six widgets. Read widgets by *name* from `widgets_values_named` when the frontend wrote it, and otherwise treat only the seed-like widget as carrying an extra control value. Mapping positionally without that offset silently feeds the control string in as `steps`.
- **Check the render graph is closed before submitting.** Nodes that are not wired to an output (an idle `PET2IPromptRewriter` parked on the canvas is the usual one here) must be dropped, or the prompt refers to a node id that does not exist.

Verified: a real saved workflow (reference-image path, `QwenImage21Cache`, accelerator node) converted this way submitted and executed, writing an image — there is no server-side validator for stored form, so an executed converted run is the only proof the wiring is right.

## The 500 that is not a real error

If you POST the raw stored structure (or a bare list) as the `prompt` value, ComfyUI passes validation and then crashes in `server.py` `post_prompt`:

```
self.node_replace_manager.apply_replacements(prompt)
→ AttributeError: 'list' object has no attribute 'items'
```

`apply_replacements` calls `prompt.items()`, so `prompt` must be a dict. Symptom: HTTP 500 "Server got itself in trouble" with **no 400 and no validation message** — distinct from every other prompt error, which returns a structured 400. When you see this 500, the first thing to check is that the submitted `prompt` is the converted id-keyed dict, not the stored `nodes`/`links` structure.

## Preferred path

For image generation with the Qwen-Image-2.1 stack, submit through the client instead of hand-building a graph: `cd /mnt/data2/ComfyUI && .venv/bin/python run_qwen21_t2i.py "<brief>" --enhance ...`. The client owns the API-format conversion. Reach for the manual conversion only when you must submit a specific stored workflow file verbatim.
