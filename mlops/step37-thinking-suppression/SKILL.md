---
name: step37-thinking-suppression
description: "Suppress Step 3.7 Flash forced thinking mode by overriding the chat template. Tokens are special, not suppressible via logit_bias."
version: 1.1.0
author: Hermes Agent
settings:
  template_path: ~/llm-server/step37-no-think.jinja
  preset_section: step37
  think_token: 128798
  close_think_token: 128799
---

# Step 3.7 Flash — Thinking Suppression

## Problem

Step 3.7 Flash (DeepSeek v3 architecture) always outputs chain-of-thought in `reasoning_content` and leaves `content` empty. Its chat template unconditionally prepends `<think>\n` to every assistant response, even with `chat-template-kwargs = {"enable_thinking":false}`.

This breaks code generation benchmarks because code gets lost in `reasoning_content` instead of appearing in `content`.

## Key Findings

| Approach | Result |
|---|---|
| `enable_thinking:false` (chat-template-kwargs) | ❌ Template ignores this flag |
| `logit_bias: {128798: -100}` (suppress `<think>`) | ❌ Special token (type 3), not a sampling choice |
| `logit_bias: {128799: +100}` (force `</think>`) | ❌ Breaks sampler — outputs "128" repeatedly |
| `reasoning_budget: 0` | ❌ Ignored |
| `--reasoning off` | ❌ Not in this llama.cpp build |
| **Override chat template** | ✅ Works |

## Solution: Chat Template Override

### 1. Template file

Located at `~/llm-server/step37-no-think.jinja` — copy of the original GGUF template with `<think>\n` removed from the generation prompt. To regenerate from a new GGUF:

```bash
# Extract original template
gguf-dump /path/to/step37.gguf --json | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(d['metadata']['tokenizer.chat_template']['value'])
" > original-template.jinja

# Edit: find the block at the end that says:
#   {%- if add_generation_prompt %}
#       {{- '<|im_start|>assistant\n<think>\n' }}
#   {%- endif %}
# Remove the `<think>\n` so it becomes:
#   {%- if add_generation_prompt %}
#       {{- '<|im_start|>assistant\n' }}
#   {%- endif %}
```

### 2. Router preset

Already applied in `router-preset.ini` section `[step37]`:

```ini
jinja = true
chat-template-file = /home/cricri/llm-server/step37-no-think.jinja
```

### 3. Reload

```bash
curl -s -X POST http://localhost:8080/models/unload -H 'Content-Type: application/json' -d '{"model":"step37"}'
sleep 2
curl -s -X POST http://localhost:8080/models/load -H 'Content-Type: application/json' -d '{"model":"step37"}'
# Wait for status="loaded"
```

## Post-fix artifact

The model may still emit `</think>` mid-response (its internal architecture switches between think/not-think states). Clean with:

```python
import re
clean = re.sub(r'\s*</think>\s*', '\n', content).strip()
```

This does NOT affect code extraction (markdown fences still work).

## ⚠️ Critical Trade-off: Research Benchmark Regression

The template fix **improves coding but destroys research ability**. Step 3.7 Flash's research agent performance depends on its thinking capability.

| Benchmark | With thinking (original) | **No-think template** | Δ |
|---|---|---|---|
| **Coding pass@1** | 60% | **86.7%** | **+27pp** |
| **Coding overall** | 0.637 | **0.755** | **+0.118** |
| **Research composite** | **1.035** 🏆 | **0.160** | **-0.875** |
| Research coverage | 1.76 | 0.0 | -1.76 |
| Research specificity | 4/5 | 1/5 | -3pp |
| Research impl. depth | 5/5 | 1/5 | -4pp |
| Research time | 2022s (34 min) | 353s (6 min) | 5.7x faster but useless |

**Root cause:** Without the `<think>` trigger, the model skips the synthesis phase entirely — it jumps to tool calls before processing findings, producing shallow or empty deliverables.

**Recommendation:** Run step37 with the **default template** (thinking ON) for research tasks. Use the **no-think template** only for coding/structured-output tasks where thinking artifacts corrupt extraction. You cannot run both simultaneously — the model needs a reload to switch templates.

## Per-Task Template Strategy

To get the best of both worlds, maintain TWO step37 entries in the preset:

```ini
# Router preset: run whichever you need
[step37]             # Default thinking template — for research
load-on-startup = 0
model = /mnt/data2/models/step-3.7-flash/Step-3.7-Flash-UD-IQ4_XS-00001-of-00003.gguf
# ... other params ...
# No chat-template-file line → uses GGUF native template (thinking ON)

[step37-nothink]     # Overridden template — for coding
load-on-startup = 0
model = /mnt/data2/models/step-3.7-flash/Step-3.7-Flash-UD-IQ4_XS-00001-of-00003.gguf
# ... other params ...
chat-template-file = /home/cricri/llm-server/step37-no-think.jinja
```

Then load whichever variant you need:
```bash
curl -X POST http://localhost:8080/models/load -H 'Content-Type: application/json' -d '{"model":"step37"}'       # thinking ON
curl -X POST http://localhost:8080/models/load -H 'Content-Type: application/json' -d '{"model":"step37-nothink"}'  # thinking OFF
```

## Benchmark Impact

| Metric | Before (corrupt) | After (template fix) | Δ |
|---|---|---|---|
| pass@1 | 60% (9/15) | **86.7%** (13/15) | **+27pp** |
| complexity | 78% | 69% | -9pp |
| numerical | 67% | **100%** | **+33pp** |
| refactor | 56% | 39% | -17pp |
| **overall** | **0.637** | **0.755** | **+0.118** |

Syntax errors eliminated. Remaining failures are logic issues (p08 merge_k, p14 calculator), not parsing artifacts.

## Refresh After Reboot

1. Verify router + model_manager are up
2. Wait for auto-load to finish (qwen36-35b, qwen35-9b, qwen36-27b)
3. Unload auto-loaded models: `POST /models/unload` for each
4. Load step37: `POST /models/load {"model":"step37"}`
5. Wait for status "loaded" (~85s)

## Related Skills & References

- `router-preset-model-tuning` → `references/thinking-suppression-techniques.md` — detailed token type analysis and logit bias mechanics
- `coding-benchmark-runner` → `references/step37-bench-results.md` — full before/after benchmark tables