---
name: halogen-flash-lane
description: Use when serving/benchmarking halogen-flash on Strix Halo.
---

# halogen-flash lane (Qwen3.8-Flash-Next on Strix Halo / gfx1151)

halogen-flash-server is a closed-source engine built for one model on one GPU
(peonist-ai/halogen-flash-server). It serves the model's own `.hgn` checkpoint
(5.53 bpw, 68.0 GiB resident) OR a llama.cpp GGUF of the same model, with MTP
speculative decoding that is byte-identical to serial greedy.

On this box it is **~2.4x the archived llama.cpp recipe's decode rate** at 64k
(49.2 tok/s MTP against ~21), and roughly 4x on prefill.

## The lane

| | |
|---|---|
| launcher | `~/llm-server/start-halogen-flash.sh` (container `halogen-flash`) |
| API | `http://0.0.0.0:8741/v1` (OpenAI-compatible, incl. `/v1/responses`) |
| engine port | 8730, loopback inside the container, deliberately unpublished (no auth) |
| weights | `~/models/qwen3.8-flash/qwen38-flash-next-w4b.hgn` + `.overlay.hgn` (auto-loaded) + `tokenizer/` |
| image | `ghcr.io/peonist-ai/halogen-flash-server:0.14.2` |
| bench kit | `~/llm-server/bench-halogen/` (harness, campaign scripts, raw JSONL, REPORT-*.md) |
| stop | `podman stop -t 60 halogen-flash` — **never SIGKILL** |
| GUI control | model-manager header buttons **Qwen3.8-Flash Load/Unload** and **ComfyUI Start/Stop**, backed by `GET /api/lanes`, `POST /api/lane/flash`, `POST /api/comfyui` on :8079 (proxied through the GUI on :8081). Flash start is gated on routing OFF + ComfyUI stopped, in the UI and again server-side (409 naming each blocker); stop is never gated. The lane is launched inside the `halogen-flash-lane.scope` transient systemd scope, so restarting model-manager does not kill it |

Config: since 2026-09-29 the lane is a **128k** lane — `HALOGEN_CTX=131072`,
`HALOGEN_KV_POOL_POSITIONS=262144` (two resident 128k conversations),
`HALOGEN_KV_SLOTS=2`, `HALOGEN_MAX_TOK=32768`, vision tower unset. Holds
**96.3 GiB** (68.0 weights + 7.2 KV + 21.1 working), leaving 12.1 GiB for
everything else. The measured **64k baseline** (92.7 GiB: CTX 65536 / pool
131072) is one command away — every sizing knob is now an env override:
`CTX=65536 POOL=131072 ./start-halogen-flash.sh`.

**Why 128k, and the arithmetic that matters:** a request reserves
`prompt + max_tokens`, so a lane whose CTX is smaller than that sum is a hard
400, never a truncation. At CTX 65536 the research bench died mid-run at ~57k
prompt tokens (51,280 prompt + 8192 max_tokens); at CTX 131072 the runner's
110k forced-synthesis threshold plus 8192 max_tokens fits with room spare.
Size the lane from the engine's own budget line, never from `free`: MemTotal
122.7 − 68 weights − 20 reserve leaves ~34.7 GiB for pool + arena + slots
(7.2 + 21.1 + 1.4 here).

