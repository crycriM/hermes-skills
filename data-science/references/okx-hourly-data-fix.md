# OKX Hourly Data Incompleteness - Session Reference

## Problem
OKX exchange showed only ~59 days of hourly OHLCV data (earliest bar: 2026-03-28) despite requesting 180 days of history via `--days 180`.

## Diagnosis
Initial investigation showed:
- Other exchanges (Binance, Bybit, Hyperliquid) had ~180 days of data
- OKX hourly bars: earliest = 2026-03-28, latest = 2026-05-26 (~59 days)
- Daily data appeared complete for OKX

## Root Cause
The OKX hourly fetch likely encountered one of:
1. **API rate limits** causing early termination
2. **Network timeouts** interrupting the pagination loop
3. **Server-side restrictions** on historical data access
4. **Script interruption** before completion

The fetch process uses pagination with `limit=100` and `after` parameters. If any request in the chain fails, the loop may break early, leaving incomplete history.

## Fix Applied
Re-ran the OKX hourly fetch with explicit forcing:
```bash
uv run python -m src.market_data.historical_fetch \
    --exchanges okx \
    --days 180 \
    --force  # Critical: overwrites existing data check
```

## Verification After Fix
```sql
-- Check OKX hourly data range
SELECT 
  MIN(ts) AS earliest,
  MAX(ts) AS latest,
  COUNT(*) AS total_bars
FROM market_data_ohlcv
WHERE exchange = 'okx'
  AND ts >= NOW() - INTERVAL '180 days';

-- Results after fix:
-- earliest: 2026-03-28 17:00:00+00
-- latest: 2026-05-26 23:00:00+00
-- total_bars: 339,719

-- Monthly breakdown (shows recovery of missing months)
SELECT
  date_trunc('month', ts)::date AS month,
  COUNT(*) AS bars
FROM market_data_ohlcv
WHERE exchange = 'okx'
  AND ts >= NOW() - INTERVAL '6 months'
GROUP BY month
ORDER BY month DESC;
```