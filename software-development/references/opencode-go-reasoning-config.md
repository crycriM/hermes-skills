# OpenCode Go / Moonshot Reasoning Config Quirk

## Problem
Moonshot API (via OpenCode Go) rejects requests that contain **both** `thinking` and `reasoning_effort` in the same request object.

**Error:** `HTTP 400: cannot specify both 'thinking' and 'reasoning_effort'`

## Affected Models on OpenCode Go
- `moonshotai/kimi-k2.5`, `moonshotai/kimi-k2.6` (Kimi K2 series)
- `deepseek/deepseek-v4-pro` (DeepSeek V4 series)

These models go through `OpenCodeGoProfile.build_api_kwargs_extras()` in
`plugins/model-providers/opencode-zen/__init__.py`.

## Root Cause
The old code set `extra_body = {"thinking": {"type": "enabled"}}` AND
`top_level = {"reasoning_effort": "high"}` simultaneously. Moonshot's wire
shape only accepts one or the other.

## Fix
For Kimi K2 and DeepSeek models on OpenCode Go, use **only** top-level
`reasoning_effort`. Set `extra_body = {}`.

```python
# In __init__.py, _is_kimi_k2_model() / _is_deepseek_thinking_model() branches:
extra_body = {}  # NOT {"thinking": {"type": "enabled"}}
top_level = {"reasoning_effort": normalize_effort(effort)}
```

## Verification
Run: `pytest tests/plugins/model_providers/test_opencode_go_profile.py -v --tb=short`
Expected: all 21 opencode-go tests pass.
