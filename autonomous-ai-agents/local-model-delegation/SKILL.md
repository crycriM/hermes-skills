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

The model names kilo can target live under `provider.local.models` in
`~/.config/kilo/kilo.jsonc` (local provider baseURL = model-manager proxy
`http://localhost:8079/v1`). Current set (2026-08):

- `local/qwen38-27b` — THINKING variant. **The user's default for implementation
  delegation** (they corrected mid-session 2026-08-24: "launch session on thinking
  version of the model" — i.e. NOT `-nothink`).
- `local/qwen38-27b-nothink` — same weights, reasoning off; clean `content`, thinking
  in `reasoning_content`.
- `local/qwen36-35b` — smaller/faster, the kilo default previously.
- `local/step37`, `local/qwen35-9b` — also present at times.

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

## Pitfalls

- Model name typos: kilo quietly falls back or errors — run the smoke test first.
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
- Context compaction is NOT task-boundary driven: kilo auto-compacts on token pressure
  (threshold_percent or the reserved output-cap buffer), mid-task — never explicitly
  between tasks. On local models the proxy's hard ceiling (~131k) can still kill the
  run; plan scoped continuations instead of trusting compaction. Mechanics:
  references/kilo-context-compaction.md (used with the context-ceiling-recovery.md pattern).
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