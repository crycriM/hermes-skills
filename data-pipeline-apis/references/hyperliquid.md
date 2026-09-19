# Hyperliquid API Notes

## Candle Data Status (2026-05)

**HTTP candleSnapshot now works** — but requires a `req` object wrapper (recent API change):

```json
{ "type":"candleSnapshot","req":{"coin":"BTC","interval":"1d","startTime":<ms>,"endTime":<ms>}}
```

Note: the previous non-wrapper format `{\"type\":\"candleSnapshot\",\"coin\":\"BTC\",...}` returns HTTP 422. The `req` wrapper **must** be present.

### Working intervals (lowercase only):
- `1d` — daily candles (works, returns ~31 candles for a 30-day range)
- `4h` — 4-hour candles (works, ~187 per month)
- `8h` — 8-hour candles (works, ~94 per month)
- `1w` — weekly candles (works, ~6 per month)

### Non-working intervals (return 0 candles — no historical data at these granularities):
- `1m`, `5m`, `15m`, `30m`, `1h`, `2h`, `12h` — REST returns empty results for all of these
- **Note**: WebSocket subscriptions for sub-daily intervals work, but HTTP candleSnapshot does not return historical data

### Case sensitivity:
- Intervals are case-sensitive lowercase. `1H`, `1D`, `1W` all return HTTP 422.
- Only the exact lowercase strings above work.

### Response format:
- Price fields (`o`, `c`, `h`, `l`) are returned as **strings** (not numbers) for precision
- Volume field `v` is a string
- Trade count `n` is an integer in milliseconds
- Timestamp fields (`t`, `T`) are integers in milliseconds

### Instrument universe:
- 230 instruments available via the `meta` endpoint
- Symbols formatted as `BTC`, `ETH`, etc. — adapter adds `-USD` suffix internally

## candleSnapshot Debugging (Rust Serde Errors / HTTP 422)

When Rust serde errors occur with Hyperliquid API, check these first:
1. **Endpoint still exists** — try simpler types like `meta` to verify basic connectivity
2. **Correct type key** — not `candleSnapshot`, not `CandleSnapshot`, not `candles`
3. **Required fields present** — serde rejects if any required field is missing
4. **Type matching** — timestamps must match expected Rust types (i64/f64), not strings
5. **req wrapper missing** — if type key is correct but 422 persists, the `req` object wrapper may be required
6. **Wrong interval string** — Hyperliquid only returns historical candles for `1d`, `4h`, `8h`, `1w`. Other intervals return 0 results silently (not an error).

**Debugging order:** Try `{ "type":"meta" }` → if that works, the endpoint is fine; try simpler types like `l2Book` → if those work but your type fails, the handler doesn't exist or payload format is wrong.

## Other Hyperliquid Endpoints

### Working info endpoints:
- `meta` — universe, marginTables, collateralToken
- `l2Book` — L2 orderbook snapshot for a coin

### Deprecated / non-working:
- WebSocket candle subscription still works: `{ "method": "subscribe", "subscription": { "type": "candle", "coin": "<coin>", "interval": "<interval>" } }`
- But note: no REST candle data at sub-daily granularity (see above)

## Candle Interface (WebSocket)

```typescript
interface Candle {
  t: number;     // open millis
  T: number;     // close millis
  s: string;     // coin
  i: string;     // interval
  o: string;     // open price (string for precision)
  c: string;     // close price (string for precision)
  h: string;     // high price (string for precision)
  l: string;     // low price (string for precision)
  v: string;     // volume (base unit, string for precision)
  n: number;     // number of trades
}
```

## Historical Fetch Pipeline Integration

When adding Hyperliquid as a data source to `historical_fetch.py`:
- Use `--exchanges hyperliquid` to run the fetcher
- The adapter uses daily interval (`1d`) because hourly candles return 0 results
- After fetching, all symbols should have exactly 61 bars (one per day for ~2 months)
- Verify with: `SELECT symbol, count(*) FROM market_data_ohlcv WHERE exchange='hyperliquid' GROUP BY symbol`
