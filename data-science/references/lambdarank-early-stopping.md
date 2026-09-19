# LambdaRank Early Stopping with Custom Eval Metric

How to add early stopping to LightGBM LambdaRank training using a different
metric than the training objective — specifically, training on NDCG but
stopping on per-date Spearman CORR (the Numerai tournament's actual metric).

## Problem

`src/models/lambdarank_train.py` trains LambdaRank with `num_iterations=2000`
and no validation set. With 97+ features and no early stopping, the model
overfits — live corr for m5_rc was declining (0.039 -> 0.033, last round -0.042).

## Solution

### 1. Custom feval for Spearman CORR

LightGBM's `feval` parameter accepts a callable:
`(preds, dataset) -> (eval_name, eval_result, is_higher_better)`.

The closure pre-sorts validation rows by date and computes per-date Spearman
in O(n log n) per eval call:

```python
def _make_spearman_feval(val_dates, val_target):
    sorted_idx = np.argsort(val_dates, kind="stable")
    unique_dates, start_indices = np.unique(val_dates[sorted_idx], return_index=True)
    # Pre-compute group slices
    groups = [...]
    
    def feval(preds, dataset):
        corrs = []
        for idx, target_d in groups:
            c = float(spearmanr(preds[idx], target_d).correlation)
            if not np.isnan(c):
                corrs.append(c)
        return "spearman_corr", np.mean(corrs), True
    return feval
```

### 2. Disable built-in metric on validation set

The critical insight: `first_metric_only=True` in `lgb.early_stopping` watches
the FIRST metric in the evaluation result list. By default, that's NDCG@5
(the training metric), NOT the custom feval.

To make early stopping watch ONLY spearman_corr, set `metric="None"` in the
params dict when a validation set is provided:

```python
train_params = {**LAMBDA_PARAMS, "metric": "None"}
```

This disables the built-in NDCG eval metric. The lambdarank objective still
trains on NDCG internally — we're only changing what metric early stopping
watches on the validation set.

### 3. Early stopping callback

```python
callbacks = [lgb.early_stopping(
    stopping_rounds=100,
    first_metric_only=True,  # watch only spearman_corr
    verbose=True,
)]
```

With `metric="None"` and feval providing spearman_corr, the eval result list
contains only `spearman_corr`, so `first_metric_only=True` correctly targets it.

### 4. Train/val split for live submission

For `submit_s2_live.py` (which has no CV), use a time-based 80/20 split:

```python
all_dates = sorted(train_df["date"].unique().to_list())
split_idx = int(len(all_dates) * 0.8)
fit_df = train_df.filter(pl.col("date").is_in(all_dates[:split_idx]))
val_df = train_df.filter(pl.col("date").is_in(all_dates[split_idx:]))
model = train_lambdarank_fold(fit_df, features, target, starters,
                              val_df=val_df, early_stopping_rounds=100)
```

For `train_s2_combined.py` (CV), pass the CV validation fold directly as `val_df`.

## Verification

Smoke test with synthetic data confirms:
- Without `val_df`: all 2000 iterations run (backward compatible)
- With `val_df`: stops early, log shows `Evaluated only: spearman_corr`
- `best_iteration` is set on the returned Booster

## Key pitfalls

1. **`first_metric_only=True` watches the first metric in the list, not a named
   one.** Without `metric="None"`, the first metric is NDCG@5, not your feval.
   You MUST disable the built-in metric to make early stopping watch feval.

2. **`feval` metrics always appear AFTER built-in metrics** in the eval result
   list. There's no way to reorder them.

3. **scipy `spearmanr` returns a `SignificanceResult`**, not a tuple. Access
   via `.correlation` attribute. Pyright doesn't resolve the type — use
   `# type: ignore[attr-defined]`.

4. **LambdaRank validation labels must be residualized** the same way as
   training labels (per-date OLS against starters, then rank-bin to quintiles).
   But the Spearman feval should use the RAW target, not the binned labels,
   because Spearman on binned quintiles would be on the residualized target
   rather than the true target.

5. **Production model (m5_draft) is unaffected.** `scripts/submit_live.py`
   does not import from `lambdarank_train.py`. The shared module is used only
   by `submit_s2_live.py` and `train_s2_combined.py` (both m5_rc).

## Files touched

- `src/models/lambdarank_train.py` — added `val_df`, `early_stopping_rounds`
  params, `_make_spearman_feval`, `metric="None"` when val provided
- `scripts/submit_s2_live.py` — `train_final_model()` does 80/20 time split
- `scripts/train_s2_combined.py` — passes CV val fold to `train_lambdarank_fold`