---
title: Llama Slot Pinning
name: llama-slot-pinning
description: Setup for llama-server with slot pinning for multi-model deployments
tags: [llama, slot-pinning, kv-cache, multi-model]
---

# Llama Slot Pinning Skill

## Overview
This skill provides a reproducible setup for configuring the llama-server with slot pinning to persist prompt KV caches across restarts. It is intended for multi‑model deployments where each model has its own dedicated slot set.

## Prerequisites
- llama-server binary built with KV‑cache support.
- Sufficient disk space for `--slot-save-path`.
- Model files in GGUF format.

## Step‑by‑step Setup
1. **Define parallel slots** – choose a number of slots that matches the expected concurrency.
   ```bash
   ./llama-server -m modelA.gguf \
     --parallel 4 \
     --ctx-size 8192 \
     --slot-save-path /path/to/cache_data
   ```
   - `--parallel N` creates N independent slots.
   - `--ctx-size` must be large enough for the pinned prompt plus new tokens.
   - `--slot-save-path` enables the slot‑save/restore API.

2. **Start the server** – run the command in the background or as a service. Verify it is listening:
   ```bash
   curl http://localhost:8080/slots
   ```

3. **Save a slot state** – after a request is processed, call:
   ```bash
   curl -X POST http://localhost:8080/slots/0?action=save
   ```
   - Use the slot ID returned by the initial request (or list slots to find it).
   - The cache is written to the directory from `--slot-save-path`.

4. **Restore a slot** – to re‑use a pinned prompt:
   ```bash
   curl -X POST http://localhost:8080/slots/0?action=restore
   ```

5. **Erase a slot** – clear an unwanted cache:
   ```bash
   curl -X POST http://localhost:8080/slots/0?action=erase
   ```

## Multi‑Model Considerations
- **Separate cache directories** – give each model its own `--slot-save-path` to avoid cross‑contamination.
- **Slot allocation** – keep the same `--parallel` count per model; you can run multiple server instances on different ports and load‑balance them.
- **Context size per model** – adjust `--ctx-size` per model based on its prompt length.

## Pitfalls & Tips
- **Disk I/O bottleneck** – saving large KV caches frequently can saturate SSD. Batch saves (e.g., after N requests) and monitor I/O.
- **Slot starvation** – with many concurrent requests, a slot may be evicted. Use `--parallel` conservatively and monitor `/slots` metrics.
- **Restart safety** – before stopping the server, save all active slots; otherwise the cache is lost.
- **Version compatibility** – KV‑cache format changed in llama.cpp v0.2.0. Ensure the server and client versions match.

## Verification
1. Send a request, note the slot ID.
2. Save the slot, stop the server, restart with the same `--slot-save-path`.
3. Restore the slot and confirm the prompt resumes without pre‑fill (token generation starts immediately).

## Example Script (optional)
A small Bash wrapper can automate the save/restore cycle:
```bash
#!/usr/bin/env bash
MODEL=$1
PORT=$2
SLOT_ID=$3
ACTION=$4  # save|restore|erase

./llama-server -m $MODEL --port $PORT \
  --parallel 4 --ctx-size 8192 \
  --slot-save-path ./cache_$MODEL &
SERVER_PID=$!

sleep 2  # give server time to start
if [ "$ACTION" = "save" ]; then
  curl -X POST http://localhost:$PORT/slots/$SLOT_ID?action=save
elif [ "$ACTION" = "restore" ]; then
  curl -X POST http://localhost:$PORT/slots/$SLOT_ID?action=restore
elif [ "$ACTION" = "erase" ]; then
  curl -X POST http://localhost:$PORT/slots/$SLOT_ID?action=erase
fi

kill $SERVER_PID
```

## Usage
- Save as `~/skills/llama-slot-pinning/llama-slot-pinning.sh` and make executable.
- Call from your orchestration layer when you need to pin a prompt for a specific model.

---
*End of skill.*