---
name: data-science
description: "Quantitative trading, backtesting, and data pipeline operations: futures backtesting, market data ingestion, Numerai crypto modeling, and taoshi vanta miner."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Data-Science, Quantitative-Trading, Backtesting, Market-Data, Numerai, Crypto, Mining]
    related_skills: [futures-backtesting, market-data-ingestion, numerai-crypto-modeling, taoshi-vanta-miner]
---

# Data Science

Quantitative trading, backtesting, and data pipeline operations.

## 1. Futures Backtesting

Build and debug futures/commodity backtesting systems with correct accounting, signal validation, and ensemble combiner design.

See: `references/futures-backtesting.md`

## 2. Market Data Ingestion

Data pipeline for market data: OKX, Binance, CCXT, DuckDB, resampling, and various API quirks.

See: `references/market-data-ingestion.md`

## 3. Numerai Crypto Modeling

End-to-end model development for Numerai Crypto v2.0: data pipeline, feature engineering, purged CV, LGBM training, live submission, and monitoring.

See: `references/numerai-crypto-modeling.md`

**Score history fetching:** `scripts/fetch_numerai_scores.py` pulls official
submission scores and round performances for all models. API quirks documented
in `references/numerai-score-fetching.md` — notably `resolved` is always
`False` for Crypto per-day scores, and `round_model_performances_v2` is the
reliable source for round-level comparison.

**LambdaRank early stopping:** `train_lambdarank_fold` now accepts an optional
`val_df` for early stopping on per-date Spearman CORR (the tournament metric),
distinct from the NDCG training objective. Key technique: set `metric="None"`
to suppress built-in NDCG eval so `first_metric_only=True` watches the custom
feval. See `references/lambdarank-early-stopping.md` for the full pattern.

## 4. Taoshi Vanta Miner

Taoshi Vanta mining operations: signal models, lookahead fixes, backtesting, and rules.

See: `references/taoshi-vanta-miner.md`

### Paper Trading Evolution (P0–P6)

**Goal:** Validate signal pipeline end-to-end with paper trading before risking Theta.
Plan: `~/projects/taoshi-miner/documents/PAPER_TRADING_EVOLUTION.md`

**Key architecture decision — single accounting engine:** The backtest
(`signal_bridge/backtest/`) and live paper loop share `signal_bridge/sim/engine.py`.
No second copy of `Position`, `Portfolio`, `execute_signal`, fees, `DrawdownScaler`,
`compute_metrics`, or `run_walk_forward`. The backtest `__init__.py` re-exports
everything from `sim/` for backward compat.

**P0 (done):** Extracted `sim/` engine. Validation: identity check (same objects
from both import paths), smoke test on execution + drawdown scaling + metrics.

**P1–P4 plan:** Versioning/config YAML, live paper loop, risk controls, analytics API.

**P2 (done):** Live paper-trading loop — `signal_bridge/sim/paper_account.py` (PaperAccount class), `signal_bridge/paper_sim.py` (standalone loop), `signal_bridge/router.py` (paper endpoints), `signal_bridge/main.py` (lifespan wiring). Key design: delta rule on signal changes, idempotent JSONL persistence, drawdown scaling via `DrawdownScaler`, circuit-breaker at 8% DD (halt new signals), 10% elimination. Endpoints: `/api/v1/paper/metrics`, `/api/v1/paper/positions`, `/api/v1/paper/equity`.

**P3 (done):** Risk controls online — `_risk_check_allow_new()` in PaperAccount enforces three gates before execution: (1) elimination halts new positions (FLAT always allowed to close), (2) `MAX_POSITIONS` cap on simultaneous positions, (3) `MAX_SINGLE_POSITION` cap per pair. Elimination timestamp tracked and persisted in equity.jsonl. All three gates configurable via PaperAccount constructor.

**P4 (done):** Analytics API delivered in P2 — `/api/v1/paper/metrics`, `/paper/positions`, `/paper/equity` endpoints live.

**P5 plan:** Testnet wiring (netuid 116) with `vali_objects` pre-flight gate.
**P6 plan:** Mainnet (netuid 8).

