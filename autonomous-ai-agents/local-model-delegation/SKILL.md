---
name: local-model-delegation
description: "Use when delegating coding to a local LLM via kilo run."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Delegation, Kilo, Local-Model, Router, Model-Manager, qwen38-27b]
    related_skills: [ai-coding-agents, model-manager, router-preset-model-tuning, hermes-agent]
---

# Local-Model Delegation

Delegating implementation work to a LOCAL model (not a cloud agent) on this machine:
`kilo run --model local/<name>`. Overlaps with the user-owned `ai-coding-agents` skill
(which covers kilo CLI generally) and `model-manager` (the proxy). If the user adopts
those skills, merge this one's content into them.

## 1. Which local model to use

Targets are whatever `provider.local.models` in `~/.config/kilo/kilo.jsonc` holds — READ
that file, never trust a remembered list: the local provider gets re-pointed as lanes move
(model-manager proxy `:8079/v1` for llama.cpp presets, the halogen lane `:8741/v1` for
`qwen3.8-flash-next-halogen`). The JSON key is the model id kilo resolves; `name` is only
a display alias. Names seen in the past — verify before use: `qwen38-27b` (THINKING
variant, **the user's default for implementation delegation**; never substitute `-nothink`
unless asked), `qwen38-27b-nothink`, `qwen36-35b`, `qwen3.8-flash-next-halogen` (display
name `qwen38-flash`).

**Every custom model entry needs an explicit `limit` block** —
`"limit": {"context": <the endpoint's real context>, "output": <reservation you accept>}`.
Kilo otherwise sends `max_tokens: 32000` on every request (hard-coded
`min(limit.output, 32000) || 32000`) and never arms auto-compaction (`limit.context === 0`
disables it outright). What that costs, and the trigger arithmetic, are in
references/kilo-context-compaction.md.

Rule: when the user says "delegate to local model X", use the base name
(`local/qwen38-27b`), i.e. the thinking variant, unless they say otherwise.

## 2. Launching the session

```bash
# one-off, quick
kilo run --model local/qwen38-27b 'Implement ... and add tests'

# long task: write a self-contained prompt to /tmp, pipe it in, background + log
kilo run --model local/qwen38-27b < /tmp/prompt.md   # background=true, notify_on_complete=true, tee to a log
```

Smoke-test the model BEFORE the long session (cheap; catches wrong names and swap
failures):
`kilo run --model local/qwen38-27b 'Respond with exactly: KILO_SMOKE_OK'`
→ success looks like `> code · qwen38-27b` then the reply.

Address the model as `-m <provider>/<model-key>` with the key from the config (see §1).
The display-name alias does not resolve in the non-interactive path — a config whose
`"model"`/`agent.*.model` hold the alias fails with `Model not found: local/<alias>.
Did you mean: <key>?` even though the interactive TUI resolves it.

## 3. Switching model variants (thinking vs nothink)

`qwen38-27b` and `qwen38-27b-nothink` load the SAME GGUF weights — leaving both loaded
doubles ~20 GB and the user is OOM-sensitive ("do not stack models"). Swap via the
model-manager proxy's safe API:

```bash
curl -s -X POST http://localhost:8079/api/unload -H 'Content-Type: application/json' -d '{"model":"qwen38-27b-nothink"}'
sleep 2 && curl -s -X POST http://localhost:8079/api/load -H 'Content-Type: application/json' -d '{"model":"qwen38-27b"}'
# verify:  curl -s http://localhost:8079/v1/models   → target loaded, duplicate unloaded
```

Always confirm the current load state first (`GET /v1/models`); a loaded model that is
actively serving should not be unloaded mid-request.

## 4. Prompt recipe for task-list and spec-plan delegations

When delegating from a spec/task doc (e.g. SHORTEND_PHASE1_TASKS.md or a research plan
like private/ZERO-RATE-RESEARCH-PLAN.md), the prompt must be self-contained (the
delegate knows nothing of the conversation). Include:

1. Mission + exact scope: which tasks IN, which tasks OUT (blocked stubs, heavy runs).
2. Real absolute paths (no `~` symlinks) for repos, venv, test runner.
3. Docs to read FIRST (authoritative; note which doc wins on conflict).
4. Hard rules: TDD test-first (watch it fail → implement → pass), no new dependencies,
   no silent drops / stratify-and-count, keep diffs minimal, **do NOT git commit
   unreviewed work** — name and override project workflow docs that instruct commits
   (skewbik's docs/TDD.md does), do not run the long operational job (the orchestrator
   runs it).
5. Pre-registered constants copied verbatim (do not let the delegate re-derive or tune).
6. Per-task acceptance criteria (tests to write, "done when").
7. Final report contract: per-task done/blocked, exact test command + pass/fail,
   files created/modified, deviations with reasons.
8. For research/spec plans (not task lists): enumerate concrete code deliverables
   (D1..D5 style) each with acceptance criteria, plus an explicit SCOPE OUT naming the
   operational runs the operator executes AFTER code lands (sweeps, backtests,
   inference, analysis phases) and what the delegate must never run.

## 5. Orchestration sequence (verify-first)

1. BEFORE delegating: verify repo state against the task doc — git HEAD/tags, dirty
   tree size, whether referenced code/fields exist (grep), data completeness for the
   operational run. Fix stale references IN the spec doc before the delegate reads it
   (this session: baseline commit `55e77c1` was stale — HEAD had moved to `ba992df`).
2. Delegate only the CODE deliverables. Keep long operational steps (pinned backtests,
   data runs that feed the analysis) for yourself, executed AFTER the code lands —
   they often depend on the delegate's output (e.g. CLI flags + rank fields must exist
   before the pinned run).
3. After the delegate reports: verify yourself. Re-read files, re-run the exact test
   commands. A successful summary is a self-report, not proof.
4. Report open decisions (e.g. "commit the dirty tree to mint the baseline tag?") to
   the user rather than committing uncommitted work yourself.

## 6. When a local child fails or dies mid-run

A long local delegation can end in a provider error after doing most of the work. Two
failure shapes, both of which look like "the task did nothing" and are not:

- **`HTTP 400: model '<name>' not found`, returned in ~0.1 s with `api_calls=1`** — the
  configured child model name does not exist on the router (a stale or renamed preset).
  `delegation.model` / `delegation.provider` / `delegation.base_url` are a pin **separate
  from `model.default`**, so children can be broken while the parent runs fine. Validate
  before dispatching: `curl -s http://localhost:8080/v1/models` and compare with
  `hermes config get delegation.model`; fix with
  `hermes config set delegation.model <name-from-that-list>` (the patch/write tools refuse
  `config.yaml` as security-sensitive).
- **`HTTP 400: model is not loaded`, after a long run** — the router unloaded the model
  under the child (swap, pressure, another session). Nothing is wrong with the prompt.

In both cases, **inspect the artifacts before re-dispatching**: file size/mtime, grep for
symbols the task was supposed to introduce, then run the child's own test command yourself.
A dead child usually leaves most of the implementation on disk and only fails on its
closing calls — finish the remainder in the orchestrator (cheaper and faster than paying
for the whole run again). The child's full tool trace, which shows exactly where it
stopped, is at `~/.hermes/cache/delegation/live/<delegation_id>/task-<n>.log`.

Prefer a pin that the router **already has resident**: a non-loaded pin makes every child
wait on a fresh load and stacks another large model in RAM, which this user forbids.

## 7. When the local endpoint refuses a request (a 400 from the provider)

A refusal that names the request budget is the CLIENT's sizing problem, not a broken model
or proxy: both local endpoints reserve `prompt + max_tokens` per request and hard-400 when
the sum exceeds their context (`max_tokens N does not fit: prompt is P tokens and the
context is C, leaving room for R`). Do not restart services or reload models for it.

Route to the verbatim error instead of guessing:

- `~/.local/share/kilo/kilo.db` (sqlite; table `message`, the `data` column is JSON) — the
  assistant row's `error` field carries `data.message`, `statusCode`, `responseBody` and
  `metadata.url`: the exact endpoint and the provider's own words.
