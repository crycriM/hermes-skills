# Aster DEX — Implementation Reference

**Status:** ✅ Implemented (2026-06-20)
**Adapter:** `src/market_data/adapters/aster.py`
**Commit:** `1f7a1d0`

## API Summary

Aster (asterdex.com) has a **Binance-compatible fapi**. Same endpoint structure, same response shapes. No auth needed for public endpoints.

| Property | Value |
|----------|-------|
| Base URL | `https://fapi.asterdex.com/fapi` |
| Perpetual USDT-M pairs | 477 (as of 2026-06-20) |
| Auth | None for public endpoints |
| CCXT id | `aster` (v4.5.56+) |

## Endpoints (all GET, Binance-compatible)

| Purpose | Path | Key params | Response |
|---------|------|-----------|----------|
| Instruments | `/v1/exchangeInfo` | — | `symbols[]` with `contractType`, `marginAsset`, `status` |
| OHLCV | `/v1/klines` | `symbol`, `interval`, `startTime`, `endTime`, `limit` (max 1000) | Array of `[ts, o, h, l, c, vol, closeTs, quoteVol, trades, takerBuyVol, takerBuyQuoteVol, 0]` |
| Open Interest | `/v1/openInterest` | `symbol` | `{"symbol":"BTCUSDT","openInterest":"5631.127","time":...}` (base units) |
| Price | `/v1/ticker/price` | `symbol` | `{"symbol":"BTCUSDT","price":"63342.2","time":...}` |
| Funding Rate | `/v1/premiumIndex` | `symbol` | `{"symbol":"BTCUSDT","markPrice":"...","lastFundingRate":"0.00004463",...}` |

## Symbol Format

- Native: `BTCUSDT` (no separator, like Binance)
- Canonical (internal): `BTC-USDT`
- 1000x convention: `1000PEPEUSDT` → `PEPE-USDT` (same as Binance)

## Discovery via CCXT

Before building the raw adapter, CCXT confirmed capabilities:
```python
import ccxt
ex = ccxt.aster({'options': {'defaultType': 'swap'}})
print(ex.has)  # fetchOHLCV, fetchFundingRate, fetchMarkets all True
# fetchOpenInterest: False in ccxt — but raw API has it at /v1/openInterest
```

**Key finding:** CCXT reports `fetchOpenInterest: False` but the raw fapi endpoint works. Always verify raw API directly — CCXT capability flags can lag behind exchange API additions.

## Smoke Test Results (2026-06-20)

```
Instruments: 477
Sample: ['ASTER-USDT', 'BTC-USDT', 'ETH-USDT', 'BNB-USDT', 'SOL-USDT']
BTC funding rate: 4.4e-05
BTC OI (USDT): 356,707,118
OHLCV bars: 3 (1h, last 3 hours)
```

## Adapter Notes

- Mirrors `BinanceAdapter` structure (same pagination, same native_map pattern)
- OI returned in base units — multiply by `/v1/ticker/price` for USDT notional
- Funding from `/v1/premiumIndex` (not `/v1/fundingRate`) — returns `lastFundingRate` field
- `trade_count=0` hardcoded (consistent with all other adapters — unreliable cross-exchange)

## Next Step

Run preselection ingest to backfill Aster OHLCV into TimescaleDB:
```bash
uv run python -m src.market_data.historical_fetch \
    --exchanges binance bybit okx hyperliquid aster \
    --days 7
```
