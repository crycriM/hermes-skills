---
name: crypto-perp-exchange-adapters
description: "Normalize crypto perp symbols (1000x), OI, universe gates."
version: 1.0.0
author: pincemi
license: MIT
tags: [crypto, perp, binance, bybit, okx, hyperliquid, aster, symbols, open-interest, universe]
metadata:
  hermes:
    tags: [crypto, perp, binance, bybit, okx, hyperliquid, symbols, open-interest, universe]
    related_skills: [data-pipeline-apis, cross-sectional-perp-signal]
---

# Crypto Perp Exchange Adapters & Universe Data

## When to Use

Load this skill when:
- Debugging crypto perp exchange adapters (Binance/Bybit/OKX/Hyperliquid/Aster USDT-M
  perps), especially any 400-Invalid-Symbol, missing-symbol, or wrong-symbol symptom.
- Canonicalizing exchange symbols, or mapping canonical `BASE-USDT` <-> native contract ids.
- Building open-interest / funding enrichment (e.g. Coinalyze) or fixing a "ranking metric
  is all zeros" symptom.
- Tuning or building liquidity/CLS universe selection gates (PERP32/PERP128 perimeters).
- A scheduled turnover-dampened universe/sizing job is stuck at a tiny asset count.

Building exchange adapters and data layers for USDT-margined perpetual futures across
Binance, Bybit, OKX, Hyperliquid, and Aster (a Binance-compatible fapi clone). Focus:
getting symbol normalization, canonical<->native mapping, and OI/coverage math right so
liquidity-ranking / universe-selection (CLS-style scoring) actually works.

## Micro-contract symbols — the #1 pitfall

Native USDT-M perp symbols carry a price multiplier that must be stripped for a canonical
`BASE-USDT` form and re-added when calling back to the exchange:

| Native (exchange)                | Base      | Canonical used internally |
|----------------------------------|-----------|---------------------------|
| `1000PEPEUSDT` / `1000SHIBUSDT`  | PEPE/SHIB | `PEPE-USDT` / `SHIB-USDT` |
| `1000XECUSDT`                    | XEC       | `XEC-USDT` (perp exists as `1000XEC`) |
| `1000000MOGUSDT`/`1000000BOBUSDT`| MOG/BOB   | `MOG-USDT` / `BOB-USDT` |

Three hard rules (each was a real production bug):

1. **Match the real multiplier prefixes explicitly**, longest first —
   `for mult in ("1000000", "1000"): if native.startswith(mult): ...`.
   `startswith("1000")` is TRUE for `1000000MOGUSDT` and `native[4:]` mangles it into
   `000MOGUSDT` -> garbage canonical `000MOG-USDT`. And NEVER strip an arbitrary leading
   digit run: `1INCHUSDT` has `1` as part of its base name and must stay `1INCH-USDT`.
2. **The canonical<->native map is only usable on the instance that built it.** When
   adapters come from a factory (`get_adapter()`) that returns a NEW instance per call,
   a bare `_to_native("PEPE-USDT")` with an empty map falls back to naive concatenation
   -> `PEPEUSDT` (nonexistent) -> HTTP 400 `Invalid Symbol` for EVERY micro token.
   Guard with a lazy `await fetch_instruments()` before any native lookup, and reuse ONE
   adapter per exchange across the per-symbol fetch loop (don't `get_adapter()` per symbol).
3. **Two natives can collapse to one canonical.** Binance lists both `CATUSDT` and
   `1000CATUSDT`, and both `BOBUSDT` and `1000000BOBUSDT`. When building the map, detect
   canonical collisions (two natives -> same canonical) and decide which variant to keep
   (micro is usually the more liquid one).

## OI coverage window vs aggregate median window

If OI/funding history is enriched from an aggregator with a shallow window (Coinalyze free
~90 days) but the ranking metric is a LONG-window median (e.g. 180-day AOI), the uncovered
older half dilutes the median to ~0 and the OI weight contributes nothing — undetected,
because the pipeline reports "OI weight inactive" not an error.

Fix: split the metric into `value_full` (long window) and `value_recent` (same aggregate
`FILTER (WHERE trade_date >= end - INTERVAL '<recent> days')`), then publish
`COALESCE(value_recent, value_full, 0)`. Keep volume on the full window (it is fully
covered); apply the recent-window treatment only to metrics whose source has a coverage gap.

## Gate tuning: measure the funnel empirically before relaxing

Before relaxing a universe/liquidity gate to grow a candidate pool, reproduce the funnel
against the live DB: fetch the raw CLS inputs, apply the market-cap filter, then count how
many pass each threshold `T` for `adv >= T AND recent_adv >= T`. This tells you the exact
minimal release (measured in candidates) instead of guessing. Example result that guided a
fix: at `T=5M` only ~110 pass (needs 126 for a 128-universe) but `T=3M` gives ~145. Set the
gate per-perimeter rather than globally so the smaller, stricter universe is untouched.

## Scheduled universe jobs: `--dry-run` causes a perpetual cold start

Turnover-dampened selection reads the previous period's selection from a persisted store
to cap additions/removals per period. If the scheduled job runs with a `--dry-run` flag
that skips the DB write, the previous selection is NEVER persisted -> `previous` is empty
every run -> the universe is stuck at its first-period cap forever (e.g. a 128-universe
returns `ok` but only ~12 assets of 128). Keep `--dry-run` for manual validation only;
scheduled runs must persist. Symptom to watch: a universe job that should have "warmed up"
over weeks still reports the same tiny asset count every week.

## Pitfalls

- **Aggregator exchange codes are non-obvious** (Coinalyze: `6`=Bybit, `3`=OKX, `H`=HL,
  `A`=Binance, `S`=Aster). Verify against the live `/exchanges` endpoint, never docs.
- **Prefer linear (USDT/USDC-margined) contracts** when building aggregator symbol maps to
  avoid silently mapping to an inverse/coin-margined contract of the same pair.
- **Timestamp units differ per endpoint** (Coinalyze `/open-interest` = ms, history `t` = s).
- **Volume storage: use BIGINT** for quote volume / trade-count proxy columns on OKX-type
  data — values can exceed 32-bit int range.

## References

- `references/rankit-universe-session.md` — full 2026-08 runbook: live-verified Binance
  1000x/1e6x native list, the fresh-adapter-instance bug, Coinalyze OI backfill wiring, the
  PERP32/PERP128 gate-funnel numbers, and the CLS recent-window OI fix.