- `~/.local/share/kilo/log/opencode.log` — `stream error` lines with provider/model and the
  same message in time order; `pruning ... found pruned=0` lines show what compaction did.
- To learn what the client SENDS rather than what you assume, run
  `scripts/echo-openai-server.py` (logs each request's model, `max_tokens`, message/tool counts, the
  whole key list, and the reasoning family) and point a throwaway config at it with
  `KILO_CONFIG=<file> kilo run --pure -m ...`. When the field must also be *accepted* by the live
  endpoint, use the sibling `scripts/logging-pass-through-proxy.py`: same capture, real upstream
  answering.
- Validate any config edit with `kilo config check` ("No config warnings.") before
  restarting the session.

## 8. A client knob is a claim until you capture the request

A UI knob or CLI flag is not evidence that anything reached the model. Measured on Kilo Code CLI
7.8.1 against a custom `@ai-sdk/openai-compatible` provider: the reasoning-effort picker sent
**nothing** for every level (`--variant low|medium|high|max`, no variant, a model id Kilo
recognises, a per-model `options` block — the same body keys every time), so the lane silently ran
at the server's default. The picker looked like it worked; only the wire showed it did not.

Capture it — both harnesses ship with this skill:

- `scripts/echo-openai-server.py <port> <log>` — answers itself, no GPU cost, proves what the client
  SENDS.
- `scripts/logging-pass-through-proxy.py <port> <host:port> <log>` — forwards to the live endpoint
  and streams the reply back; use it when the question is also "does the server accept it".

Isolate the run from the user's setup: a scratch `kilo.jsonc` whose `baseURL` points at the probe,
reached via `XDG_CONFIG_HOME=<scratch>` + `KILO_CONFIG_DIR=<scratch>/kilo` + a scratch
`XDG_DATA_HOME`, launched with `--pure` so their plugins stay out. Nothing of theirs is touched.

Rules that fall out of it:

- **Log the client's key list, not a fixed field list.** A probe that prints only the fields you
  already know about is how a knob that never arrives gets confirmed as working.
- **Never advertise a level the endpoint refuses.** Kilo's effort enum includes `max`; a server
  defining only `none|minimal|low|medium|high|xhigh` answers 400 for it.
