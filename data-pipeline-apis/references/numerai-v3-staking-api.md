# Numerai Staking v3 History API (tournament 12 / crypto)

Verified 2026-08-23 against live GraphQL (numerapi 2.23.2). Recon method:
introspect `__schema { queryType { fields { name } } }` and `__type(name: "...")`
via `api.raw_query(q, {}, authorization=True)` before trusting docs.

## Scope gate

`v3StakeClaim` / `v3StakeClaims` / `v3StakeRound` require token scope
**`web3_staking`**. Default Numerai tokens (upload/read/stake) lack it ->
GraphQL error `Insufficient permission for web3_staking`. Fix: create a new
token at numer.ai -> Account -> API tokens. Check current scopes via
`api.get_account()['apiTokens']`.

## What works WITHOUT web3_staking scope

| Endpoint | Gives | Quirks |
|---|---|---|
| raw query `stakeTransactions(limit, offset, modelIds)` | per-model x round stakes + tx hash | `note` field holds tx hash; types seen: `strategy stake`; paginated |
| `pending_model_payouts(tournament=12)` | settled payouts per model x round | negative `payoutNmr` == burn; zeros come as string `"0E-18"`; only ~30 recent rounds |
| raw query `model(modelId) { returnsValues { date oneDayNmr allTimeNmr } }` | daily NMR P&L + cumulative per model | `allTimeNmr` matches sum of positive payouts exactly (cross-check); only last ~25 days populated |
| `wallet_transactions()` | wallet deposits/withdrawals | withdrawal `to` == the account's own **v3 allocation strategy contract** (Numerai-automated migration/sweep), not an exit — verify via `owner()` on-chain == numerai wallet |
| `round_model_performances_v2(model_uuid)` | scores incl. `payoutSettled` per score type | needs model UUID not username; deprecated but works |

## Endpoints needing web3_staking scope

- `v3StakeClaim(roundId, modelId, staker)` — single claim proof
- `v3StakeClaims(staker, tournamentId)` — **batch**, all claims for a wallet
- `v3StakeRound(roundId, tournamentId)` — installed numerapi omits the
  required `tournamentId` arg (bug); must raw-query with
  `v3StakeRound(roundId: String!, tournamentId: Int!)`

Wei fields (`burnAmountWei`, `payoutAmountWei`, `claimableAmountWei`) are
strings -> NMR = `Decimal(wei) / Decimal(10)**18`.

## Reference implementation

`~/projects/numerai-folders/numerai-crypto-bot/src/numerai/stake_history.py`
(+ `tests/test_stake_history.py`). CLI:
`PYTHONPATH=. uv run python3 -m src.numerai.stake_history --json exports/stake_history.json [--claims]`.
Raises `Web3ScopeError` when scope missing; falls back to payout-based burn
reconstruction.
