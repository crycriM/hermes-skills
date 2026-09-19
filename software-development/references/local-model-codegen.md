# Generating Code via Local LLM Models

## When to Use

When you need to delegate code generation to a local model (via llama.cpp or similar) instead of using `delegate_task`. This is useful when:
- The model has specific domain knowledge (quant finance, signal processing)
- You want to preserve parent context for orchestration
- The task is a single file or function, not multi-step

## Key Patterns

### 1. Payload Delivery

**DON'T** inline JSON in shell arguments — special characters, newlines, and quotes will break:

```bash
# BROKEN — shell will eat the prompt
curl -X POST ... -d '{"messages": [{"content": "long python code with """ and \n"}]}'
```

**DO** write the JSON payload to a temp file:

```python
import json
with open("/tmp/payload.json", "w") as f:
    json.dump(payload, f)
terminal(f"curl -s --max-time 300 -X POST {API_URL} -H 'Content-Type: application/json' -d @/tmp/payload.json", timeout=310)
```

The proxy may have a lower timeout (e.g. 120s on port 8079). Hit the llama-server directly on its port for long generations:

```python
# Proxy (lower timeout)
API = "http://localhost:8079/v1/chat/completions"

# Direct (model-specific port, higher timeout)
API = "http://localhost:50439/v1/chat/completions"  # qwen36-27b
```

### 2. System Prompt

Be explicit about output format. Local models are more literal than cloud APIs:

```
"Only output raw Python code. No markdown fences. No explanations."
```

Still, models often output markdown fences anyway. Always strip them:

```python
if "```python" in code:
    code = code.split("```python")[1].split("```")[0].strip()
elif "```" in code:
    code = code.split("```")[1].split("```")[0].strip()
```

### 3. Model Hallucination Handling (most important)

Local models often hallucinate imports and module structures. Common patterns found in practice:

| Hallucination | Reality |
|---|---|
| `from signal_bridge.utils.constants import ...` | These constants are defined in the file itself |
| `import pandas as pd` | Not installed / not needed |
| `from typing import Dict, Callable, Any` | Use bare dict/callable (Python 3.9+) |
| `pyvinecopulib.BicopControls, FamilySet` | API is `FitControlsBicop`, `BicopFamily`, uses `.select()` method |
| `signal_fn(bar, train_slice: slice, prices: Dict[str, np.ndarray])` | `train_slice` is `dict`, `prices` is `Dict[str, float]` (mark prices!) |
| Completely different signal architecture (MACD-based, different combining logic) | Must restore original from git + surgically add only the new function |

**Fix strategy:** Always do syntax check → import check → quick smoke test. Fix hallucinations in order:
1. Wrong imports → patch
2. Wrong function signatures → patch (type hints don't affect runtime, but non-existent modules crash)
3. Wrong architecture → restore original from git, add only the new function

### 4. O(n²) Optimization Patches

Local models frequently generate naive loop-based implementations that work on small data but timeout on real data:

```python
# Generated (O(n²)):
for i in range(WARMUP, n_bars):          # 8784 iterations
    features = extract_regime_features(ohlcv[:i+1])  # O(n) each = O(n²)

# Fixed (O(n)):
features = extract_regime_features(ohlcv)  # One vectorized pass
for i in range(WARMUP, n_bars):
    vol_ratio = features[i, 3]             # Classification only
```

Check for this pattern on any function that loops over `range(WARMUP, n)` and calls a sub-function that also loops.

### 5. API Mismatch Detection

Test the generated code with SYNTHETIC data before running the real backtest:

```python
# Synthetic data test
np.random.seed(42)
closes = 100 + np.cumsum(np.random.randn(n) * 0.02)
synth = np.column_stack([np.arange(n), closes*0.99, closes*1.01, closes*0.99, closes, np.ones(n)*1000])
result = my_function(synth)
assert result.shape == expected_shape, f"Got {result.shape} expected {expected_shape}"
```

If the synthetic test passes, try a quick backtest with `--days 7` to verify full pipeline integration before the expensive 30d run.

### 6. Temperature Setting

For code generation, use `temperature: 0.3` — low enough to be deterministic, high enough to have some creativity. For reasoning/analysis tasks (like the lookahead audit), `temperature: 0.0` for maximum determinism.

## Example Workflow

```
1. Write prompt with full file context, exact function signatures, constraints
2. Write to /tmp/payload.json
3. curl with --max-time 300 to model's direct port
4. Extract response, strip markdown fences
5. Syntax check (ast.parse)
6. Import test
7. Fix hallucinations (imports first, then signatures, then architecture)
8. Synthetic data smoke test
9. Quick backtest (--days 7)
10. Full backtest (--days 30)
```