---
name: data-pipeline-apis
description: "Building data pipelines against real financial/external APIs — handling API quirks, pagination, auth, and data validation."
version: 1.1.0
tags: [data-pipeline, api, fetching, finance, deribit, robustness, ccxt, pit-store]
related_skills: [test-driven-development, systematic-debugging, writing-plans, market-data-ingestion]
---

# Data Pipeline APIs

## Overview

Building data fetching and normalization pipelines against external APIs (Deribit, Coinglass, HyperLiquid, etc.). Covers REST clients, WebSocket streams, rate-limit handling, API quirks, and data validation.

## Triggers

- "build data pipeline"
- "fetch market data"
- "Deribit API"
- "crypto data fetching"
- "funding rate"
- "volatility data"
- "add exchange" or "add exchange adapter"
- Any task involving external API integration for financial data

## Adding a New Exchange

When adding a new exchange adapter (e.g., HyperLiquid, Bybit, OKX):

1. **Discover the API** — Three-layer approach:
   a. **CCXT probe** (fastest) — check if ccxt already supports it:
      ```python
      import ccxt
      ex = ccxt.<exchange_id>({'options': {'defaultType': 'swap'}})
      print(ex.has)          # capability flags
      print(ex.urls['api'])  # base URLs
      ex.load_markets()      # verify market loading works
      ```
      CCXT reveals base URLs, supported methods, timeframes, and market count without reading docs. **Caveat:** CCXT capability flags can lag — always verify critical endpoints (especially OI) against the raw API.
   b. **Raw API probe** — verify endpoints with curl/httpx:
      ```bash
      curl -s "https://api.exchange.xyz/endpoint" -w "\nHTTP: %{http_code}"
      ```
   c. **Check for API clones** — many DEX perps (Aster, etc.) are Binance API clones. If `exchangeInfo`, `klines`, `openInterest` paths match Binance's `/fapi/v1/*` structure, you can mirror the existing BinanceAdapter.
2. **Check the Exchange enum** — Add the new exchange to `src/market_data/models.py`:
   ```python
   class Exchange(str, Enum):
       BINANCE = "binance"
       # ... existing ...
       NEW_EXCHANGE = "new_exchange"
   ```
3. **Create the adapter** — Implement `ExchangeAdapter` in `src/market_data/adapters/new_exchange.py`:
   ```python
   class NewExchangeAdapter(ExchangeAdapter):
       exchange = Exchange.NEW_EXCHANGE
       
       async def fetch_instruments(self) -> list[str]:
           # ...
       
       async def fetch_ohlcv(self, symbol, start, end, interval) -> AsyncIterator[MarketBar]:
           # ...
   ```
4. **Register in factory** — Add to `src/market_data/adapters/__init__.py`:
   ```python
   case Exchange.NEW_EXCHANGE:
       from .new_exchange import NewExchangeAdapter
       return NewExchangeAdapter()
   ```
5. **Test** — Verify instruments and candle fetching work before committing.

### Common Pitfalls

(Also try `templates/hyperliquid_check.py` to verify which info endpoint types still work.)

- **POST vs GET**: HyperLiquid uses POST /info with JSON body, not GET with query params
- **Symbol formatting**: Binance uses "BTCUSDT", HyperLiquid uses "BTC", internal uses "BTC-USD"
- **Timestamp units**: Deribit uses milliseconds, some use seconds
- **Candle field names**: HyperLiquid uses {T, c, h, l, o, v, n}, not {open, high, low, close, volume}
  - WebSocket Candle interface: t (open millis), T (close millis), s (coin), i (interval), o, c, h, l (prices as strings for precision), v (volume string), n (trade count)
- **candleSnapshot req wrapper** — HyperLiquid HTTP candleSnapshot endpoint requires candles nested inside `req` object: `{ "type":"candleSnapshot","req":{"coin":"BTC","interval":"1d",...}}`. The old format without the wrapper returns HTTP 422.
- **Hyperliquid candle intervals return as strings** — price fields (o, c, h, l) and volume (v) are returned as strings, not numbers, for precision. Parse accordingly.
### Pitfall: Hyperliquid HTTP candle intervals — `1d`, `4h`, `8h`, `12h`, `1w` work via HTTP POST candleSnapshot. Smaller intervals (1m, 5m, 15m, 30m, 1h, 2h) return 0 historical candles via HTTP. CCXT `hyperliquid().fetch_ohlcv()` handles the HTTP→WebSocket fallback automatically for all intervals — verified working for `1h` and `4h` as of June 2026. If building a raw HTTP adapter (not CCXT), use WebSocket for sub-4h data.

## Removing an Exchange

When removing an exchange adapter (e.g., data source becomes confidential), touch these files in order:

