# Thinking Suppression Techniques

For models that unconditionally produce reasoning tokens before output (DeepSeek architecture, Step 3.7 Flash, etc.).

## Token ID Discovery

Find the `<think>` and `</think>` token IDs for any loaded model via the router tokenize endpoint:

```bash
# Start token
curl -s http://localhost:8080/tokenize \
  -H "Content-Type: application/json" \
  -d '{"content":"<think>","model":"MODEL_NAME"}' | python3 -m json.tool
# → {"tokens": [128798]}

# End token
curl -s http://localhost:8080/tokenize \
  -H "Content-Type: application/json" \
  -d '{"content":"</think>","model":"MODEL_NAME"}' | python3 -m json.tool
# → {"tokens": [128799]}
```

Detokenize to confirm:
```bash
curl -s http://localhost:8080/detokenize \
  -H "Content-Type: application/json" \
  -d '{"tokens": [128798]}'
# → {"content":"<think>"}
```

### Known token IDs across architectures

| Model family | `<think>` token | `</think>` token | Token type | Notes |
|---|---|---|---|---|
| Step 3.7 Flash (DeepSeek v3 arch) | 128798 | 128799 | **Special (type 3)** | Logit_bias on these corrupts sampling |
| DeepSeek R1 / R1-distill | varies | varies | Usually special | Check via /tokenize |
| Qwen3.5 / QwQ | varies | varies | Regular + special mix | Check via /tokenize |

### Token type matters for logit bias effectiveness

The GGUF tokenizer assigns a **type** to each token: 1 = normal, 3 = special (control). Special tokens (`type=3`) differ from regular tokens in how the sampler handles them:

- **Normal tokens (type 1)**: Respond to `logit_bias` normally. A positive bias makes them more likely; negative bias less likely. The model_manager's reasoning budget system works for these.
- **Special tokens (type 3)**: Used for architectural switches (thinking mode on/off, role boundaries). Do NOT respond to `logit_bias` in the normal way. Applying bias on them can **corrupt** the sampler — observed behavior: the output becomes repeated token ID numbers (e.g. "128128128128..." instead of text).

Check token types in GGUF metadata:
```bash
gguf-dump /path/to/model.gguf --json | python3 -c "
import sys, json
d = json.load(sys.stdin)
# token_type output is a list parallel to tokens
# type 3 = special, type 1 = normal
print('Token 128798 type:', d['metadata'].get('tokenizer.ggml.token_type', {}).get('value', [])[128798])
print('Token 128799 type:', d['metadata'].get('tokenizer.ggml.token_type', {}).get('value', [])[128799])
"
```

### Architecture-specific notes

**Step 3.7 Flash (DeepSeek v3 BPE tokenizer, `pre=deepseek-v3`):**
- `<think>` = 128798, `</think>` = 128799 — both type 3 (special)
- Tokens are **single special tokens**, not multi-token sequences
- The chat template unconditionally prepends `<think>\n` to every assistant response
- `enable_thinking:false` in `chat-template-kwargs` is silently ignored — the template has no `{% if enable_thinking %}` conditional
- `logit_bias` on either token does NOT suppress thinking
- Bias on `</think>` (128799) causes the sampler to produce "128128128..." tokens (observed empirically with logit_bias: {128799: 100})
- Model_manager's `max_reasoning_tokens` + logit_bias pipeline is ineffective for this model
- **model-manager search gap:** `model_manager.py` searches for `</think_>` (with trailing underscore) and `</thinking>` but NOT `</think>`. Step 3.7 Flash uses the plain `</think>` (128799). If you add a model-manager config entry for step37, the thinking close token will NOT be found, and no bias will be applied. To fix: add `</think>` to the search list in both `preload_thinking_tokens()` and `_handle_completion()` in `model_manager.py`.
- **Only effective fix**: chat template override (see section below)

**Qwen3.5/Qwen3.6 architecture:**
- Thinking tokens may be multi-token sequences (e.g. `</think>` splits into `</` + `think` + `>`)
- The model_manager searches for `</think_>` (last token = `_>` or `>`) to find the most specific token for bias
- These DO respond to logit_bias — positive bias on the close token fragment effectively closes thinking early
- The native `reasoning_budget` API parameter also works
- Model_manager's dual mechanism (native budget + logit_bias) is the recommended approach

