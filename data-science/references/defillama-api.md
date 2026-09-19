# DefiLlama API — Free On-Chain Data Provider

Discovered during Numerai Crypto bot development (2026-06). DefiLlama provides
free, open-source DeFi analytics data — chain-level TVL, fees, revenue, DEX
volumes, active users, yields, and more. No API key required for the free tier.

**Base URL:** `https://api.llama.fi`

## Key Endpoints Used for Numerai Crypto

### `/v2/chains` — Chain List with TVL
Returns all supported chains with current TVL, `gecko_id`, `cmcId`, name.

```json
{
    "gecko_id": "ethereum",
    "tvl": 65998652431.40,
    "tokenSymbol": "ETH",
    "cmcId": "1027",
    "name": "Ethereum",
    "chainId": 1
}
```

**Mapping to Numerai symbols:** Use `cmcId` or `gecko_id` to match against the
resolver's mapping. The Numerai UCID matches the CoinMarketCap ID (cmcId).

### `/v2/historicalChainTvl/{chain}` — Historical TVL Time Series
Returns daily TVL data as `[{"date": unix_timestamp, "tvl": float}]` going back
to ~2020 for major chains. ~3000 data points per chain.

```python
resp = requests.get(f"{BASE_URL}/v2/historicalChainTvl/{chain_name}")
data = resp.json()  # list of {date: ts, tvl: float}
```

### `/overview/fees/{chain}` — Chain Fee/Revenue Data
Returns total fees, protocol breakdown, and historical fee charts. The
`totalDataChart` field gives daily fee data.

## Provider Architecture

The `OnChainProvider` in `src/data_sources/defillama.py` follows the same
backfill + incremental pattern as the `DerivativesProvider`:

1. **Build chain mapping** — Map Numerai ucid → DefiLlama chain name via
   `CHAIN_OVERRIDES` dict (hand-curated for accuracy since auto-mapping via
   cmcId can match wrong protocols)
2. **Fetch chain TVL** — One API call per chain, fast (~0.3s each)
3. **Compute derived features** — TVL change % at 1d, 7d, 30d windows
4. **Store in PIT store** — Same `insert_features()` pattern, source=`"defillama"`

## Chain Name Overrides

Auto-mapping via cmcId/gecko_id is unreliable:
- A token can exist on multiple chains with the same cmcId
- Some tokens (LINK, UNI) are protocol tokens, not L1 chains
- DefiLlama chain names use internal conventions (e.g., "OP Mainnet" not "Optimism")

Maintain a `CHAIN_OVERRIDES` dict:

```python
CHAIN_OVERRIDES = {
    "1": "Bitcoin",          # BTC → Bitcoin
    "1027": "Ethereum",      # ETH → Ethereum
    "5426": "Solana",        # SOL → Solana
    "3890": "Polygon",       # MATIC → Polygon
    "11840": "OP Mainnet",   # OP → OP Mainnet (NOT "Optimism")
    "52": "XRPL",            # XRP → XRPL
    "5805": "Avalanche",     # AVAX → Avalanche
    "3794": "CosmosHub",     # ATOM → CosmosHub
    "10603": "Injective",    # INJ → Injective
    "23035": "Sei",          # SEI → Sei
    "22771": "Celestia",     # TIA → Celestia
}
```

Set symbols with no chain mapping to `None` (e.g., stablecoins, tokens that
aren't L1/L2 chains).

## Derived Features from TVL

From the raw TVL time series, compute:

| Feature | Description |
|---|---|
| `tvl` | Current chain TVL in USD |
| `tvl_change_1d` | (TVL(t) − TVL(t-1)) / TVL(t-1) |
| `tvl_change_7d` | 7-day percentage change |
| `tvl_change_30d` | 30-day percentage change |

These are stored as JSON in the `onchain` column of the PIT store features table.

## Known Issues

### Historical TVL Starts at 0
For chains launched after 2020, DefiLlama returns 0 TVL for dates before the
chain existed. The `_process_tvl` method handles this naturally (0 → None
for percentage changes since `prev=0` triggers the guard).

### Chain Names ≠ Protocol Names
DefiLlama distinguishes between chain-level data (TVL of all DeFi on a chain)
and protocol-level data (TVL of a specific dApp). Chain names like "OP Mainnet"
or "CosmosHub" don't always match the common brand name. When adding a new
symbol, verify the chain name via `/v2/chains` first.

### Rate Limiting
The free API is generous. 26 chains backfilled in ~8 seconds with
`RATE_LIMIT_DELAY=0.25s`. No 429 errors observed during testing.