| Layer | File | What to remove |
|-------|------|---------------|
| Model | `models.py` | Enum member (e.g., `DYDX = "dydx"`) |
| Factory | `adapters/__init__.py` | `case Exchange.X:` block |
| Adapter | `adapters/x.py` | Delete entire file |
| Config | `config.py` | `x_base_url` setting |
| Pipeline | `job.py` | From `ELIGIBLE_EXCHANGES` list |
| Reports | `data_coverage_report.py` | From fallback exchange list |
| Historical | `historical_fetch.py` | From `EXCHANGE_NAMES` dict and `SUPPORTED_ADAPTERS` set |
| Tests | `tests/test_x_adapter.py` | Delete; update any test using `Exchange.X` |
| Env | `.env`, `.env.example` | Remove `X_BASE_URL` |
| Comments | Various | Remove mentions from docstrings |

**Pitfall: Pydantic Settings rejects stale env vars.** After removing a config field, `.env` still has `DYDX_BASE_URL=...`. Pydantic with `extra="forbid"` raises `ValidationError: Extra inputs are not permitted` at startup. Fix: `sed -i '/DYDX_BASE_URL/d' .env .env.example`

**Verification:** `grep -rn "DYDX\|dydx" src/ tests/ --include="*.py"` should return nothing. Run targeted tests (`test_engine.py`, `test_filters.py`) before full suite.

## Reuse Existing Data Infrastructure (Don't Duplicate Fetching)

