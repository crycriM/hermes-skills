---
name: numerai-crypto-staking
description: Use for Numerai Crypto (t12) staking, API, strategy reads.
---

# Numerai Crypto Staking & API Operations

Class of work: interacting with the Numerai Crypto tournament (tournament 12) — submissions, stakes, v3 atomic staking, the on-chain strategy contract, and the web3-scoped API key. Covers recon, reads, and mutation planning (never executes mutations without explicit user go + `--live`).

## Context
- Project: `~/projects/numerai-folders/numerai-crypto-bot` (cron submit 14:30 + watchdog 14:45; plan doc `docs/staking-automation-plan.md`).
- Keys live in the project `.env`: `NUMERAI_PUBLIC_ID`/`NUMERAI_SECRET_KEY` (submission scope), `NUMERAI_STAKE_PUBLIC_ID`/`NUMERAI_STAKE_SECRET_KEY` (web3 staking scope). Naming drift (STAKE vs STAKING) exists — check before assuming.
- v3 staking = strategy contract operated by Numerai. We hold no private keys, pay no gas, sign no txs; automation = GraphQL reads + signed authorizations consumed on-chain by Numerai's service.

## Client setup (numerapi 2.23.2 — the pin matters)
- Use `CryptoAPI` for tournament 12. `NumerAPI` defaults to tournament 8; `stake_get` exists only on `NumerAPI` (and is tournament-8-oriented anyway).
- numerapi's v3 helpers (`v3_stake_config`, `v3_stake_round`, `v3_stake_claim`) send queries WITHOUT the `tournamentId` arg → the live API rejects with `Expected type "Int!", found null`. **Always use `raw_query(query, variables, authorization=True)` with explicit `tournamentId: 12`** instead of the helpers.
- No `get_submission_status`/`get_allocations` in this version → raw GraphQL: `model(modelId: $id) { submissions { filename selected round { tournament number } } }`, filter `selected && round.number == N && round.tournament == 12`.
- `v3UserProfile(modelName: $m)` = the web-app-facing model profile: `stakeValue`, `stakeValues { time value }` (Nmr history), plus performance fields. Null profile = field arg missing (it also accepts `tournament`).
- `wallet_transactions()` works with the STAKE key; deposits/withdrawals to/from wallet 0xc728fd8e... pattern = payouts + strategy sweep automation.

## dotenv pitfall
`load_dotenv()` with no args searches from the SCRIPT's location, not cwd. Probe scripts placed in /tmp silently fail to load the project `.env` → `KeyError` on `NUMERAI_*` while the same code works from project files (auth.py works because it lives in the repo). Always `load_dotenv(os.path.join(os.getcwd(), ".env"))` in probes.

## On-chain recon (keyless, public RPCs)
1. **Get the ABI**: Blockscout verified-contract API works without a key:
   `https://eth.blockscout.com/api?module=contract&action=getabi&address=<0x...>` (Sourcify 404s for Numerai contracts; Etherscan needs a key). Response: `{"message":"OK","result":"<json-abi-string>"}` — parse `result`.
2. **eth_call / eth_getLogs** against publicnode / eth.drpc.org / 1rpc.io/eth / cloudflare-eth.com, with `User-Agent: Mozilla/5.0` and endpoint fallbacks (publicnode 403s flakily; 1rpc most reliable).
3. **Keccak selectors without polluting the venv**: `uv run --with pycryptodome --with eth-abi python3 script.py` — `Crypto.Hash.keccak` for selectors/topic0, `eth_abi.encode/decode` for calldata/outputs.
4. **Per-model strategy config**: `modelConfig(uint256 tournamentId, bytes32 modelId) -> (uint128 perRoundStake, uint8 mode, bool enabled)`. Unset entries return (0,0,False) WITHOUT reverting → zeros do not mean a wrong key.
5. **Prove "never configured"**: `eth_getLogs` on the strategy for topic0 of `ModelConfigUpdated(uint256,bytes32,uint128,uint8,bool)` = `0x481bad5c91011256e508ab43ccad86a505b44506b18d7f9dddd7a863bf711767`. **fromBlock pitfall**: a fromBlock above current head silently returns 0 logs — use `0x0`.
6. **Model key encoding (bytes32) unresolved as of 2026-08**: ascii-dashless-uuid / hex-decoded / keccak-of-name all return identical zeros on empty config, so they're indistinguishable until a real config exists. The first `ModelConfigUpdated` event topic reveals the exact encoding.

## Safety
- Read-first: inspect `dir(api)` + `inspect.signature/getsource` before calling anything. `stake_set/increase/decrease/drain/change` and `v3_stake_auth` are mutation/authorization paths — do not call them in recon.
- `v3StakeAuth(submissionId, staker, maxAmount)` returns a signed authorization — inert without on-chain execution, but treat calls as intent: get user go + confirm the staker address first.
- Never print `NUMERAI_*_SECRET_KEY` values; mask when showing .env contents.
- All reads should be cross-checked: strategy `availableBalance()` vs idle NMR; `owner()` vs wallet; `staking()` vs `v3StakeConfig(tournamentId:12)`.

## Verification steps
- Sanity: `v3StakeConfig(tournamentId:12)` returns staking contract 0xC1f46Adf..., nmrAddress 0x1776e1F2..., owner 0x1105aFAF...; strategy `staking()` returns the same address.
- Cross-check web-app stakes vs on-chain: `v3UserProfile.stakeValues` tail ≈ 0 should match `modelConfig` = (0,0,False).

## References
- `references/strategy-contract-abi.md` — verified ABI surface, addresses, events, state snapshot 2026-08-24.