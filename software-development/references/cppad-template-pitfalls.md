# CppAD Template Pitfalls

CppAD automatic differentiation with `CppAD::AD<double>` introduces subtle breakage
in templated C++ code that works perfectly for `double`. These are the traps hit in
the volsurface/skewbik codebase.

## 1. `operator==` on AD types returns `AD<bool>`, not `bool`

**Wrong:**
```cpp
template <class T>
void solve(const std::vector<T>& p_vDiag) {
  if (p_vDiag[0] == T(0))           // BUG when T = CppAD::AD<double>
    throw std::runtime_error("...");
}
```

`CppAD::AD<double>::operator==` returns `CppAD::AD<bool>`, which enters the
AD tape as a conditional branch. Even when the condition is never true (pivot
always > 0), the tape records the comparison expression, polluting every
derivative through the kernel. The result is a Jacobian that disagrees with
finite differences by 1-90% relative.

**Fix — overloaded extractor:**
```cpp
inline double extractDouble(double p_fX) { return p_fX; }
inline double extractDouble(const CppAD::AD<double>& p_oX) { return CppAD::Value(p_oX); }

template <class T>
void solve(const std::vector<T>& p_vDiag) {
  if (std::fabs(extractDouble(p_vDiag[0])) < 1e-15)
    throw std::runtime_error("...");   // pure scalar — not taped
}
```

## 2. Same issue with all relational operators

Every relational operator (`==`, `!=`, `<`, `>`, `<=`, `>=`) on `AD<double>`
returns `AD<bool>`. All corrupt the tape when used in `if(...)`. Extract the
underlying double first.

**Includes comparisons against literals:**
```cpp
if (p_vDiag[i] < 1e-12)   // Also returns AD<bool>
```

## 3. CppAD Jacobian via Reverse — full Jacobian vs projected gradient

**Goal:** Compute J[r][c] = d(c_r) / d(s_c) (N_prices x N_params).

**Wrong — Reverse with all-ones seed gives projected gradient:**
```cpp
std::vector<double> seed(N_prices, 1.0);
auto grad = fun.Reverse(1, seed);    // d(sum_r c_r)/d(s), NOT per-price
```

**Correct — one Reverse per output channel:**
```cpp
for (int r = 0; r < N_prices; ++r) {
  std::vector<double> seed(N_prices + N_obj, 0.0);
  seed[r] = 1.0;
  auto dPrice_dS = fun.Reverse(1, seed);
  for (int c = 0; c < N_params; ++c)
    Jac[r * N_params + c] = dPrice_dS[c];
}
```

## 4. Boundary conditions in Omega (DLV diffusion)

When building the Omega second-difference operator for DLV diffusion on
a strike grid with a reflecting boundary at K=0:

- **i=1** (first interior point): set `omegaMinus[1] = 0` — no backward
  diffusion, mass cannot go to negative strikes
- **i=N-2** (last interior point): set `omegaPlus[N-2] = 0` — no forward
  diffusion beyond the last strike

## 5. `CppAD::Value()` on independent variables — assertion failure

**Problem:** Calling `CppAD::Value(x)` on an AD variable that was declared
via `CppAD::Independent(...)` triggers a hard assertion.

**Fix — `if constexpr` guard for AD types:**
```cpp
template <class T>
void solveThomas(const std::vector<T>& p_vDiag, ...) {
  if constexpr (!std::is_same_v<T, CppAD::AD<double>>) {
    double l_fDiag = extractDouble(p_vDiag[0]);
    if (std::fabs(l_fDiag) < 1e-15)
      throw std::runtime_error("zero pivot");
  }
}
```

## 6. Jacobian vs FD comparison — noise guard and tolerance

**Problem:** Near boundary-adjacent parameters, FD can be near machine
epsilon while CppAD gives the exact small-but-nonzero value.

**Fix — synthetic reference floor:**
```cpp
double l_fRefSafe = std::max(std::fabs(l_fCppAD), std::fabs(l_fFD), 1e-8);
double l_fRelErr = l_fAbsErr / l_fRefSafe;
```

**Practical tolerance:** Use `<= 0.01` (1%) per-element; boundary-adjacent
FD underflow is the limiting factor, not tape accuracy.

## 7. Logistic shrinkage blending for wing priors

```cpp
double scaled = kappa * (x - x_mid);
if (scaled > 20.0) return 1.0;
if (scaled < -20.0) return 0.0;
return 1.0 / (1.0 + exp(-scaled));
```

**Common mistake:** mixing `|x|` with a half-width offset instead of
a simple `kappa * (x - x_mid)` which handles sign at the caller.

## 8. AD tape must mirror double-path control flow exactly — including post-call overwrites

**Example — SANOS DLV density decode with fixed mass source at K=0:**
The `double`-path does `q = decodeDlvStep(...)` then `q[0] = 1.0` (boundary).
If the AD tape skips the overwrite, the objective is wrong by 1e8 and the
gradient direction is garbage. Every post-call side effect in the reference
path must appear identically inside the tape.

## 9. Large σ²Δt causes DLV mass/mean loss — Thomas solve near-singular

**Problem:** When `σ²Δt > ~10`, `Q^{-1} = I + Ω·Σ²·Δt` becomes near-singular
(off-diagonals dominate), and Thomas solve loses mass conservation.

**Mitigation:**
1. **Shrink σ** at near-boundary strikes (`K_MIN_SIGMA` floor of ~0.05).
2. **Use small Δt** (0.01 instead of 0.10) in mass/mean property tests.
3. **Test pattern:** seed `q_prev` at ATM node, not 0-strike, for
   mass/mean verification. Test 0-strike source with small sigma only.

## 10. AD tape debugging: standalone comparison with FD

**Problem:** AD tape produces wrong result but builds and runs silently.
The tape can be off by 1e8 with zero gradients.

**Correct approach:** Write a standalone program that computes both the
AD and FD (reference) paths at the same input and compares elementwise:

```cpp
auto pricesRef = computePricesRef(sigma);
// ... call AD tape at same sigma ...
for (size_t i = 0; i < N; ++i)
  fprintf(stderr, "  [%zu] Ref=%.10e AD=%.10e diff=%.2e\n",
          i, pricesRef[i], pricesAD[i],
          std::fabs(pricesRef[i] - pricesAD[i]));
```

Work backward from price differences through the chain:
q → q_prev → sigma → anchor matrix — the first divergence pinpoints
the bug (typically a missing side-effect overwrite in the tape).

## 11. When replacing FD gradients with AD tape in a calibrator

**What the AD tape replaces:** sigma=exp(s), q=decodeDlvStep, q[0]=1
overwrite, c=A·q, all objective terms (smoothabs+softplus+shrinkage),
and the gradient via Reverse(1,{1.0}).

**What to remove from caller:** FD gradient loop, manual shrinkage
gradient, any pre-computed prices/obj the AD tape now handles, any
static helpers that become unused (`-Werror` catches these).

**Critical verification sequence:**
1. Run existing tests as baseline
2. Build standalone comparison (§10) at one parameter vector
3. Verify obj and grad match to 1e-6 rel err
4. Switch calibrator to AD path
5. Verify test suite passes

Without step 2-3, you cannot distinguish tape bugs from legitimate
convergence differences.
