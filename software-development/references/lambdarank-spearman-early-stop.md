# LambdaRank with Custom Spearman Early Stopping

## Problem

LambdaRank trains on **NDCG** (Normalized Discounted Cumulative Gain), but in
many ranking problems the actual evaluation metric is **per-group Spearman
CORR** (e.g., Numerai Crypto scores per-date Spearman). Training all 2000
iterations on NDCG can overfit to NDCG while Spearman degrades.

## Solution

Add a validation set (chronological split: last 20% of dates) and early-stop on
a custom `feval` that computes mean per-date Spearman CORR.

### Key pieces

1. **Residualized target**: same as training — OLS per date against starter/feature columns, then rank-bin to quintiles. Both train and validation sets get the same treatment.

2. **Custom feval closure**: pre-computes date-group indices once, then at each
   iteration computes per-group Spearman between raw predictions and raw target
   (not the binned labels). Returns `("spearman_corr", mean_corr, True)`.

3. **Disable built-in NDCG on eval** — set `metric: "None"` in the params dict
   when a validation set is provided, so only the feval metric appears on the
   validation set. The training objective still uses NDCG (LambdaRank).

4. **early_stopping(first_metric_only=True)** watches only the feval metric
   (it's the only one on the validation set), so early stopping fires on
   Spearman degradation.

### Code skeleton

```python
import lightgbm as lgb
from scipy.stats import spearmanr

def make_spearman_feval(val_dates, val_raw_target):
    """Build a feval computing mean per-date Spearman CORR."""
    sorted_idx = np.argsort(val_dates, kind="stable")
    uniq_dates, starts = np.unique(val_dates[sorted_idx], return_index=True)
    n = len(val_raw_target)
    groups = []
    for i in range(len(uniq_dates)):
        start = starts[i]
        end = starts[i + 1] if i + 1 < len(uniq_dates) else n
        idx = sorted_idx[start:end]
        groups.append((idx, val_raw_target[idx]))

    def feval(preds, dataset):
        corrs = []
        for idx, target_d in groups:
            if len(idx) < 5:
                continue
            c = float(spearmanr(preds[idx], target_d)[0])
            if not np.isnan(c):
                corrs.append(c)
        mean_c = float(np.mean(corrs)) if corrs else 0.0
        return "spearman_corr", mean_c, True

    return feval
```

### Pitfalls

- **`spearmanr` returns a `SignificanceResult`** — access via
  `float(result.correlation)`, not tuple indexing. Pyright may complain about
  `.correlation` being unknown; suppress with `# type: ignore[attr-defined]`.

- **`first_metric_only=True` with built-in metrics active** — if the params
  include `metric: "ndcg"`, the built-in NDCG is the *first* metric and the
  feval metric is appended. Setting `first_metric_only=True` then watches
  NDCG, not your custom metric. **Fix**: disable built-in metrics when a
  validation set is present by passing `metric: "None"` in params.

- **Validation target for LambdaRank vs for Spearman**: the Dataset needs
  integer labels (0-4, residualized). The feval needs raw target (float 0-1).
  Store both separately.

- **Best iteration**: LightGBM automatically predicts using `best_iteration`
  after early stopping. No manual index is needed.

### Applicability

Any ranking problem where:
- Training uses NDCG (LambdaRank, LambdaMART)
- Evaluation uses Spearman, Kendall, or another non-NDCG metric
- The validation set should be a realistic time-based split (not random)
