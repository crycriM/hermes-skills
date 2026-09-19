# Numerai Crypto model-evolution reference

## Comparison matrix

| Axis | Production control | Experimental variant |
|---|---|---|
| Target | continuous target | residual target or transformed bins |
| Objective | L2 regression | LambdaRank or residual L2 |
| Features | frozen production stack | production plus one family |
| Validation | purged walk-forward | identical folds and dates |
| Neutralization | explicit inference-time lambda ladder | only if serveable |
| Output | rank-normalized prediction | residual-only or beta-restored, explicitly labeled |

## Recommended experiment order

1. Reproduce the frozen production control.
2. Compare raw-target regression to inference-time neutralization.
3. Compare residual labels and beta restoration separately.
4. Add one feature family at a time.
5. Test feature sampling and tree capacity.
6. Run horizon diagnostics before accepting short-lived signals.
7. Validate in a separate slot and wait for multiple resolved score days.

## Minimum metrics

- Per-date CORR mean, standard deviation, and Sharpe.
- Neutralized CORR for lambda values 0, 0.2, 0.5, 0.7, and 1.0.
- MMC or a clearly labeled offline MMC proxy.
- Fold-by-fold deltas against the control.
- Feature coverage, zero rate, and late-fold sign stability.
- Prediction rank correlation across adjacent rounds.
- Horizon ribbon at 1, 3, 7, 20, 30, and 60 days.

## Promotion gate

Keep the production slot unchanged. Promote only when a candidate has positive local OOS evidence, positive or non-negative MMC behavior, no severe late-fold degradation, and several comparable resolved live score days. A locally cached score table with unequal model coverage is evidence with a caveat, not a paired benchmark.
