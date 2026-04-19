---
name: json-toolcall-benchmark
description: Maintain, debug, and extend the agentic tool-call JSON benchmark in ~/llm-server/json_test/. Tests models' ability to produce valid structured tool calls across 20 cases.
---

# JSON Tool-Call Benchmark

Location: `~/llm-server/json_test/`

## Key Files
- `prompts.jsonl` — 20 test cases (P01-P20), difficulty 1-4, 11 categories
- `run_bench.py` — scoring harness (extract_json, score_case, call_model, aggregate)
- `test_harness.py` — self-test for scoring logic (no network needed)
- `results_*.json` — per-model results

## Running
```bash
python run_bench.py --endpoint http://localhost:8080/v1 --model <name> --out results_<name>.json
python test_harness.py  # verify scoring logic after any edit
```

## Thinking Model Support

Thinking models (Qwen3, GLM-4, qwopus35-27b2, etc.) output to `reasoning_content` with empty `content`. The `call_model()` function in `run_bench.py` MUST fall back:

```python
content = msg.get("content", "") or msg.get("reasoning_content", "")
```

Without this, the bench hangs silently — the model generates thinking tokens, returns empty `content`, and the scorer never gets a response. No error, no output file, just a stuck process. This was added Apr 2026 after qwopus35-27b2 hung for 6+ minutes with zero output.

The coding bench and research bench already handle this; the JSON bench was the last one fixed.

## Architecture: How Scoring Works

`score_case()` evaluates 7 independent booleans per case:
- **parsed** — JSON extracted and tool/arguments structure found (or recovered)
- **tool_correct** — tool name matches expected_tool
- **required_ok** — all expected_required keys present in args
- **types_ok** — arg types match expected_types (flat + nested + strict)
- **values_ok** — exact values, substrings, array checks, enum checks
- **no_forbidden** — no forbidden_keys present in args
- **format_ok** — no markdown fences or prose wrappers (independent of parsing)

## Key Design Decisions

### Normalization (_normalize_tool_obj)
Accepts multiple key conventions and normalizes to `{"tool":..., "arguments":...}`:
- `"name"` → `"tool"`
- `"function"` → `"tool"`
- `"args"` → `"arguments"`
- `"parameters"` → `"arguments"`
- `{"tool_call": {"name":..., "arguments/args":...}}` → flattened
- `{"tool_calls": [{"name":..., ...}]}` → take first

### score_case Recovery Patterns
When the standard envelope is not found, score_case tries in order:
1. `"arguments"` / `"args"` / `"parameters"` as args key → parsed=True
2. `{"expected_tool_name": {args}}` — tool name is the dict key → parsed=True, tool_correct=True
3. `_extract_args_from_malformed()` heuristic — single nested dict, flat dict fallback
4. Bare-args fallback: strip all known envelope keys, treat remainder as args → parsed=True, tool_correct likely False

### Partial-Credit Scoring (partial_score field)
Each CaseResult has a `partial_score` (float 0-1) computed as a weighted continuous score:
- 0.30 * tool_correct — right tool name selected
- 0.20 * required_ok — all required args present
- 0.30 * values_ok — expected values match
- 0.10 * types_ok — arg types match
- 0.10 * no_forbidden — no forbidden keys present

The scorer continues evaluating all axes even when the envelope is non-standard.
Only returns early for: (1) JSON parse failure entirely, (2) truly unrecoverable structure.
This ensures metrics discriminate independently rather than collapsing into one binary.

The `aggregate()` function reports `partial_score_mean` and `partial_score_std` globally
and per-category (`per_category.*.partial_mean`). Use these for t-tests instead of
binary binomial tests — continuous data has dramatically better statistical power.

The live display shows `partial=X.XX` alongside the PTRYVFM flags for each case.

### Malformed Recovery (_extract_args_from_malformed)
Heuristic recovery from non-standard structures:
- `{"tool_name": {args}}` — key matches expected tool
- Single nested dict value → treat as args
- Flat dict with no envelope → treat as args (strip known envelope keys)

## Benchmark Design Anti-Pattern (Lesson Learned)

