# CCXT Binance Futures — Known Quirks

Discovered during Numerai Crypto bot development (2026-06). These quirks apply
when using **sync** `ccxt` (`ccxt.binance({'options': {'defaultType': 'future'}})`).

## 1. Market Symbols Are Case-Sensitive Uppercase

```python
# WRONG — raises BadSymbol
exchange.fetch_funding_rate_history('btc/usdt')

# RIGHT
exchange.fetch_funding_rate_history('BTC/USDT')

# Also works (linear delivery contract notation)
exchange.fetch_funding_rate_history('BTC/USDT:USDT')
```

**Root cause:** Binance Futures stores symbols as `BTCUSDT` internally. CCXT maps
this to `BTC/USDT`. Lowercase `btc/usdt` bypasses the market lookup.

**Where it bites:** Override CSVs or config files often store lowercase pairs
(e.g. `btc/usdt`). Always `.upper()` the ccxt_pair when loading from CSV or
config. See `resolver.py:_load_override_csv()` for the fix pattern:

```python
"ccxt_pair": (row.get("ccxt_pair") or "").upper() or None,
```

## 2. Sync CCXT Has No `.close()` Method

```python
# WRONG — AttributeError: 'binance' object has no attribute 'close'
exchange.close()

# RIGHT — sync CCXT doesn't need closing; just let it go out of scope
# (the async ccxt.pro version has exchange.close())
```

The async variant (`ccxt.pro`) needs `.close()` to clean up the event loop.
Sync `ccxt` uses blocking `requests` under the hood with no persistent
connection state that needs explicit cleanup.

## 3. Open Interest Retention: Only 30 Days (1d timeframe)

The Binance `/futures/data/openInterestHist` endpoint has strict limits:

| `period` parameter | Data retained |
|---|---|
| `5m` | ~30 days |
| `15m` | ~30 days |
| `30m` | ~30 days |
| `1h` | ~90 days |
| `4h` | ~180 days |
| `1d` | **~30 days only** |

Even the `1d` period only retains 30 days. Requesting `startTime` older than
30 days returns HTTP 400 (`parameter 'startTime' is invalid.`), not empty
results or an error code.

**Mitigation:** Always cap OI backfill lookback:
```python
oi_lookback_days = min(requested_days, 30)
```

For OI beyond 30 days, use third-party aggregators (CoinGecko, CoinMarketCap,
TheGraph) or compute proxies from volume/volatility.

## 4. Per-Symbol Error Resilience Is Required

When iterating over many symbols, ANY symbol can fail for exchange-specific
reasons:
- Stablecoins (USDT/USDT, USDC/USDT) don't exist as perpetual futures
- Deprecated symbols still in listings but not tradeable
- Rate-limited symbols mid-batch

**Pattern:** Wrap each symbol in a try/except rather than letting one failure
kill the whole batch:

```python
for symbol, pair in symbol_pairs.items():
    try:
        data = exchange.fetch_funding_rate_history(pair, ...)
        # process
    except Exception as exc:
        logger.warning("Skipping %s: %s", symbol, exc)
        continue
    time.sleep(RATE_LIMIT_DELAY)
```

Without this, USDT/USDT would abort a 100-symbol backfill at symbol #3.

## 5. `fetch_funding_rate_history` Pagination

Binance returns funding rates in ~1000-row pages (8h intervals since ~2019).
The pagination loop should advance by 1 day (86,400,000 ms) per iteration:

```python
current_since = last_timestamp_ms + 86_400_000
```

Safety guard: if `all_rates[-1][0] <= all_rates[-2][0]` (no progress), break.
