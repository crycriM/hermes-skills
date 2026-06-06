---
name: coding-benchmark-runner
description: Run the 15-problem Python coding & algorithmic soundness benchmark against local models on the llama.cpp router.
tags: [benchmark, coding, local-models, llama-cpp]
---

# Coding Benchmark Runner

Run the 15-problem Python coding & algorithmic soundness benchmark against local models served via the llama.cpp router.

## Location

`~/llm-server/coding_test/` — contains `run_bench.py`, `prompts.jsonl`, `test_cases.py`, `reference_solutions.py`, `test_harness.py`

## Pre-flight

```bash
cd ~/llm-server/coding_test && python3 test_harness.py
```

All 32 assertions must pass before running real benchmarks.

## Known issues & fixes

1. **Python 3.14 multiprocessing**: Python 3.14 defaults to `forkserver` context. The harness uses `mp.set_start_method("fork")` in `main()`, but `test_harness.py` needed the same fix added at module level before importing `run_bench`. If `test_harness.py` fails with `RuntimeError: An attempt has been made to start a new process...`, add `import multiprocessing as mp; mp.set_start_method("fork")` at the top.

2. **Thinking models (GLM-4, etc.)**: Some models return all output in `reasoning_content` with empty `content`. `call_model()` in `run_bench.py` now falls back to `reasoning_content` when `content` is empty. If you see 0/0 scores on a model that clearly produced output, check the API response structure.

3. **Stdout buffering**: Always run with `python3 -u` in background mode, otherwise output is held until process exits and you can't monitor progress.

4. **Progress logging**: `run_bench.py` now prints per-problem progress with timestamps: `[wall: Xs]` for total elapsed, model response time, refactor response time, and per-problem duration. All prints use `flush=True`. If you see no output for minutes, the model is in its thinking phase — normal for GLM-4 etc.

5. **max_tokens**: Bumped to 8192 (was 2048, then 4096). The p14_simple_calculator problem (diff=4) needs ~2600+ tokens. GLM-4 at 14.5 t/s hit the 2048 limit and produced truncated syntax errors. 8192 is safe for all models.

6. **HTTP timeout**: Auto-calculated as `max_tokens * 0.12s/token + 60s margin` (~1043s for 8192 tokens). Previous fixed 600s timeout caused carnice-27b to fail on p06/p07/p08 — dense 27B at 55W generating 6K+ tokens easily exceeds 600s. The 500 Internal Server Error on p14 was likely OOM or llama.cpp bug, not a timeout issue. Do NOT hardcode timeouts.

7. **Incremental results saving**: Results JSON is written after every problem (not just at the end). This prevents total data loss if the process is killed or crashes. The JSON includes a `progress` field like `"8/15"`. If a run is interrupted, partial results are still in the output file.

8. **Token tracking**: Each problem result now includes `solve_time_s`, `refactor_time_s`, `scoring_time_s`, `total_time_s`, `solve_tokens`, `refactor_tokens`. The stdout line also shows total tokens per problem: `[94.4s, 1234 tok]`.

9. **Don't kill running processes unnecessarily**: The harness only writes to JSON at the end of each problem. Killing mid-problem loses that problem's data. Only kill between problems if needed (check the JSON `progress` field first).

## Running a benchmark

```bash
cd ~/llm-server/coding_test && python3 -u run_bench.py \
    --endpoint http://localhost:8080/v1 \
    --model <model-name> \
    --prompts prompts.jsonl \
    --out results_<model>.json
```

- `--skip-refactor` halves runtime (no refactor stability metric)
- Router endpoint: `http://localhost:8080/v1`
- Model name must match the `[section]` name in `~/llm-server/router-preset.ini`

### Grammar-variant coding benchmark (standard vs compact CoT)

To benchmark models with AND without grammar constraints (e.g., compact CoT coding grammar vs free-form), use the combined harness:

```bash
cd ~/llm-server/coding_test && python3 run_coding_grammar_bench.py \
    --endpoint http://localhost:8079 \
    --models qwen36-27b-Q4_0,qwen36-27b-cot \
    [--skip-refactor] \
    --out results_coding_grammar.json
```

This runs 4 combinations (2 models × 2 grammars) sequentially and produces:
- Per-(model, grammar) summary: pass@1, complexity, numerical, refactor, overall_score, avg_tokens, tps
- Delta table: compact vs standard — token delta %, wall delta %, t/s delta %, P@1 delta, score delta

Grammars tested: `standard` (no grammar), `compact` (CoT coding grammar — enforces <think> block + code output).

**Critical endpoint rule:** Always use `http://localhost:8079` (model-manager proxy), NOT `http://localhost:8080` (raw router). The proxy handles model loading; the raw router returns 404 for unloaded models.

**Model loading before the run:**
```bash
# Verify current state
curl -s http://localhost:8079/proxy/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('Loaded:', d.get('loaded',[]))"

# Load models (if not already loaded)
curl -s -X POST http://localhost:8079/api/load -H 'Content-Type: application/json' -d '{"model": "qwen36-27b-Q4_0"}'
curl -s -X POST http://localhost:8079/api/load -H 'Content-Type: application/json' -d '{"model": "qwen36-27b-cot"}'
```

If models share VRAM, load one, unload the other, load second. Monitor with `curl -s http://localhost:8079/proxy/status`.

**Model names:** Must match `[section]` in `router-preset.ini`. The `-cot` variants have CoT template baked into startup args; per-request grammar injection overrides this cleanly for comparison testing. `qwen36-27b-Q4_K_M` is the same GGUF file as `qwen36-27b-cot` — use whichever is uncommented in the preset.

## Model management

`model_manager.py` is now a passive proxy (no `swap` subcommand). Swap models manually via curl:
```bash
# Unload current model
curl -s -X POST http://localhost:8080/models/unload -H 'Content-Type: application/json' -d '{"model":"<current-model>"}'
# Wait for memory to free
sleep 10
# Load new model
curl -s -X POST http://localhost:8080/models/load -H 'Content-Type: application/json' -d '{"model":"<new-model>"}'
```
Do NOT unload a model during a running bench — it kills the model mid-problem and produces garbage results (500 errors for remaining problems).

## Thinking Mode Testing

For models with configurable thinking mode (`enable_thinking` in `chat-template-kwargs` in router-preset.ini), **always benchmark both modes**. The effect is model-dependent and unpredictable:

- **qwen36-35b (MoE 35B/3B):** Thinking OFF is strictly better — +0.057 coding, +0.095 JSON, 3x faster. Thinking tokens introduced noise.
- **holo3-35b (MoE 35B/3B):** Thinking ON is critical — -0.122 coding without it, numerical stability collapsed from 1.00 to 0.67.
- **gemma4-31b (dense 31B):** Thinking ON produced reasoning_content; OFF produced direct content. Impact TBD.

Same architecture class (Qwen3.5 35B-A3B MoE), opposite outcomes. You cannot predict which mode is better without benchmarking.

