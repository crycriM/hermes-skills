# Reasoning Budget Sampler Internals (llama.cpp build 8920)

Source: `common/reasoning-budget.cpp`, `common/reasoning-budget.h`, `common/sampling.cpp`

## State Machine

```
IDLE → COUNTING → (remaining ≤ 0) → FORCING → DONE
                                   → WAITING_UTF8 → FORCING → DONE
         ↑                                                    │
         └──────────── re-arm on new <think_> tag ─────────────┘
```

- **IDLE**: Passthrough, watching for `start_tokens` sequence (e.g. `<think_>`)
- **COUNTING**: Decrementing `remaining` per generated token, watching for `end_tokens` (e.g. `</think_>`)
- **WAITING_UTF8**: Budget exhausted mid-UTF8, waiting for completion
- **FORCING**: Sets all logits to `-inf` except forced token (the budget message + `</think_>` sequence)
- **DONE**: Passthrough forever, BUT re-arms if a new `start_tokens` sequence appears

## Per-slot, not per-model

Each slot in llama-server gets its own sampler chain including its own `rbudget` instance. Initialized in `common_sampling_init()` when `reasoning_budget_start` and `reasoning_budget_end` are non-empty. The sampler is cloned per-slot.

## Prefill token processing (THE BUG)

The sampler processes ALL prefill tokens during `init_sampler()`:
```cpp
for (const auto & token : prefill_tokens) {
    llama_sampler_accept(rbudget, token);
}
```

This means:
- If the prompt contains a previous `<think_>...</think_>` from conversation history, the sampler transitions IDLE→COUNTING→DONE during prefill
- The template's trailing `<think_>` tag (from `enable_thinking:true`) triggers a re-arm with FRESH budget
- Each historical `<think_>...</think_>` pair is handled correctly (COUNTING→DONE→re-arm)
- **BUT:** If any historical thinking block is truncated (unclosed `</think_>`, from a previous budget-forced response), the sampler enters COUNTING and does NOT find a matching `</think_>`. It stays in COUNTING, consuming the budget on historical tokens. With `reasoning-budget = 1024`, this exhausts the budget before generation starts.

**Symptom:** `reasoning-budget: activated` followed immediately by `budget exhausted, forcing end sequence` at the same timestamp during `init_sampler`. The model never generates thinking tokens — the forced `</think_>` is emitted before generation begins.

**Fix (applied 2026-05-04):** Disable `reasoning-budget` in `router-preset.ini` entirely. Let model_manager enforce limits via `max_tokens` (total output cap, not affected by prefill) + `logit_bias` (soft nudge toward `</think_>`). This sidesteps the prefill consumption bug.

## Generation token processing

```cpp
if (gsmpl->rbudget && is_generated) {
    llama_sampler_accept(gsmpl->rbudget, token);
}
```

Only generated tokens (not prefill) trigger accept during the main loop. The `is_generated` flag ensures prefill-only processing happened in `init_sampler`.

## Log messages (NO slot ID)

All reasoning-budget log messages come from `reasoning-budget.cpp` and do NOT include slot IDs:
- `"reasoning-budget: activated, budget=%d tokens"` — transition to COUNTING
- `"reasoning-budget: deactivated (natural end)"` — end_tokens matched
- `"reasoning-budget: budget exhausted, forcing end sequence"` — remaining hit 0
- `"reasoning-budget: forced sequence complete, done"` — forced tokens all emitted
- `"reasoning-budget: re-activated on new start tag, budget=%d tokens"` — re-arm in DONE state

**Cross-referencing technique:** The `init_sampler: id N | task T` log happens at the same timestamp as the corresponding `reasoning-budget: activated` for that slot. Use this to attribute budget events to specific slots.

## Logit bias interaction (model_manager)

The model_manager's logit bias is a separate mechanism that biases the `</think_>` token's logit value BEFORE the request reaches llama-server. This is a "soft nudge" — it increases the probability of closing the thinking block before the hard budget forces it.

**Current behavior (2026-05-04):** When `max_tokens == 0` (caller didn't set it), the proxy enforces `max_tokens = max_reasoning_tokens + 512` AND applies full bias strength. The +512 headroom ensures room for text output after the thinking block closes. The bias also handles `logit_bias` in both list and dict format, converting list to dict internally for correct merging.

## Timing math

For qwen36-35b on Vulkan (gfx1151):
- Thinking token speed: ~22 t/s (inside `<think_>`)
- Text token speed: ~38 t/s (after `</think_>`)
- max_reasoning_tokens = 1024 → 1024/22 = **~46 seconds** of thinking
- Total max_tokens = 1536 → worst case ~60 seconds total (1024 thinking + 512 text)
- Previous budget of 4096 caused 186s thinking episodes that looked like infinite loops
