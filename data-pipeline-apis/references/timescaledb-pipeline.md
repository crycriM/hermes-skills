# TimescaleDB Pipeline Reference

## Schema

Table `market_data_ohlcv` with columns:
- `symbol` TEXT NOT NULL
- `ts` TIMESTAMPTZ NOT NULL  
- `exchange` TEXT NOT NULL (binance/bybit/okx/hyperliquid)
- `open`, `high`, `low`, `close`, `volume` DOUBLE PRECISION
- `open_interest` DOUBLE PRECISION
- `funding_rate` DOUBLE PRECISION
- `trade_count` BIGINT (after migration for OKX volCcyQuote overflow)

Primary key: `(symbol, ts, exchange)` — upserts on conflict.

Hypertable on `ts` with 1-day chunk interval.

## CLS Queries

### Per-exchange CLS pass (25+ days of data in last 30 days):
```sql
SELECT symbol, exchange, count(DISTINCT ts::date) as data_days
FROM market_data_ohlcv
WHERE ts >= NOW() - INTERVAL '30 days'
GROUP BY symbol, exchange
HAVING count(DISTINCT ts::date) >= 25
ORDER BY exchange, symbol;
```

### Per-symbol CLS pass (across all exchanges):
```sql
SELECT symbol, count(DISTINCT exchange) as sources, count(DISTINCT ts::date) as days
FROM market_data_ohlcv
WHERE ts >= NOW() - INTERVAL '30 days'
GROUP BY symbol
HAVING count(DISTINCT ts::date) >= 25
ORDER BY symbol;
```

### Universe eligibility check (30+ distinct symbols):
```sql
SELECT count(DISTINCT symbol) FROM market_data_ohlcv WHERE exchange = '<exchange>';
```

## Historical Fetcher Usage

```bash
# Fetch from a single exchange
uv run python -m src.market_data.historical_fetch --exchanges hyperliquid --days 60 --limit 50

# Fetch from multiple exchanges (Binance hourly, Hyperliquid daily)
uv run python -m src.market_data.historical_fetch --exchanges binance,hyperliquid --days 60

# Dry run (fetch but don't insert)
uv run python -m src.market_data.historical_fetch --exchanges hyperliquid --days 60 --dry-run --limit 10
```

## Exchange Data Coverage Summary (May 2026)

### OHLCV Table

| Exchange | Bars | Symbols | Date Range | Span | Avg bars/day |
|---|---|---|---|---|---|
| Binance | 2,131,767 | 513 | 2025-11-28 → present | 180d | 11,843 |
| Bybit | 1,576,803 | 411 | 2025-11-28 → present | 180d | 8,762 |
| Hyperliquid | 678,115 | 158 | 2025-11-28 → present | 180d | 3,767 |
| OKX | 339,719 | 240 | 2026-03-28 → present | **59d** ⚠️ | 5,734 |

### Daily Table (market_data_daily)

| Exchange | Bars | Symbols | Earliest | Latest |
|---|---|---|---|---|
| Binance | 91,508 | 525 | 2025-11-28 | present |
| Bybit | 68,610 | 428 | 2025-11-28 | present |
| Hyperliquid | 34,202 | 193 | 2025-11-28 | present |
| OKX | 200,009 | 333 | 2022-06-17 | present |

Note: OKX daily data extends back to 2022 (preselection phase works fine), but hourly history is truncated to 59 days. Hyperliquid uses daily HTTP REST (1h not available via REST — use WebSocket for sub-daily).

## Key Code Changes for Exchange Integration

### historical_fetch.py updates needed:
1. Add exchange to `SUPPORTED_ADAPTERS` set
2. Update `fetch_bars()` to accept interval parameter
3. Add exchange-specific interval override (HyperLiquid uses "1d" instead of "1h")
4. Pass interval to the adapter's fetch_ohlcv method

### DB schema updates:
- `trade_count` column must be BIGINT (not INTEGER) for OKX volCcyQuote overflow protection

## CLS Query Param Bug

When `exchange=None` in `fetch_cls_inputs()`, the CLS_AGGREGATE_SQL still had `$3` for exchange filtering but only 2 parameters were passed. Fix: use `.format(exchange_filter=...)` pattern — empty string when None, `"AND exchange = $3"` when not None. See `references/cls-query-bug.md` for full details.

## Data Quality Notes

- OKX has ~17 zero-volume bars (stock-like symbols: AAPL, AMD, AMZN) — filtered out by CLS query's `WHERE daily_volume > 0`
- Hyperliquid adapter returns 0.0 for OI/funding rate — no REST endpoints available
- Kafka consumer functional but empty — no real-time messages (normal for historical-only pipeline)

---

## Ingestion Diagnostics

### Connection via docker exec

When `psql` fails with `pg_wrapper` errors (no `postgresql-client-<version>` installed), bypass by connecting via the container directly:

```bash
docker exec -i rankit-timescaledb-1 psql -U rankit -d rankit <<'EOSQL'
SELECT ...;
EOSQL
```

The docker container's POSTGRES_PASSWORD env var may be masked in `docker inspect` output — check via `docker exec bash -c 'echo $POSTGRES_PASSWORD'` to get the actual value.

### Diagnostic Query Suite

Run these after any major ingestion run to verify data quality:

#### 1. Overview
```sql
SELECT
  exchange,
  COUNT(*) AS total_bars,
  COUNT(DISTINCT symbol) AS distinct_symbols,
  MIN(ts)::date AS earliest_date,
  MAX(ts)::date AS latest_date,
  ROUND(EXTRACT(epoch FROM MAX(ts) - MIN(ts))/86400) AS span_days
FROM market_data_ohlcv
GROUP BY exchange
ORDER BY exchange;
```

