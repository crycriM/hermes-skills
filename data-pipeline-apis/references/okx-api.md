# OKX API Reference

## Verified Endpoints (May 2025)

- Base URL: `https://www.okx.com`
- Instruments: `GET /api/v5/public/instruments?instType=SWAP`
- Candles: `GET /api/v5/market/candles`
- Open Interest: `GET /api/v5/public/open-interest`
- Funding Rate: `GET /api/v5/public/funding-rate`

## Filtering Linear Perpetuals (USDT-Settled)

OKX SWAP instruments include both inverse (settled in underlying) and linear (USDT-settled). Filter for linear perpetuals:

```python
# Filter criteria (NOT quoteCcy == "USDT")
s.get("ctType") == "linear"      # linear perpetuals
s.get("settleCcy") == "USDT"     # settled in USDT
s.get("state") == "live"         # actively traded
```

**Why not `quoteCcy`?** The OKX API returns `quoteCcy: ""` (empty) for most SWAPs. Use `settleCcy` instead.

## Symbol Formatting

- Internal format: `BTC-USDT`
- OKX format: `BTC-USDT-SWAP`
- Conversion: `f"{symbol}-SWAP"` for requests, `.replace("-SWAP", "")` for responses

## Interval Format

OKX requires **uppercase** intervals:
- `1H` (not `1h`)
- `1M` (not `1m`)
- `1D` (not `1d`)
- `1W` (not `1w`)

```python
okx_interval = interval.replace("h", "H").replace("m", "M").replace("d", "D").replace("w", "W")
```

## Candle Field Indices

OKX returns 8 columns in candles array (indices 0-7):

| Index | Field | Example (BTC) |
|-------|-------|---------------|
| 0 | timestamp (ms) | `1778828400000` |
| 1 | open | `80553` |
| 2 | high | `80984.8` |
| 3 | low | `80523.2` |
| 4 | close | `80969.2` |
| 5 | base volume | `271747.11` |
| 6 | volCcy (base currency units) | `2717.4711` |
| 7 | volCcyQuote (quote/USDT) | `219503146.46408` |
| 8 | confirm (0=incomplete, 1=complete) | `0` |

**For CLS scoring**: Use `c[7]` (quote volume in USDT) as `volume` — this represents actual trading value.

**⚠️ CRITICAL — trade_count field**: OKX does NOT return explicit trade count. The adapter stores `c[6]` (volCcy = base currency volume) in `trade_count`. This is semantically wrong — for low-price tokens (PEPE at $0.00001), $100M volume = 10 trillion base units, inflating "trade count" by millions of times and corrupting CLS z_atradecount scores. See `references/okx-trade-count-bug.md` in the `market-data-ingestion` skill for full analysis and fix options.

## Pagination (Critical)

OKX returns candles **newest-first**, paginated with `after` parameter:

```
GET /api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1H&after=1778083199999&limit=100
```

- `after`: return data with timestamp **less than** this value (older data)
- Response is newest-to-oldest within each page
- To get full range: start from `end_ms`, then use `candles[-1][0] - 1` for next request

**Correct pagination loop:**
```python
current_end_ms = end_ms
while current_end_ms > start_ms:
    resp = await client.get("/api/v5/market/candles", params={
        "instId": okx_symbol,
        "bar": okx_interval,
        "after": current_end_ms,  # older than this
        "limit": 100,
    })
    candles = resp.json()["data"]
    for c in candles:
        yield parse_bar(c)
    # Advance to older data
    current_end_ms = int(candles[-1][0]) - 1
```

**Wrong**: Using `start_ms` as `after` parameter (oldest-first logic) — this returns zero results.

## Data Type Overflow

OKX quote volume (`c[7]`) can exceed 2^31-1 for high-volume assets. Use `BIGINT` in TimescaleDB:

```sql
ALTER TABLE market_data_ohlcv ALTER COLUMN trade_count TYPE BIGINT;
```

The `trade_count` field currently stores `volCcy` (base currency units, c[6]) which can be in trillions for low-price tokens. This is a known data quality bug — see warning above.

## Rate Limiting

- OKX is generally rate-limit friendly
- Add 0.5s delay between requests to be safe
- No explicit 429 responses observed with moderate usage

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Parameter bar error` | Using lowercase `1h` | Use uppercase `1H` |
| `0 candles returned` | Using `start_ms` as `after` param | Use `end_ms` for first request |
| `invalid literal for int()` | Trade count has decimals | Use `int(float(c[6]))` |

## Test Commands

```bash
# List instruments
curl -s "https://www.okx.com/api/v5/public/instruments?instType=SWAP" | jq '.data | length'

# Check BTC candles (newest first)
curl -s "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1H&limit=3" | jq '.'

# Verify pagination works
curl -s "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=1H&after=1773647999999&limit=100" | jq '.data | length'
```