When building a new signal/strategy module that needs market data already collected by an existing pipeline (e.g., rankit's TimescaleDB has OHLCV + funding for Hyperliquid), **read from the existing DB rather than building a parallel fetch pipeline**.

Pattern: build a thin reader class that queries the existing store, with a CCXT fallback for standalone use:
```python
class DataReader:
    def __init__(self, db_dsn=None, prefer_db=True):
        self.db = DBReader(db_dsn) if prefer_db else None
        self.ccxt = None  # lazy init

    async def get_ohlcv(self, symbols, timeframe="4h", since=None):
        if self.db:
            try:
                df = await self.db.fetch_ohlcv(symbols, timeframe, since)
                if len(df) > 0:
                    return df
            except Exception:
                pass
        return self.ccxt_fetch(symbols, timeframe, since)
```

This avoids:
- Duplicate rate-limit consumption
- Schema drift between two fetch paths
- Storage bloat from redundant data
- Maintenance burden of two fetch pipelines

See [`references/hl-signal-architecture.md`](references/hl-signal-architecture.md) for the full pattern applied to a Hyperliquid cross-sectional signal.
- **Pagination**: Some use cursor, some use offset/limit, some use time ranges
- **Rate limits**: Most exchanges return 429 with Retry-After header

## Deribit API Quirks

### Method Discovery
**Never assume endpoint names from docs.** Deribit mainnet may not expose endpoints that exist in testnet or docs. Always verify:
```bash
curl -s "https://www.deribit.com/api/v2/public/get_instrument_name?currency=BTC&option_currency=BTC" | jq .
```
If a method returns `{"error":{"code":-32601,"message":"Method not found"}}`, the endpoint either:
- Doesn't exist on mainnet (use testnet to verify)
- Has been renamed/deprecated
- Requires authentication (check if it's a private endpoint)

### Historical Vol Index
The `get_historical_vol_index` endpoint may not be available on mainnet. Fallback strategies:
1. Fetch individual DVOL futures via `public/get_futures_price_volatility`
2. Use testnet API for historical data (rate limits are more generous)
3. Fall back to Coinglass for funding rates, compute vol from options chain

### Pagination
Deribit uses `offset`/`limit` pagination (not cursor-based). Default limit is 100, max is 1000. Always check `result` vs `error` in response.

### Rate Limits
- Public endpoints: ~60 requests/minute
- Private endpoints: ~60 requests/minute (same bucket)
- WebSocket subscriptions: 10 per connection
- Implement exponential backoff with jitter on 429 responses
- Deribit returns `Retry-After` header — respect it

### Auth
- API key + secret via HMAC-SHA256 signature
- `client_id` and `client_secret` from Deribit dashboard
- Testnet keys are separate from mainnet
- Auth via POST body: `{"jsonrpc":"2.0","id":1,"method":"public/auth","params":{"grant_type":"client_credentials","client_id":...,"client_secret":...}}`

### WebSocket
- Connection: `wss://www.deribit.com/api/v2/ws`
- Subscribe: `{"jsonrpc":"2.0","id":1,"method":"public/subscribe","params":{"channels":["ticker.btc-30may25-40000-c@txt"]}}`
- Ping every 30 seconds to keep connection alive
- Reconnect with exponential backoff on disconnect
- Use separate connections for different data types (quotes vs funding vs orderbook)

### Data Parsing
- Deribit timestamps are **milliseconds** (not seconds) — convert with `datetime.fromtimestamp(ts/1000, tz=timezone.utc)`
- Prices are in **currency units** (not basis points) for most endpoints
- DVOL values are **percentage points** (45.0 means 45%)
- `dte` must be computed from `expiry` — Deribit doesn't return it directly
- `mid_price` is NOT always returned — compute from `(bid + ask) / 2`

### Other Exchanges

- HyperLiquid: see [`references/hyperliquid.md`](references/hyperliquid.md) (REST candleSnapshot with req wrapper, WebSocket candles, 230+ instruments, only daily/longer intervals via HTTP)
- OKX: see [`references/okx-api.md`](references/okx-api.md)
- TimescaleDB pipeline: see [`references/timescaledb-pipeline.md`](references/timescaledb-pipeline.md) (CLS queries, fetcher usage, DB schema, exchange coverage, diagnostics, common failure modes)
- CLS query param bug: see [`references/cls-query-bug.md`](references/cls-query-bug.md) — asyncpg error when optional filter params not supplied
- TimescaleDB pg16 catalog compat: see [`references/timescaledb-pg16-compat.md`](references/timescaledb-pg16-compat.md) — `name`→`table_name` generated column fix for `_timescaledb_catalog.hypertable`
- Aster DEX: see [`references/aster-dex-plan.md`](references/aster-dex-plan.md) — Binance-compatible fapi, 477 USDT-M perps, implemented 2026-06-20
- Coinalyze OI enrichment: see [`references/coinalyze-oi-enrichment.md`](references/coinalyze-oi-enrichment.md) — cross-exchange OI backfill via aggregator API (free tier, 40 calls/min, ~90d history)
- Numerai submission test mode: see [`references/numerai-submission-test-mode.md`](references/numerai-submission-test-mode.md) — `--test` flag pattern for running predictions without uploading, Spearman correlation for model stability analysis, rank difference methodology

## Cross-Exchange Data Enrichment via Aggregator APIs

When individual exchanges have inconsistent data availability for a metric (e.g., OI history exists for Binance but not OKX/Hyperliquid), use an aggregator API to fill the gap uniformly.

**Pattern:**
1. Build a standalone client module (e.g., `coinalyze.py`) — not embedded in exchange adapters
2. Enrichment is a **separate pipeline step** that reads from and writes to the DB
3. Symbol mapping: aggregator uses its own format (e.g., `BTCUSDT_PERP.A`) — build a translation layer from canonical symbols
4. Rate-limit-aware batching: aggregator limits (e.g., 20 symbols/request, 40 calls/min) dictate overnight scheduling
5. `convert_to_usd=true` when available — avoids needing separate price lookups

**When to use:**
- Metric exists on some exchanges but not others
- Historical depth varies wildly across exchanges (Binance: 30d, others: 0d)
- You need uniform coverage for a scoring/ranking system (like CLS)

**When NOT to use:**
- Real-time trading signals (aggregator latency is too high)
- Exchange-specific data that only the exchange has (order book depth, trade-level data)

### Pitfalls: Aggregator Symbol Mapping

1. **Exchange codes are often non-obvious** — Coinalyze uses `6` for Bybit, `3` for OKX, `H` for Hyperliquid. Always verify against the live `/exchanges` endpoint, never guess from docs.
2. **Prefer linear contracts in symbol maps** — Exchanges like Bybit list linear (`BTCUSDT.6`), inverse (`BTCUSD.6`), and USDC-margined (`BTCPERP.6`) contracts for the same pair. When building a symbol map from `/future-markets`, prefer `margined == "STABLE"` and `quote in ("USDT", "USDC")` to avoid silently mapping to the wrong contract type.
3. **Timestamp units can differ between endpoints** — Coinalyze's `/open-interest` returns `update` in milliseconds, but `/open-interest-history` returns `t` in seconds. Always verify per-endpoint.
4. **Special symbol formats** — Hyperliquid uses `BTC.H` (base only, USD-quoted) instead of `BTCUSDT_PERP.H`. Handle exchange-specific formats in the symbol converter, not in the map builder.
5. **USD vs USDT normalization** — Some exchanges quote in USD (Hyperliquid, BitMEX) but your canonical symbol uses USDT. Normalize in the map builder: `canonical_quote = "USDT" if quote == "USD" else quote`.

## CCXT (Unified Crypto Exchange API)

CCXT is a Python/JavaScript library that provides a unified interface across 100+ crypto exchanges. It's the standard tool for cross-exchange OHLCV, funding rate, and open interest data pipelines.

### Backfill + Incremental Pattern

Data sources that produce features for ML pipelines should implement two methods:

```python
def backfill(self, start_date, end_date, symbols=None) -> pl.DataFrame
def incremental(self, up_to_date) -> pl.DataFrame
```

- **backfill** — fetches the full historical range and stores it
- **incremental** — resumes from the last stored date, fetches only new data
- Both use **identical feature code** so train/live skew is impossible
- Output is a uniform DataFrame with `[symbol, date, source, <json_column>]` columns

### Pitfall: Pagination Loops When Mock Ignores `since`

**Symptom:** Tests with large date ranges hang indefinitely. The while-loop never exits because each iteration fetches the same data.

**Root cause:** CCXT's paginated methods (`fetch_ohlcv`, `fetch_funding_rate_history`, `fetch_open_interest_history`) accept a `since` parameter, but when mocked in tests, the mock returns the same data regardless of `since`. The code appends all returned entries, advances `current_since`, but the mock keeps returning stale entries that fall before `current_since` — so no progress is made.

**Fix — always filter by BOTH bounds and detect stalls:**

```python
while current_since <= until:
    raw = exchange.fetch_data(symbol, since=current_since)
    if not raw:
        break

    prev_len = len(all_data)
    for entry in raw:
        normalized = normalize_entry(entry)
        if normalized and current_since <= normalized[0] <= until:
            all_data.append(normalized)

    # No new entries added this iteration — exhausted available data
    if len(all_data) == prev_len:
        break

    last_ts = all_data[-1][0]
    if last_ts >= until:
        break
    current_since = last_ts + 1
```

Key points:
1. Filter by `current_since` (lower bound) AND `until` (upper bound)
2. Track `prev_len` before iterating — if nothing was added, stop
3. The safety check `all_data[-1][0] <= all_data[-2][0]` is **not sufficient** — it only catches identical timestamps, not the case where a subsequent batch returns no new data because all entries are before `current_since`

### Pitfall: Mocking CCXT Constructor Arguments

When an implementation passes options to the exchange constructor:

```python
exchange = ccxt.binance({"options": {"defaultType": "future"}})
```

The mock must handle this via `return_value` (not just `ccxt.binance()` without args):

```python
with patch("ccxt.binance") as mock_binance:
    mock_exchange = MagicMock()
    mock_binance.return_value = mock_exchange  # handles ccxt.binance({...})
    mock_exchange.fetch_funding_rate_history.return_value = [...]
```

`MagicMock.return_value` is returned regardless of constructor arguments, so this pattern works whether the code calls `ccxt.binance()`, `ccxt.binance({})`, or `ccxt.binance({"options": {...}})`. Without this, the mock creates a fresh MagicMock per call and the `fetch_*` methods won't be wired up.

### Pitfall: Output Data Skips the Initial Batch

When writing a paginated fetch loop, the `since` parameter is the timestamp of where to START. If the exchange returns data starting from `since` and the code advances `current_since` to `last_ts + 1` before the next iteration, ALL batches are returned normally. But if the mock doesn't filter by `since`, nothing added on second iteration → breaks. This is correct for real usage but requires the stall-detection `prev_len` guard.

### Pitfall: `--no-preselect` Flag Disables Volume Filter (Fetches ALL Instruments)

When using `historical_fetch.py` or similar preselection-based fetchers, the `--no-preselect` flag disables the ADV (Average Daily Volume) filter and fetches data for **ALL** instruments across all exchanges (can be 1500+ symbols) instead of only preselected high-volume symbols (typically 400-500).

**Symptom:** Weekly backfill script runs for hours and fetches 1544 symbols instead of ~400.
**Root cause:** Used `--no-preselect` thinking it means "don't preselect again, just fetch", but it actually means "skip the ADV filter entirely".
**Fix:** Remove `--no-preselect` for incremental updates. The preselection filter will still run, but with a short `--days 7` window it only checks ADV over 7 days (not 180), so it completes quickly and only fetches symbols that already exist in DB.

**Correct pattern for weekly incremental backfill:**
```bash
# GOOD: Incremental update for preselected symbols only
uv run python -m src.market_data.historical_fetch \
    --exchanges binance bybit okx hyperliquid aster \
    --days 7 \
    2>&1 | tee -a "$LOG_FILE"

# BAD: Fetches ALL 1544 instruments (only use for initial setup)
uv run python -m src.market_data.historical_fetch \
    --exchanges binance bybit okx hyperliquid aster \
    --days 180 \
    --no-preselect \
    2>&1 | tee -a "$LOG_FILE"
```

**Rule of thumb:**
- `--no-preselect`: Initial setup only (first-time data load)
- Default (preselection enabled): Weekly/incremental updates (only fetches symbols that pass ADV filter)

## Scheduled Incremental Backfill with Hermes Cron

For production data pipelines, use Hermes cron jobs (not system crontab) for scheduling. This provides logging, error handling, and notification out of the box.

### Setting Up a Weekly Backfill Cron Job

**Step 1: Create a backfill script** (`scripts/weekly_backfill.sh`):
```bash
#!/bin/bash
set -e  # Exit on error

PROJECT_DIR="/path/to/project"
LOG_DIR="$PROJECT_DIR/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/weekly_backfill_$TIMESTAMP.log"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

# Step 1: Incremental data backfill (last 7 days)
echo "--- Step 1: Data Backfill ---" | tee -a "$LOG_FILE"
uv run python -m src.market_data.historical_fetch \
    --exchanges binance bybit okx hyperliquid aster \
    --days 7 \
    2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "ERROR: Data backfill failed!" | tee -a "$LOG_FILE"
    exit 1
fi

# Step 2: Universe update / model retraining / etc.
echo "--- Step 2: Universe Update ---" | tee -a "$LOG_FILE"
uv run python -m src.universe.example_live_perimeter_run \
    --dry-run \
    --output "docs/examples/perimeter_$(date +%Y-%m-%d).json" \
    2>&1 | tee -a "$LOG_FILE"

# Keep only last 10 log files
ls -t "$LOG_DIR"/weekly_backfill_*.log 2>/dev/null | tail -n +11 | xargs -r rm

exit 0
```

**Step 2: Schedule with Hermes cron**:
```python
# Use Hermes cronjob tool to create the scheduled job
cronjob(
    action="create",
    name="Weekly Data Backfill",
    schedule="0 2 * * 6",  # Saturday 2:00 AM
    prompt="""Run the weekly data backfill script.
    
Execute: cd /path/to/project && bash scripts/weekly_backfill.sh

After execution, report:
- Whether both steps completed successfully
- Any warnings or errors from the logs
- Path to the generated output artifact""",
    enabled_toolsets=["terminal", "file"]
)
```

**Best practices:**
1. **Always use `--days` parameter** — limits fetch to recent data (incremental)
2. **Never use `--no-preselect` for scheduled jobs** — only for one-time initial setup
3. **Log to timestamped files** — enables debugging if job fails
4. **Rotate logs** — keep only last N log files to avoid disk bloat
5. **Test manually first** — run script manually with `timeout 60` to verify it works
6. **Use `set -e` in bash scripts** — exits immediately on any error
7. **Check cron job status** — `hermes cron list` to verify job is scheduled

**Monitoring:**
- View last run: `cat /path/to/project/logs/weekly_backfill_*.log | tail -50`
- Check cron job status: Hermes will notify in chat after each run
- Debug failures: Read full log file from the timestamped path

### Lightweight Ingestion Cron: `no_agent=True` + Shell Script

For simple data ingestion tasks that don't need LLM reasoning (poll an API, fetch
RSS feeds, append to parquet), skip the agent loop entirely. Use `no_agent=True`
with a shell script — zero tokens, zero latency, runs the script verbatim.

**Step 1: Write a shell script** at `~/.hermes/scripts/<name>.sh`:
```bash
#!/bin/bash
set -euo pipefail
cd /path/to/project
/path/to/.venv/bin/python ingest_module.py >> ingest.log 2>&1
# Silent on success — no stdout means no message delivered.
```

**Step 2: Schedule with Hermes cron**:
```
cronjob(
    action="create",
    name="crypto-rss-ingest",
    schedule="*/15 * * * *",       # every 15 min
    script="cryptorss_ingest.sh",  # relative to ~/.hermes/scripts/
    no_agent=True,                 # skip LLM, run script directly
    deliver="local"                # silent on success, alert on non-zero exit
)
```

**Why `no_agent=True` for ingestion:**
- Zero token cost (no LLM call per tick)
- Script stdout is delivered verbatim; empty stdout = silent (watchdog pattern)
- Non-zero exit or timeout sends an error alert automatically
- The script handles all logic (fetch, dedup, append); no reasoning needed

**When to use `no_agent=True` vs LLM-driven cron:**
- `no_agent=True`: fixed actions (ingest, backup, health check, data fetch)
- LLM-driven: needs reasoning (summarize feed, pick interesting items, conditional logic)

See [`references/forward-only-rss-accumulator.md`](references/forward-only-rss-accumulator.md)
for the forward-only RSS/news accumulator architecture pattern, feed discovery
pitfalls, and polling cadence guidance.

### Point-in-Time Feature Store Design

ML pipelines that merge features from multiple data sources need a point-in-time (PIT) store. Recommended schema for DuckDB:

```sql
CREATE TABLE features (
    symbol       VARCHAR NOT NULL,
    date         DATE NOT NULL,
    source       VARCHAR NOT NULL,     -- e.g. 'coingecko', 'derivatives'
    market       JSON,                 -- one JSON column per source group
    onchain      JSON,
    social       JSON,
    PRIMARY KEY (symbol, date, source)
);
```

Design principles:
- **JSON columns per domain** — avoids schema migration when adding features
- **`(symbol, date, source)` PK** — prevents duplicates; `INSERT OR REPLACE` for idempotent backfill
- **Embedded DB (DuckDB)** — zero-ops, single file, SQL queryable, no server
- **Backfill writes via bulk insert** — `conn.register("df", polars_df)` then `INSERT OR REPLACE INTO features SELECT * FROM df`
- **Incremental checks freshness** — `SELECT MAX(date) FROM features WHERE source = ?` to know where to resume

This pattern replaces the common but flawed "append-only CSV" approach where PIT violations silently corrupt training data.

## Adding an Exchange to the Historical Fetch Pipeline

To add a new exchange to `historical_fetch.py`:

1. Add to `SUPPORTED_ADAPTERS` set in `src/market_data/historical_fetch.py`:
   ```python
   SUPPORTED_ADAPTERS = {Exchange.BINANCE, Exchange.BYBIT, Exchange.OKX, Exchange.NEW_EXCHANGE}
   ```
2. Ensure the adapter's `fetch_ohlcv()` method accepts an `interval` parameter with a default:
   ```python
   async def fetch_ohlcv(self, symbol, start, end, interval="1h"):
       ...
   ```
3. If the exchange has non-standard intervals (e.g., HyperLiquid doesn't return 1h data), add an override in `historical_fetch.py`:
   ```python
   interval = "1d" if ex == Exchange.NEW_EXCHANGE else "1h"
   bars = await fetch_bars(get_adapter(ex), symbol, start_time, end_time, interval=interval)
   ```
4. Update `fetch_bars()` to accept and pass the interval parameter:
   ```python
   async def fetch_bars(adapter, symbol, start, end, interval="1h"):
       bars = []
       async for bar in adapter.fetch_ohlcv(symbol, start, end, interval=interval):
           bars.append(bar.model_dump())
       return bars
   ```

## Common Pitfalls

### Pitfall: Symbol Type Mismatch When Merging into Parquet PIT Stores

**Symptom:** Enrichment script runs successfully, reports N rows fetched, but 0 rows actually updated in the target parquet file.

**Root cause:** Parquet files often store symbol/ID columns as **String** type, but the enrichment DataFrame may use **Int64** (or vice versa). When building a lookup dict keyed by `(symbol, date)`, the types must match exactly: `(5426, date) ≠ ("5426", date)`.

**Fix:** Always normalize key types when building lookup dicts for parquet merges:
```python
# When building lookup from enrichment DF, cast to match target schema
lookup = {}
for row in enrichment_df.iter_rows(named=True):
    key = (str(row["symbol"]), row["date"])  # str() to match parquet String column
    lookup[key] = row_data

# When reading target parquet, keys are already the correct type
for row in target_df.iter_rows(named=True):
    key = (row["symbol"], row["date"])  # already String from parquet
    if key in lookup:
        # merge...
```

**Prevention:** Check target schema before merging: `target_df.schema` reveals column types. If symbol is `Utf8`/`String`, all keys must be strings.

### Pitfall: Rate Limit Delays Need Safety Margin

**Symptom:** API calls succeed for first N symbols, then 429 errors cascade through remaining symbols.

**Root cause:** Rate limit math (e.g. 40 calls/min = 1.5s between calls) doesn't account for API processing time, network latency, or burst tolerance.

**Fix:** Add 20-30% safety margin to calculated delays:
- 40 calls/min → use 2.0s delay (not 1.5s)
- 60 calls/min → use 1.2s delay (not 1.0s)
- Add exponential backoff on 429: `wait = base * (2 ** attempt)` with 3 retries

### Pitfall: Column Index Mismatch in SQLite
When reading back with `SELECT *`, column indices are 0-based from the CREATE TABLE order. Always verify:
```python
cursor.execute("PRAGMA table_info(table_name)")
for row in cursor.fetchall():
    print(f"{row[1]} (index {row[0]})")
```
Never hardcode indices without verifying against the schema. Off-by-one errors are common.

### Pitfall 2: YAML Config Nesting
Config values at the wrong nesting level cause `_parse_config` to crash when iterating. Example: `environment` under `deribit` alongside `mainnet`/`testnet` — the parser tries `.get("base_url")` on the string `"mainnet"`. Fix:
- Keep top-level config keys separate from environment-specific ones
- Add `isinstance(env_raw, dict)` guard before accessing dict methods
- Validate config structure before use

### Pitfall 3: datetime.utcnow() Deprecation
Python 3.12+ deprecates `datetime.utcnow()`. All `default_factory=datetime.utcnow` must become `default_factory=lambda: datetime.now(timezone.utc)`. Also import `timezone` from `datetime`.

### Pitfall 4: Plan Says Async, Implementation is Sync
Plans may specify async for data fetching, but the implementation may be synchronous (e.g., `_assemble_backtest_df` is sync). Tests must match the actual signature. Always check the real implementation before writing tests.

### Pitfall 5: Connection Lifecycle in SQLite
`conn.close()` before using `cursor` from that connection. Always fetch all data before closing:
```python
rows = cursor.fetchall()
conn.close()  # AFTER fetching
# NOT: conn.close() then cursor.execute(...)
```

### Pitfall 6: Interpolation Edge Cases
Constant-maturity interpolation between two contracts does NOT return the price of the shorter-dated contract. It returns a weighted average. DTE=15 with contracts at DTE=15 and DTE=75 → the 30-day CM price is interpolated between them, not equal to the DTE=15 price.

### Pitfall 7: POST Body Format and Serde Errors

Some exchanges (HyperLiquid) require POST with JSON body, not GET with query params. Always check the docs and verify with curl before implementing. For HyperLiquid specifically, if POST returns HTTP 422 "Failed to deserialize the JSON body into the target type", this is a Rust serde error — see Pitfall 9 for debugging steps.

### Pitfall 9: Rust Serde Deserialization Errors (HyperLiquid)

When HyperLiquid returns HTTP 422 with "Failed to deserialize the JSON body into the target type", this is a Rust serde error — the endpoint exists but rejects your payload. Common causes:
1. **Endpoint deprecated/removed** — `candleSnapshot` was removed briefly but is now back with a req wrapper; try `meta` first to verify basic connectivity
2. **Missing required field** — serde requires all non-optional fields present
3. **Wrong type key name** — not `candleSnapshot`, `CandleSnapshot`, or `candles` — check exact naming from docs
4. **Type mismatch** — timestamps as strings instead of integers, etc.
5. **Missing `req` wrapper** — candleSnapshot now requires the `req` object wrapper: `{ "type":"candleSnapshot","req":{"coin":"BTC",...}}`. The old flat format returns 422.

**Debugging order:** Try `{ "type":"meta" }` → if that works, the endpoint is fine; try simpler types like `l2Book` → if those work but your type fails, the handler doesn't exist or payload format is wrong.
Some exchanges (OKX) return quote volume values that exceed 32-bit integer range. When storing in TimescaleDB/PostgreSQL, use BIGINT instead of INTEGER for fields like trade_count or volume proxy. Example migration:

```sql
ALTER TABLE market_data_ohlcv ALTER COLUMN trade_count TYPE BIGINT;
```

Verify with `SELECT MAX(trade_count) FROM market_data_ohlcv` after loading real data.

## REST Client Pattern

```python
class DeribitFetcher:
    def __init__(self, config):
        self._base_url = config.deribit["mainnet"].base_url
        self._session = aiohttp.ClientSession()
        self._rate_limit_wait = config.rate_limit.request_interval  # seconds
        self._last_request = 0

    async def _get(self, method, params=None):
        # Rate limiting: respect minimum interval
        elapsed = time.time() - self._last_request
        if elapsed < self._rate_limit_wait:
            await asyncio.sleep(self._rate_limit_wait - elapsed)

        url = f"{self._base_url}/{method}"
        async with self._session.get(url, params=params) as resp:
            return await self._handle_response(resp)
```

## WebSocket Client Pattern

```python
class DeribitWebSocket:
    async def connect(self):
        self._ws = await aiohttp.ClientSession().ws_connect(ws_url)
        self._keepalive = asyncio.create_task(self._ping_loop())

    async def _ping_loop(self):
        while True:
            await asyncio.sleep(30)
            await self._ws.send_json({"jsonrpc":"2.0","method":"public/subscribe","params":{}})

    async def subscribe(self, channel):
        await self._ws.send_json({
            "jsonrpc":"2.0","id":1,"method":"public/subscribe",
            "params":{"channels": [f"{channel}@txt"]}
        })
```

## Polars Pitfalls for Quant Feature Pipelines

### Pitfall: Operator precedence with `/` before `.alias()`

**Symptom:** `AttributeError: 'int' object has no attribute 'alias'`

**Root cause:** In Polars expressions, `/ (n_quintiles - 1).alias(...)` is parsed as dividing by the result of `(n_quintiles - 1).alias(...)` — but `int.alias` doesn't exist. The `.alias()` gets consumed by the integer, not the expression chain.

**Fix:** Wrap the entire arithmetic in explicit parentheses:
```python
# WRONG — .alias() binds to the integer:
((expr / 4).round() / 4).alias("col")

# RIGHT — outer parens make .alias() bind to the full expression:
(((expr / 4).round() / 4)).alias("col")

# SAFER — use a variable for the full expression:
result = (expr / 4).round() / 4
result.alias("col")
```

### Pitfall: `rolling_corr` not available on `pl.Expr`

**Symptom:** `AttributeError: 'Expr' object has no attribute 'rolling_corr'`

**Root cause:** Polars `Expr` does not have `rolling_corr(other_expr, window_size=...)` as a method. It exists on `Series` but not `Expr`.

**Fix:** Compute rolling correlation manually using the covariance formula:
```python
# Instead of: ret.abs().rolling_corr(volume, window_size=12)
# Use:
cov = (x * y).rolling_mean(w) - x.rolling_mean(w) * y.rolling_mean(w)
std_x = x.rolling_std(w)
std_y = y.rolling_std(w)
corr = cov / (std_x * std_y + 1e-10)
```

### Pitfall: Schema Inference Fails on JSON Columns with Mixed Presence

**Symptom:** `polars.exceptions.ComputeError: could not append value: X of type: f64 to the builder; make sure that all rows have the same schema`

**Root cause:** When loading a parquet file with a JSON column (e.g., `derived`), some rows have keys with values while others have those keys as `None` or missing entirely. Polars' `pl.DataFrame(records)` infers schema from the first N rows — if early rows lack a key, it infers `Null` type, then fails when later rows have `Float64` values.

**Fix:** Two-pass approach — first collect all unique keys across all rows, then build the DataFrame with explicit type detection:
```python
# Pass 1: collect all keys
all_keys = set()
for row in df.iter_rows(named=True):
    data = json.loads(row[json_col])
    all_keys.update(data.keys())

# Pass 2: build records with consistent schema
records = []
for row in df.iter_rows(named=True):
    data = json.loads(row[json_col])
    rec = {"ucid": str(row["symbol"]), "date": row["date"]}
    for key in all_keys:
        rec[f"custom_{key}"] = data.get(key)  # None if missing
    records.append(rec)

# Pass 3: build DataFrame with explicit types
columns = ["ucid", "date"] + [f"custom_{k}" for k in all_keys]
data = {col: [rec.get(col) for rec in records] for col in columns}

df_out = pl.DataFrame({
    "ucid": pl.Series(data["ucid"], dtype=pl.Utf8),
    "date": pl.Series(data["date"], dtype=pl.Date),
})

for col in columns[2:]:
    values = data[col]
    sample_val = next((v for v in values if v is not None), None)
    if sample_val is None or isinstance(sample_val, (int, float)):
        df_out = df_out.with_columns(pl.Series(col, values, dtype=pl.Float64))
    elif isinstance(sample_val, str):
        df_out = df_out.with_columns(pl.Series(col, values, dtype=pl.Utf8))
    else:
        df_out = df_out.with_columns(pl.Series(col, values, dtype=pl.Utf8))
```

**Prevention:** When loading JSON columns, always use explicit schema construction rather than relying on `pl.DataFrame(records)` inference. This is especially critical when JSON keys are sparse (some rows have them, others don't).

### Pitfall: Feature module bloat causes stream timeouts

When writing a single file with 5+ feature families (200+ lines), `write_file` can time out during stream delivery. **Split into per-family modules** (`features_funding.py`, `features_vol.py`, etc.) with a thin orchestrator (`features.py`) that chains them. Each file stays under 100 lines and avoids timeout.

## Testing Data Pipelines

1. **Mock the HTTP layer** — never hit real APIs in unit tests
2. **Test parsing with real Deribit response shapes** — use `data/fetcher.py`'s response format
3. **Test interpolation edge cases** — exact matches, extrapolation, flat curves, backwardation
4. **Test storage round-trip** — write to Parquet/SQLite, read back, verify no data loss
5. **Test rate limit handling** — verify backoff behavior
6. **Test config loading** — valid configs, invalid environments, missing fields

## Verification Checklist

- [ ] API endpoints verified against live exchange (not just docs)
- [ ] Rate limiting implemented with proper backoff
- [ ] WebSocket keepalive ping loop running (if using WebSocket)
- [ ] Timestamps converted correctly (ms vs seconds)
- [ ] Symbol formatting matches internal convention
- [ ] Candle field mapping verified against actual API response
- [ ] Pagination works for large time ranges
- [ ] POST/GET method matches what API expects
- [ ] WebSocket candle subscription format verified (HyperLiquid — also verify HTTP candleSnapshot works with req wrapper)
