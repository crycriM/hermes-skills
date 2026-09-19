# Binance OI API Limit Fix - Session Reference

## Problem
During data ingestion diagnosis, discovered that Binance OI backfill was updating zero bars despite API calls appearing to succeed. Root cause was HTTP 400 errors from the Binance `/futures/data/openInterestHist` endpoint when requesting more than 30 days of historical data.

## Error Transcript
```
INFO:httpx:HTTP Request: GET https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&startTime=1764374400000&limit=500 "HTTP/1.1 400 Bad Request"
ERROR:__main__:  Failed to fetch Binance/BTC-USDT: {'msg': \"parameter 'startTime' is invalid.\", 'code': -1130}
```

## Root Cause Analysis
- Binance's `/futures/data/openInterestHist` endpoint only retains **30 days** of historical OI data
- The original `backfill_oi_binance` function used `days=180` parameter directly
- When `startTime` requested data older than 30 days, API returned HTTP 400
- The function checked `if result != "UPDATE 0":` but since no HTTP exception was raised (the request failed before reaching the DB update), the OI backfill loop never executed
- Result: Zero OI bars updated across all symbols

## Fix Implemented
Added lookback capping in `src/market_data/historical_fetch.py`:

```python
# Binance /futures/data/openInterestHist only retains 30 days of data
oi_lookback_days = min(days, 30)

native = adapter._to_native(symbol)
end_ms = int(datetime.now(timezone.utc).replace(
    hour=0, minute=0, second=0, microsecond=0
).timestamp() * 1000)
start_ms = end_ms - oi_lookback_days * 86_400_000
```

## Verification
After fix:
```
INFO:__main__:  Binance/BTC-USDT: 97 hourly bars updated
INFO:__main__:  Binance/ETH-USDT: 97 hourly bars updated
```

## Session Commands
```bash
# Test the fix with limited lookback
uv run python -m src.market_data.historical_fetch \
    --exchanges binance,bybit \
    --backfill-oi \
    --days 30 \
    --limit 2

# Verify results
docker exec -i rankit-timescaledb-1 psql -U rankit -d rankit <<'SQL'
SELECT exchange, symbol, 
       COUNT(*) AS total_bars,
       COUNT(*) FILTER (WHERE open_interest > 0) AS oi_populated
FROM market_data_ohlcv
WHERE exchange IN ('binance', 'bybit')
  AND ts >= NOW() - INTERVAL '5 days'
GROUP BY exchange, symbol
ORDER BY exchange, symbol;
SQL
```