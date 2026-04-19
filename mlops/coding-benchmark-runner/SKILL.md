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

Same architecture class (Qwen3.5 35B-A3B MoE), opposite outcomes. You cannot predict which mode is better without benchmarking.

**Procedure:**
1. Set `chat-template-kwargs = {"enable_thinking":false}` in router-preset.ini
2. `systemctl --user restart m5-router.service`
3. Run JSON bench + coding bench
4. Set `chat-template-kwargs = {"enable_thinking":true}` (or remove the line if that's the default)
5. Restart router, run both benches again
6. Compare and record both rows in `merged_bench_results.md` with a `Think` column (yes/no/—)

Record both configurations in the main results table as separate rows (e.g., `qwen36-35b` with Think=no, `qwen36-35b` with Think=yes).

## Pitfalls

1. **Never run without `-u` flag** — Python buffers stdout when redirected; you'll see zero output for the entire run until it finishes. NOTE: even with `-u`, some models (e.g. carnice-35b thinking MoE) produce zero stdout while actively running. Always check the JSON output file's `progress` field to verify the bench is advancing — it's the only reliable progress indicator.
2. **Don't restart runs unless necessary** — each restart costs 30-60 min. The incremental JSON save means you can check `progress` to know where it is. If you must restart, at least the partial results are preserved.
3. **Model swap time** — the router needs to unload the current model and load the new one. Expect 30-90s of silence after starting a new model's run. Don't panic, just wait.
4. **Thinking models (GLM-4, Qwen3.5, Step-3.5-Flash)** — they generate all reasoning tokens before emitting any visible output. A problem can show no progress for 3-5 minutes even though the model is actively generating. Step-3.5-Flash generates ~4400 tokens per solve, taking ~4 min solve + ~4 min refactor = ~8 min per problem (~2 hours total).
5. **Process death diagnosis** — if a bench process dies silently (no crash output, process gone), check: (a) the results JSON for progress, (b) dmesg for OOM kills, (c) test the model manually with curl to see if it's the model or the harness. Common causes: HTTP timeout too short, router 500 error (llama.cpp crash on large prompts), or OOM.
6. **ornsteinV-27b dies at 1/15** — known issue where the process exits silently after scoring p01. Root cause unclear (not OOM, not timeout). May need investigation. Model works fine with manual curl requests.
7. **step35-flash is a thinking model** — outputs to `reasoning_content` not `content`. The harness handles this fallback, but the model is extremely slow (~18 t/s, spills to RAM on Strix Halo). Needs 2+ hours for full run. Use 10800s timeout minimum. Its refactors frequently hit the 8192 token cap, producing truncated syntax errors and tanking refactor_stability to 0.33.
8. **Never unload a model during a running bench** — calling `/models/unload` or `model_manager.py swap` while a bench is running kills the model mid-problem, causing 500 errors for all remaining problems. The old results file will contain garbage partial data. Always wait for the bench to complete first.
9. **Router restart needed for INI changes** — ANY change to `router-preset.ini` (new model, changed params) requires `systemctl --user restart m5-router.service`. The router caches the entire preset at startup. Changing `no-mmap` to `mmap` or `ctx-size` without restart means the old params are still used silently.
10. **Always benchmark thinking models in both modes** — thinking mode effect is model-dependent. qwen36-35b (Qwen3.6 MoE) improved significantly WITHOUT thinking: +0.057 coding, +0.095 JSON, 3x faster. Conversely, holo3-35b (same base arch, Qwen3.5 MoE) degraded severely without thinking: -0.122 coding, -0.333 numerical. Always test `enable_thinking:true` AND `enable_thinking:false` before settling on a config. Toggle via `chat-template-kwargs = {"enable_thinking":true/false}` in router-preset.ini.
10. **model_manager.py swap memory wait** — after unloading a large model (100 GB+), memory takes time to free. The swap command polls /proc/meminfo for up to 60s. Don't use a fixed 2s delay or it will abort on false "not enough memory". Use system MemAvailable (not VRAM/GTT) on Strix Halo — unified memory means the VRAM/GTT split is meaningless.
11. **Router 10s force-kill on large models** — when loading a model after unloading another, the router force-kills the new spawn after 10 seconds if the old instance hasn't fully shut down. For 100GB+ models, cleanup takes minutes. Always unload, wait 15-30s, then load. If you see "force-killing model instance after 10 seconds timeout" in journalctl, this is the cause.
12. **Models >100GB need mmap=true** — on 128GB Strix Halo, models >100GB fail with Vulkan `ErrorOutOfHostMemory` when using `no-mmap = true`. Switch to `mmap = true` and reduce `ctx-size` (e.g., 32768 instead of 131072) to fit. The model loads from disk on-demand instead of preloading all tensors into VRAM.
13. **APU free memory is unreliably reported** — `free -h` and `/proc/meminfo` MemAvailable under-report on Strix Halo APU. Don't rely on them for capacity decisions. If the model fits on paper (~103GB model vs 128GB total), try loading it — the reported 22GB "available" was misleading.

## Active models (uncommented in router-preset.ini)

- qwen35-122b, qwopus35-27b, carnice-27b, ornsteinV-27b, harmonic-27b
- holo3-35b, qwopus-moe-35b, carnice-35b
- nemotron-120b, nemotron-cascade2-30b
- glm47-flash, minimax25, mistral4-small-119b, step35-flash
- gemma4-31b, gemma4-26b-moe

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
| gemma4-26b-moe | Q8_0 | 1.00 | 0.73 | 1.00 | 0.67 | 0.880 | 76 min |
| minimax25 | IQ4_XS | 0.93 | 0.64 | 1.00 | 0.64 | 0.827 | 78 min |
| qwen36-35b | Q8_0 | 1.00 | 0.80 | 1.00 | 0.80 | 0.920 | 3.5 min |
| step35-flash | IQ4_XS | 0.80 | 0.75 | 1.00 | 0.33 | 0.727 | 127 min |
| ornsteinV-27b | Q4_K_M | 0.80* | 0.75* | 1.00* | 1.00* | 0.71* | partial 5/15 |

Notes:
- Thinking models (harmonic, step35, minimax, GLM-4) are slow — 100-250s per solve.
- step35-flash hits 8192 token cap on refactors → truncated syntax errors, worst refactor score.
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
