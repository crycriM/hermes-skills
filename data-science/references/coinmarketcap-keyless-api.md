# CoinMarketCap API — Market Cap Rankings

Two modes: **authenticated** (Pro API, when `COINMARKETCAP_API_KEY` is set in `.env`)
or **keyless** (Trial Pro API, no auth required).

## Endpoints

| Mode | URL | Auth |
|---|---|---|
| Authenticated | `https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest` | `X-CMC_PRO_API_KEY` header |
| Keyless | `https://pro-api.coinmarketcap.com/trial-pro-api/v3/cryptocurrency/listings/latest` | None |

## Key Parameters

| Param | Value | Effect |
|---|---|---|
| `limit` | 1–500 | Number of top-ranked coins to return |
| `sort` | `market_cap` (default) | Sort by CMC market cap rank |
| `sort_dir` | `desc` (default) | Highest market cap first |

## Response Shape (v3)

Returns an **array** in `data`:

```json
{
  "status": { "error_code": 0 },
  "data": [
    {
      "id": 1,
      "name": "Bitcoin",
      "symbol": "BTC",
      "cmc_rank": 1,
      "quote": {
        "USD": { "market_cap": 1472835407547.82 }
      }
    }
  ]
}
```

- `cmc_rank` — 1-based market cap rank
- `symbol` — uppercase ticker (e.g. `BTC`, `ETH`, `SOL`)
- `quote.USD.market_cap` — market cap in USD

v1 endpoint (`/v1/cryptocurrency/listings/latest`) returns `data` as an **object map** keyed by ID instead of an array.

## Known Issues

### Duplicate Symbols
CMC may return multiple entries with the same `symbol` (e.g. two different coins sharing a ticker). Always deduplicate by keeping the lowest `cmc_rank` (highest rank) — that's the canonical token.

### Error Code 1002
`{"error_code": 1002, "error_message": "API key missing."}` — on the **keyless** path this means you accidentally sent `X-CMC_PRO_API_KEY` header. Drop the header. On the **authenticated** path, it means the API key is invalid/missing.

### String error_code (confirmed on BOTH keyless and authenticated)

Both v3 authenticated and keyless endpoints return `error_code` as a **string**, not integer (e.g. `"0"` not `0`). Always cast with `int(error_code)` before comparing — `error_code != 0` fails because `"0" != 0` is `True` in Python 3.

### Rate Limiting
The keyless tier is rate-limited but generous enough for a single weekly fetch (500 coins, one call per universe run). If you hit 429, add a retry with backoff.

## Usage in rankit

The `src/universe/market_cap.py` module wraps both modes and auto-selects based on `settings.coinmarketcap_api_key`:

```python
rankings = await fetch_market_cap_rankings(limit=500)
# → {"BTC": 1, "ETH": 2, "SOL": 5, ...}
```

When `COINMARKETCAP_API_KEY` is set in `.env`, uses the authenticated endpoint.
When empty, falls back to the keyless Trial Pro API.

Graceful degradation: returns `None` on any error, allowing the pipeline to continue without the market cap gate.

The mapping from exchange symbols (`BTC-USDT`) to CMC symbols (`BTC`) is done by splitting on `-` and taking the base currency. Tokens not found in the CMC rankings are dropped.

## Config

```ini
# .env — optional, enables authenticated Pro API endpoint
COINMARKETCAP_API_KEY=2dce60...
```
