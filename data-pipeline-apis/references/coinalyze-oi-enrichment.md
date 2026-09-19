# Coinalyze OI Enrichment — Cross-Exchange Open Interest via Aggregator API

**Status:** ✅ Implemented (2026-06-20), verified with live API
**Client:** `src/market_data/coinalyze.py`
**Backfill script:** `src/market_data/oi_backfill_coinalyze.py`
**Commit:** `07b062a`

## Problem

Individual exchanges have inconsistent OI data availability:
- **Binance**: 30 days of hourly OI history via `/futures/data/openInterestHist`
- **Bybit**: Hourly OI via `/v5/market/open-interest` (base units, needs price conversion)
- **OKX, Hyperliquid, Aster**: Current OI only — no historical endpoint
- **Result**: `market_data_daily.open_interest` was always 0 for most exchanges → CLS `aoi` metric meaningless

## Solution: Aggregator API Enrichment

Use Coinalyze (aggregator that collects OI from all exchanges) to backfill historical OI into `market_data_daily`.

## Coinalyze API Summary

| Property | Value |
|----------|-------|
| Base URL | `https://api.coinalyze.net/v1` |
| Auth | `api_key` header (free tier: sign up at coinalyze.net) |
| Rate limit | 40 calls/min |
| Max symbols/request | 20 |
| Historical depth | ~90 days intraday, unlimited daily |
| Cost | Free (cite source if public) |

## Symbol Format

Coinalyze uses **non-obvious exchange codes** (verified 2026-06-20):

| Code | Exchange | Symbol Example |
|------|----------|----------------|
| A | Binance | `BTCUSDT_PERP.A` |
| 6 | Bybit | `BTCUSDT.6` |
| 3 | OKX | `BTCUSDT_PERP.3` |
| H | Hyperliquid | `BTC.H` ⚠️ special format |
| S | Aster | `BTCUSDT.S` |
| 8 | dYdX | `BTCUSDT_PERP.8` (historical) |
| 0 | BitMEX | `XBTUSDT_PERP.0` |
| 2 | Deribit | `BTC-PERP.2` |
| 4 | Huobi/HTX | `BTCUSDT_PERP.4` |
| 7 | Phemex | `BTCUSDT_PERP.7` |
| Y | Gate.io | `BTCUSDT_PERP.Y` |
| W | WOO X | `WOOUSDT_PERP.W` |
| K | Kraken | `BTCUSDT_PERP.K` |

### ⚠️ Pitfalls

1. **Exchange codes are NOT alphabetical** — Bybit is `6`, OKX is `3`, not B/O
2. **Hyperliquid uses special format** — `BTC.H` (base only), not `BTCUSDT_PERP.H`. Quote is USD not USDT
3. **Prefer linear contracts** — Bybit has `BTCUSDT.6` (linear), `BTCUSD.6` (inverse), `BTCPERP.6` (USDC). Symbol map must prefer linear (USDT/USDC-margined) over inverse/coin-margined
4. **Timestamps are SECONDS** — not milliseconds. `t: 1781395200` = Unix timestamp in seconds
5. **USD→USDT normalization** — Hyperliquid quotes in USD, but canonical symbol is `BTC-USDT`. Map builder must normalize

### Discovery

Call `/exchanges` endpoint to get current code mapping. Cache at runtime:
```python
exchanges = await client.fetch_exchanges()
# Returns: [{"name": "Binance", "code": "A"}, {"name": "Bybit", "code": "6"}, ...]
```

## Key Endpoints

| Endpoint | Purpose | Params |
|----------|---------|--------|
| `/exchanges` | List exchange codes | — |
| `/future-markets` | All futures markets with symbols | — |
| `/open-interest` | Current OI | `symbols` (comma-sep, max 20), `convert_to_usd` |
| `/open-interest-history` | Historical OI time series | `symbols`, `interval`, `from`, `to`, `convert_to_usd` |
| `/ohlcv-history` | OHLCV with volume | `symbols`, `interval`, `from`, `to` |

