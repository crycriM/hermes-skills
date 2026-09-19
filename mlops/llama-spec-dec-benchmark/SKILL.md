---
name: llama-spec-dec-benchmark
description: Run speculative decoding benchmarks with llama.cpp llama-server, comparing with/without thinking mode. For AMDVLK Vulkan GPU inference.
---

# Llama.cpp Speculative Decoding Benchmark

## Prereq
- Distrobox with AMDVLK (`RADV_PERFTILE=1` env var) or AMDVLK installed on host
- llama-server compiled from target commit
- Two free ports (baseline + spec dec server)
- Model in Q4_K_M or similar quantization

## Pattern: Two-server A/B benchmark

### Server 1 — Baseline (no spec dec)
```bash
llama-server \
  -m "$MODEL" \
  -c 8192 \
  -tb 4096 \
  --port 8085 \
  -t 12 \
  --log-disable \
  --batch-size 512 \
  --ctx-size 8192
```

### Server 2 — With speculative decoding (start with n=3, NOT n=24)
```bash
llama-server \
  -m "$MODEL" \
  -c 8192 \
  -tb 4096 \
  --port 8084 \
  -t 12 \
  --log-disable \
  --batch-size 512 \
  --ctx-size 8192 \
  --spec-type ngram-mod \
  --spec-ngram-size-n 3 \
  --draft-max 48 \
  --draft-min 12
```

### Warmup both servers (same prompt, ignore timing)
```bash
curl -s --max-time 30 -X POST http://localhost:$PORT/v1/completions \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Explain quantum entanglement","max_tokens":10,"temperature":0.8,"seed":42}'
```

### Benchmark JSON helpers
```bash
cat > /tmp/bench_plain.json << 'EOF'
{"prompt":"What is the capital of France?","max_tokens":200,"temperature":0.8,"seed":42,"stop":["</s>","<|end|>"]}
EOF

cat > /tmp/bench_think_plain.json << 'EOF'
{"prompt":"<|channel|>think\nExplain quantum entanglement in simple terms<|end|>","max_tokens":200,"temperature":0.8,"seed":42,"stop":["</s>","<|end|>"]}
EOF
```

### Run benchmarks
```bash
# No thinking
curl -s --max-time 120 -X POST http://localhost:8084/v1/completions -H 'Content-Type: application/json' -d @/tmp/bench_plain.json
curl -s --max-time 120 -X POST http://localhost:8085/v1/completions -H 'Content-Type: application/json' -d @/tmp/bench_plain.json

# With thinking
curl -s --max-time 120 -X POST http://localhost:8084/v1/completions -H 'Content-Type: application/json' -d @/tmp/bench_think_plain.json
curl -s --max-time 120 -X POST http://localhost:8085/v1/completions -H 'Content-Type: application/json' -d @/tmp/bench_think_plain.json
```

### Parse results
```python
import json, sys
d = json.load(sys.stdin)
u = d['usage']; t = d['timings']
print(f"Prompt: {u['prompt_tokens']} tok | {t['prompt_ms']:.0f}ms ({t['prompt_per_second']:.1f} tok/s)")
print(f"Decode: {u['completion_tokens']} tok | {t['predicted_ms']:.0f}ms ({t['predicted_per_second']:.1f} tok/s)")
```

## Critical: Wait for model load completion before benchmarking

When using llama.cpp's `/v1/models/load` endpoint (router mode), the load request returns immediately but the model takes time to actually load into memory. **Never use a fixed sleep** — large models (27B+) can take 30-90 seconds to load.

**Correct pattern: Poll `/v1/models` until model status is "loaded"**

```bash
# Trigger load
curl -s http://localhost:8080/v1/models/load \
  -H "Content-Type: application/json" \
  -d "{\"id\": \"qwen36-27b-V\"}" > /dev/null

# Poll until status is "loaded" (up to 2 minutes)
for i in {1..120}; do
  status=$(curl -s http://localhost:8080/v1/models 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print([m['status']['value'] for m in d['data'] if m['id']=='qwen36-27b-V'][0] if any(m['id']=='qwen36-27b-V' for m in d['data']))" 2>/dev/null || echo "error")
  
  if [[ "$status" == "loaded" ]]; then
    echo "Model loaded!"
    break
  fi
  
  if [[ $i -eq 120 ]]; then
    echo "ERROR: Model failed to load"
    exit 1
  fi
  sleep 1
done

# NOW make completion requests
curl -s -X POST http://localhost:8080/v1/chat/completions ...
```

