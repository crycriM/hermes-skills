---
name: scheduled-data-jobs
description: "Use when scheduled data jobs fail silently or go stale."
version: 1.0.0
tags: [cron, scheduler, data-pipeline, pit-store, hardening, ingestion]
---

# Scheduled Data Jobs

Patterns for production scheduled jobs that move data: Hermes `no_agent=True`
cron scripts and the incremental refresh pipelines they wrap. Distilled from
debugging jobs that failed silently for weeks (exit-127 PATH breakage,
pipe-masked failures, a PIT store frozen at a hardcoded end date).

## 1. The Cron Environment Contract

Hermes executes no_agent scripts with a **stripped environment**:

- PATH = `/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` —
  NO `~/.local/bin`, no pyenv, no nvm. Any unqualified binary (`uv`, custom
  per-user tools) exits 127 the moment the daemon restarts with a clean env.
  Interactive success proves nothing: your login shell has paths cron doesn't.
- `uv run` does NOT load the project `.env`. Credentials that "always worked"
  may have been leaking through the daemon's own inherited environment;
  one restart silently revokes them.
- HOME is set, but never trust `~` expansion in LLM-written wrappers —
  use absolute paths everywhere.

**Hardened wrapper checklist** (template: `templates/cron-wrapper.sh`):

```bash
#!/bin/bash
set -e -o pipefail                    # pipes must NOT mask the real exit code
export PATH="/home/<user>/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /abs/path/to/project || exit 1
set -a; source /abs/path/to/project/.env; set +a   # explicit secret sourcing
/abs/path/to/.local/bin/uv run python3 script.py 2>&1 | tail -20
```

**Exit-code honesty:** a script ending in `cmd | tail` reports tail's exit 0
to the scheduler. Without `pipefail`, a dead pipeline shows `status: ok`.
Empty stdout = silent success (watchdog pattern); non-zero exit alerts.

## 2. Debugging a Failing or "Successful" Scheduled Job

1. `cronjob action=list` — note `job_id`, `last_status`, schedule.
2. Read the output transcripts — they contain captured stderr EVEN WHEN
   status says ok: `ls -t ~/.hermes/cron/output/<job_id>/*.md | head`,
   then inspect the latest.
3. Reproduce under cron conditions, not interactively:
   `env -i HOME=/home/<user> PATH=<stripped-cron-PATH> bash script.sh; echo $?`
4. Sweep sibling scripts for the same latent bug:
   `grep -HnE "\b(uv|python3?|curl|wget)\b" ~/.hermes/scripts/*.sh` —
   one broken wrapper usually means others share the pattern.
5. Distinguish failure modes: execution error vs delivery error
   (`last_status` vs `last_delivery_error`); model fallback (grep agent.log
   for "Fallback activated" / "model ... not found").

## 3. Incremental PIT-Store Refresh Pattern

Point-in-time feature stores (DuckDB `features` table + exported parquet
snapshots) go stale in a characteristic way: one-shot backfillers with
hardcoded end dates (`--to 2026-05-01`) freeze the table while every
downstream consumer keeps running happily on old data — features null-fill
to 0 and models quietly lose signal without any error anywhere.

**Rules:**

- Daily updaters must EXTEND, never re-run fixed windows: start =
  `(SELECT MAX(date) FROM features WHERE source=?) + 1 day`, end = today.
  Skip cleanly when already current.
- Export snapshots atomically: write `<name>.parquet.tmp`, then
  `os.replace()`. Never leave consumers reading a half-written parquet.
- Enrichment steps that only UPDATE existing rows (e.g. merging aggregated
  OI into an exported table by `(symbol, date)` key) must run AFTER the
  extend step in the same job — chain them in one wrapper script.
- `Updated 0 rows` has three known causes, check in order:
  1. Key type mismatch — parquet stores symbol as String, enrichment frame
     uses Int64; cast keys with `str()` when building lookup dicts.
  2. Zero date overlap — fetched window (e.g. rolling 90d) vs table's
     `MAX(date)`; always check the target's date range first.
  3. Wrong join column entirely.
- Know each source's history depth (e.g. Binance OI ~30 days via CCXT,
  Coinalyze aggregator ~90 days) so nulls at the old end of backfilled
  ranges are expected, not bugs.
- After wiring the chain, run one full catch-up manually and verify real
  values land (sample recent rows, count enriched rows > 0) before trusting
  the schedule.

## Consolidation Note

This skill overlaps `devops` (§ Cron Agent + cron-debugging reference) and
`data-pipeline-apis` (CCXT backfill+incremental pattern, Coinalyze OI
enrichment reference). Both were user-owned at write time. If they get
adopted via `hermes curator adopt`, fold sections 1–2 into
`devops/references/cron-debugging.md` and section 3 into
`data-pipeline-apis/references/coinalyze-oi-enrichment.md`, then delete
this skill.
