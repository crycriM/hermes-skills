# Model Switch base_url Persistence Fix

## Bug: Local model selection wipes base_url from config

### Reproduction
1. Have a local model server configured (e.g., lmstudio on 127.0.0.1:1234, llama.cpp on :8080)
2. Run `hermes model` or use TUI `/model` command
3. Select a local model provider (lmstudio, ollama, etc.)
4. Observe: base_url is deleted from config.yaml, no URL prompt appears

### Root Cause Analysis

**Trace through the code:**

1. **CLI picker** (`cli.py` line 7350 `_open_model_picker`): shows provider list → model list → calls `switch_model` with `explicit_provider=provider_data.get("slug")`

2. **`switch_model`** (`model_switch.py` line 615): 
   - Receives `explicit_provider` (e.g., "lmstudio")
   - PATH A (line 678): explicit provider → resolves via `resolve_provider_full` → calls `resolve_runtime_provider(requested=target_provider, ...)`
   - The runtime resolution may return empty `base_url` for local providers not in the current runtime config
   - Lines 862-896: credential resolution block — no fallback when `base_url` stays empty

3. **`_persist_model_switch`** (`tui_gateway/server.py` line 1088):
   ```python
   if result.base_url:
       model_cfg["base_url"] = result.base_url
   else:
       model_cfg.pop("base_url", None)  # ← DELETES existing base_url
   ```

4. **Result**: when local model is selected, base_url becomes empty string → gets popped from config → error

### Related Code

**The problematic block in model_switch.py (lines 862-896):**
```python
if provider_changed or explicit_provider:
    try:
        runtime = resolve_runtime_provider(
            requested=target_provider,
            target_model=new_model,
        )
        api_key = runtime.get("api_key", "")
        base_url = runtime.get("base_url", "")   # may be empty for local
        api_mode = runtime.get("api_mode", "")
    except Exception as e:
        return ModelSwitchResult(success=False, ...)  # early return
else:
    try:
        runtime = resolve_runtime_provider(
            requested=current_provider,
            target_model=new_model,
        )
        api_key = runtime.get("api_key", "")
        base_url = runtime.get("base_url", "")
        api_mode = runtime.get("api_mode", "")
    except Exception:
        pass  # base_url stays "" — never restored
```

**The persistence trigger (server.py lines 1097-1103):**
```python
model_cfg["default"] = result.new_model
model_cfg["provider"] = result.target_provider
if result.base_url:
    model_cfg["base_url"] = result.base_url
else:
    model_cfg.pop("base_url", None)  # deletes if empty
save_config(cfg)
```

### Fix Location

**Primary fix**: `hermes_cli/model_switch.py` after line 894 (after the `except Exception: pass` in the else branch)

Add:
```python
# If base_url is still empty but we have a target provider,
# fall back to the provider's configured base_url so local
# model servers don't get wiped from config.
if not base_url and target_provider:
    pdef = resolve_provider_full(
        target_provider,
        user_providers,
        custom_providers,
    )
    if pdef and pdef.base_url:
        base_url = pdef.base_url
```

**Secondary concern**: `_persist_model_switch` unconditionally pops base_url when empty — this is correct behavior once switch_model properly preserves it, but worth noting that it will continue to delete stale base_url entries.

### Related Functions
- `_apply_model_switch`: server.py line 1106 — calls switch_model, handles result
- `_model_flow_custom`: main.py line 3563 — CLI custom endpoint flow (also prompts for URL)
- `_model_flow_named_custom`: main.py line 4390 — CLI named custom provider flow (probes /models)
- `_open_model_picker`: cli.py line 7350 — TUI model picker modal

### Test Scenario
1. Configure lmstudio with base_url in config.yaml
2. Select lmstudio via `hermes model` TUI
3. Verify base_url persists in config.yaml after selection
4. Verify no error produced