# Parity-rate delegations (ZERO-RATE plan) — per-task session pattern, validated 2026-08-25

Worked example: skewbik/private/ZERO-RATE-RESEARCH-PLAN.md D1-D5 delegated to
`kilo run --auto --model local/qwen38-27b`, split into one fresh session per deliverable
after two whole-run failures. The repo is the handoff between sessions; the operator
verifies each landing (re-runs that task's tests) before launching the next.

## Failure chronology (why per-task sessions beat one long run)

- run 1: model read all references, validated its LP estimator design in /tmp scratch,
  then ENDED the session without writing a single file. Exit 0 via tee -> misleading.
- run 2: ~1h scratch-LP debugging loop (slack/rhs sign conventions), then drifted toward
  editing UNRELATED `src/volsurface` call sites ("scalar tv" quirk); killed by operator.
- T1 (pre-`--auto`): first move was `git worktree` / sibling-repo / `git show <sha>`
  exploration -> unallowlisted bash -> auto-reject -> "run ended with an auto-rejected
  permission". Fix: `--auto` + a hard no-explore clause + git-write ban in the prompt.
- T1b: excellent debugging (found the fixture bug below), then stopped mid-implementation.
- T3+: with --auto + per-task prompts, sessions landed real files (module 14/17, loader +
  smoke) and stopped only with a PASS line or a precise finding.

## Operator verification finds (contract bugs the delegate implements faithfully)

1. Delegate-written test fixtures encode YOUR semantic errors. `_row()` dropped put
   prices -> every `build_panel` fixture returned None; the tight-span formula
   `S*(1.001*arange(1,11))` gave a 900% span (backwards, meant 0.9%); the depth-1 book
   had a degenerate interval. The delegate correctly diagnosed (a) as a fixture bug, then
   stopped. Operator fixed the fixtures (they are the contract; the "frozen" rule protects
   the assertions, not the fixtures).
2. One wrong REJECTION RULE was baked into the module from a mis-built fixture: an
   interval gate `hi <= 0` "no executable box" deleted every strike above F — where the
   parity value y = D(F-K) is legitimately negative and the far wings are the strikes the
   plan needs for slope identification. Real data: 5/12 (May) and 12/20 (June) matched
   pairs silently discarded; after removing the gate, all 11 expiries build panels.
3. Gate-triage probe: a 2-min /tmp script counting survivors per gate reason on ONE real
   snapshot pinned the culprit in one run. Do this before touching configs.

## Validation bookmark (research milestone, 2026-02-19 00:00)

INTERVAL (primary LP) fit, forward_mark leg, L0 book:
- 2026-05-29 T=0.2720: D=0.99308, r=2.55%/yr, b=2.72%, F/S=1.00742, n_pairs=11
- 2026-06-26 T=0.3486: D=0.99013, r=2.85%, b=3.02%, F/S=1.01059, n_pairs=18
Pilot midpoint-WLS disclosure: r 2.59%/2.90%, F/S 1.00768/1.01094 -> agreement ~2-3 bp,
loss=0 on every expiry (lines fit inside executable bands; the identified D-bounds are the
informative output, not the point D).
Short-dated instability as predicted: T=0.0037 gives D-bounds 0.990..1.013 -> r swings
±40%/yr; the conversion-leg noise floor (±34 bp per snapshot, plan section 1) dominates.

## Still open at session end

- T3 discount_mode axis (in flight), T4 <out>_rates.parquet + dropped ledger, operator
  finisher (full suite, STATUS.md, real-day smoke) — not run.
- Cosmetic: np.where divide-by-zero RuntimeWarning in WLS (both branches evaluated);
  silence with np.errstate if it pollutes logs.