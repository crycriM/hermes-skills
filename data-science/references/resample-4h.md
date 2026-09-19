# 4h OHLCV — Direct Fetch and Resample

**Table:** `market_data_ohlcv_4h` — hypertable, 1-day chunks, idempotently created by `init_db()`.

## Approach A: Direct Fetch (preferred)

Fetch 4h bars directly from exchange APIs using `historical_fetch.py --interval 4h`:

```bash
python -m src.market_data.historical_fetch \
    --exchanges binance bybit okx hyperliquid \
    --interval 4h \
    --no-preselect \
    --days 180
```

This writes directly to `market_data_ohlcv_4h` without touching the 1h table.

**Key mechanics:**
- `target_table = "market_data_ohlcv_4h"` when `args.interval == "4h"`
- `check_existing()` queries the 4h table with the `table` parameter
- Insert uses `insert_4h_bar`/`insert_4h_batch` (separate upsert functions in `db.py`)
- Coverage heuristic: expects ≥5 bars/day (6 for perfect 4h coverage)
- OI backfill is skipped for 4h (only relevant for 1h)
- Force delete targets the 4h table

**Bars count:** ~1,080 per symbol for 180 days (vs ~4,320 for 1h).

## Approach B: Resample from 1h

If 1h data already exists, resample in-place:

```bash
python -m src.market_data.resample_4h            # full history
python -m src.market_data.resample_4h --days 90   # last 90 days
python -m src.market_data.resample_4h --verbose    # debug output
```

## SQL (in `db.py`)

```sql
INSERT INTO market_data_ohlcv_4h (...)
SELECT
    symbol,
    time_bucket('4 hours', ts) AS ts,
    exchange,
    FIRST(open, ts)    AS open,
    MAX(high)          AS high,
    MIN(low)           AS low,
    LAST(close, ts)    AS close,
    SUM(volume)        AS volume,
    LAST(open_interest, ts) AS open_interest,
    AVG(funding_rate)  AS funding_rate,
    0                  AS trade_count
FROM market_data_ohlcv
WHERE ts >= $1 AND ts < $2
GROUP BY symbol, exchange, time_bucket('4 hours', ts)
ON CONFLICT (symbol, ts, exchange) DO NOTHING
```

## Batch Processing (resample only)

Iterates in 7-day windows. Safe to interrupt and resume.

## Connection Quirk

Settings use `postgresql+asyncpg://` (SQLAlchemy convention). asyncpg.connect() needs `postgresql://`. Both scripts strip the scheme.
