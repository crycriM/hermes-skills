# Adapting Numerai Crypto Models to Vanta Network (SN8)

Reference for porting the Numerai Crypto v2.0 modeling pipeline to Taoshi's Vanta Network
on Bittensor Subnet 8. Written after initial reconnaissance (2026-06-06).

## Quick Context

**Vanta SN8** is a competitive trading signal network where miners submit LONG/SHORT/FLAT
orders and validators evaluate them on real-time PnL. It's fundamentally different from
Numerai's cross-sectional ranking problem.

## Key Differences

| Aspect | Numerai Crypto v2.0 | Vanta Network SN8 |
|--------|---------------------|-------------------|
| Problem type | Cross-sectional ranking of 300+ coins | Direction + leverage on 6–12 assets |
| Target | Spearman rank correlation | Realized PnL (profit/loss) |
| Horizon | 20 business days (~28d) | Continuous, event-driven |
| Output | Percentile ranks [0,1] | LONG/SHORT/FLAT + leverage (0.01–2.5x for crypto) |
| Risk management | None (pure prediction) | 10% MDD elimination, portfolio leverage caps, risk penalties |
| Scoring delay | ~30 days for resolution | Weekly payout (debt-based) |
| Evaluation metric | Spearman CORR | Average daily PnL (100% weight) + Sharpe/Calmar/Sortino/Omega (0% weight currently) |
| Data sources | Numerai-provided 22 TA features | Glassnode (on-chain), LunarCrush (social), OHLCV from exchange APIs |
| Signal frequency | Once per round (daily) | Continuous (5s cooldown per pair) |

## Architecture — Local Project

**Repo:** `~/projects/taoshi-miner/`
- `ptn/` — cloned vanta-network (validators, RPC services, data generators)
- `signal_bridge/` — FastAPI service (port 8000) translating ML signals → miner orders
- `neurons/custom_miner.py` — miner forward() override (OUTDATED, see TASK-16)
- `documents/` — PLAN.md, PROGRESS.md, REMAINING_TASKS.md

**Pending tasks (from REMAINING_TASKS.md):**
- TASK-16: Rewrite signal forwarder (poll signal bridge, POST changed signals to miner REST API)
- TASK-17: Configure miner API key (`mining/miner_secrets.json`)

**Signal flow (corrected, NOT pull-based):**
```
ML Signal Source → Signal Bridge (port 8000) → Signal Forwarder → Miner REST API (port 8088) → Bittensor Validators
```
The forwarder polls the bridge for changes and pushes to the miner API — the miner does NOT pull
from the bridge on validator request.

## What Ports Over From Numerai

1. **Feature engineering concepts** — DPP (funding rates + OI), FD (TVL/price divergence),
   regime detection, and sentiment are all applicable. But they need real-time exchange data
   instead of Numerai's precomputed features.

2. **Backfill infrastructure** — CCXT for OHLCV/funding rates, DefiLlama for on-chain TVL.
   The `data_generator/` directory in ptn already has Polygon, Tiingo, Binance, Bybit, Kraken connectors.

3. **Signal bridge architecture** — already built. Replace `ExampleProvider` with a real ML provider.

4. **Training discipline** — purged CV, feature importance analysis, neutralization concepts
   (though the implementation is radically different).

## What Does NOT Port

1. **Cross-sectional ranking** — useless on 6–12 pairs. Direction + confidence matters instead.

2. **Neutralization** — no "crowd starter features" to neutralize against. Risk management
   replaces neutralization as the guardrail.

3. **Purged time-series CV** — need walk-forward backtesting that respects:
   - Position state (LONG/SHORT/FLAT transitions)
   - Leverage limits (position + portfolio caps)
   - Drawdown constraints (10% MDD = elimination)
   - Carry fees, spread fees, slippage costs
   - Market hours (crypto 24/7, forex closes weekends)

4. **LGBM ranking model** — becomes a directional classifier or regression model outputting
   (direction, leverage, confidence) triples.

## Supported Assets (Crypto — active)

| Symbol | Pair |
|--------|------|
| BTCUSD | BTC/USD |
| ETHUSD | ETH/USD |
| SOLUSD | SOL/USD |
| XRPUSD | XRP/USD |
| DOGEUSD | DOGE/USD |
| ADAUSD | ADA/USD |