**Nemotron 3 (NVIDIA, LatentMoE):**
- Uses `</think_>` and `...tags...`
- Token IDs are architecture-specific (non-contiguous)
- Chat template supports `enable_thinking` and `grace_period` kwargs
- The model_manager's `</think_>` search pattern targets this family
- Logit bias + reasoning_budget both effective

## Chat Template Analysis

The root cause is in the model's baked-in Jinja chat template. Extract it:

```bash
gguf-dump /path/to/model.gguf --json | python3 -c "
import sys, json
d = json.load(sys.stdin)
ct = d['metadata'].get('tokenizer.chat_template', {})
print(ct.get('value', 'NOT FOUND'))
"
```

### What to look for

The generation prompt section at the **end of the template**:

```
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
{%- endif %}
```

If there's an unconditional `<think>\n` after the assistant role tag, thinking is forced on every response. A typical offender:

```
{{- '<|im_start|>assistant\n<think>\n' }}
```

### Fix: Create a modified template

1. Copy the full template text
2. Locate the `{% if add_generation_prompt %}` block at the end
3. Remove `<think>\n` so it becomes just `{{- '<|im_start|>assistant\n' }}`
4. Save as e.g. `~/llm-server/modelname-no-think.jinja`
5. Add `chat-template-file` to the router preset and restart

The template MUST remain valid Jinja2 — check syntax:
```bash
python3 -c "
from jinja2 import Environment
env = Environment()
with open('/home/cricri/llm-server/modelname-no-think.jinja') as f:
    env.parse(f.read())
print('Template syntax: VALID')
"
```

## Model Manager Config

The model_manager proxy (port 8079) can inject logit_bias on `</think>` to close thinking early. Configure in `~/llm-server/model-manager-config.yaml`:

```yaml
models:
  model_name:
    max_reasoning_tokens: 128      # Hard cap — if max_tokens > this, bias kicks in
    logit_bias_strength: 15.0      # 5-8 gentle, 10-12 balanced, 13+ strong, 15+ near-complete
    target_thinking_tokens: 50     # Token count to target closing around
```

Parameter guidelines:
- `logit_bias_strength: 5-8` — gentle nudge, model still has room to think
- `logit_bias_strength: 10-12` — balanced, closes thinking before budget exhaustion
- `logit_bias_strength: 13+` — strong suppression, thinking block closes quickly
- `logit_bias_strength: 15+` — near-complete suppression of extended reasoning
- `target_thinking_tokens: 50` — forces thinking to close very early (~2 seconds)
- Lower `target_thinking_tokens` = tighter per-step reasoning

No restart needed — model_manager reloads config on each request.

## Logit Bias Mechanics

Important distinction between the two thinking token types:

**`<think>` (start token):**
- A special "architectural" token, not a regular sampled token
- Sets the model's internal state to "thinking mode"
- `logit_bias` with ANY value (including -100) on this token has ZERO effect
- Not a sampling choice — the model transitions to thinking state internally

**`</think>` (end token):**
- A regular special token that the model CAN choose to generate
- Positive `logit_bias` encourages the model to close thinking earlier
- The model_manager injects this automatically for configured models
- Works through the standard sampling mechanism

## Per-Request API Parameters

The OpenAI-compatible API accepts these parameters to control thinking per-request:

```json
{
  "model": "model_name",
  "messages": [...],
  "reasoning_budget": 0,
  "max_tokens": 1024,
  "logit_bias": {128799: 15.0}
}
```

- `reasoning_budget`: Native llama.cpp support — signals to close thinking at ~N tokens
- `logit_bias` with `</think>` token ID: Positive bias closes thinking earlier
- Setting `reasoning_budget: 0` does NOT disable thinking on all models — some ignore it

## Verification

Test that thinking is suppressed:

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MODEL_NAME",
    "messages": [{"role":"user","content":"Say exactly: DONE"}],
    "max_tokens": 100,
    "temperature": 0.01
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
msg = data['choices'][0]['message']
rc = msg.get('reasoning_content', '') or ''
c = msg.get('content', '') or ''
print(f'reasoning_content: {repr(rc[:100])}')
print(f'content: {repr(c[:100])}')
print(f'Thinking suppressed: {len(rc) < 50}')
"
```

After thinking suppression, `reasoning_content` should be empty or very short, and `content` should contain the direct response.
