# Perimeter Universe — Exchange Format Normalization

The perimeter files (`data/perimeter/recup_perimeter_YYYY-MM-DD.json`) contain
perpetual swap listings from multiple exchanges. Each exchange uses a different
symbol format. The normalizer in `src/ingest/perimeter.py` strips suffixes to
extract bare tickers for survivorship-bias-free asset matching.

## Exchange Symbol Formats

| Exchange | Input Symbol | Stripped To | Strip Rule |
|----------|-------------|-------------|------------|
| Binance (fut) | `BTCUSDT` | `BTC` | Remove USDT/USDC/BUSD suffix |
| Bybit | `BTCUSDT` | `BTC` | Same suffix strip |
| Okex | `BTC-USDT-SWAP` | `BTC` | Take first `-` segment |
| Hyperliquid | `BTC/USDC:USDC` | `BTC` | Take first `/` segment |
| Bitget | `BTC` | `BTC` | Already bare |

## Known Stablecoin Suffixes

Stripped in order of check: `USDT`, `USDC`, `BUSD`, `TUSD`, `DAI`, `FDUSD`, `USD`.

Minimum ticker length after stripping: 2 chars. Max: 10. Must match `[A-Z0-9]+`.

## Normalization Code (Python)

```python
def _extract_ticker(symbol: str) -> str | None:
    s = symbol
    # Hyperliquid: BTC/USDC:USDC -> BTC
    s = s.split("/")[0] if "/" in s else s
    # Okex: BTC-USDT-SWAP -> BTC
    s = s.split("-")[0] if "-" in s else s
    # Strip stablecoin suffixes
    for suffix in ("USDT", "USDC", "BUSD", "TUSD", "DAI", "FDUSD", "USD"):
        if s.endswith(suffix) and len(s) > len(suffix) + 1:
            s = s[: -len(suffix)]
            break
    if not re.match(r"^[A-Z0-9]{2,10}$", s):
        return None
    return s
```

## Ticker Alias Map

For articles that spell out full names (e.g. "Solana" instead of "SOL"),
the alias map in `src/ingest/perimeter.py` translates. Do NOT add aliases
for tokens that might have different tickers across exchanges — the perimeter
file already handles that.

Key aliases for well-known coins:
- BITCOIN→BTC, ETHEREUM→ETH, SOLANA→SOL
- DOGECOIN→DOGE, CARDANO→ADA, POLKADOT→DOT
- CHAINLINK→LINK, AVALANCHE→AVAX, POLYGON→MATIC
- APTOS→APT, ARBITRUM→ARB, OPTIMISM→OP

## Matching Behavior

Two-pass strategy to avoid false positives from 3-letter tickers matching
random words:
1. Source code: check aliases first (longest prefix match wins)
2. Then raw tickers (longest ticker first, whole-word boundary required)

Ticker `$TICKER` or `TICKER` patterns both match (common for crypto notation).

## Adding a New Exchange

Check an old perimeter file to see if the exchange was present historically.
Exchange keys change over time (e.g., `binance` → `binancefut`). The loader
handles any key name — it just unions all symbol lists from all keys.
