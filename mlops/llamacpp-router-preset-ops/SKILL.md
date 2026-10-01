---
name: llamacpp-router-preset-ops
description: Use when a preset edit must reach the running router.
version: 1.0.0
author: PinceMi
license: MIT
platforms: [linux]
tags: [llamacpp, llama-server, router-preset, restart, reasoning, thinking, verification, strix-halo]
metadata:
  hermes:
    tags: [llamacpp, llama-server, router-preset, restart, reasoning, thinking, verification]
    related_skills: [router-preset-model-tuning, router-troubleshooting, router-service-recovery, model-manager]
triggers:
  - "preset edit not taking effect"
  - "disable thinking in the preset"
  - "restart m5-router"
  - "reasoning flags preset"
  - "change a model preset"
  - "retire or remove a model lane"
---

# llama.cpp Router Preset Ops

Getting an edited preset onto the *running* router without cutting live inference, and proving the
edit landed. Companion skills own the other halves and are user-owned — read them, do not rewrite
them: `router-preset-model-tuning` (onboarding a model, architecture, memory layout, spec decoding),
`router-troubleshooting` / `router-service-recovery` (service will not start, orphan INI lines, port
conflicts).

## When to use

- A `router-preset.ini` edit (reasoning flags, sampling, chat template, spec decoding) must go live.
- "I changed the preset and nothing happened" — the stale-instance class.
- A router restart is needed but somebody may be mid-generation.
- A model lane is being retired or replaced (a model name is being removed from the stack and its
  callers pointed at another lane): layer map and verification in `references/lane-retirement-sweep.md`.

## Hard invariant: a preset edit is inert until the router restarts

The router caches the presets at boot. Unloading and reloading a model through the :8079 proxy does
**not** re-read the file — the child process keeps the argv it was spawned with. A model loaded before
the edit keeps the old `--chat-template-kwargs`, `--reasoning-*`, sampling, everything. Confirm the
gap by comparing the child's argv with the INI, not by reading the INI again. A deletion is inert for
two processes, not one: the router re-reads the preset at boot, and `model-manager` builds its `:8079`
model list at its own startup — until both restart, a deleted lane is still advertised.

## Procedure

1. **Back up the INI before editing** (`cp -a router-preset.ini backups/router-preset.ini.before-<what>-$(date +%Y%m%d-%H%M%S)`),
   then edit with `patch` anchored on a block unique to that section — twin sections (e.g. a model and
   its `-nothink` sibling) share whole runs of identical lines, so include a line the twin lacks.
2. **Parse-check the file**:
   ```bash
   bash ~/llm-server/start-native-router.sh --help 2>&1 | head -20
   ```
   This does NOT print usage — it launches the router binary, which parses `router-preset.ini` and
   prints `Loaded N custom model presets from <path>` plus the model list. N must equal the number of
   uncommented `[sections]`; a bad key or malformed line shows up as an ERROR line instead of the
   banner. Safe to run while the service is up — it exits without taking the port (verify afterwards
   with `ss -tlnp | grep :8080`: only the service process should be listening).
3. **Check who is being served before touching the service.** Never restart mid-generation:
   ```bash
   curl -s http://localhost:8080/v1/models                 # ids whose status.value == "loaded"
   curl -s 'http://localhost:8080/slots?model=<id>'        # any is_processing=true -> busy
   curl -s http://localhost:8079/proxy/status              # {"loaded": [...], "models": [{name,status,loaded,size_gb}]}
   ```
   `/slots` WITHOUT a `model` parameter returns `{"error": ...}` — a dict, not a list. Probe per id, and
   treat a failed/odd probe as BUSY.
4. **Restart on a quiet WINDOW, not a single sample.** An agentic session goes idle between turns, so
   require several consecutive idle polls (~60 s) before restarting: `systemctl --user restart m5-router`.
   Then `systemctl --user restart model-manager` (its model list is fetched at startup) and wait for
   `/health` on 8080 before doing anything else.
5. **Clean up the preloads.** The restart re-preloads every `load-on-startup = 1` section — tens of GB
   here, and `user@1000.service` carries `ManagedOOMMemoryPressure=kill`, so a stacked preload gets the
   router SIGKILLed with no kernel OOM line in the journal. `POST :8079/api/unload {"model":"<id>"}`
   whatever you do not need, and check `free -g`.
6. **Reload the target** with `POST :8079/api/load {"model":"<id>"}` (never on :8080 — router mode has
   no load endpoint there), then poll `/v1/models` until its `status.value == "loaded"`.
7. **Prove the edit reached the child**: read that model's `status.args` from `curl -s :8080/v1/models`
   and look for the flags you changed (present, absent, values). The argv is the only proof — a config
   file that reads correctly says nothing about the running process. Then verify BEHAVIOURALLY through
   the proxy with a real request (a `max_tokens: 64` call is enough for a thinking-off change).

