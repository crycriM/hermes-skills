# Memory Pruning: Before & After

## Session: 2026-06-10 — "memory.md full" fix

### Problem
MEMORY.md at 2,146/2,200 chars (97%). Turn header showed "MEMORY [97% — 2,138/2,200 chars]". 
User reported recurrent "memory.md full" issue.

### Diagnosis
Two dense blocks were the culprits:

1. **Taoshi SN8 block** (1,610 chars — 75% of file): Full signal model catalog with descriptions, 
   backtest results with individual Sharpe ratios, AdaVol/Copula/Funding alpha details. 
   All of this already lived in `taoshi-vanta-miner` skill.

2. **Numerai Crypto block** (153 chars after first pass): Module paths, hyperparameters, 
   model names. Already in `numerai-crypto-modeling` skill.

### Before (MEMORY.md, 2,146 chars)
```
Taoshi SN8 miner: ~/projects/taoshi-miner. Bittensor subnet 8 (testnet 116). Signal bridge (FastAPI :8000). 12 pairs.
Signal models (signal_bridge/backtest/):
- trend_mr (production): per-pair Ridge + BTC regime + AdaVol vol sizing.
- AdaVol regime (P1): adaptive EWMA vol forecasting, 3 regimes (LOW/MED/HIGH_VOL). Runner: --regime-mode adavol.
- AdaVol position sizing (P3): compute_adavol_forecast() per asset, leverage = base * (|pred|/adaVol_forecast) * regime_mult. In trend_mr_model.py. 
- Copula (P2): Student-t GARCH + bivariate copula. Fails on 5m real data.
- Funding alpha (P4): funding rate z-score dual-regime (MR on |z|>2, momentum on |z|>1.5). In funding_alpha.py. Fetches from Binance via CCXT.
- Others: momentum, regime, pooled_rank, ensemble, portfolio.
Backtests (30d 5m, 11 pairs, bias-fixed):
- Baseline rule-based: +12.1% ret, 1.85 Sharpe.
- P1 only (AdaVol regimes): +21.4%, 3.47 Sharpe.
- P1+P3 (AdaVol regimes + sizing): +23.0%, 3.34 Sharpe.
```

### After (MEMORY.md, 1,005 chars)
```
Taoshi SN8 miner: ~/projects/taoshi-miner (see taoshi-vanta-miner skill). Bittensor subnet 8 (testnet 116). Signal bridge (FastAPI :8000). Prod model: trend_mr (per-pair Ridge + BTC AdaVol regimes + vol sizing). 12 pairs.
```

### Result
| Metric | Before | After |
|--------|--------|-------|
| MEMORY.md size | 2,146 chars | 1,005 chars |
| Limit | 2,200 | 2,500 |
| Headroom | 54 chars (2.5%) | 1,495 chars (60%) |

Also cleaned: stale `.lock` files from Mar-Apr 2026, config limit bumped via `hermes config set memory.memory_char_limit 2500`.

### Principle
When skills already contain the details, memory should be a **directory of pointers**, not a **duplicate knowledge base**. Every char in memory costs tokens on every turn. Skill details cost tokens only when the skill is loaded.
