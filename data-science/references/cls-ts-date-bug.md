# CLS SQL `ts` vs `ts::date` — Cross-Exchange Day Splitting Bug

## The Bug

The CLS aggregation query (`src/universe/cls_queries.py`) aggregates daily OHLCV data across exchanges. In the `per_exchange_day` CTE, the `ts` column was aliased as `trade_date` without casting to DATE:

```sql
per_exchange_day AS (
    ...
    ts             AS trade_date,   -- TIMESTAMPTZ, not DATE
    ...
),
per_symbol_day AS (
    SELECT symbol_norm, trade_date, SUM(daily_volume) ...
    FROM per_exchange_day
    GROUP BY symbol_norm, trade_date  -- groups by exact timestamp, not calendar day
),
```

OKX stores daily bars at 16:00 UTC (midnight KST+8). Binance and Hyperliquid store at 00:00 UTC. The GROUP BY on TIMESTAMPTZ treats these as different values, splitting each calendar day into 2+ rows:

```
Date           Exchange       Timestamp              Result
─────────────  ─────────────  ─────────────────────  ──────────────────────
2025-11-29     binance        2025-11-29 00:00 UTC   Group 1 (2 exchanges)
2025-11-29     hyperliquid    2025-11-29 00:00 UTC   Group 1
2025-11-29     okx            2025-11-29 16:00 UTC   Group 2 (1 exchange)
```

## Impact

- `days_of_data` in CLS output is ~2× the lookback window (359 for 180-day)
- Cross-exchange ADV is ~50% of the true combined value
- Median is computed over split rows (half-volumes), further distorting rankings
- All symbols are affected, not just those on OKX

## Example: XLM-USDT

```
Before fix:  ADV = $22M,  days_of_data = 359
After fix:   ADV = $52M,  days_of_data = 181
```

## The Fix

```sql
-- BEFORE (broken):
ts             AS trade_date,

-- AFTER (fixed):
ts::date        AS trade_date,
```

This ensures all exchanges' data for the same calendar day is summed together before median computation.

## Verification

```sql
-- Check that days_of_data ≤ lookback_days
SELECT symbol, days_of_data 
FROM cls_inputs  -- or wherever CLS results are stored
WHERE days_of_data > 180;

-- Check combined ADV is reasonable (should be sum of all exchanges)
SELECT symbol, adv 
FROM cls_inputs 
WHERE symbol = 'BTC-USDT';  -- should be ~$25-30B, not ~$9B
```

## Broader Lesson: Data Quality Debugging Pattern

When cross-exchange aggregation produces unexpected results, follow this pattern:

1. **Check raw per-exchange data**: Query `market_data_daily` grouped by exchange to see each exchange's contribution
2. **Check timestamps**: Look at exact `ts` values for the same symbol/date across exchanges — different offsets (00:00 vs 16:00 UTC) indicate timestamp alignment issues
3. **Check symbol normalization**: Verify that CASE WHEN normalization produces identical `symbol_norm` values across exchanges (hex comparison for hidden chars)
4. **Check aggregation behavior**: Run the GROUP BY manually and compare row counts — if N exchanges × M days produces > M rows, there's a timestamp or normalization issue
5. **Compare mean vs median**: If mean >> median, launch spikes are inflating the average (use median instead)

This pattern applies to any cross-exchange aggregation, not just CLS.
