---
name: numerai-crypto-operations
description: "Numerai Crypto (t12) submission and v3 staking operations."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Numerai, Crypto, Staking, Submission, GraphQL, Web3, Tournament-12]
    related_skills: [data-science, numerai-model-evolution]
---

# Numerai Crypto Operations (tournament 12)

Daily submission, v3 atomic staking, stake history/ledger, and read-only API
operations for Numerai Crypto. Complements `numerai-model-evolution` (model
research) and the modeling sections of the `data-science` umbrella.

## When to use

- Submitting models, checking submission status, or debugging the submit cron.
- Reading staking state: current stakes, wallet flows, round windows, on-chain balances.
- Building or testing the v3 staking automation bot (staking-automation-plan.md).
- Any read against the Numerai GraphQL API with the `NUMERAI_STAKE_*` key.

## Project layout & auth

- Project: `~/projects/numerai-folders/numerai-crypto-bot` (same dir via
  `/mnt/data1/cricri/...`). Run scripts from the project root with
  `uv run python3 ...`.
- `src/numerai/auth.py: get_api()` reads `NUMERAI_PUBLIC_ID` / `NUMERAI_SECRET_KEY`
  from `.env` (submission client). Web3-scoped ops use
  `NUMERAI_STAKE_PUBLIC_ID` / `NUMERAI_STAKE_SECRET_KEY` (also `.env`).
  Plan docs may say `_STAKING_`; the actual var names are `_STAKE_`.
- Submit cron: `numerai-crypto-submit.sh` (no_agent, 14:30 CEST), watchdog 14:45 —
  both in `~/.hermes/scripts/`, workdir = project, must absolute-path binaries.

## numerapi 2.23.2 pitfalls (verified)

- Use `CryptoAPI` for tournament 12 — it sets `tournament_id = 12`. Plain
  `NumerAPI` defaults to tournament 8; `stake_get` exists only there.
- **v3 helpers are broken against the live API**: bundled `v3_stake_config`,
  `v3_stake_round`, `v3_stake_claim` omit the now-required `tournamentId` arg →
  `ValueError: In argument "tournamentId": Expected type "Int!", found null.`
  ALWAYS use `raw_query` with explicit `tournamentId: 12`.
- **No `get_submission_status`**: use
  `model(modelId:) { submissions { filename selected round { number tournament } } }`
  and filter on round + `selected: True`.
- **`raw_query` defaults to `authorization=False`** — private queries
  (submissions, v3StakeRound, stake state) fail with "You must be authenticated"
  unless you pass `authorization=True`. Public queries (rounds open/close times)
  are fine without it. Round timestamps come back as ISO strings
  (`2026-08-25T12:00:00Z`), not unix — parse with `datetime.fromisoformat`.
- Round windows are IRREGULAR (24h–72h, opening daily at 14:00 CEST). The
  submit cron fires at 14:30 CEST, right after a 14:00 open — so most open
  rounds ALREADY have a selected submission from that day's 14:30 run.
  Before a MANUAL submission: (1) verify the window is open via
  `rounds(tournament: 12, number: N) { openTime closeTime }` (ISO strings,
  parse with fromisoformat), and (2) list existing submissions with
  `model(modelId:) { submissions { filename selected round { number } } }`
  (`authorization=True`). If the open round already has a selected submission,
  a manual re-run is a redundant override — the last upload before close wins,
  with only minutes/seconds of fresher data. Don't duplicate the cron's work
  unless the user explicitly wants a re-submission.
- GraphQL `__schema` introspection is blocked on api-tournament.numer.ai
  ("syntax error before:") — discover fields from numerapi source or trial queries.

## Staking safety (mutations)

- `stake_set / stake_increase / stake_decrease / stake_drain / stake_change`
  are mutations — never call without explicit user go.