**Never gate all metrics behind a single parse check with early returns.** If you do:
- Every metric becomes perfectly correlated with the parse gate
- You measure one thing (did they use the exact key names?) across 7 labels
- The benchmark cannot discriminate between "wrong tool but correct types" and "right tool but wrong types"

**Fix:** Score partial matches. Return early only when there's truly nothing to evaluate (complete parse failure). Let each metric fail independently.

## Prompt Contract
All 20 prompts now include the `{"tool": "<name>", "arguments": {...}}` contract.
If adding new cases, include this in the system prompt or models will use free-form keys.

## Thinking Mode Impact

Thinking mode can HURT some models on the JSON bench:
- **qwen36-35b**: 0.905 → 1.000 when thinking DISABLED (+0.095). Thinking tokens introduced parse failures (P06, P09 had empty output).
- **holo3-35b**: 0.932 → 0.933 — essentially no change, but P15 (deeply nested) failed without thinking.

Always benchmark both `enable_thinking:true` and `enable_thinking:false` for thinking-capable models.

## Statistical Power (Critical Limitation)

With n=20 binary pass/fail outcomes, the benchmark CANNOT statistically distinguish models.

**Actual results (13 models run):**
- Best parse rate: 50% (10/20), 95% CI [0.299, 0.701] — that's +/-20pp
- No pairwise comparison between any two models reached significance (all p > 0.45)
- The #1 and #13 ranked models are statistically indistinguishable

**Minimum n per model to detect gaps (80% power, α=0.05, binary outcomes):**
- 5pp gap: ~1565 cases
- 10pp gap: ~388 cases
- 15pp gap: ~170 cases
- 20pp gap: ~93 cases
- 30pp gap: ~39 cases

**How to improve significance (three levers, by impact):**
1. Parser normalization + recovery (DONE) — accepts name/args/function/parameters aliases and {tool_name:{args}} pattern. Spreads scores by testing intelligence not format compliance.
2. Partial-credit scoring (DONE) — continuous 0-1 per case via partial_score field. Use partial_score_mean for t-tests.
3. Scale n to 100-200 via template permutation (permute paths, numbers, tool names). ~5s/case locally, 150 cases = 12 min/model.

**Bottom line:** At n=20 with continuous partial-credit scores, you can detect ~15pp gaps. With binary scores, you need ~170 cases for the same gap. Always prefer continuous scoring.

## Thinking Mode Testing

See coding-benchmark-runner skill for the full procedure. Key finding: thinking mode affects JSON scores too — qwen36-35b went from 0.905 (thinking) to 1.000 (no-thinking). Always test both modes for thinking-capable models.

## Extending
Add cases by appending to `prompts.jsonl`. Available check types:
- `expected_tool`, `expected_required`, `expected_types`, `expected_values`, `forbidden_keys`
- `nested_checks` — dotted-path type checks
- `array_item_checks` — min length, required fields per item
- `enum_checks` — enforce enum membership
- `string_contains` — substring assertions
- `strict_types` — reject stringified numbers/booleans
- `format_checks.no_markdown_fence` / `no_prose`
- `assistant_prior` + `tool_result` + `followup` — multiturn/recovery

After adding cases, run `test_harness.py` to verify.

## Running All Models (run_all_benches.py)

The `run_all_benches.py` script benchmarks all models sequentially via the router.
Update the MODELS list from `~/llm-server/router-preset.ini` sections whenever models change.

```bash
# Update model list from INI:
grep -E '^\[' ~/llm-server/router-preset.ini | tr -d '[]'

# Run (models load on demand via router at :8080):
python3 -u run_all_benches.py

# Clear old results before re-run:
rm -f results_*.json bench_summary.json
```

Each model takes ~5-20 min (loads on demand, thinking models slower).
Total: 12 models × 20 prompts ≈ 2-3 hours.

## Validation: Parser Fix Impact

After implementing normalization + partial-credit scoring, re-running models showed dramatic improvement:
- glm47-flash: 0.50 → 1.00 overall (was 10/20 parse, now 20/20)
- carnice-27b: 0.40 → 0.95
- harmonic-27b: (new model) 0.95

This confirmed the hypothesis: models were semantically correct but using non-standard key names. The parser was the bottleneck, not model intelligence.