**Pitfall — PnL double-count on close (CRITICAL, fixed):** `execute_signal` in the FLAT/FLIP_CLOSE path was adding realized PnL to `portfolio.cash` on top of the mark-to-market unrealized PnL already accounted for. Fix: remove the cash addition in the FLAT/FLIP_CLOSE path — MTM already accounts for PnL; close only applies spread fee and logs the trade. Without this fix, every equity/PnL number the system produces (including backtest results) is inflated.

**Pitfall — Elimination not sticky (HIGH, fixed):** `Portfolio.is_eliminated` checked `drawdown >= MAX_DRAWDOWN` each time — if cash recovered, the account would un-eliminate. Fix: added `eliminated: bool = False` field to Portfolio. Once triggered, it stays set permanently.

**Pitfall — Carry fee overcharge in live loop (HIGH, fixed):** `main.py` used `time.sleep(5)` (5s) but `apply_carry_fees` charges per 5-min bar, resulting in ~60× overcharge per bar. Fix: changed to `time.sleep(PAPER_POLL_INTERVAL_SEC)` where `PAPER_POLL_INTERVAL_SEC` defaults to 300s (one bar), configurable via env var.

**Pitfall — backtest vs live divergence:** The `PortfolioLiveProvider` (T3) rebuilds
`make_portfolio_signal_fn` every emit, resetting `PortfolioState` hysteresis. Live
signals will be **churnier than the backtest**. The paper sim faithfully tracks
realized signals — this divergence is a feature, not a bug.

**Pitfall — `arch` dependency:** The backtest runner imports `copula_signal` which
needs `arch` (GARCH/E-GARCH). Missing in the default venv. Install with `pip install arch`
when running copula models. Not required for P0–P4.

**Pitfall — Paper sim import paths:** `PaperAccount` lives in `signal_bridge/sim/paper_account.py` — it imports from `..models` (parent-level, not `.models`) and `..signal_store` (parent-level), and `from .engine import ...` (same package). The `sim/__init__.py` imports `PaperAccount` from `.paper_account`, not from `.engine`. The standalone `paper_sim.py` uses absolute imports (`from signal_bridge.models import ...`). Mix relative/absolute imports across the package boundary to avoid `ModuleNotFoundError`.

**Existing plans in project:**
- `documents/signal-pipeline-paper-sim-plan.md` — detailed local sim design (two fidelity tiers: lightweight + `vali_objects` authoritative)
- `documents/mvp-paper-trading-testnet.md` — testnet wiring steps (T1–T8)
- `documents/IMPROVEMENT_PLAN_SN8.md` — model improvements (copula, funding alpha, vol-weighted ensemble)

## 5. VolSurface / Skewbik — Deployment & Debugging

Full-stack setup and troubleshooting for the volsurface/skewbik system:
crypto implied-vol surface engine (C++17 core + Python bindings),
TimescaleDB data pipeline, FastAPI backend, Next.js frontend.

See: `references/volsurface-skewbik-deployment.md`

## 6. Numerai Crypto — LAPACK DLASCL NaN Guard

LAPACK routines (`lstsq`, `solve`, `inv`, `LedoitWolf`) crash when the input
contains NaN. The symptom is:

    On entry to DLASCL parameter number  4 had an illegal value

Every `np.linalg.*` call site in the project needs `np.nan_to_num` on inputs
BEFORE the call — not just the allocation/neutralizer path, but also the
LambdaRank training path (`lambdarank_train.py`, `train_lambdarank.py`,
`train_lambdarank_beta.py`, `lgbm_train.py`) which calls `lstsq`.

The S2 model (`submit_s2_live.py`) uses `train_lambdarank_fold` →
`residualize_and_bin_target` — a separate code path from the allocation
neutralizer. Both must be patched independently.

See: `references/lapack-dlascl-nan-fix.md`

### Pitfalls

