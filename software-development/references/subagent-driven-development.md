# Subagent-Driven Development — Verification & Fixup

Subagents (via `delegate_task`) produce code asynchronously. The most common failure mode is NOT that they do nothing — it's that they return plausible-looking code with subtle bugs. The parent agent is ultimately responsible for verifying every subagent deliverable.

## 1. Always Verify the Build

A subagent that reports "task completed" may have:
- Written syntactically correct code that doesn't compile (missing includes, wrong types)
- Written code that compiles but fails tests (wrong formulas, sign errors, noise-sensitive tolerances)
- Changed build files (CMakeLists.txt) that need re-cmaking
- Left stale object files that mask build or link errors

**Checklist after every subagent return:**
```
cd <build> && cmake .. 2>&1        # re-configure (subagent may have added source files)
make -j$(nproc) 2>&1 | tail -10    # build, catch compile/link errors
ctest -R <test_pattern> -V          # run relevant tests
```

## 2. The Three Bug Classes in Numerical Code

When a subagent writes templated C++ numerical code, bugs fall into three buckets:

### Class A — Compile-time errors
- Missing includes (e.g. `<cmath>`, `<type_traits>`, `<algorithm>`, `<functional>`)
- Wrong template argument deduction (e.g. passing `int` where `const CEssviSurface&` expected)
- `using namespace` scoping (out-of-function `using` vs in-function `using`)
- Missing `#include` for types used in cpp/h files (depends on transitive includes)

**Fix:** read compile errors, add includes or fix types. Do not assume the subagent set up includes correctly even if the code "looks right."

### Class B — Logical / numerical errors
- Sign errors in deformation/perturbation formulas (`k - R·u` vs `k + R·u`)
- Wrong test expectations (expected value computed using the same wrong formula)
- Oversight of boundary conditions (e.g. clamped values at grid edges causing O(0.01) error)
- Physics violations (mass not conserved due to missing reflecting-boundary terms)

**Fix:** run the test with debug output. Compare intermediate values between C++ and pure-numpy reference. Isolate which element is wrong and trace the formula.

### Class C — Noise-sensitive tolerances
- FD vs AD comparison at boundary-adjacent parameters where FD derivative → 0
- Grid interpolation error at coarse or non-uniform grids
- Boundary clamping truncation at wings

**Fix:** use a synthetic reference floor (`max(ref, 1e-8)`) for rel-err, widen tolerance at edges, document why (e.g. `// boundary clamping in coarse grid`). Do NOT tighten to 1e-9 everywhere — some elements are truly noisier.

## 3. Systematic Fixup Workflow

```
1. Build the subagent's output         →  find compile errors
2. Run the failing test with debug     →  find which assertions fail
3. Read the implementation             →  trace the formula/logic
4. Read the test                       →  check if test expectation is correct
5. Patch implementation OR test        →  fix the bug
6. Build and re-run                    →  verify fix
7. Run full test suite                 →  verify no regression
```

Do NOT patch-and-pray. The subagent can produce multiple correlated bugs (e.g. a sign error in both implementation AND test expectation). Read both files before making any change.

## 4. Common Pitfalls to Check First

When a subagent's C++ code fails, check these before deep-diving:

- **Allman braces + 2-space indent**: subagents often default to K&R braces and 4-space indent. Easy to miss in review because the code looks like valid C++. If the project has formatting rules in CI, this causes a warnings-as-errors failure.
- **Hungarian prefixes**: subagents almost never add `p_`/`l_`/`m_` prefixes. CI may not enforce this if the prefix convention is only in the style guide, not in -Werror. But review should catch it.
- **Missing `const`-correctness**: subagents write non-`const` methods that should be `const`. This compiles but is bad practice.
- **`using namespace std;` in headers**: subagents may add this. Reject it.
- **Exception safety**: subagents may add catch-blocks that swallow errors. The project convention is throw, don't swallow.

## 5. When to Re-Dispatch vs Fix Yourself

**Re-dispatch when:** the subagent got the architecture wrong (wrong class hierarchy, wrong module split, wrong signature). Explaining the fix takes fewer tokens than fixing it, and the subagent can produce a correct first draft.

**Fix yourself when:** the subagent got the architecture right but has small bugs (sign errors, missing includes, wrong tolerances). These are quicker to patch than to re-explain.
