# Market Making Strategy — Condensed Knowledge

From strategy design sessions in `~/projects/clmm-animation/docs/`. Covers DLMM spot MM, bidirectional perp MM, risk mitigation for non-hedgeable tokens, and the quant-vs-RL question.

---

## 1. DLMM Spot MM (Meteora)

### Core mechanism
A DLMM bin is a limit order. Bins below mid hold quote token (resting bids); bins above hold base token (resting asks). A ladder of single-sided bins on both sides is an order book. Full price oscillation (fall through bid, rise through ask) realizes the round-trip spread.

### Three knobs to tune
1. **Spread width** — `inner_offset` (bins from active). Tight = more fills, smaller spread, higher adverse selection. Wide = fewer fills, larger spread, more idle capital.
2. **Refresh tempo** — keeper loop: withdraw + re-center when mid drifts. Over-refresh bleeds via gas/priority fees.
3. **Inventory skew** — `target_skew` from `evaluate_rebalance`, steers capital between sides.

### The hard part: adverse selection
Placing the ladder is trivial; profiting is not. Resting orders fill when informed flow runs them over. Three models layer on top:
1. **Regime classifier** (OU half-life, Hurst, HMM, VPIN, trend filter) — gate whether to quote at all.
2. **Inventory controller** (Avellaneda-Stoikov reservation price) — skew quotes to shed inventory.
3. **Refresh policy** — trade fill-rate against gas cost.

### Dynamic fee modeling
Meteora DLMM fees are volatility-based and accrue only on crossed bins. Net edge = `roundtrip_spread + crossed_fee_bps - gas - adverse_selection`. Fee is a state variable, not a constant.

---

## 2. Bidirectional Perp MM (Hyperliquid/Aster/Lighter)

### Why perp MM is simpler than spot MM
- Single signed delta (net position), not two-token inventory
- Rebalance = place opposite order (zero cost), not swap + withdraw + redeposit
- No custody risk (synthetic exposure), no rug risk
- Continuous price ticks (not discrete bins)
- Sub-second finality on Hyperliquid

### Three revenue streams
1. **Spread capture** — buy bid, sell ask
2. **Maker rebate** — Hyperliquid pays -0.003% at tier 4+ with staking; Aster pays -0.50 bps for qualified MMs
3. **Funding** — if inventory oscillates around zero, funding cost ~0. Negative funding + slight short bias = funding income.

### AS maps cleanly to perp MM
```
r(t) = S - q * γ * σ² * (T-t)    → inventory tilt of quote center
δ = γ*σ²*(T-t)/2 + (2/γ)*ln(1+γ/κ)  → half-spread
```
Use Guéant asymptotic (T→∞) for stationary keeper loop.

### Funding-aware AS
Add funding term to reservation price:
```
r(t) = S - q*γ*σ²*(T-t) - q*funding_rate*(T-t)/(2*margin)
```
Shifts quotes to shed inventory in the direction that minimizes funding cost.

### Risk: liquidation
- Low leverage (1-3x max)
- AS tilt naturally reduces inventory
- Hard inventory cap: stop quoting on side that increases |q|
- Auto-deleverage: market-order excess if |q| > CRITICAL

### Risk: adverse selection
- Per-fill markout tracking (measure PnL k seconds after fill)
- VPIN monitoring
- Hidden orders on Aster (reduces signaling)
- Fill-rate spike detection

### Example economics (SOL-PERP, Hyperliquid tier 4)
- Gross spread: ~6.7 bps
- Maker rebate: +0.3 bps
- Adverse selection: -1 to -3 bps
- Net edge: ~4-6 bps per round trip

---

## 3. Risk Mitigation for Non-Hedgeable Tokens

### Multi-layer defense fence (outer to inner)

| Layer | Trigger | Action | Latency |
|---|---|---|---|
| Regime gate | OU/Hurst/VPIN/trend fails | Stop placing bids | 1 poll |
| Inventory cap | base_share > 65% | Stop bids, max sell skew | 1 poll |
| Adverse selection breaker | mean markout < -30bps / 20 fills | Widen 2x or stop | N fills |
| Price stop | adverse move > 2% | De-risk mode (passive sell → TWAP) | 1 poll |
| Drawdown stop | drawdown > 5% | Full exit | 1 poll |
| Rug kill-switch | TVL -30% or price gap >20% in 1 block | Emergency Jito bundle exit | 1 slot |

### Liquidity-aware stop-loss (three execution branches)

**Case A — Liquidity sufficient:** Swap via aggregator, or TWAP if slippage borderline.

**Case B — Liquidity vanishing (rug):** Jito bundle with max priority fee, accept up to 50% slippage, route through alternate venue.

**Case C — No liquidity:** Withdraw LP position, hold tokens in wallet, alert for manual review. Don't dump into zero depth.