**Pitfall:** Using `sleep 3` or any fixed timeout after load request. Large models will still be loading when first completion request arrives, resulting in `"model is not loaded"` errors. Always poll status endpoint.

**Status values returned by `/v1/models`:**
- `unloaded` — model defined in preset, not yet loaded
- `loading` — model is loading into memory
- `loaded` — model ready for inference

## Critical: Check if spec dec actually fires

**Correct timing stat fields:** `draft_n` and `draft_n_accepted` (NOT `draft_ngram`).

```python
import json, sys
d = json.load(sys.stdin)
u = d['usage']; t = d['timings']
print(f"Prompt: {u['prompt_tokens']} tok | {t['prompt_per_second']:.1f} tok/s")
print(f"Decode: {u['completion_tokens']} tok | {t['predicted_per_second']:.1f} tok/s")
print(f"Drafts: {t.get('draft_n',0)} | Accepted: {t.get('draft_n_accepted',0)} | Rejected: {t.get('draft_n',0)-t.get('draft_n_accepted',0)}")
```

**IMPORTANT: Use wall-clock time for comparison, NOT `predicted_per_second`.**
The API's `predicted_per_second` often shows LOWER values with spec dec enabled even when wall time improves. This is because `predicted_ms` counts all draft-verification work. Always compute wall tok/s = `completion_tokens / predicted_ms * 1000`.

**If `#gen drafts = 0`** — spec dec is NOT working. On Qwen3.6-27B this typically means `--spec-ngram-size-n` is too large. Try n=3 (not the default n=12).

**If drafts fire but `predicted_per_second` looks worse** — compute wall-clock speedup properly. 100% acceptance rate can still show lower `predicted_per_second` while being slower in actual wall time.

**Draft count varies wildly by model and n value:**
| Model | n | Drafts/run | Acceptance | Wall speedup |
|-------|---|-----------|-----------|-------------|
| Qwen3.6-27B Q4_K_M | 3 | 35-66 | 100% | **-11%** (slower!) |
| Qwen3.6-27B Q4_K_M | 24 | 8 | 100% | 0% |
| Gemma4-31B Q4_K_M | 3 | 280 | ~1.4% | negative |

**CRITICAL FINDING (2025-04-25):** On AMDVLK Vulkan + Qwen3.6-27B Q4_K_M, ngram-mod speculative decoding is 11-15% SLOWER than plain generation across all n values tested (n=3, n=8, n=16, n=24). The draft verification overhead on AMDVLK exceeds any benefit. Plain generation at ~12 tok/s is faster than any spec dec configuration. This held across: chat-template prompts, plain completion prompts, 2-run averages, and 6-run alternating benchmarks.

**Why it fails on AMDVLK:** The AMDVLK Vulkan path has different memory access patterns than CUDA. Draft token verification requires KV-cache lookups which appear to be more expensive per lookup on AMDVLK. The n-gram cache builds successfully (100% acceptance on Qwen) but wall-clock time still degrades.

## Thinking mode
For models that support `<|channel|>think\n...\n<|end|>` instruction format:
- Prepend `<|channel|>think\n` to the prompt
- Use `stop=["</s>","<|end|>"]` to truncate after think block

## Verified

- Gemma4-31B Q4_K_M: n=3 produces 280 drafts but ~98% rejection → slower overall
- Qwen3.6-27B Q4_K_M: n=3 produces 66 drafts at 100% acceptance → +8% wall-clock speedup
- n=24 (default-ish) on Qwen3.6-27B: only 8 drafts, zero speedup
- Decode throughput: ~12 tok/s plain on AMDVLK (RDNA3 7900 XTX)
- `predicted_per_second` in API is unreliable — always use wall-clock timing