`scripts/restart-router-when-idle.py <target-section> [--unload <id> ...]` runs steps 3-7 unattended
and prints the live argv + `free -g`. Run it as `terminal(background=true, notify=true)` and read the
log it writes under `~/llm-server/logs/`; its idle probe is the part measured on a busy router, so read
that log rather than assuming the restart happened.

## Turning thinking OFF on an entry with a custom `chat-template-file`

Some templates emit the think tags **unconditionally** — the Qwen3.8 "sharp" template
(`chat_template_sharp.jinja`) derives `ns_state.thinking` from `enable_thinking` (default true) and
from `reasoning_effort` (`none` also switches it off), and its `add_generation_prompt` block writes the
pair either way: an EMPTY pair when thinking is off, an opening tag when on. For those entries keep the
parser ON and disable at the template layer:

```ini
reasoning = on
reasoning-format = deepseek
chat-template-kwargs = {"enable_thinking":false}
# drop reasoning-effort / reasoning-preserve / reasoning-budget / reasoning-budget-message:
# with thinking off there is nothing to preserve or cap, and a leftover budget misleads the next reader
```

- **Do NOT "just set `reasoning = off`" on such an entry.** The template still writes the empty pair;
  with the parser off those literal tags have nowhere to go but `content`. `reasoning = off` +
  `chat-template-kwargs = {"enable_thinking":false}` is the right shape only for entries whose template
  emits NOTHING when thinking is off (a baked-in Qwen template — the removed `[qwen35-9b]` lane was the
  worked example of that shape, so a new section must be proved, not assumed).
- Classify before choosing — read the generation-prompt block, do not guess:
  ```bash
  grep -nE "enable_thinking|reasoning_effort|add_generation_prompt" /path/to/template.jinja
  ```
- Verify after the restart: the answer starts immediately in `content` with empty/short
  `reasoning_content`, instead of a CoT block first.
- **When the ask is "disable thinking", change the reasoning keys only.** Sampling (temp / top-p /
  presence-penalty) is a separate axis, often deliberately mirrored across twin entries so a client can
  A/B by model name — touch it only on request, and say so in the reply.

## Retiring or replacing a lane

Removing a model from the stack is a sweep, not a one-file edit: the app config can be clean while the
lane is still declared in the preset that serves it, and the retirement propagates into every doc that
counts lanes or does preload arithmetic. Full layer map, grep order and verification commands:
`references/lane-retirement-sweep.md`.

- Grep every layer BEFORE reporting "nothing to do", and quote the file path that proves each layer
  clean. App-side keys that wire a model to an endpoint are `model.default`, `providers.<p>.default_model`,
  `model_aliases.<alias>`, `delegation.model`, and `auxiliary.<tool>.model` — one per tool, each failing
  silently if left pointing at a retired lane.
- Delete the section outright (timestamped backup first). Never retarget a lane by renaming its section
  onto an existing name: duplicate `[names]` make the preset ambiguous.
- Recompute every derived number the lane fed — preload totals in comments and docstrings, section counts
  in the spec/README, memory-headroom arithmetic, "active models" lists. Stale counts are how the next
  session mis-plans a load.
- In skills and docs, retarget prescriptive guidance (which lane to run cron / benchmarks / delegation on)
  and leave historical records alone — journal lines, monitoring trees, dated worked examples, session
  transcripts and `state.db` are evidence, not wiring. State in the reply which class you kept.
- Report the removal as PENDING until router + model-manager restart, with the re-preload cost, and hand
  the window to the user (see the restart pitfall below).

## Pitfalls

- **Restarting a service on a shared box is a decision, not a detail.** Ask which window the user wants
  (now / at the next idle moment / leave pending) and state plainly what the restart drops. Deferring
  the restart is a legitimate choice; do the editable part and hand the timing decision over.
- **The restart kills hand-started standalone servers too.** The unit's ExecStop is a pattern
  `pkill -TERM -f llama-server` inside the distrobox, so servers someone launched by hand on other
  ports die with it and do not come back. Snapshot cmdlines (`ps -eo pid,etime,cmd`) before restarting
  and tell the user which lanes went away.
- **A `--help` invocation of the start script is not a no-op** — it starts the router binary, which parses
  the INI and prints `Loaded N custom model presets` + the model list, then exits without binding the
  port. It also starts preloading the `load-on-startup` lanes, so afterwards check the ports are still
  held by the service and that no stray `llama-server` survived:
  `ss -tlnp | grep -E ':(8080|8079)'` and `ps -eo pid,ppid,cmd | grep llama-server | grep -v grep`.
  Do not wrap it in a retry loop or run it while debugging a bind error.
- **Reasoning-family keys ARE valid preset entries**: `reasoning`, `reasoning-format`,
  `reasoning-effort`, `reasoning-preserve`, `reasoning-budget`, `reasoning-budget-message`. A stale
  valid-keys list that omits them must not be "fixed" by deleting them from the INI; extend the
  validator's `KNOWN_KEYS` instead.
- **Do not present an unverified preset edit as done.** Editing the file is step 1 of 7; the change is
  live only when the child argv shows it, and correct only when a real request behaves as intended.