### Response Shape (Current OI)
```json
[{
  "symbol": "BTCUSDT_PERP.A",
  "value": 6239198307.774,
  "update": 1781967221434
}]
```
- `value` = OI in USD (if `convert_to_usd=true`) or base asset
- `update` = timestamp in **milliseconds** (note: different from history endpoint!)

### Response Shape (OI History)
```json
[{
  "symbol": "BTCUSDT_PERP.A",
  "history": [
    {"t": 1781395200, "o": 6576879091.66, "h": 6690849239.42, "l": 6563731575.83, "c": 6677701197.98}
  ]
}]
```
- `t` = timestamp in **SECONDS** (not milliseconds!)
- `o/h/l/c` = OHLC of OI (use `c` for end-of-day OI)
- If `convert_to_usd=true`, values are USD notional; otherwise base asset units

### Response Shape (OHLCV History — for volume)
```json
[{
  "symbol": "BTCUSDT_PERP.A",
  "history": [
    {"t": 1774137600, "o": 68881.5, "h": 69555.8, "l": 67300, "c": 67830.6, "v": 134874.88, "bv": 66105.44, "tx": ..., "btx": ...}
  ]
}]
```
- `v` = volume in base asset units
- `bv` = buy volume (taker buy)
- `tx` = trade count, `btx` = buy trade count
- Use this to compute `oi_volume_ratio = open_interest / volume`

## Verified OI Data (2026-06-20)

| Exchange | BTC OI | Status |
|----------|--------|--------|
| Binance | $6.25B | ✅ |
| Bybit | $3.27B | ✅ |
| OKX | $1.94B | ✅ |
| Hyperliquid | $1.92B | ✅ |
| Aster | N/A | Not yet on Coinalyze |

## Integration Pattern

```python
from src.market_data.coinalyze import CoinalyzeClient

client = CoinalyzeClient()  # reads COINALYZE_API_KEY from settings
await client.fetch_future_markets()  # builds symbol map

# Fetch daily OI for BTC on Binance
history = await client.fetch_open_interest_history(
    symbol="BTC-USDT",
    exchange="binance",
    start=datetime(2026, 3, 1),
    end=datetime(2026, 6, 1),
    interval="daily",
    convert_to_usd=True,
)
# Returns: [{"t": 1781395200, "o": ..., "h": ..., "l": ..., "c": 6677701197.98}, ...]
# Note: t is in SECONDS, not milliseconds
```

## Backfill Script Usage

```bash
# Set API key
export COINALYZE_API_KEY=***

# Backfill 90 days for all exchanges
uv run python -m src.market_data.oi_backfill_coinalyze --days 90

# Dry-run (test without DB writes)
uv run python -m src.market_data.oi_backfill_coinalyze --days 90 --dry-run

# Limit for testing
uv run python -m src.market_data.oi_backfill_coinalyze --days 7 --limit 5

# Specific exchanges only
uv run python -m src.market_data.oi_backfill_coinalyze --exchanges binance bybit okx hyperliquid
```

## Timing Estimate

For PERP128 universe (128 symbols × 5 exchanges = 640 pairs):
- 640 API calls ÷ 40 calls/min = 16 minutes
- With 1.5s inter-call delay: ~16 min total
- **Best run overnight** via cron

## Numerai PIT Store Integration (Parquet-based)

For the Numerai crypto bot (`numerai-crypto-bot`), OI enrichment targets a **parquet PIT store** rather than TimescaleDB.

**Script:** `scripts/backfill_coinalyze_oi.py`
**Target:** `data/pit_store/derivatives.parquet`
**Schema:** `symbol` (String ucid), `date` (Date), `derived` (JSON string)

### Integration Pattern

