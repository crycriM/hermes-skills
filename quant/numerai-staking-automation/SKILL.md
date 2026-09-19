---
name: numerai-staking-automation
description: Use when working with Numerai v3 staking or on-chain state.
---

# Numerai Staking & v3 API Operations

Workflow knowledge for reading and (eventually) automating Numerai staking:
tournament API quirks, keyless on-chain state reads, contract surface
recovery, and fail-soft cron reporting. Home of the numerai-crypto-bot
staking features.

## When to use
- Reading staking state (per-model stakes, allocation strategy, strategy idle)
- Building/extending staking automation (staking_bot, plan/apply flows)
- Verifying or debugging Numerai v3 API queries and on-chain reads
- Adding staking status to the daily submit report

## Key API facts (numerai-crypto-bot venv, numerapi 2.23.2)
- Use `CryptoAPI` (not `NumerAPI`) for tournament 12 — it sets
  `tournament_id = 12`; `NumerAPI` defaults to tournament 8.
- numerapi's v3 helpers (`v3_stake_config/round/claim`) OMIT the now-required
  `tournamentId` arg and fail with `Expected type "Int!", found null`. Always
  call via `raw_query` with explicit `tournamentId: 12`.
- There is no `get_submission_status` — query `model(modelId){submissions}`
  raw and filter by round/tournament/selected.
- Read-only v3 surface: `v3StakeConfig(tournamentId)`, `v3StakeRound(tournamentId, roundId)`,
  `v3UserProfile(modelName){stakeValue stakeValues{time value}}` (server-side
  web-app stake series), `wallet_transactions()`, `get_models()`.
- Schema introspection: `__schema` is blocked ("syntax error before"); but
  `__type(name: "...")` works, and wrong-field-name errors leak real root
  fields ("Did you mean ...").
- **Never call mutations without explicit user go**: `v3StakeAuth` (issues a
  real signed authorization), `stake_set/increase/decrease/drain/change`,
  and all strategy `setModelConfig*`/`withdraw`/`invokeFor` paths. Dry-run
  and read-only-first is the standing rule.

## On-chain reads (keyless, public RPC)
- RPC list with fallbacks + browser UA (publicnode 403s without UA):
  publicnode, drpc, 1rpc, cloudflare-eth.
- Get verified ABIs WITHOUT an API key from Blockscout:
  `https://eth.blockscout.com/api?module=contract&action=getabi&address=0x...`
  (Sourcify 404s for these; Etherscan needs a key).
- Proxies: read EIP-1967 impl slot via `eth_getStorageAt` (slot
  0x360894a1...382bbc), then fetch the IMPl's ABI.
- Strategy contract 0x5d5aa402..dc71 (ABI saved at
  `numerai-crypto-bot/contracts/strategy_abi.json`):
  - `modelConfig(uint256 tournamentId, bytes32 model) -> (uint128 per_round, uint8 mode, bool enabled)`
  - `availableBalance()`, `owner()`, `operator()`, `staking()`, `factory()`
  - Mutations: `setModelConfig(tournamentId, model, perRoundStake, mode, enabled)`,
    `setModelConfigs(...)`, `deposit`, `withdraw`, `claimToOwner`, `updateSubmissionHashFor`, `invokeFor`
- v3 staking contract 0xC1f46Adf.. (impl 0x8decf3f8..): `stakeByRound(uint256 roundId, address staker, bytes32 modelId) -> uint256` is THE per-model per-round stake read. Also `rounds(uint256)` for round windows, `claimedByRound`.
- Unset model config reads as `(0, 0, False)` — don't confuse "call worked" with "config exists". Confirm with event log scan: `eth_getLogs` for `ModelConfigUpdated` topic0; zero events = never configured.
- Selector computation: venv has no keccak — use `uv run --with pycryptodome` (ephemeral). Embed PRECOMPUTED selectors in production scripts to stay dependency-free.
- Model key encoding on-chain is unresolved (ascii-uuid / hex-decoded / keccak-name all return the same zeros for empty config). The `ModelConfigUpdated` event log will reveal the true encoding on the first real `setModelConfig`.

## Pitfalls
- `load_dotenv()` with no args searches from the CALLING SCRIPT's location, not cwd — scripts outside the project (e.g. /tmp probes) must pass the explicit path.
- eth_call errors like `invalid hex string` / `Invalid params` are almost always YOUR padding: every calldata word must be exactly 64 hex chars (address = 24 zeros + 40 hex; bytes32 = 32 zeros + value).
- `modelConfig`/`rounds` reads do not revert for unset entries — they return defaults. Revert usually means a wrong selector, not a wrong key.
- Web-app "allocation strategy" settings are SERVER-SIDE and separate from on-chain `modelConfig` — the web app can display auto-stake values while on-chain stakes stay 0. Read both, label both.
- Payout→strategy auto-sweeps (wallet tx pairs within ~25s) are Numerai's operator automation, not user exits.

## Daily report pattern
`scripts/round_staking_status.py` prints a compact fail-soft block appended to
the 14:30 no_agent submit cron:
`uv run python3 scripts/round_staking_status.py || echo "staking status unavailable"`.
Design rule: status/report scripts must NEVER raise — each source in its own
try/except, exit 0 always, so `set -e` submit chains and the cron report
survive any API/RPC outage.

## References
- `references/numerai-v3-contracts-and-queries.md` — addresses, precomputed selectors, query templates, verified read recipes.