- `v3_stake_auth(submission_id, staker, max_amount)` returns a SIGNED
  authorization (EIP-712 payload). Inert until the strategy contract executes it
  on-chain, but treat as mutation-adjacent: confirm staker + amount first.
- `v3_stake_claim(round_id, model_id, staker)` is a read (claim proof).

## Read paths (verified raw queries)

- `v3StakeConfig(tournamentId: 12)` → staking contract address, authorizationSigner,
  nmrAddress, owner, paused, pendingOwner, serviceWallet.
- `v3StakeRound(tournamentId: 12, roundId: "N")` → state (Open/Closed),
  openTime/closeTime/resolveTime (unix), resolved, totalStaked (pool-wide),
  totalPayout, remainingPayout/Burn, payoutFactor, stakeCap/stakeThreshold.
- `wallet_transactions()` → fund-flow trail; READ the automation by pairing
  deposits/withdrawals of equal amount within ~25 s (payout → strategy auto-sweep
  is the "recycle" automation configured in the web app).
- On-chain (keyless): NMR balance/strategy idle via `balanceOf` (`0x70a08231`),
  owners via `owner()` (`0x8da5cb5b`) — see `scripts/probe_v3_state.py`.

## Pitfalls

- **dotenv trap:** `load_dotenv()` with no args searches the *calling script's*
  directory, not cwd. Probe scripts outside the project silently load nothing →
  use `load_dotenv(os.path.join(os.getcwd(), ".env"))`.
- **publicnode RPC returns 403 without a User-Agent header** — always send UA;
  fallbacks eth.drpc.org / 1rpc.io/eth / cloudflare-eth.com.
- Strategy per-model config getters are NOT guessable (all probes revert); read
  them only with the real strategy ABI (Numerai public repos / verified source).
- Calldata args must be exactly 64 hex chars (32 bytes); malformed padding yields
  `cannot unmarshal invalid hex string`.
- keccak-256 selectors when pycryptodome is absent (never dirty the venv):
  `uv run --with pycryptodome python3 …`.

## Submit cron failure: 4 GiB worker MemoryMax cgroup (Sep 2026)

Hermes cron (no_agent) jobs and background terminal commands run inside a
systemd scope with a HARD `MemoryMax` cgroup cap: 4 GiB on this machine
(`tools/process_registry._worker_memory_max_bytes()` = min(enclosing
cgroup limit, RAM/2, 4 GiB); the `TERMINAL_LOCAL_MEMORY_MAX_MB` env var can
only TIGHTEN it, never raise it).

- Running the 5 model scripts in parallel peaked >4 GiB within ~8 s → kernel
  OOM-killed a python in the cron scope (`journalctl | grep hermes-worker-cron-984c79a51188`),
  all 5 model logs went silent right after the PIT join lines, and the job
  died silently (Sep 11-15 2026; Sep 11 variant: no OOM but 12h CPU / 85 min
  wall of thrash → 3600 s timeout). Interactive/serial runs take ~16-20 s
  per model and peak ~1.3 GiB.
- FIX (script header): models run SEQUENTIALLY. Stale comment claiming
  serial exceeds the 3600 s timeout was wrong — parallel was only needed
  when numerapi API latency made each run ~17 min. Serial also removes the
  parallel download race (5 procs overwriting the same `data/raw` file →
  spurious FileNotFoundError in `auth.py: download_dataset` copystat).
- Diagnostic shortcut: `/tmp/repro` runs the script interactively; if it
  completes in seconds but cron dies with no output file, suspect cgroup
  OOM — check `journalctl --since ... | grep -E 'oom-kill|Memory cgroup'`
  and the scope's `Consumed ... memory peak` line.

## Support files

- `references/numerai-staking-v3-api.md` — full API surface, contract/address map,
  exact working queries, error signatures, open items for the staking bot phase.
- `scripts/probe_v3_state.py` — runnable read-only state probe (models,
  submissions, v3 config/round, wallet tx, on-chain balances). Run from project root.