1. Load universe from `src/universe/override.csv` → extract ticker from `ccxt_pair` column (e.g. `"BTC/USDT"` → `"BTC"`)
2. Map ticker → Coinalyze symbol: `f"{ticker}USDT_PERP.A"`
3. Fetch 90-day daily OI history per symbol
4. Compute derived features: `oi_change_1d` (pct_change), `oi_change_7d` (pct_change n=7)
5. **Fetch OHLCV for volume** — Coinalyze `/ohlcv-history` returns `v` (volume) per day. Join by timestamp to compute `oi_volume_ratio = open_interest / volume`. Guard against division by zero:
   ```python
   # Build volume lookup from OHLCV history
   volume_by_ts = {h["t"]: h.get("v", 0.0) for h in ohlcv_history}
   
   # Compute ratio with zero-volume guard
   df = df.with_columns(
       pl.when(pl.col("volume") > 0)
       .then(pl.col("open_interest") / pl.col("volume"))
       .otherwise(None)
       .alias("oi_volume_ratio")
   )
   ```
6. **Merge into existing parquet** by updating the `derived` JSON column:
   ```python
   # Build lookup with STRING keys (parquet stores symbol as String)
   oi_lookup = {}
   for row in oi_df.iter_rows(named=True):
       key = (str(row["symbol"]), row["date"])  # ← str() is critical
       oi_lookup[key] = {"open_interest": ..., "oi_change_1d": ..., ...}
   
   # Update each row's derived JSON
   for row in deriv_df.iter_rows(named=True):
       derived = json.loads(row["derived"])
       key = (row["symbol"], row["date"])  # already String in parquet
       if key in oi_lookup:
           derived.update(oi_lookup[key])
   ```

### ⚠️ Pitfall: Symbol Type Mismatch in Parquet Merges

**Symptom:** Merge completes but updates 0 rows despite having valid OI data.

**Root cause:** The parquet file stores `symbol` as **String** (e.g. `"5426"`), but the OI DataFrame uses **Int64** (e.g. `5426`). Tuple keys `(5426, date)` ≠ `("5426", date)`.

**Fix:** Always cast to `str()` when building the lookup dict from the OI DataFrame:
```python
key = (str(row["symbol"]), row["date"])
```

### Coverage (2026-06-20)

- 69/87 universe symbols got OI data (18 tokens lack perp markets on Coinalyze)
- 2,721 rows updated out of 136,825 total (only last 90 days have OI)
- 2,681 rows have `oi_volume_ratio` populated (40 had zero volume)
- Daily cron at 10:00 UTC keeps the rolling 90-day window fresh

### ⚠️ Pitfall: `market` JSON Column is Empty

The original Binance backfill (`backfill_binance.py`) only populated the `derived` JSON column with funding rate data. The `market` JSON column remains empty `{}` for all rows — it does NOT contain volume data. This is why we need Coinalyze's `/ohlcv-history` endpoint to get volume for `oi_volume_ratio`.

### Rate Limit Handling

Coinalyze free tier: 40 calls/min. With 87 symbols:
- **2.0s delay** between calls (not 1.6s — tested, 1.6s triggers 429s)
- **Exponential backoff** on 429: 5s → 10s → 20s retries (3 attempts max)
- Total runtime: ~3 minutes for full universe

## General Pattern: Aggregator APIs for Cross-Exchange Enrichment

When individual exchanges have inconsistent data availability, aggregator APIs fill the gap:

| Data Gap | Aggregator | Notes |
|----------|-----------|-------|
| OI history (all exchanges) | Coinalyze | Free tier, ~90d intraday |
| Funding rate history | Coinalyze, Coinglass | Coinglass has paid tiers |
| Liquidation data | Coinalyze | Per-exchange long/short |
| Long/short ratio | Coinalyze | Exchange-specific |

**Design principle:** Build the aggregator client as a standalone module (`coinalyze.py`), not embedded in exchange adapters. The enrichment is a separate pipeline step that reads from and writes to the DB, not a real-time adapter concern.