- **Advertising beats hand-configuring.** A client builds per-model options from its catalog entry,
  so the model has to declare them (Kilo: `reasoning_options` — served via `KILO_MODELS_PATH` /
  `KILO_MODELS_URL`, or stamped by a config `plugin`'s `config` hook). Deployed here:
  `~/.config/kilo/models-catalog.json` (models.dev + a `local` provider for the halogen lane),
  rebuilt by `~/.config/kilo/bin/refresh-kilo-catalog.py`; that lane's engine-side level list is in
  the `halogen-flash-lane` skill.
- **An opaque client documents itself in its binary.** `grep -a -o -E '<PREFIX>_[A-Z_]+' <binary> |
  sort -u` surfaces the env-var surface (that is how `KILO_MODELS_PATH`, `KILO_MODELS_URL` and
  `KILO_CONFIG_DIR` were found), and grepping a field name near its use shows the wire mapping
  (`@ai-sdk/openai-compatible` merely renames `reasoningEffort` to `reasoning_effort` and remaps no
  values). Do this before concluding a facility does not exist.
- **Client listings are not the request path.** `kilo models --verbose` prints config defaults for a
  custom provider (`reasoning: null`, a default `limit.output`) even while the wire carries
  `reasoning_effort`. Only the captured body counts.
- **Non-interactive shells skip the bottom of `~/.bashrc`.** Debian's guard returns early, so an
  export below it reaches your terminal and nothing else (Kilo, cron, agent runs). Put it above the
  guard, and for agent-run `kilo run` add the file to Hermes' `terminal.shell_init_files` or prefix
  the variable per invocation — `~/.hermes/config.yaml` and `~/.hermes/.env` are not agent-writable,
  so that hook is the user's to add.

## Pitfalls

- Model name typos: kilo quietly falls back or errors — run the smoke test first, and for a
  delegated child validate the configured name against the live router
  (`curl -s http://localhost:8080/v1/models`); a stale preset name kills every child before
  its first token and surfaces only in the child's result.
- Delegates left to their own devices will "just commit" — the no-commit rule must be
  explicit in the prompt, and the operator must flag tag/commit decisions to the user.
- `kilo run` DIES on permission auto-reject: a single unallowlisted bash command
  (e.g. `ls ~/projects/...`, `git show <sha>`) ends the run with
  "run ended with an auto-rejected permission". Launch with `kilo run --auto` and
  ban git WRITE ops in the prompt (commit/add/rm/stash/push/reset/checkout/worktree);
  allowlisting commands is too brittle.
- Premature "done": the model sometimes ends the session after a design insight or
  scratch validation WITHOUT writing files (validated 2026-08-25: THREE runs did
  this). Prompt must pin the end state to a real artifact: "you are NOT done until
  you ran the pytest command and it printed a PASS line"; design/scratch/reading are
  not completion.
- Exploration drift: given free rein the model runs `git log --all`, worktree list,
  sibling-repo ls — irrelevant and burns context. Explicit "do NOT explore: no git
  log/worktree, no ls ~/projects — work only in the repo root + /tmp".
- Multi-deliverable tasks: do NOT run one long session for D1..D5. Run ONE fresh
  `kilo run` per deliverable, sequential (repo on disk is the handoff; fresh window
  resets the 131k ceiling). The operator verifies each landing (re-run that task's
  tests) before launching the next. Small tail failures after a delegate lands most
  of a module: fix them yourself in the orchestrator (faster, no overflow risk) —
  the delegate still did the heavy lifting.
- Long local-model sessions (thinking variant at ~20-30 tok/s) take 30-90+ min for
  multi-file tasks; use background + notify_on_complete, never block on it.
- The delegate's tests need the venv with the editable package: run them via
  `/mnt/data1/cricri/projects/volcalibration/skewbik/.venv/bin/python -m pytest <file> -x -q`.
- Context compaction is NOT task-boundary driven: it fires on a single computed trigger
  (`min(context, context*threshold_percent/100) - reserved`) whenever the model's
  `limit.context` is known — and never at all when it is 0, which is the state of any
  custom local entry without a `limit` block. Set the limit, then compaction arms itself
  mid-task; it still never waits for a task boundary, so plan scoped continuations for
  >1-module runs. Mechanics: references/kilo-context-compaction.md (used with the
  context-ceiling-recovery.md pattern).
- `tee` exit-code trap: launching as `kilo run ... | tee log` means the completion
  notification's "exit code 0" is TEE's, not kilo's (kilo's real exit: 1 = context
  overflow, permission-kill, etc.). A "completed normally 0" proves nothing — verify via
  the log tail AND on-disk artifacts (`git status`), not the exit code.
- Frozen-test contracts need an OPERATOR audit of the fixture layer: when a delegate writes
  the test file that becomes the "frozen" contract, fixture bugs silently become the spec.
  Validated 2026-08-25: delegate-authored fixtures had (a) put prices dropped by the row
  helper (every panel built None), (b) a backwards strike-span formula (900% clutter vs the
  intended 0.9% span), (c) a degenerate depth-1 book — and one WRONG REJECTION RULE baked in
  as "expected behavior" (an interval gate `hi <= 0` that deleted every strike above F, i.e.
  the far wings the research needed). The delegate chased (a) as an implementation bug and
  stopped; the operator fixed the fixtures and the gate. A delegate will faithfully implement
  a wrong contract — a real-data smoke test (even a failing one) from day one is the cheapest
  detector. Worked example + validation numbers: references/parity-rate-delegation-2026-08-25.md.
- Gate-triage probe: when a real-data pipeline gate kills everything, instrument the few
  gates with a per-reason survivor counter over ONE snapshot (2-min throwaway script in
  /tmp) instead of guessing which gate is at fault — the `hi <= 0` case above was pinned
  this way in a single run (5/12 and 12/20 matched pairs silently deleted).