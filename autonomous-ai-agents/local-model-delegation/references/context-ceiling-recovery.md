# Local-model context ceiling & recovery (validated 2026-08-25)

Working example: SHORTEND Phase 1 T1–T4 deployment to `kilo run --model local/qwen38-27b`
on the skewbik-shortend project.

## The failure

131072 tokens is a hard ceiling for qwen38-27b via the :8079 model-manager proxy.
A long multi-file `kilo run` (TDD 4 research modules in one session) fills its running
context with tool output and dies mid-task. It happened TWICE, identically:

- run 1 (`kilo_shortend_t1t4.log`): `Error: request (131617 tokens) exceeds the
  available context size (131072 tokens)` at line ~546. Session recovered, finished
  T1+T2 (23/23 tests green), then got cut off before T3. Exit 1.
- run 2 (`kilo_shortend_t3t4.log`): died at 131742 tokens. Completed T3 (29/29),
  never started T4 / STATUS append. Exit 1.

In both cases the tail of the log showed successful partial work — green tests, finished
modules, a "Done — status" summary block — NOT a code failure. Exit code 1 does not mean
failure; it means "the context window ran out mid-run".

Diagnosis tip: read the END of the log (how far did it get? did it reach the summary
block? did it START the next task?) rather than grepping for the error string.

## The recovery workflow (worked)

1. Verify on-disk state yourself, don't trust the self-report:
   `ls <research>/*.py`, list created test files, re-run the suite. The partial work
   was genuinely green (23/23, then 29/29). Only base the continuation on real state.
2. Write a scoped continuation prompt (`write_file` to /tmp). It must:
   - enumerate what's done and now FROZEN (import-only, never re-edit)
   - name only the REMAINING tasks
   - re-state PATH rules + venv + test command (fresh session has no memory)
   - explicitly warn: "previous run died of context overflow — keep tool output lean":
     pipe pytest through `tail -15`, grep instead of full-file reads, don't re-read
     frozen modules, stop & report rather than spin if you approach the limit
   - give the exact FULL-suite command INCLUDING the new test files
3. Relaunch in a fresh session (window resets): `kilo run --model local/qwen38-27b
   < /tmp/continuation.md > /tmp/kilo_run_<n>.log 2>&1`, background + notify_on_complete.
4. For a SMALL remaining slice, finish it yourself in the orchestrator instead of a
   third kilo run (faster, no third overflow risk). Here that meant writing
   `phase1_report.py` + test (pure aggregation, no heavy imports) by hand, running
   the suite to green, and appending the docs line.

## Outcomes

- T4 `phase1_report.py` written directly by the orchestrator, TDD with planted-pattern
  synthetic tests. One real test-data trap: fixture weekdays MUST be derived from the
  actual calendar (`date(y,m,d).weekday()`) — assuming `2026-02-01` is a Monday when it
  is really a Sunday silently shifts the planted pattern off its target day. Derive
  dates in the fixture, never hardcode day→weekday assumptions.
- Full suite ended 35/35 (screen 10 + np_skew 13 + bootstrap 6 + report 6).
- The continuation pattern is now the standard for >1-module local-model delegations.

## Column-layout facts for T4-style aggregators (skewbik-shortend outputs)

- `scr_snapshots`: date, n_rows, n_null_params, n_w0_bad, H_Q, n_tenors, sign_changes,
  r2, reason, excluded
- `scr_strata`: stratum, date, n_rows, H_Q, n_tenors, sign_changes, r2, reason, excluded
- `scr_dayblock`: date, hour_bucket, rank, n_snaps, median_hq, frac_excluded, sign_change_rate
- `np_dayblock`: date, hour_bucket, rank, n_slices, median_abs_psi, mean_n_quotes, hq_day
- `np_slices`: ts, date, hour_bucket, rank, T_years, tau, w0, n_quotes, beta_z, psi_np,
  psi_svi, sku_reason, material
- `volsurface.market.time_change`: DayOfWeekTimeChange().tau(T, t); weekday order is
  Python's date.weekday() = Mon=0..Sun=6.
