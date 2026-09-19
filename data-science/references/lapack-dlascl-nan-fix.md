# LAPACK DLASCL "Illegal Value" — NaN in NumPy/SciPy Linear Algebra

## Symptom
```
On entry to DLASCL parameter number  4 had an illegal value
```
or
```
numpy.linalg.LinAlgError: Lapack routine ... got an illegal value
```

## Root Cause
LAPACK routines (called by `np.linalg.inv`, `np.linalg.solve`, `scipy.linalg`, `sklearn.covariance.LedoitWolf`) use scaled row operations internally. If the input matrix contains `NaN` or `±Inf`, the scaling factor becomes `NaN` → `DLASCL` aborts.

## Typical Entry Points in Quant Pipelines

1. **`scipy.stats.norm.ppf()` at rank boundaries** — `ppf(0) = -inf`, `ppf(1) = +inf`. Clip to [-3, 3] but add `nan_to_num` as final guard.
2. **`LedoitWolf.fit()` on dirty data** — any NaN row in the returns matrix propagates to NaN in the covariance estimate.
3. **`np.std()` on all-NaN column** — returns NaN, which then zeros out downstream vol-dependent computations.
4. **Polars null mask edge cases** — `is_not_null()` catches literal NaN/null, but arithmetic on the extracted NumPy array can produce `NaN` from `0/0` or `Inf - Inf`.
5. **`np.linalg.lstsq()` on NaN features** — the S2 model's `residualize_and_bin_target` calls `lstsq(X, y)` per-date. If any starter feature has NaN (e.g. from rolling windows on early dates, or from copula z-score columns), LAPACK crashes. This is the **most commonly hit path** in the Numerai submission pipeline because `submit_s2_live.py` runs daily and the feature matrix accumulates edge cases over time.
6. **`np.linalg.solve()` on near-singular `X'X`** — if a column is constant or perfectly collinear with another, the regularized solve can still produce NaN in edge cases.

## Fix Pattern (defensive, minimal change)

```python
import numpy as np

# Before ANY linalg call, sanitize inputs:
X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

# After computing a matrix, also sanitize outputs:
cov = np.nan_to_num(cov, nan=0.0, posinf=0.0, neginf=0.0)
cov = (cov + cov.T) / 2.0  # enforce symmetry

# For weight vectors:
w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
```

## Prevention Strategy for Numerai Crypto Bot

Sanitize at the earliest choke point — don't wait until the linalg call to discover NaN. Clean data as soon as it enters the function.

### Complete Inventory of LAPACK Call Sites (7 total)

| File | Function | Call | Fixed? |
|---|---|---|---|
| `hl_signal/allocation.py::estimate_sigma()` | LedoitWolf covariance | `LedoitWolf().fit()` + `np.cov()` | Yes |
| `hl_signal/allocation.py::scores_to_mu()` | Blom score → expected return | `norm.ppf()` | Yes |
| `hl_signal/allocation.py::compute_aim_portfolio()` | Markowitz weights | `np.linalg.inv()` / `pinv()` | Yes |
| `hl_signal/allocation.py::realized_vol()` | Trailing vol | `np.std()` | Yes |
| `src/models/neutralizer.py::Neutralizer.neutralize()` | Ridge residualization | `np.linalg.solve()` | Yes |
| `src/models/lambdarank_train.py::residualize_and_bin_target()` | Per-date OLS for LambdaRank | `np.linalg.lstsq()` | Yes |
| `hl_signal/lgbm_train.py::residualize_target()` | Per-date OLS for HL signal | `np.linalg.lstsq()` | Yes |

And duplicate `lstsq` calls in CV loops of training scripts:
- `scripts/train_lambdarank.py` (2 calls: `residualize_target` + fold loop)
- `scripts/train_lambdarank_beta.py` (2 calls: `residualize_target` + fold loop)

### Danger Zones

- **The S2 model path (`submit_s2_live.py`)** calls `train_lambdarank_fold` → `residualize_and_bin_target` which uses `lstsq`. This runs daily in cron. If starter features contain NaN (copula z-score columns, early dates with short window history), it triggers DLASCL. Fixing `neutralizer.py` alone does NOT protect this path — they are separate call graphs.
- **`np.linalg.lstsq` catches `LinAlgError`** so the script doesn't crash, but it prints the LAPACK warning to stderr anyway and falls back to non-residualized targets on those dates, degrading model quality.
- **The `nan_to_num` pattern must be applied to BOTH X AND y** before the call. Cleaning only the matrix but not the target still leaves `Inf - Inf` in the residual computation.

## Verification
After applying the fix, run the full test suite to confirm no regressions. The fix is functionally transparent — replacing NaN/Inf with 0 does not change the statistical meaning (no signal = 0 weight/residual), and prevents crashes on production data with edge cases.
