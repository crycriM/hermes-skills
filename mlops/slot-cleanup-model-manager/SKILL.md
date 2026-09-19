---
name: slot-cleanup-model-manager
description: Design and implementation of automatic slot KV cache cleanup in model_manager.py. Uses backend slot querying, staleness detection via shadow count, and unload/reload cycles to reset accumulated KV cache per model.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [model-manager, slot-cleanup, kv-cache, llama-cpp]
---

# Slot KV Cache Cleanup in Model Manager

## Problem

llama.cpp slots accumulate KV cache that never gets freed. With `n_discard=0`
and no slot-level cache eviction, slots from completed sessions hold stale
KV cache permanently. The model_manager's `/api/models` tracks `ctx_used`
per-request (SSE timings), but the actual slot-level cache is invisible.

After long agentic runs, slots can hold 100K+ tokens of stale KV cache
consuming VRAM.

## Solution

Three components added to `model_manager.py`:

### 1. Backend slot querying

`_get_model_backend_ports()` — queries router `/v1/models`, extracts the
`--port` arg for each loaded model's backend process.

`get_backend_slots(model_name, port)` — queries the backend directly
(not through router) at `http://localhost:{port}/slots` to get raw
slot state including `n_prompt_tokens`, `id_task`, `is_processing`.

### 2. Staleness detection

`check_slot_staleness(model_name, slots)` — tracks per-model slot health
via `SLOT_HEALTH` dict. A model is stale when:

- All slots are idle (`is_processing=false`)
- Slot task IDs haven't changed for 6 consecutive poll cycles (~60s)
- At least one slot has >256 tokens of KV cache
- Cleanup cooldown (300s) has passed

### 3. Cleanup action

`cleanup_stale_slots()` — called from the poller loop each cycle.
Performs `router_post("/models/unload", ...)` + `router_post("/models/load", ...)`
to reset all slots. Clears `SLOT_CONTEXT_USAGE` tracking.

### 4. Manual endpoint

`POST /api/slot-cleanup` with optional `{"model": "name"}` body.
Returns per-model results with action taken and reason.

## Key thresholds

| Parameter | Value | Description |
|-----------|-------|-------------|
| `SLOT_STALE_SECONDS` | 60 | Idle time before considering stale |
| `SLOT_CLEANUP_SHADOW_COUNT` | 6 | Consecutive polls with unchanged task IDs |
| `SLOT_CLEANUP_COOLDOWN` | 300 | Minimum seconds between cleanups per model |
| min tokens to trigger | 256 | Skip cleanup for trivial caches |

## Why not n_discard/n_keep?

`n_discard` would evict KV cache mid-session for agentic use (100-tool-call
runs need accumulated context). Unload/reload between sessions preserves
per-session cache continuity while clearing between sessions.

## Why not cache_prompt=false / slot_id?

These parameters are consumed by the llama.cpp router's load balancer
and don't propagate to individual backend servers in multi-model mode.
Direct backend querying bypasses the router.
