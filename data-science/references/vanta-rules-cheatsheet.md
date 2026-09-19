# Vanta Network Trading Rules — Quick Reference

Extracted from docs.taoshi.io and ptn/CLAUDE.md (v8.8.8, 2026-06).

## Trade Pairs

### Crypto (active)
| Symbol | Pair | Leverage Range |
|--------|------|----------------|
| BTCUSD | BTC/USD | 0.01 – 0.5× |
| ETHUSD | ETH/USD | 0.01 – 0.5× |
| SOLUSD | SOL/USD | 0.01 – 0.5× |
| XRPUSD | XRP/USD | 0.01 – 0.5× |
| DOGEUSD | DOGE/USD | 0.01 – 0.5× |
| ADAUSD | ADA/USD | 0.01 – 0.5× |

### Forex (active)
32 pairs across G1–G5 groups. Leverage range: 0.1 – 5×.

### Blocked
All indices (SPX, DJI, NDX, VIX, FTSE, GDAXI), JPY crosses, USDMXN, equities, commodities.

## Position Rules

- Max 1 open position per trade pair (uni-directional)
- First order on a pair determines direction (LONG or SHORT). Can't flip — must close and re-open.
- Leverage clamped to pair-specific min/max on every order
- Min order leverage: 0.001

## Portfolio Caps

| Asset Class | Per-Position Cap | Portfolio Contribution Scaling | Portfolio Cap |
|-------------|-----------------|-------------------------------|---------------|
| Crypto | 0.5× | ×10 | 10× (effective ~1× raw crypto total) |
| Forex | 5× | ×1 | 10× |

Crypto contribution: 0.5× position → 5× portfolio. With 6 pairs at max: 6 × 5 = 30× but capped at 10×.

## Fees

| Fee Type | Crypto Rate | Forex Rate | Schedule |
|----------|------------|------------|----------|
| Carry fee | 0.03% per 8h (10.95% annual) | 0.008% per 24h (3% annual) | Charged on position market value |
| Spread fee | 0.05% × order value (on each order) | None | Per-order |
| Slippage | Higher for large orders, low liquidity | N/A | Per-order |

Carry fee intervals: Crypto 04:00/12:00/20:00 UTC, Forex 21:00 UTC Mon-Fri.

## Risk & Scoring

- **Max drawdown**: 10% → automatic elimination
- **Daily drawdown limit**: 5% (MAX_DAILY_DRAWDOWN = 0.95)
- **Challenge period**: 61–90 days, must reach rank 15+ to graduate
- **Probation**: Below rank 15 → 30 days to recover or eliminated
- **Immunity**: 4 hours after registration (not for eliminated miners)

### Scoring Weights
| Metric | Weight |
|--------|--------|
| Average Daily PnL | 90% |
| Calmar Ratio | 2% |
| Sharpe Ratio | 2% |
| Omega Ratio | 2% |
| Sortino Ratio | 2% |
| Statistical Confidence | 2% |

### Risk Profiling Penalties
Avoid:
- Stepping 3+ times into a losing position
- Using >50% of available leverage or increasing leverage by >150% on losing position
- Uneven time intervals between orders (non-TWAP pattern)

## Order Lifecycle

1. Signal sent via REST API (`POST /api/submit-order`)
2. Miner forwards to validators via Bittensor SendSignal synapse
3. Validators execute and maintain positions
4. Scoring updates every 5 minutes
5. Weekly payout (debt-based, targets completion by month day 25)

## Cooldowns

- 10-second minimum between orders on the same trade pair
- Rate limiting: malicious spam → orders ignored

## Holidays (Forex/Commodities Only)

New Year's Day (Jan 1), Good Friday, Christmas Day (Dec 25), Boxing Day (Dec 26). Weekend observance for holidays falling on weekends.

## Scoring Recency Weights

Exponential decay on daily returns:
- Most recent 10 days: 40% weight (Average Daily PnL), 25% (other metrics)
- Most recent 30 days: 70% (PnL), 50% (other)
- Most recent 70 days: 87% (PnL), 75% (other)

## Registration

- Mainnet: netuid 8, testnet: netuid 116
- Registration fee: <1 TAO on mainnet
- Wallet: coldkey + hotkey pair
- **CRITICAL**: Never reuse hotkeys from eliminated/deregistered miners — permanently blacklisted.