**Restarting it with different settings:** patch the launcher's env defaults,
then `POST /api/lane/flash {"action":"stop"}` followed by
`{"action":"start","variant":"text"}` — **stop first**, because model-manager
refuses `start` on an already-running lane ("the lane is already running in
text mode") rather than restarting it. The stop path is never gated; start
requires routing OFF + ComfyUI stopped. A reload with warm page cache is fast:
68 GiB of weights locked in 5.3 s, engine listening in 8 s, readiness from
`/health` in ~15 s (a genuinely cold load is the ~90 s figure).

### Startup timing: the KV-pool reservation is the slow, scary step

A vision-mode start measured 2026-09-30 (started right after the text container
was stopped, weights warm in page cache): weights pinned in 13.2 s, **KV pool
reserved at 102.9 s** with 434 compaction stalls (141 failed), engine listening
at 106 s. The engine's own warning lines at 34 s / 64 s ("still reserving the
KV pool after N s ... other large processes on this host make it slower") are
normal host-memory pressure, not a hang: the block count was *rising*, which is
the "kernel is compacting for this step, it finishes on its own" case. Treat
<120 s as expected for a lane start; only flat block count + climbing failures
is the stuck case that needs the previous tenant to release memory.

### Vision: present on disk, off in the lane

The vision tower is a SEPARATE checkpoint file and it is already downloaded:
`~/models/qwen3.8-flash/qwen38-flash-next-vision.hgn` (0.84 GiB / 856 MiB,
beside the trunk it patches). The vendor README: "without it the server is
text-only and refuses an image with a message naming the setting that turns it
on ... Put it beside the checkpoint and start the server with
`HALOGEN_VISION_TOWER=1`."

- This lane runs without it on purpose (`HALOGEN_VISION_TOWER` unset in
  `start-halogen-flash.sh`), so `/health` reports
  `vision.disabled_because: the engine was started without a vision tower` and
  refuses images. Text behaviour is byte-identical either way.
- The flag is real in image 0.14.2 — the binary carries `HALOGEN_VISION_TOWER`
  plus `HALOGEN_VISION_ATTN`, `HALOGEN_VISION_FA_HILO`,
  `HALOGEN_VISION_FA_WAVES`, `HALOGEN_VISION_MAX_PIXELS`,
  `HALOGEN_VISION_TIMING`.
- To turn it on: the launcher takes it as a flag — `VISION=1
  ~/llm-server/start-halogen-flash.sh` (it adds `-e HALOGEN_VISION_TOWER=1`).
  `DRY_RUN=1` prints the exact podman argv and starts NOTHING, which is how to
  check the mode wiring without paying a 68 GiB load.
- **Both modes share the ONE container name `halogen-flash` on purpose.** The
  lane holds ~93 GiB, so text and vision must never be resident together;
  starting one replaces the other through the launcher's removal block (a clean
  `podman stop -t 60`, never a SIGKILL — that is what leaves the GTT allocated).
  The mode is readable from the container's own env while the engine is still
  loading, and from `/health` → `vision.enabled` once it is up.
- Model-manager exposes the choice as a second header button
  (`POST /api/lane/flash {"action":"start","variant":"vision"}`); a switch under
  a live request is refused with 409 and the in-flight count.
- Image input once on: a `data:` URL or bare base64 in an image content part;
  `http(s)` URLs are refused; `max_pixels` 3,686,400 (≈1920x1920), size a
  multiple of 32.
- The archived llama.cpp lane used the same tower in GGUF form
  (`mmproj-Qwen3.8-Flash-Next-f16.gguf`, 904 MB) — not usable by this engine.

## Driving it from a client (Kilo, Zed/ACP, opencode)

Reasoning is chosen per request by the client, and every client hides that
behind its own config surface. Full detail, captured wire bodies and the
per-client traps live in **references/clients.md**. The load-bearing rules:

- Levels are `none | minimal | low | medium | high | xhigh`; an omitted field
  means thinking ON at the engine default `xhigh`. `max` is never valid -- the
  engine answers 400.
- A client model entry must carry the REAL model id
  (`local/qwen3.8-flash-next-halogen`); the display name `qwen38-flash` fails to
  resolve in Kilo, Zed and opencode alike, sometimes silently.
- A request reserves `prompt + max_tokens`, so the client's output reservation
  and its idea of the context window both matter: an unknown `limit.context`
  disables auto-compaction, and the session then 400s instead of compacting.
- `model-manager` does NOT proxy this lane's chat completions. Point clients at
  `:8741` directly and set the reasoning field yourself.

### Auditing what effort a past request used

The engine log is **not** enough: `serve_api:` lines only carry `think on` / `think off`, never the level.
The level lives in Kilo's own database — `~/.local/share/kilo/kilo.db`:

- `session.model` is JSON: `{"providerID":"local","id":"qwen3.8-flash-next-halogen","variant":"high"}`
- every assistant `message.data` carries `variant` + `model` + a `tokens` block whose `reasoning` is the CoT
  for that step; `part` rows hold the `reasoning` text and the final `text`
- join the two by timestamp and by arithmetic: the lane's `prompt N (M cached, K new)` equals the step's
  `input + cache.read`, and `generated G` equals `output + reasoning` — an exact check that the row you
  read is the request you think it is

To confirm a level on the wire after the fact, replay it: `ACP_EFFORTS=high KILO_CONFIG=<scratch> python3
acp_drive.py` with `logproxy.py` on 8752 captures `reasoning_effort: high` on `/v1/chat/completions`.

## Rules that matter

1. **It wants the machine.** Stop ComfyUI (`systemctl --user stop comfyui`) and
   any other GPU tenant first: this box crashes when rendering and inference
   run together, and a co-tenant also steals the page cache the 47.7 GiB
   n-gram lookup table is read through.
2. **Believe the engine's `host memory left for everything else` line, not
   `free`.** The kernel counts the locked weights as reclaimable cache, so
   `free`/`MemAvailable` overstate headroom by ~68 GiB.
