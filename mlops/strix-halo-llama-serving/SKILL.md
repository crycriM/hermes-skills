---
name: strix-halo-llama-serving
description: "Serve big GGUF standalone on Strix Halo ROCm."
metadata:
  hermes:
    tags: [llama.cpp, rocm, strix-halo, distrobox, mtp, engram, serving]
    related_skills: [distrobox-vulkan-llama-bench, custom-llama-cpp-build, router-preset-model-tuning]
---

# Strix Halo — standalone llama-server (ROCm / EngramHalo)

Run a big GGUF standalone (its own port, outside the model router) on the M5 Strix Halo
iGPU. Applies to Qwen3.8-Flash variants ("Signal") and the EngramHalo fork.

## Pick the right host

Big Qwen3.8-Flash quants need the **prebuilt ROCm toolbox**, not a Vulkan build:

- Distrobox `llama-rocm-10.0-engramhalo`, image
  `docker.io/kyuz0/amd-strix-halo-toolboxes:rocm-10.0-engramhalo`
  (EngramHalo.cpp fork, ROCm 10.0, gfx1151). All available tags are listed in
  `~/sources/amd-strix-halo-toolboxes/refresh-toolboxes.sh`.
- Create it with the device passthrough the script uses:
  `--device /dev/dri --device /dev/kfd --group-add video --group-add render --group-add sudo --security-opt seccomp=unconfined`
- Only the ROCm build has the long-context decode fixes; mainline llama.cpp collapses at
  100K+ context on this GPU.

## Launcher pattern

A launcher script under `~/llm-server/` is the reference (retired ones are kept in
`~/llm-server/attic/`): kill the previous pid from a
pid-file, `distrobox enter <box> -- bash -c '...'`, run `llama-server` with the log
redirected to a file, write the pid, then poll `/health` until ready (a 60–90 s load is
normal). **Gate that poll on the BODY, not on the response arriving:** while loading,
`/health` answers HTTP **503** with `{"error":{"message":"Loading model"}}`, and both
`curl -s ... >/dev/null` and `urlopen(...)` count a 503 response as success — a launcher
written that way prints "ready after 2s" and then every request fails or queues. Require
`"status":"ok"`, and retry 503 in any benchmarking client (a busy slot returns it too).

Working flag set:

```
-ngl 999 -fa on -ctk q8_0 -ctv q8_0 \
-lm mmap --lazy-mode on -c 163840 -b 8192 -ub 2048 -t 4 --parallel 1 \
--jinja -a <alias> \
--spec-type draft-mtp,ngram-mod --spec-draft-n-max 4 --spec-draft-p-min 0.75
```

Model `Signal-3.8-Flash-Next-AP-Q4_K_XL.gguf` + sidecar
`Qwen3.8-Flash-Next-MTP-Q8_0.gguf`. Reference guide (flags, expectations, network):
https://gist.github.com/chm123/b0b3eec2b7f68e09e5855e23fef44dba

## Pitfalls — each of these cost a restart

- `--tensor-read-lazy` **does not exist** in this build (`error: invalid argument`). The
  SSD-engram switch is `-lm mmap --lazy-mode on`.
- `-lm mmap` keeps RSS around 3 GB for a 95 GB model (engram table read on demand). Low
  RSS is expected, not a failed load.
- `HSA_ENABLE_SDMA=0` + `HSA_XNACK=1` (recommended by the gist) **dropped decode from 24
  to 16 t/s here** — leave both unset unless re-measured after a revert.
- The prebuilt toolbox image ships **no web UI**: `/` and `/index.html` return 415/404,
  and `--no-webui` is a no-op. The UI exists only in source builds — do not chase it;
  use the API or point another frontend at it.
- Flag spelling varies per build; `--help` is the source of truth (`-fa on` works on build
  10807 while other builds need `--flash-attn on`; `--lazy-mode` vs `--tensor-read-lazy`).
- `-ctk`/`-ctv` must stay `q8_0` — bf16 KV crashes on gfx1151.
- `--parallel 1` only; multi-slot is unvalidated on the QSA gather path.

