---
name: router-benchmark-runner
description: Run agentic tool-call benchmarks across all models on the m5-router sequentially. Handles model swap warmup, output buffering, and missing model files.
version: 1.0
---

# Router Benchmark Runner

Run agentic tool-call benchmarks across all models on the m5-router sequentially.

## Prerequisites

- Benchmark script: `~/llm-server/json_test/run_bench.py`
- Prompts: `~/llm-server/json_test/prompts.jsonl`
- Router running: `systemctl --user status m5-router.service`
- Python `requests` lib on host

## Key Pitfalls

### 1. Model warmup required
llama-server router (`--models-max 1`) must swap models between runs. The swap takes 10-60s+ depending on model size. Sending a bench request immediately returns 500. **Must send warmup requests with retry loop** until model responds 200.

```python
def wait_for_model(model_id, timeout=600):
    while time.time() - t0 < timeout:
        r = requests.post(f"{ENDPOINT}/chat/completions",
            json={"model": model_id, "messages": [{"role":"user","content":"hi"}], "max_tokens":3},
            timeout=60)
        if r.status_code == 200:
            return True
        time.sleep(5)
```

### 2. Output buffering kills visibility
`subprocess.run(capture_output=True)` buffers all output until the child exits. **Cannot see progress**. Must redirect to a log file:
```bash
stdbuf -oL python3 -u run_all_benches.py >> bench_run.log 2>&1
```
Monitor with `tail bench_run.log`.

### 3. Check model files exist before running
Models get moved/deleted. Verify paths from router-preset.ini:
```python
import configparser, os
cp = configparser.ConfigParser()
cp.read('router-preset.ini')
for sec in cp.sections():
    model = cp.get(sec, 'model', fallback='')
    if model and not os.path.exists(model):
        print(f'MISSING [{sec}]: {model}')
```

### 4. Skip completed models
Result files (`results_{model_id}.json`) with `overall_score > 0` and `n == 20` can be skipped on rerun.

## Workflow

1. Restart router cleanly: `systemctl --user restart m5-router.service`
2. Clear stale results if needed: `rm results_*.json`
3. Run: `python3 -u run_all_benches.py >> bench_run.log 2>&1` (background)
4. Monitor: `tail bench_run.log` or check result json files
5. Final ranking in `bench_summary.json`

### 5. Model output formats vary
Different models wrap tool calls differently. The parser's `_normalize_tool_obj` must handle:
- `{"tool": "name", "arguments": {...}}` (standard)
- `{"name": "name", "arguments": {...}}` (alias)
- `{"tool_call": {"name": "name", "arguments": {...}}}` (Carnice, some Qwen fine-tunes)
- XML `<tool_call/>` blocks (Qwen3.5 with jinja template when tools passed via API)

If a model scores unexpectedly low, check its raw output first — it may be valid JSON with a different wrapper key.

### 6. Qwen3.5 models need custom jinja template
All Qwen3.5-based models (qwopus, carnice, holo3, ornstein, REAP) need `jinja = true` and `chat-template-file = /home/cricri/llm-server/qwen35-chat-template.jinja` in router-preset.ini. Without it, thinking mode and tool calling break (21 upstream fixes in that template).

## Quick score check

```bash
python3 -c "
import json, glob
for f in sorted(glob.glob('results_*.json')):
    d = json.load(open(f))
    m = f.replace('results_','').replace('.json','')
    s = d['summary']
    print(f'{m:30s} score={s[\"overall_score\"]:.4f}  parse={s[\"parse_rate\"]:.2f}  tool={s[\"tool_selection_rate\"]:.2f}  val={s[\"value_match_rate\"]:.2f}')
"
```

## Generating final summary

```python
import json, glob, os
results = {}
for f in sorted(glob.glob("results_*.json")):
    d = json.load(open(f))
    m = os.path.basename(f).replace("results_","").replace(".json","")
    results[m] = d["summary"]
ranked = sorted(results.items(), key=lambda x: x[1]["overall_score"], reverse=True)
summary = {
    "benchmark": "json_tool_calling_v1", "date": "YYYY-MM-DD", "n_prompts": 20,
    "ranking": [{"rank": i+1, "model": m, **s} for i, (m, s) in enumerate(ranked)],
}
json.dump(summary, open("bench_summary.json","w"), indent=2)
```