**Procedure:**
1. Set `chat-template-kwargs = {"enable_thinking":false}` in router-preset.ini (for models using this mechanism)
2. `systemctl --user restart m5-router.service`
3. Run JSON bench + coding bench
4. Set `chat-template-kwargs = {"enable_thinking":true}` (or remove the line if that's the default)
5. Restart router, run both benches again
6. Compare and record both rows in `merged_bench_results.md` with a `Think` column (yes/no/—)

Record both configurations in the main results table as separate rows (e.g., `qwen36-35b` with Think=no, `qwen36-35b` with Think=yes).

### Toggling reasoning mode via `reasoning` key (Gemma, etc.)

Some models (Gemma 4) don't use `chat-template-kwargs` for thinking. Instead, use the `reasoning` key in router-preset.ini:

```ini
# Disable thinking:
reasoning = off

# Enable thinking:
reasoning = auto
```

**Critical: `reasoning = none` is INVALID.** The valid values are `on`, `off`, `auto`. Using `none` is silently ignored and falls back to the parent default.

**Critical: parent router `--reasoning` flag overrides per-model INI.** If `start-native-router.sh` has `--reasoning auto`, per-model `reasoning = off` in the INI is ignored. Fix: remove `--reasoning` from `start-native-router.sh` entirely, then add `reasoning = auto` to every model section in the INI. Only the model being tested gets `reasoning = off`.

**Verification:** After restarting and loading the model, check the child process args:
```bash
# Check loaded model's reasoning flag
curl -s http://localhost:8080/v1/models | python3 -c "
import sys,json
d=json.load(sys.stdin)
for m in d.get('data',[]):
    if m['id']=='MODEL_NAME':
        args=m.get('status',{}).get('args',[])
        if '--reasoning' in args:
            idx=args.index('--reasoning')
            print(f'reasoning={args[idx+1]}')
"
# Or quick test:
curl -s http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"MODEL","messages":[{"role":"user","content":"2+2?"}],"max_tokens":50}' | \
  python3 -c "import sys,json; m=json.load(sys.stdin)['choices'][0]['message']; print('thinking:', bool(m.get('reasoning_content','')))"
```

## Post-benchmark variant pruning

After benchmarking multiple GGUF variants of the same model family (e.g., Qwen 3.6 27B Q4_0 vs Q4_K_M), compare results and prune the router preset to retain only the best performing variant.

### Comparison metrics
Prioritize these metrics in order:
1. `pass@1` (correctness, weight 0.45 in benchmark)
2. `overall_score` (weighted sum of all metrics)
3. `t/s` (tokens per second, runtime efficiency)
4. `avg_tokens` (token usage per problem, lower is better for speed/cost)

### Pruning steps
1. Open `~/llm-server/router-preset.ini`
2. Identify all `[section]` entries for the model family (e.g., `qwen36-27b-Q4_0`, `qwen36-27b-Q4_K_M`, `qwen36-27b-cot`)
3. Comment out or delete sections for underperforming variants (retain only the best)
4. Save the INI file
5. Restart the router service to apply changes:
   ```bash
   systemctl --user restart m5-router.service
   ```
6. Verify the proxy (port 8079) reflects updates:
   ```bash
   curl -s http://localhost:8079/proxy/status | python3 -c "import sys,json; d=json.load(sys.stdin); print('Models configured:', len(d.get('models',[]))); [print(f'  {m[\"name\"]} (loaded: {m[\"loaded\"]})') for m in d.get('models',[]) if '<model-family>' in m['name'].lower()]"
   ```

### Example: Qwen 3.6 27B pruning
Benchmark results:
- `qwen36-27b-Q4_0`: P@1=85.7%, Score=0.85, 12 t/s, 634 tok/problem
- `qwen36-27b-Q4_K_M`: P@1=85.7%, Score=0.82, 9 t/s, 1215 tok/problem

Pruning action: Retain `qwen36-27b-Q4_0`, remove all other 27B variants from the preset.

### Notes
- The router caches `router-preset.ini` at startup; restart is mandatory for changes to take effect.
- Re-run benchmarks if adding new variants of the same model family later.

## Cross-Model Benchmark Comparison

Use this workflow when comparing benchmark results from **different model families** (e.g., Qwen 3.6 27B vs Qwopus35 27B) to select the best model for a specific use case, not just variants of the same family.

### When to use
- Comparing 2+ models from different architectures/families (not just quant variants of the same base model)
- Selecting a primary model for a recurring task (e.g., coding pipeline, research agent)
- Evaluating tradeoffs between accuracy, speed, token efficiency, and stability

### Parse heterogeneous benchmark JSON structures
Different benchmark scripts produce different JSON schemas. Common patterns:
1. **Grammar bench (Qwen 3.6 27B Q4_0 style)**: Nested summary under `summary.<model_grammar_label>` with keys `pass_at_1`, `overall_score`, `avg_tokens`, `avg_tps`
2. **Flat bench (Qwopus 35 27B style)**: Flat `summary` object with `pass_at_1`, `overall_score`; token/speed data must be calculated from `problems` array:
   ```python
   import json
   with open('results_qwopus35_27b.json') as f:
       data = json.load(f)
   problems = data["problems"]
   total_tokens = sum(p.get("solve_tokens", 0) for p in problems)
   total_time = sum(p.get("solve_time_s", 0) for p in problems)
   avg_tokens = total_tokens / len(problems)
   avg_tps = total_tokens / total_time if total_time > 0 else 0
   ```

### Metrics priority (cross-model)
Same as variant pruning, but add refactor_stability earlier for pipeline use cases:
1. `pass@1` (correctness, weight 0.45)
2. `refactor_stability` (iterative coding stability, critical for feature pipelines)
3. `overall_score` (weighted sum of all metrics)
4. `t/s` (tokens per second, runtime efficiency)
5. `avg_tokens` (token usage per problem, lower is better for speed/cost)

### Conclusion framework
Draw conclusions based on use case:
- **Recurring pipeline task (e.g., feature implementation)**: Prioritize refactor_stability > t/s > avg_tokens > pass@1. Verbose models with high token usage are penalized.
- **One-off hard problem**: Prioritize peak pass@1 > overall_score. Speed/token usage less critical.
- **Research/reasoning task**: Check if CoT variant exists, prioritize traceable reasoning over raw coding metrics.

### Example: Qwen 3.6 27B Q4_0 vs Qwopus35 27B
| Metric | Qwen 3.6 27B Q4_0 | Qwopus35 27B (best) |
|--------|-------------------|--------------------|
| Pass@1 | 85.71% | 93.33% |
| Overall Score | 0.8524 | 0.8700 |
| Avg Tokens/Problem | 634.1 | 2043.5 |
| Avg t/s | 12.1 | 11.6 |
| Refactor Stability | 83.3% | 71.4% |

Conclusion: Qwen is better for recurring coding pipelines (faster, more token-efficient, more refactor-stable). Qwopus is better for one-off hard problems with higher peak accuracy.

## Pitfalls

1. **Never run without `-u` flag** — Python buffers stdout when redirected; you'll see zero output for the entire run until it finishes. NOTE: even with `-u`, some models (e.g. carnice-35b thinking MoE) produce zero stdout while actively running. Always check the JSON output file's `progress` field to verify the bench is advancing — it's the only reliable progress indicator.
2. **Don't restart runs unless necessary** — each restart costs 30-60 min. The incremental JSON save means you can check `progress` to know where it is. If you must restart, at least the partial results are preserved.
3. **Model swap time** — the router needs to unload the current model and load the new one. Expect 30-90s of silence after starting a new model's run. Don't panic, just wait.
4. **Thinking models (GLM-4, Qwen3.5, Step-3.5-Flash)** — they generate all reasoning tokens before emitting any visible output. A problem can show no progress for 3-5 minutes even though the model is actively generating. Step-3.5-Flash generates ~4400 tokens per solve, taking ~4 min solve + ~4 min refactor = ~8 min per problem (~2 hours total).
5. **Process death diagnosis** — if a bench process dies silently (no crash output, process gone), check: (a) the results JSON for progress, (b) dmesg for OOM kills, (c) test the model manually with curl to see if it's the model or the harness. Common causes: HTTP timeout too short, router 500 error (llama.cpp crash on large prompts), or OOM.
6. **ornsteinV-27b dies at 1/15** — known issue where the process exits silently after scoring p01. Root cause unclear (not OOM, not timeout). May need investigation. Model works fine with manual curl requests.
7. **step35-flash / step37 (Step 3.x Flash models)** — these are thinking models by nature; they output to `reasoning_content` not `content`, even when `chat-template-kwargs = {"enable_thinking":false}` is set in the router preset. The `enable_thinking` flag is silently ignored by some templates — the model continues producing thinking tokens and leaving `content` empty. The harness fallback (`content or reasoning_content`) handles this. step35-flash is extremely slow (~18 t/s, spills to RAM on Strix Halo). Needs 2+ hours for full run. Use 10800s timeout minimum. Its refactors frequently hit the 8192 token cap, producing truncated syntax errors and tanking refactor_stability to 0.33. step37 at IQ4_XS (~95GB, mmap) is also slow but thinking bleed-through can be fixed via chat template override - see step37-thinking-suppression skill. After the fix, pass@1 jumps from 60% to 87% with zero syntax errors.
8. **Never unload a model during a running bench** — calling `/models/unload` or `model_manager.py swap` while a bench is running kills the model mid-problem, causing 500 errors for all remaining problems. The old results file will contain garbage partial data. Always wait for the bench to complete first.
9. **Router restart needed for INI changes** — ANY change to `router-preset.ini` (new model, changed params) requires `systemctl --user restart m5-router.service`. The router caches the entire preset at startup. Changing `no-mmap` to `mmap` or `ctx-size` without restart means the old params are still used silently.
10. **Always benchmark thinking models in both modes** — thinking mode effect is model-dependent. qwen36-35b (Qwen3.6 MoE) improved significantly WITHOUT thinking: +0.057 coding, +0.095 JSON, 3x faster. Conversely, holo3-35b (same base arch, Qwen3.5 MoE) degraded severely without thinking: -0.122 coding, -0.333 numerical. Always test `enable_thinking:true` AND `enable_thinking:false` before settling on a config. Toggle via `chat-template-kwargs = {"enable_thinking":true/false}` in router-preset.ini.
10. **model_manager.py swap memory wait** — after unloading a large model (100 GB+), memory takes time to free. The swap command polls /proc/meminfo for up to 60s. Don't use a fixed 2s delay or it will abort on false "not enough memory". Use system MemAvailable (not VRAM/GTT) on Strix Halo — unified memory means the VRAM/GTT split is meaningless.

11. **Sandbox `__build_class__` and `__name__` errors** — models' generated code may reference `__build_class__` (metaclasses) or `__name__` (module-level checks), which aren't in the default exec namespace. This causes `NameError: __build_class__ not found` or `NameError: name '__name__' is not defined` and 0/3 correctness.
   - Fix for `__build_class__`: add `"__build_class__"` to the `safe_builtins` dict
   - Fix for `__name__`: initialize the `ns` dict with `"__name__": "__main__"` and `"__doc__": None` (NOT in `safe_builtins`). The exec namespace needs these defined before running user code.
   - Apply to both `run_bench.py` and `run_coding_grammar_bench.py`.
11. **Batch script model swap timing** — when running multiple models sequentially in a batch script, the router needs adequate time between unload and load. With only 10s sleep, models fail to load (503 Service Unavailable on all subsequent requests). Use 15s post-unload + 20s post-load + readiness verification loop (ping `/v1/models` up to 10 times with 5s intervals). Without this, the entire bench run produces 0.0 scores on every problem.
11. **Router 10s force-kill on large models** — when loading a model after unloading another, the router force-kills the new spawn after 10 seconds if the old instance hasn't fully shut down. For 100GB+ models, cleanup takes minutes. Always unload, wait 15-30s, then load. If you see "force-killing model instance after 10 seconds timeout" in journalctl, this is the cause.
12. **Models >100GB need mmap=true** — on 128GB Strix Halo, models >100GB fail with Vulkan `ErrorOutOfHostMemory` when using `no-mmap = true`. Switch to `mmap = true` and reduce `ctx-size` (e.g., 32768 instead of 131072) to fit. The model loads from disk on-demand instead of preloading all tensors into VRAM.
13. **APU free memory is unreliably reported** — `free -h` and `/proc/meminfo` MemAvailable under-report on Strix Halo APU. Don't rely on them for capacity decisions. If the model fits on paper (~103GB model vs 128GB total), try loading it — the reported 22GB "available" was misleading.

## Reference material

- `references/step37-bench-results.md` — step37 (Step-3.7-Flash IQ4_XS) partial results and observations about thinking-mode bleed-through.

## Active models (uncommented in router-preset.ini)

- qwen35-9b, qwen36-27b (MTP), qwen36-35b (MTP)
- qwen35-122b, qwopus35-27b, carnice-27b, ornsteinV-27b, harmonic-27b
- holo3-35b, qwopus-moe-35b, carnice-35b
- nemotron-120b, nemotron-cascade2-30b
- glm47-flash, minimax25, mistral4-small-119b, step35-flash
- gemma4-31b, gemma4-26b-moe
- step37 (Step-3.7-Flash IQ4_XS)

New models must be added to `router-preset.ini` AND the router service restarted (`systemctl --user restart m5-router.service`). Just adding to INI is not enough — the router returns 404 on `/models/load` for unknown models.

## Results (55W TDP, with refactor, 15-problem bench)

| Model | Quant | pass@1 | complexity | numerical | refactor | overall | Time |
|---|---|---|---|---|---|---|---|
| nemotron-120b | Q4_K_M | 1.00 | 0.80 | 1.00 | 0.87 | 0.933 | 18 min |
| holo3-35b | Q8_0 | 1.00 | 0.73 | 1.00 | 0.87 | 0.920 | 5 min |
| holo3-35b (no-think) | Q8_0 | 0.87 | 0.85 | 0.67 | 0.69 | 0.798 | 1.8 min |
| cascade2-30b | Q4_K_M | 0.93 | 0.79 | 1.00 | 0.86 | 0.899 | 10 min |
| qwopus-moe-35b | Q4_K_M | 0.87 | 0.85 | 1.00 | 0.85 | 0.878 | 6 min |
| qwopus-moe-35b | Q8_0 | 0.93 | 0.64 | 1.00 | 0.86 | 0.870 | 8 min |
| qwopus35-27b | Q4_K_M | 0.93 | 0.79 | 1.00 | 0.71 | 0.870 | — |
| mistral4-119b | Q4_K_M | 0.80 | 0.83 | 1.00 | 0.67 | 0.810 | 4 min |
| qwen35-122b | Q4_K_M | 0.87 | 0.69 | 1.00 | 0.85 | 0.848 | — |
| harmonic-27b | Q4_K_M | 0.87 | 0.77 | 1.00 | 0.69 | 0.832 | 67 min |
| carnice-35b | Q8_0 | 0.93 | 0.79 | 1.00 | 0.86 | 0.899 | 14 min |
| mistral4-small-119b | Q4_K_M | 0.80 | 0.83 | 1.00 | 0.67 | 0.810 | 4 min |
| glm47-flash | Q8_K_XL | 0.80 | 0.58 | 1.00 | 0.83 | 0.793 | — |
| carnice-27b | Q4_K_M | 0.67 | 0.80 | 1.00 | 0.80 | 0.770 | — |
| gemma4-31b | Q4_K_M | 1.00 | 0.67 | 1.00 | 0.73 | 0.880 | 70 min |
| gemma4-31b (no-think) | Q4_K_M | 1.00 | 0.67 | 1.00 | 0.80 | 0.893 | — |
| gemma4-26b-moe | Q8_0 | 1.00 | 0.73 | 1.00 | 0.67 | 0.880 | 76 min |
| minimax25 | IQ4_XS | 0.93 | 0.64 | 1.00 | 0.64 | 0.827 | 78 min |
| qwen36-35b | Q8_0 | 1.00 | 0.80 | 1.00 | 0.80 | 0.920 | 3.5 min |
| qwen36-27b | Q4_K_M (MTP) | 0.93 | 0.86 | 1.00 | 0.79 | **0.899** | 7 min |
| step35-flash | IQ4_XS | 0.80 | 0.75 | 1.00 | 0.33 | 0.727 | 127 min |
| step37 (thinking corrupt) | IQ4_XS | 0.60 | 0.78 | 0.67 | 0.56 | 0.637 | 155 min |
| step37 (template fix) | IQ4_XS | 0.87 | 0.69 | 1.00 | 0.39 | 0.755 | 60 min |
| ornsteinV-27b | Q4_K_M | 0.80* | 0.75* | 1.00* | 1.00* | 0.71* | partial 5/15 |

Notes:
- Thinking models (harmonic, step35, step37, minimax, GLM-4) are slow — 100-250s per solve.
- step35-flash and step37 hit 8192 token cap on refactors => truncated syntax errors, worst refactor scores. step37 with default template produced Unicode artifacts (U+2014 em-dash, curly quotes) due to thinking bleed-through. **Template fix resolved this**: after chat template override, pass@1 went from 60% to 87%, numerical from 67% to 100%, zero syntax errors. See step37-thinking-suppression skill.
- step37's JSON bench is perfect (1.0) despite thinking issues — structured output unaffected.
- Q8_0 qwopus-moe gained pass@1 but lost complexity vs Q4_K_M — net zero.
- holo3-35b best price/performance: perfect pass@1 in 5 minutes at Q8_0.
- carnice-35b rerun (model config changed): pass@1 jumped 0.73→0.93, overall 0.826→0.899. Still hits 8192 tok cap on p14 refactor.
- mistral4-small-119b rerun at Q4_K_M: pass@1 dropped 0.93→0.80, complexity improved 0.79→0.83. Overall 0.856→0.810.

Quantization fairness note: holo3-35b (Q8_0, 34.4 GB) vs qwopus-moe-35b (Q4_K_M, 19.7 GB) is not a fair comparison. Re-bench qwopus-moe at Q8_0 for apples-to-apples.

## Timing expectations

At 55W TDP, expect 5-60 min per model with refactor enabled. Small models (glm47-flash 9B) are ~14.5 t/s; large MoE models are slower. Thinking models (step35-flash, minimax25) can take 2+ hours. Fastest: holo3-35b at ~5 min.

## Metrics

- **pass_at_1**: correctness on small + edge cases (weight 0.45)
- **complexity_match_rate**: empirical O() matches expected via log-log curve fitting (weight 0.20)
- **numerical_stability**: catastrophic cancellation, overflow detection (weight 0.15)
- **refactor_stability**: both original and refactored versions pass (weight 0.20)
- **overall_score**: weighted sum

GO thresholds: pass_at_1 >= 0.80, complexity >= 0.70, numerical >= 0.67, refactor >= 0.70, overall >= 0.75

## Batch run strategy

Run models sequentially (router can only serve one at a time). Use background mode with `notify_on_complete`. Script to run all:

```bash
for model in glm47-flash qwopus35-27b carnice-27b ...; do
    python3 -u run_bench.py --endpoint http://localhost:8080/v1 \
        --model $model --out results_${model}.json
done
```

**CRITICAL — Cross-benchmark parallelism corrupts results.** Do NOT run JSON bench, coding bench, and research bench in parallel against the same router — the model can only serve one request stream at a time. Concurrent API calls cause contention, request queuing, timeout cascades, and noisy scores. Run them strictly sequentially in this order: JSON first (fastest, ~5-20 min), then coding (~5-120 min), then research (~5-60 min, depends on model). If launched in parallel by mistake, kill all processes first, clean up partial results (`rm results_*.json bench_*.log`), verify the model is idle (`curl -s http://localhost:8080/v1/models | grep loaded`), then restart serially. This is the only reliable pattern for clean per-benchmark results.
