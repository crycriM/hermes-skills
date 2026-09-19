# AMM Solution — Implementation Architecture

Project: `~/projects/amm-solution/` — two market-making bots (perp CLOB + DLMM spot) sharing one brain library (`mm_core`), with the OPMS as single order-authority for perps.

## Package Layout (as of July 2026)

```
amm-solution/
  mm-core/           # Shared brain: AS core, vol, regime, markout, risk_policy, inventory, pnl, contracts
  dex_executor/      # OPMS — FastAPI execution service (AWS). Adapters: Hyperliquid, Aster, Lighter
  perp_bot/          # Perp CLOB MM keeper + backtest (consumes mm_core, talks to OPMS via intents)
  dlmm_bot/          # DLMM spot MM keeper + backtest + exec bridge (Zone B, non-AWS)
  clmm-animation/    # Design docs (strategy, architecture, plans)
  LP-hedging-strategy/ # Existing Meteora position monitor (TS) + hedge automation (Python)
```

## Stream Progress (plan-overview.md workstreams)

- **Stream A (mm_core)**: DONE — 108 tests. All modules: as_core, vol, regime, markout, risk_policy, inventory, pnl, contracts.
- **Stream B (OPMS)**: DONE — 153 tests. strategy_kind, avellaneda_stoikov_mm (two-sided Guéant), intent_router (idempotent), md_publisher.
- **Stream C (perp_bot)**: DONE — 25 tests. keeper, opms_client, config, backtest.
- **Stream D (dlmm_bot)**: IN PROGRESS — grid + ladder + config + tests (26 tests). Keeper, backtest, exec_bridge, hedge, risk_dlmm built but tests not fully green yet. TS executor and lp-monitor bus publisher not yet built.
- **Stream E**: Not started (convergence: shared risk config diffing, shared backtest loop).

## Key Implementation Patterns

### Exec Bridge (dlmm_bot/exec_bridge.py)
JSON stdin/stdout protocol to the TS Meteora executor. Python keeper owns sequencing and strategy; TS shim owns signing and SDK calls. FakeExecBridge for tests and shadow/dry-run mode. Verbs: get_state, deposit_single_sided, withdraw, swap, refresh_bundle.

### Keeper Loop (dlmm_bot/keeper.py)
Poll → evaluate_regime → RiskPolicy → DLMM-specific risk → AS ladder → actuate. Decisions: QUOTE/WIDEN → refresh_bundle when drift exceeds threshold; STOP_QUOTING → withdraw to safe leg; DE_RISK → stop bids, drain asks, TWAP remainder; EMERGENCY_EXIT → Jito bundle withdraw + swap. CycleRecord logged as JSON lines (shadow-mode artifact). dry_run flag gates tx submission.

### Hedge Controller (dlmm_bot/hedge.py)
MA+deadband (normal regime) + vol-scaled window + hard delta-cap backstop (tail regime). Cube-root band (Zakamouline/Whalley-Wilmott): bandwidth ~ (per_trade_cost)^(1/3), so 2→4bps widens only ~26%. Emits ExecIntents to OPMS for perp shorts (not direct orders).

### DLMM Risk (dlmm_bot/risk_dlmm.py)
PairType enum: bluechip (SOL/USDC, full ladder), memecoin (one-sided, rug kill-switch, strict gate), exotic (both legs hedgeable, relaxed trend gate when hedge active). TVL rug detection, inventory %-caps, one-sided posture enforcement for memecoins.

### DLMM Backtester (dlmm_bot/backtest.py)
Event-replay of BinEvent objects (bin-crossing swaps). Fill rule: up-cross fills asks (sell base), down-cross fills bids (buy base). Dynamic fees accrue only on crossed bins. Metrics: Sharpe, max-DD, fill rate, spread capture, markout, LP fee income, rebalance cost.

## Common Pitfalls

### Python 3.14 dataclass mutable defaults
`@dataclass` fields with mutable default values (e.g., `gate: GateConfig = GateConfig()`) raise `ValueError: mutable default`. Fix: use `field(default_factory=GateConfig)`. This hits any dataclass that embeds another dataclass as a default.

### EMA convergence in tests
EMA with `alpha = dt / (dt + tau_h)` converges slowly when tau_h >> dt. For test convergence, use tau_h=10 and 5000+ iterations, not tau_h=100 with 1000 iterations.

### Keeper cycle test fixtures
Start FakeExecBridge with zero inventory balances and tvl_usd above the minimum threshold. If you start with non-zero quote inventory, the inventory cap check fires before the keeper can deposit, causing all tests to hit the de-risk path instead of the quote path.

## What Remains (Stream D)

1. TS Meteora executor shim (`dlmm_bot/executor/bridge.ts`) — thin TS layer calling `@meteora-ag/dlmm` SDK
2. lp-monitor bus publisher (`LP-hedging-strategy/lp-monitor/src/services/busPublisher.ts`) — NATS publisher for MarketSnapshot + pos.dlmm.*
3. Final test green-up (3 keeper tests need fixture fixes)
4. Full regression run across all 4 packages