Look for: exchanges with significantly shorter spans than others (e.g. OKX at 59d vs 180d for binance).

#### 2. Open Interest Coverage
```sql
SELECT
  exchange,
  COUNT(*) AS total_bars,
  COUNT(open_interest) FILTER (WHERE open_interest IS NOT NULL) AS oi_populated,
  ROUND(100.0 * COUNT(open_interest) FILTER (WHERE open_interest IS NOT NULL) / NULLIF(COUNT(*),0), 1) AS oi_pct,
  COUNT(DISTINCT symbol) FILTER (WHERE open_interest IS NOT NULL) AS symbols_with_oi
FROM market_data_ohlcv
GROUP BY exchange
ORDER BY exchange;
```

Then check for *zero* OI (distinct from NULL):
```sql
SELECT exchange,
  COUNT(*) FILTER (WHERE open_interest IS NULL) AS null_oi_bars,
  COUNT(*) FILTER (WHERE open_interest = 0) AS zero_oi_bars
FROM market_data_ohlcv
GROUP BY exchange
ORDER BY exchange;
```

**Important**: NULL OI means backfill never ran for that bar. Zero OI means backfill *ran* but produced zero — usually a bug (timestamp mismatch, API returned 0, math error). They need different fixes.

#### 3. Recency (staleness check)
```sql
SELECT
  exchange,
  ROUND(EXTRACT(epoch FROM (NOW() - MAX(ts)))/3600, 1) AS hours_since_latest
FROM market_data_ohlcv
GROUP BY exchange
ORDER BY exchange;
```

A single exchange lagging by ~1 day while others are current often points to a timezone truncation bug (`replace(hour=0, minute=0…)` cutting off the last day before midnight in that exchange's timezone).

#### 4. Gap Analysis (low-density days)
```sql
SELECT exchange, ts::date AS day, COUNT(*) AS bars
FROM market_data_ohlcv
GROUP BY exchange, ts::date
HAVING COUNT(*) < 10
ORDER BY exchange, day;
```

#### 5. Bottom symbols (lowest bar counts)
```sql
SELECT exchange, symbol, COUNT(*) AS bars
FROM market_data_ohlcv
GROUP BY exchange, symbol
ORDER BY exchange, bars ASC
LIMIT 12;
```

Symbols with far fewer bars than peers are likely new listings or had fetch errors. Cross-reference with `market_data_daily` to confirm.

#### 6. Daily table overview
```sql
SELECT exchange,
  COUNT(*) AS bars,
  COUNT(DISTINCT symbol) AS distinct_symbols,
  MIN(ts)::date AS earliest,
  MAX(ts)::date AS latest
FROM market_data_daily
GROUP BY exchange
ORDER BY exchange;
```

The daily table should extend further back than OHLCV (it's the preselection data). If daily is empty or truncated, the preselection phase failed.

### Common Failure Modes

#### FAILURE 1: Exchange hourly truncated (e.g. OKX 59d instead of 180d)
**Symptoms**: Span significantly shorter than other exchanges. Daily data fine, hourly cut off.
**Root causes**: Rate limiting aborted fetch early; `--days` argument not passed through correctly; the exchange adapter returned fewer historical candles than expected.
**Fix**: Re-run with `--force --days 180` for that exchange:
```bash
uv run python -m src.market_data.historical_fetch --exchanges okx --days 180 --force
```

#### FAILURE 2: Open Interest all zeros (Binance, Hyperliquid)
**Symptoms**: OI column 100% populated but every value is 0. No NULLs.
**Root causes**:
- **Binance**: `backfill_oi_binance` matches OI snapshots to hourly bars via `DATE_TRUNC('hour', ts)`. If timestamps differ by more than the truncation (e.g. OI API returns timestamps that truncate to a different hour boundary than the bar), the UPDATE returns "UPDATE 0" but the code counts it as success because it only checks `result != "UPDATE 0"` — a false negative.
- **Hyperliquid/OKX/dYdX**: `backfill_oi_current` stores 0.0 returned by `fetch_open_interest()` when the API doesn't support OI queries. The fallback writes 0 back to the most recent bar but doesn't touch historical bars.

**Fixes**:
- Binance: Verify the truncation alignment between OI API timestamps and bar timestamps. Add a `WHERE open_interest = 0` guard to skip bars that would be set to zero.
- Hyperliquid/OKX: The adapter should return NULL (or skip) when OI is not available, not 0.0. Fix `fetch_open_interest()` to raise `NotImplementedError` or return None.

#### FAILURE 3: Exchange 1 day behind (Bybit)
**Symptoms**: Latest bar is ~36h ago vs ~35h for other exchanges.
**Root cause**: `end_time = now().replace(hour=0, minute=0, second=0, microsecond=0)` — if an exchange's clock is slightly ahead or the API returns bars past midnight UTC, the truncation excludes the current day's data.
**Fix**: Add a small fudge factor (e.g. `timedelta(hours=1)`) to end_time, or query from two windows.

#### FAILURE 4: No canonical view
**Symptoms**: `FROM market_data_daily_canonical` fails. `SELECT * FROM pg_views WHERE viewname LIKE '%canon%'` returns empty.
**Root cause**: `refresh_canonical_view()` creates the view but the schema migration may not have been run, or the view definition was dropped.
**Fix**: Check `pg_views` to confirm. If missing, re-define the view in `db.py`'s `init_db()`:
```sql
CREATE OR REPLACE VIEW market_data_daily_canonical AS
SELECT DISTINCT ON (symbol, exchange) symbol, ts, exchange, close, volume,
  COALESCE(open_interest, 0) AS open_interest
FROM market_data_daily
ORDER BY symbol, exchange, ts DESC;
```
