# OKX trade_count Data Quality Issue

## The Bug

OKX candle API (`/api/v5/market/candles`) returns 8 fields (indices 0-7):

| Index | Field | Description |
|-------|-------|-------------|
| 0 | ts | timestamp (ms) |
| 1-4 | o/h/l/c | OHLC prices |
| 5 | vol | volume in contracts |
| 6 | volCcy | volume in **base currency units** |
| 7 | volCcyQuote | volume in **quote currency (USDT)** |

The adapter (`src/market_data/adapters/okx.py:94`) stores `c[6]` (volCcy, base units) in the `trade_count` column:

```python
trade_count=int(float(c[6])),  # volCcy (base units) used as proxy for trade activity
```

This is semantically wrong. `volCcy` is NOT trade count — it's the trading volume denominated in the base asset. For low-price tokens, this number is astronomically large.

## Impact on CLS Ranking

CLS uses `trade_count` as one of three z-scored components (ADV 55%, OI 30%, trades 15%). The inflated OKX values dominate the cross-exchange average:

```
Symbol       OKX volCcy/day      Binance real trades/day   Ratio
─────────    ──────────────────  ────────────────────────  ──────
PEPE-USDT    30,872,535,000,000       677,781              45M×
SHIB-USDT     1,707,938,700,000       121,505              14M×
BONK-USDT       747,070,600,000       121,768               6M×
DOGE-USDT       3,158,780,480         553,160             5.7K×
ASTER-USDT         17,651,547         175,407               100×
PIPPIN-USDT       218,564,940          58,323             3.7K×
```

For PEPE: z_atradecount ≈ 13.8 (vs normal range -1 to +1), adding 2.07 to CLS score (15% weight). This alone can push a mid-cap token into the top 10.

## Diagnosis Query

```sql
-- Compare OKX vs Binance trade counts for suspect symbols
SELECT symbol, exchange, 
       AVG(trade_count) as avg_trades,
       AVG(volume) as avg_vol
FROM market_data_daily
WHERE symbol IN ('PEPE-USDT','SHIB-USDT','BONK-USDT','DOGE-USDT')
  AND ts >= NOW() - INTERVAL '30 days'
GROUP BY symbol, exchange
ORDER BY symbol, exchange;
```

If OKX avg_trades is >1000× Binance, the bug is active.

## Fix Options

1. **Zero out OKX trade_count** — simplest, removes OKX from trade activity signal
2. **Use volCcyQuote / avg_price** as proxy — estimates trade count from quote volume
3. **Use volCcyQuote (c[7])** — but this is just quote volume (duplicate of ADV signal)
4. **Cap at Binance-equivalent** — normalize OKX to same order of magnitude

Option 1 is safest until a proper trade count proxy is designed.

## Related: 180-day ADV Launch Spike

CLS inputs use 180-day average ADV. Tokens that had huge launch spikes (first 2 weeks of listing) show inflated ADV even if recent daily volume is much lower. Example:

```
Token       180d ADV     Recent daily vol (combined)
────────    ──────────   ─────────────────────────
RIVER       $703M        $20-75M (declining from launch)
RAVE        $495M        $25-55M
PIPPIN      $472M        $10-30M
POWER       $103M        $2-6M (way too low)
```

This is a separate issue from the OKX bug but compounds the ranking distortion.
