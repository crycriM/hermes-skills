# Rankit universe session runbook (2026-08)

Rankit (`~/projects/rankit`) is a crypto-perp rankings platform: CLS = 70% ADV + 30%
open-interest (AOI) + 0.1 cross-listing bonus, selecting PERP32 (size 32) and PERP128
(size 128) universes from USDT-M perps on Binance/Bybit/OKX/Hyperliquid/Aster.

## Live-verified Binance native list (2026-08)

- 837 USDT-margined perpetuals total.
- `1000x` multipliers (14): `1000BONKUSDT, 1000CATUSDT, 1000CHEEMSUSDT, 1000FLOKIUSDT,
  1000LUNCUSDT, 1000PEPEUSDT, 1000RATSUSDT, 1000SATSUSDT, 1000SHIBUSDT, 1000WHYUSDT,
  1000XECUSDT, 1000XUSDT`.
- `1e6x` multipliers (2): `1000000MOGUSDT, 1000000BOBUSDT`.
- **Canonical collisions (two natives -> one canonical):** `BOBUSDT`+`1000000BOBUSDT`,
  `CATUSDT`+`1000CATUSDT`. Both a plain and a micro contract exist for these bases.
- **XEC perp exists** as `1000XECUSDT` — a reported "XEC doesn't exist" was actually the
  stripping bug producing `XECUSDT`.
- **`1INCHUSDT`** canonical is `1INCH-USDT` (leading digit is part of the base, not a
  multiplier) — the litmus test that rejects naive digit-stripping.

## The fresh-adapter-instance bug

Root cause of every `400 invalid symbol` for micro tokens: `get_adapter()` is a factory
returning a NEW adapter per call. `historical_fetch.run()` built the instrument list on
one instance (populating a canonical->native `_native_map`) but then called
`get_adapter()` AGAIN inside the per-symbol loop — fresh instance, empty map, so
`_to_native("PEPE-USDT")` -> `PEPEUSDT` -> 400. Symptom in logs:
`Failed to fetch Binance/PEPE-USDT: 400 ... symbol=PEPEUSDT`, `binance -> inserted=0 failed=11`.

Fix (applied): add `async _ensure_symbol_map()` that lazy-calls `fetch_instruments()` if
`_native_map` is empty, invoke it at the top of `fetch_ohlcv`/`fetch_open_interest`/
`fetch_funding_rate`, AND hoist one adapter per exchange out of the per-symbol loop.

## Canonicalization implementation (from the fix)

```python
_USDT_MULTI_PREFIXES = ("1000000", "1000")  # longest first

def canonical_from_native(native: str) -> str:
    for mult in _USDT_MULTI_PREFIXES:
        if native.startswith(mult):
            rest = native[len(mult):]
            if rest.endswith("USDT") and rest[:-4]:
                return f"{rest[:-4]}-USDT"
            break
    if native.endswith("USDT") and native[:-4]:
        return f"{native[:-4]}-USDT"
    return native.replace("USDT", "-USDT")
```

Live round-trip test: for every native in exchangeInfo, map to canonical and back to
native; assert no collisions (report the two known ones). Unit test `1INCHUSDT -> 1INCH-USDT`.

## Gate funnel numbers (live DB, 2026-08-29)

Raw CLS inputs = 746; CMC rankings fetched = 498.

| market-cap gate | adv & recent >= 5M | >= 3M | >= 2M |
|---|---|---|---|
| mc<=300 | 113 | **145** | 168 |
| mc<=500 | 146 | 192 | 239 |
| mc disabled | 217 | 303 | 394 |

PERP128 needs 126. Practical result: relax PERP128 to 3M (145 >= 126) while PERP32 stays
5M strict. Chosen: `GATE_ADV_USDT = {"PERP32": 5_000_000.0, "PERP128": 3_000_000.0}`.

## Warm-start / dry-run bug

`weekly_backfill.sh` ran `example_live_perimeter_run --dry-run` (default True). Because
`--dry-run` skips `publish_snapshot()`, `universe_snapshots` stayed empty, so
`get_current_universe()` returned None -> `previous_assets` empty every week -> PERP32
"ok" but stuck at 6 (2 forced + 4 max_additions), PERP128 `insufficient_data`. Fix: pass
`--dry-run=false` so snapshots persist and the universe warms by <= max_additions/week
(PERP32 to 32, PERP128 to 128).

## CLS / OI recent-window fix

Coinalyze free tier gives ~90 days of daily OI, but CLS `aoi` was a 180-day median — the
uncovered older half self-zeroed it. SQL fix in `CLS_AGGREGATE_SQL`:

```sql
PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.combined_daily_oi) AS aoi_full,
PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.combined_daily_oi)
    FILTER (WHERE d.trade_date >= $2 - INTERVAL '{recent_interval} days') AS aoi_recent,
...
COALESCE(m.aoi_recent, m.aoi_full, 0) AS aoi
```
`FILTER` on an aggregate can reference `trade_date` even though it is not in `GROUP BY`.

## OI backfill wiring

`oi_backfill_coinalyze --days 90 --exchanges binance bybit okx hyperliquid aster` writes
`market_data_daily.open_interest` (the column CLS reads). Verify >0 rows updated and re-run
`fetch_cls_inputs` to confirm `aoi` turns nonzero. Stale garbled `000MOG-USDT`/`000BOB-USDT`
rows from pre-fix runs return no Coinalyze OI (their real Coinalyze symbols don't exist).