- A standalone server launched as a Hermes background process **dies when the gateway
  restarts** — tool-launched processes live in the gateway's cgroup. If it must outlive a
  restart, install a systemd user unit (or a `systemd-run --user` scope) instead.
- Treat these servers as experiments. While the model is still moving upstream, retire the
  launcher rather than maintaining it: move the script(s) and any unit into `~/llm-server/attic/`,
  `systemctl --user daemon-reload`, and leave the toolbox image in place for the next round.

## Benchmarking a served model here

Full protocol, harness design and the cross-engine comparison recipe:
`references/serving-benchmark-protocol.md`. The rules that cost a re-run when missed:

- **Warm up and discard one request per arm** before measuring. If any of the model is
  paged rather than resident, the first request pays it (one engine read its lookup table
  off disk and decoded at 28–32 tok/s where steady state was 40–62, with identical draft
  acceptance). An A/B without a warmup measures the disk, not the model.
- **Give every benchmark prompt a unique prefix**, or prefix caching answers the repeat
  and reports a prefill rate that read nothing — worst in a size sweep, where each longer
  length is a prefix of the next (a 2,841 tok/s "pp65536" reading whose honest cold rate
  is ~1,490).
- **Read decode from `timings.predicted_per_second`**, never `completion_tokens / wall`:
  at 64k, prefill was 44 s of a 46.5 s wall for 128 tokens.
- **Measure at the depth the workload uses.** Depth is where engines diverge, and the
  cause is memory shape rather than kernels: resident/pinned weights held 49–57 tok/s at
  both 32k and 64k, while the same model behind `-lm mmap --lazy-mode on` halved
  (25.8 tok/s at 32k → 13.0 at 64k) because it streams experts from disk at depth.
- A verifiable aside: this box reproduced the EngramHalo fork's *published* 32k figure
  (90.0 s measured, 103.7 s published), which is the check that makes a comparison
  trustworthy before you quote a ratio.

## Memory accounting on this host

- Pinned/locked weights are counted by the kernel as reclaimable file cache, so `free`
  and `MemAvailable` overstate what is left by the size of the model (~68 GiB for a 4-bit
  125B checkpoint). Believe the server's own "memory left for everything else" line.
- **Never SIGKILL one of these servers, and check GTT after any unclean exit.** Every GPU
  allocation here lands in GTT (system RAM under the driver's ceiling); an engine that
  dies while the driver had work in flight can leave tens of GiB allocated with no
  process alive, after which every later start refuses at the pin guard or hangs at pool
  reservation until the host reboots. `cat /sys/class/drm/card*/device/mem_info_gtt_used`
  before starting: healthy idle is well under 1 GiB.
- Size the KV pool for **`prompt + max_tokens`, not for the context**. A pool sized at
  twice the context holds only two full-length requests once the client is allowed to ask
  for the whole context as its answer budget; the next request does not fail, it silently
  evicts the oldest conversation's cached region (one line in the log), so a lane that
  looked sized for two conversations re-prefills one of them. Lowering the server's
  max-tokens cap is the cheaper fix than growing the pool.
- A container that holds this much of the machine is stopped with a real grace period
  (`podman stop -t 60`), and the other GPU tenants are stopped first.

## Related on this machine

- Router/multi-model serving, slot pinning, preset onboarding: `model-manager`,
  `router-preset-model-tuning`, `llama-slot-pinning` — this standalone server is
  deliberately outside that router (own port, e.g. 8082).
- The halogen-flash engine for this same model family is a different lane with its own
  skill: `halogen-flash-lane` (container, port 8741, `.hgn` weights, pinned trunk).
  It beat the EngramHalo recipe here by ~4.8x prefill and ~4.4x decode at 64k.
- Podman bricked by an OOM-killed container (stale `state: 3`, `migrate` panics) and how to
  repair `db.sql`: see `docker-compose-troubleshooting`.
- Vulkan benchmarks in distrobox, MTP verification details, zombie cleanup:
  `distrobox-vulkan-llama-bench`.