- **DB auth failure masks as 500 on ALL endpoints** — `/health` works (no DB needed), but `/snapshots`, `/surface/...`, `/calibrate` all 500. Check Docker container env vars for actual user/db.
- **WS "LIVE" is transport-only** — the WebSocket connects even when DB is broken. The indicator doesn't mean data is flowing.
- **Frontend `console.error` only** — when snapshots fetch fails, the UI shows "Loading…" silently. No user-visible error state on the fetch.
- **`VOLSURFACE_DB_DSN` env var** must match the actual Docker container's `POSTGRES_USER`/`POSTGRES_DB`. Default fallback is `volsurface/volsurface` which may not exist.
- **Calibration is a no-op without C++ bridge** — the `/calibrate` endpoint refits the same raw `mid_iv` data that the initial surface fetch already fitted. With `libvs_core_shared.so` absent, band_mode has no effect and the Python SVI fallback produces identical params. Calibration only changes results when: C++ bridge is built/available, strikes are excluded via right-click, or model type is changed.

## 7. LLM News Sentiment Pipeline

Build point-in-time safe event features from LLM-extracted news, without OHLCV price data. Covers: news ingest → LLM extraction → cache → PIT feature build → text-only signal evaluation.

**Expected signal characteristics (from 7-month run on 17 RSS feeds):**

- **Event sparsity:** ~2-3 news items per hour across ALL 40 crypto assets.
  BTC (most-covered asset) gets 6.7 events/bar hourly, but 40% of assets
  have <0.5 events/bar. Most sparsity is concentrated.
- **Zero-event bars:** ~79% of hourly bars have 0 events in the 24h window.
  This drops to ~50% if you widen to 72h lookback. Daily bars would have
  <10% zero-event bars.
- **Autocorrelation:** Polarity autocorr lag=1 is ~0.99 at hourly frequency.
  News narratives persist for 24-48h. The features from T and T+1 are
  nearly identical. Daily bars cut autocorr to ~0.5-0.6, more signal/bar.
- **Polarity distribution:** mean ≈ +0.05 (slight bullish bias), std ≈ 0.23.
  The distribution is roughly symmetric when signal exists and degenerate
  (median 0.0) when no events fire. Trimming zero bars reveals std ~0.5.
- **Event type distribution:** macro (~63%), partnership (16%), other (10%),
  regulation (5%), depeg (2%), fork (1.5%), hack (1.3%), listing (1%).
  Rare events (hack, listing, depeg) are <3% of bars but carry the strongest
  price signals individually.
- **Multi-collinearity:** n_events ~ n_high_conf_events at r=0.999,
  polarity_sum ~ mag_weighted_polarity at r=0.99. Only ~5-6 independent
  dimensions across the 61-feature vector. Feature selection or PCA needed.
- **LLM sentiment from llama3-8b** produces confidence scores clustered
  around {0.78, 0.85} with very little variance — the model is not well
  calibrated for discriminating sentiment strength.
- **Info ratio (polarity-only, no price):** ~0.16 estimated. Not tradable
  alone but could contribute as a satellite signal in a multi-factor model.

**Key pitfalls:**

- PIT filter must be INSIDE `build_feature_vector`, not a caller responsibility. Unfiltered events produce identical features for every bar — a silent data bug.
- 17 RSS feeds give ~11K items over 7 months, but 95% of volume is in the last 30 days. The distribution is heavily right-skewed — early months have almost no coverage.
- Contamination audit mandatory for any LLM-derived backtest: entity redaction, extraction-only ablation, temporal holdout.
- llama3-8b at temperature=0 yields ~2s per extraction. 3,600 sequential extractions = ~2h wall-clock. Single-threaded, no async batching.
- If GDELT body text is missing (empty strings), the backfill contributes zero EventRecords despite having 340K records. Verify GDELT has actual body text before running batch ETL on it; the title/body lengths check at runtime silently drops them.

See: `references/news-sentiment-pipeline.md`
See: `references/llm-news-signal-diagnostics.md`

## 8. On-Chain & Perp Market Making Strategy

Design of market-making systems for Solana DLMM (Meteora) and perp CLOB venues (Hyperliquid, Aster, Lighter). Covers Avellaneda-Stoikov pricing, regime detection, transaction-cost-aware hedging, stop-loss design for non-hedgeable tokens, and bidirectional perp MM.

**Project:** `~/projects/clmm-animation/` — Python brain + TS executor for DLMM MM, with perp MM extension.