### De-risk mode
1. Stop accumulating (no new bids)
2. Let asks work passively (sell at your price, not market's)
3. Escalate to TWAP only if passive doesn't reduce inventory within time budget
4. Check exit depth before each TWAP chunk — if liquidity vanishes, escalate to emergency

### Rug detection signals
| Signal | Threshold |
|---|---|
| Pool TVL change (1 block) | < -30% |
| Price gap (1 block) | > 20% |
| LP count change (1 block) | < -5 or < -50% of active |
| Swap volume ratio (1 min) | buy:sell > 10:1 |
| Token mint authority | mint > 0 |
| Token metadata change | authority frozen/changed |

Rug monitor must be a separate thread (not the keeper loop), polling every slot (~400ms).

---

## 4. Quant vs RL

### Profitability drivers (in order of impact)
1. **Pool selection** — bad pool + great AS = losses; good pool + symmetric grid = profits
2. **Adverse selection measurement** — VPIN + per-fill markout; can't avoid what you can't measure
3. **Execution quality** — Jito bundles, priority fees, MEV-aware refresh
4. **Regime detection accuracy** — needs calibration on actual DLMM data
5. **Gas economics** — stochastic priority fees; refresh must be adaptive

### When quant models (AS) are sufficient
- Bluechip pairs in range-bound regimes
- When regime gate accurately prevents quoting into trends
- When backtester honestly models dynamic fees and adverse selection

### When RL becomes necessary
- AS baseline profitable but plateauing in walk-forward
- 6+ months of regime-diverse training data available
- Joint liquidity + hedge optimization for exotic pairs
- Empirical fill surface estimation (AS exponential decay is a guess)
- Competing with sophisticated counterparties (predictable AS quotes are exploitable)

### Recommended path
1. Symmetric grid → validate backtester
2. AS + regime gate → inventory-aware pricing
3. AS + regime + adaptive hedge → exotic pairs
4. RL dual-head → only after phase 3 is live and profitable
5. RL + adversarial training → compete with Prop AMMs

**Don't build RL until the AS baseline is live and profitable.** The failure modes will tell you exactly what RL needs to learn.

---

## 5. Venue Comparison (July 2026)

| Feature | Hyperliquid | Aster | Lighter |
|---|---|---|---|
| Architecture | Custom L1 (HyperBFT) | Multi-chain (BNB/ETH/SOL/ARB) | ZK-Rollup on Ethereum |
| Maker fee (base) | 0.015% | 0% (USDT perps) | 0% (standard) |
| Maker fee (VIP) | -0.003% (tier 4+ + staking) | -0.50 bps (qualified MM) | 0.002% (HFT) |
| Taker (base) | 0.045% | 0.04% | 0% / 0.02% (HFT) |
| Finality | <1 second | ~1-2s | ~1-2s + ZK proof |
| Daily volume | ~$5.8B | ~$6B | ~$3.75-4.58B |
| Max leverage | 50x | 1001x | 50x |
| Hidden orders | No | Yes | No |
| API | REST + WS (Python SDK) | REST + WS | REST + WS |
| Advanced orders | TWAP, scaling, TP/SL | Hidden, grid | Standard |

**Hyperliquid** = primary venue (deepest books, negative maker fees at scale, sub-second finality, batch order API).
**Aster** = secondary (0% maker, hidden orders, qualified MM rebates, multi-chain).
**Lighter** = opportunistic (zero fees but thinner books, declining volume).

---

## 6. Reusing Existing Stack for Perp MM

| Existing module (clmm-animation) | Perp MM adaptation |
|---|---|
| `strategy/regime.py` | Direct reuse — OU, Hurst, HMM, VPIN all work on perp price data |
| `strategy/as_core.py` | Direct reuse — AS is venue-agnostic |
| `hedge/hedge.py` | Not needed — perp IS the hedge |
| `backtest/engine.py` | Simplified — no bins/LP positions/swaps, just order-vs-trade fill simulation |
| `keeper/loop.py` | Simplified — no withdraw/redeposit, just place/cancel orders |
| `keeper/risk.py` | Modified — add liquidation monitor, funding cost, cancel-on-gap |
| `executor/` | Replace TS executor with Hyperliquid Python SDK |

---

## Project Files

Strategy docs live in `~/projects/clmm-animation/docs/`:
- `dlmm_mm_agent.md` — DLMM spot MM analysis and reproduction plan
- `multi-venue-dlmm-mm-plan.md` — Full 12-phase implementation plan (AS + regime + hedge + RL)
- `PROJECT_SUMMARY.md` — TL;DR of the full plan
- `other-dexes.md` — Meteora vs Orca/Raydium CLMM comparison
- `profitability-quant-vs-rl.md` — Quant vs RL assessment
- `risk-mitigation-non-hedgeable-tokens.md` — Multi-layer stop-loss design
- `bidirectional-perp-mm-strategy.md` — Perp CLOB MM strategy (Hyperliquid/Aster/Lighter)
- `hawkfi-agent-terminal-observations.md` — Summary of HawkFi's permissionless MM approach
- `dlo_core.py` — Strategy core (bin geometry, ladder builder, rebalance logic)