Forex (32 pairs) and commodities (XAUUSD, XAGUSD) also available.
Equities and indices currently blocked.

## Key Constraints for Strategy Design

1. **Uni-directional positions** — once a position opens LONG, it can't flip SHORT.
   Must close (FLAT) then open a new SHORT position.

2. **Leverage bounds** — Crypto: [0.01, 2.5x] per position, 5x portfolio cap.
   Minimum order leverage: 0.001.

3. **5-second cooldown** — can't submit orders for the same pair within 5 seconds.

4. **Risk profiling penalties** — avoid: stepping 3+ times into a losing position,
   using >50% of available leverage, uneven time intervals between orders.

5. **Hotkey permanence** — eliminated/deregistered hotkeys are permanently blacklisted.
   Each registration requires a fresh hotkey.

## Model Design Options

### Option A: Directional Classifier
Train a model to predict direction (UP/DOWN/FLAT) for next N hours.
Output confidence → leverage. Simple, interpretable.

### Option B: Return Regression
Predict expected return over horizon H. LONG if > threshold, SHORT if < -threshold,
FLAT otherwise. Leverage proportional to |expected_return|.

### Option C: Reinforcement Learning
Directly optimize PnL with drawdown constraints. Harder to train but naturally
respects position limits and risk management.

## Data Sources

### Glassnode (on-chain — partnership claim, no operational integration)
The GitHub README mentions a Glassnode partnership, but there is no documented API key provisioning, discount code, or access mechanism for Vanta miners. The docs site (docs.taoshi.io) has zero mentions. Glassnode is a standard paid SaaS ($29–$799/mo). Treat as an independent data source you'd pay for yourself. Analogous to our DAA/FD features from DefiLlama + GitHub.

### LunarCrush (social sentiment — partnership claim, no operational integration)
Same situation as Glassnode: mentioned in README, absent from docs, no special access path. Free tier exists (60 req/min, 3 months history). Analogous to our Coinybubble sentiment features.

### Exchange APIs (already in ptn/data_generator/)
- Polygon (equities, $248/mo)
- Tiingo (equities/forex, $50/mo)
- Binance, Bybit, Kraken (crypto — free)

### Built: CCXT Provider (signal_bridge/providers/ccxt_provider.py)
As of 2026-06-06, a working provider exists that:
- Fetches 5-min OHLCV from Binance for 6 crypto pairs via CCXT
- Computes: momentum (12/26/52 candles), volatility, RSI, volume ratio, trend strength
- Generates LONG/SHORT/FLAT signals with dynamic leverage (0.02–0.5×) + confidence score
- Auto-starts as background thread when signal bridge boots
- Pairs: BTCUSD, ETHUSD, SOLUSD, XRPUSD, DOGEUSD, ADAUSD

Signal forwarder (`neurons/signal_forwarder.py`) polls the bridge every 30s and POSTs changed orders to the miner REST API. Miner API key configured in `ptn/mining/miner_secrets.json`.

Next: improve the model with DPP (funding rates), sentiment, and regime detection features from the Numerai pipeline. Add walk-forward backtesting with Vanta's simulated fees + drawdown constraints.

## Miner REST API Contract

`POST http://127.0.0.1:8088/api/submit-order`

Headers: `Authorization: <api_key>`, `Content-Type: application/json`

Required fields: `execution_type` (MARKET/LIMIT/BRACKET), `trade_pair`, `order_type` (LONG/SHORT/FLAT)
Exactly one of: `leverage`, `value`, `quantity`

See `ptn/docs/miner_rest_server.md` for full spec.

## Next Steps (when ready to build)

1. ✅ Complete TASK-17 (API key) and TASK-16 (signal forwarder) — done 2026-06-06
2. ✅ Build a `VantaCryptoProvider` replacing `ExampleProvider` — done 2026-06-06
3. Run on testnet (netuid 116) to verify end-to-end flow
4. Improve model: add DPP/funding rate features and sentiment from Numerai pipeline
5. Build walk-forward backtester simulating Vanta's fees + drawdown rules
6. Research Glassnode/LunarCrush API for orthogonal data (note: no special miner access)