**Key insights from strategy design sessions:**

- **Quant models are the floor, RL is the ceiling.** AS + regime detection is sufficient for profitability on bluechip pairs. RL is an enhancement layer for empirical fill surfaces, refresh policy, and hedge interaction — not the foundation. Don't build RL until the AS baseline is live and profitable.
- **Perp CLOB MM is structurally simpler than spot DLMM MM.** Single signed delta (not two-token inventory), zero rebalance cost (just cancel/place orders), no custody risk, no rug risk. The cost: liquidation risk and funding cost — neither exists in spot.
- **Stop-loss for non-hedgeable tokens must be liquidity-aware.** A price threshold alone is insufficient — exiting into vanishing liquidity crystallizes losses. The stop-loss is a composite trigger (price + drawdown + rug signal + inventory aging) with three execution branches: clean exit (sufficient depth), emergency Jito bundle (rug in progress), or hold-and-alert (no liquidity).
- **De-risk mode** is the key difference between professional and amateur MM: stop accumulating, let asks work passively, escalate to TWAP only if passive doesn't reduce inventory within a time budget. Don't market-dump.

**Venue fee comparison (as of July 2026):**

| Venue | Maker fee (base) | Maker fee (VIP) | Taker (base) |
|---|---|---|---|
| Hyperliquid | 0.015% | -0.003% (tier 4+ + staking) | 0.045% |
| Aster | 0% (USDT perps) | -0.50 bps (qualified MM) | 0.04% |
| Lighter | 0% (standard) | 0.002% (HFT) | 0% / 0.02% (HFT) |

See: `references/market-making-strategy.md`

### Implementation architecture

The design docs have evolved into code in `~/projects/amm-solution/`. Four pip packages: `mm-core` (shared brain), `dex_executor` (OPMS), `perp_bot`, `dlmm_bot`. Streams A/B/C are done (309 tests total). Stream D (DLMM bot) is in progress — keeper, backtest, exec_bridge, hedge, risk_dlmm built; TS executor and bus publisher not yet built.

See: `references/amm-solution-implementation.md`

## 9. Critical Rules

### Numerai Submission Safety
**When testing new models or running validation experiments, submission MUST be turned off.**
- Use `--no-submit` flag or set `SUBMIT=False` in submission scripts
- Never submit predictions during test runs unless explicitly requested by user
- Accidental submissions corrupt live tournament results and cannot be undone
- **Always run a submission in `--test` mode (no upload) after any download-related code change** — a download-step failure looks like a silent skip, not an upload error, so a live run would appear to have succeeded while silently doing nothing.

**Run all five Numerai models serially when testing locally.** Five submission processes running in parallel exhaust the Strix Halo cgroup memory limit and trigger the kernel OOM killer mid-training (~1000 MB per process at the PIT/feature step), killing every model at the same line. The production cron succeeds because it runs in a separate cgroup with a higher limit; a local test run does not. Run them one at a time (the `--test` flag is enough to validate the pipeline end-to-end before any live submit).

### Numerai Score History Fetching
- `scripts/fetch_numerai_scores.py` pulls official scores for all models (m5_draft, m5_rc)
- Run: `PYTHONPATH=. uv run python3 scripts/fetch_numerai_scores.py`
- `submission_scores` API: `resolved` is always `False` for Crypto per-day scores — filter on `value is not null` instead
- `round_model_performances_v2` (deprecated): reliable source for round-level corr/percentile/payouts
- See `references/numerai-score-fetching.md` for API quirks and cross-model comparison pattern

### LambdaRank Early Stopping (m5_rc only)
- `train_lambdarank_fold` now accepts `val_df` + `early_stopping_rounds=100`
- Training metric: NDCG. Early stopping metric: per-date Spearman CORR via `feval`
- Must set `metric="None"` when val_df provided, otherwise `first_metric_only=True` watches NDCG@5, not feval
- `submit_s2_live.py` uses 80/20 time split; `train_s2_combined.py` passes CV val fold
- Production m5_draft unaffected — `submit_live.py` does not import from `lambdarank_train.py`
- See `references/lambdarank-early-stopping.md`