3. **After any unclean exit, check
   `cat /sys/class/drm/card*/device/mem_info_gtt_used`.** Tens of GiB with
   nothing running means the driver kept a dead engine's memory, and every
   later start hangs at "reserving the KV pool" until the host reboots.
   `podman events --since 4h --stream=false` is the cheap check (without
   `--stream=false` it prints the backlog then **streams forever**, so it looks
   like a hang — a foreground call in an agent session will just time out).
   The launcher's own `podman stop -t 60`
   closes the container with `died 0`, and **`died 1` means the engine left on
   its own** — 2026-09-29 20:00:18 the lane logged `died 1` and ComfyUI entered
   `active` 17 s later (20:00:28), i.e. a swap-out for rendering, not a clean
   stop. Reference baseline right after a fully unloaded router: 14.7 GiB GTT.
4. **A 64k prompt plus its answer must fit `HALOGEN_CTX`** (a request reserves
   prompt + max_tokens). A prompt past it is a hard 400, never a truncation.
5. `HALOGEN_WEIGHTS_LOCK=1` (worth it on a shared host) silently runs unlocked
   here: a rootless container cannot exceed the user's 8 MiB hard memlock
   limit. Fix is `cricri hard memlock unlimited` + soft in
   `/etc/security/limits.conf` and a fresh login.

## Measuring this engine (the traps)

- **Warm up first, always.** The first request after a restart decodes at
  28-32 tok/s instead of 40-60 with *identical draft acceptance*: the lookup
  table is on disk and decode reads 16 rows per token. Any A/B without a
  discarded warmup measures the disk. (`lookup table: ... took N s` in the log
  reports a read of >=2 s.)
- **Give every benchmark prompt a unique prefix** or the prompt cache answers
  it and prefill reads nothing. The image's own `sweep` mode reuses one filler
  prompt, so its longer lengths are prefixes of each other and report
  cache-assisted prefill (we saw 2,841 tok/s at pp65536 that way).
- **llama.cpp (and the EngramHalo fork) answer 503 `{"error":{"message":
  "Loading model"}}` while loading** — `curl >/dev/null` and `urlopen` both
  treat that as success. Gate on the body saying `"status":"ok"`, and retry
  503 in any client.
- Read decode from the response's `timings.predicted_per_second` (excludes
  prefill); prefill is `prompt_per_second`; `draft_n`/`draft_n_accepted` give
  acceptance per round. `cache_n` tells you if a request was a cache hit.
- Report decode as a mean over prompt shapes with the shape set named: 34-63
  tok/s at the same depth, spread is acceptance (code/proof draft better than
  chat/prose), not noise.

## Measured on this box (64k, MTP, greedy, thinking off)

prefill 1,491 tok/s · decode 49.2 tok/s · TTFT 43.9 s; serial decode 35.3.
Follow-up turn at 64k: **0.39 s TTFT** (100% cached) against 44.2 s cold.
Tuning: the shipped defaults win. `HALOGEN_MTP_DEPTH=3` 48.8 (wider spread),
`HALOGEN_PLD=0` 49.4 (identical on single-turn shapes; keep it on for agent
traffic), `HALOGEN_INDEXER_BUDGET=4096` 47.96 decode and **-13% prefill**
(TTFT 50.3 s) — 2048 is right for a speed lane at 64k.

## Head-to-head harness

`~/llm-server/bench-halogen/probe-engramhalo-depth.sh` restates the old recipe
(EngramHalo.cpp build in distrobox `llama-rocm-10.0-engramhalo`, GGUF
AP-Q4_K_XL + MTP Q8_0 head, port 8082), measures it with the same prompts and
depths, and restores the halogen lane on exit (a `trap`, so it also fires on
a failed arm — verify with `curl :8741/health` rather than trusting the log).
`run-h2h-engramhalo.sh` is the older two-phase version.

Measured 2026-09-28, four shapes x 2 reps at 64k on both sides:

| | halogen (.hgn, defaults) | EngramHalo (GGUF) | ratio |
|---|---:|---:|---:|
| prefill tok/s | 1,501 | 307 | 4.89x |
| decode tok/s | 49.53 (36.9-60.7) | 16.74 (12.1-19.8) | 2.96x |
| TTFT at 64k | 43.6 s | 213.4 s | 4.9x |

The GGUF lane is memory-mapped with lazy tensor reads, so it pays the disk
while decoding at depth (25.8 tok/s at 32k -> 16.7 at 64k, floor 12.1) and its
prefill never warms (303-311 tok/s across seven rows). Two caveats to keep
attached to those numbers: it is a K-quant against a 5.53 bpw checkpoint, so
this compares recipes rather than engines at equal bits; and **it did not
survive its own benchmark** — it died outright at 64k twice in three sessions
(once on a single 64k prompt sent while halogen's page cache was still
resident, once mid-bench on the eighth row). It needs the whole box, and it
still falls over doing the work the lane exists for.
