# CLS Query Param Bug Fix

## Problem
When `exchange=None` in `fetch_cls_inputs()`, the CLS_AGGREGATE_SQL still had `$3` for exchange filtering but only 2 parameters were passed, causing:
```
asyncpg.exceptions._base.InterfaceError: the server expects 3 arguments for this query, 2 were passed
```

## Root Cause
The CTE used `WHERE exchange = $3 AND ts >= $1 AND ts < $2` — when exchange is None, `$3` is not supplied but asyncpg requires the parameter count to match.

## Fix
Use `.format()` to conditionally include the exchange filter:
```python
if exchange is None:
    sql = CLS_AGGREGATE_SQL.format(exchange_filter="")
    rows = await conn.fetch(sql, start, end)  # 2 params
else:
    sql = CLS_AGGREGATE_SQL.format(exchange_filter="AND exchange = $3")
    rows = await conn.fetch(sql, start, end, exchange)  # 3 params
```

The SQL uses a `{exchange_filter}` placeholder:
```sql
WITH daily_stats AS (
    SELECT symbol, DATE_TRUNC('day', ts), ...
    FROM market_data_ohlcv
    WHERE ts >= $1 AND ts < $2
    {exchange_filter}
    GROUP BY symbol, DATE_TRUNC('day', ts)
)
SELECT ...
```

## Pattern for future CLS queries
When a query has optional filter parameters, avoid having the SQL string always reference positional params that may not be provided. Use format placeholders instead.
