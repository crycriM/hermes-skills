---
name: headroom-ai-integration
description: Integrating headroom-ai v0.24+ into Python proxies as a per-request context-compression step before the LLM. Covers API differences from the original plan, CompressConfig fields, content router auto-strategy selection, Python 3.14 install with PyO3 forward-compat, and proxy wiring patterns.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [headroom, context-compression, proxy, llama-cpp, python]
---

# Integrating headroom-ai into a Python LLM proxy

## When to use

You're routing `/v1/chat/completions` requests through a Python proxy (model
manager, gateway, sidecar) and want to compress tool outputs, file trees, code
blocks, and long conversation history *before* they hit the LLM. Targets
agentic and coding sessions where context bloat dominates token cost.

## v0.24 API gotchas (vs. older docs and the plan in ~/llm-server)

The plan written in early June 2026 referenced headroom-ai ≤ 0.5 and several
fields no longer exist. Verified against v0.24.0 (current as of 2026-06-13):

### CompressConfig fields (v0.24)
```python
CompressConfig(
    target_ratio=0.5,              # aim for this size; None = use content-router default
    protect_recent=4,              # last N messages untouched (was 2 in older plan)
    min_tokens_to_compress=200,    # skip short conversations (was min_chars in plan)
    compress_user_messages=False,  # user turns preserved verbatim (v0.24 default)
    protect_analysis_context=True, # protect reasoning / chain-of-thought
    kompress_model=None,           # optional ML model for prose (heavy)
)
```

### Compress function signature
```python
from headroom import compress, CompressConfig
result = compress(
    messages,                       # list[dict] in OpenAI format
    model="qwen36-35b",             # required-ish: drives content-router strategy
    model_limit=131072,             # context window; pass from your model config
    config=CompressConfig(...),
)
```

### CompressResult fields
- `messages` — list[dict], ready to forward
- `tokens_before`, `tokens_after`, `tokens_saved` — ints
- `compression_ratio` — float (after / before; 0.36 = 64% saved)
- `transforms_applied` — list of router-internal tags like `router:mixed:0.26`,
  `router:protected:user_message`, `router:protected:recent_code`

### `strategies` is GONE
v0.24 picks strategies automatically per-message via the content router
(`text` / `code` / `smart_crusher` / `mixed`). No manual strategy list.
YAML/plan schema should drop the `strategies` field.

## Python 3.14 install

Native extension fails to build with default flags. Use PyO3 forward-compat:

```bash
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 pip install "headroom-ai[proxy]"
```

Works on the existing `~/llm-server/venv` (Python 3.14).

## Proxy wiring pattern (used in model_manager.py)

```python
# Module-level guards — set in main() from CLI flags
COMPRESSION_GLOBALLY_DISABLED = False

def _compress_messages(messages, model_info, model_name):
    if COMPRESSION_GLOBALLY_DISABLED or not HEADROOM_AVAILABLE or not model_info.compression_enabled:
        return messages, {}
    if not messages or len(messages) <= model_info.compression_protect_recent:
        return messages, {}
    try:
        cfg = CompressConfig(
            target_ratio=model_info.compression_target_ratio,
            protect_recent=model_info.compression_protect_recent,
            min_tokens_to_compress=model_info.compression_min_tokens,
            compress_user_messages=model_info.compression_compress_user,
        )
        result = headroom_compress(messages, model=model_name,
                                    model_limit=model_info.ctx_size, config=cfg)
        return list(result.messages), {
            "tokens_before": result.tokens_before,
            "tokens_after": result.tokens_after,
            "tokens_saved": result.tokens_saved,
            "compression_ratio": result.compression_ratio,
            "transforms": result.transforms_applied,
        }
    except Exception as e:
        logging.warning(f"compression failed for {model_name}: {e}")
        return messages, {}
```

Insert the call **before** the reasoning-budget / logit-bias step so token
accounting reflects the compressed prompt. The Pyright / lsp checker doesn't
know `headroom_compress` and `CompressConfig` exist; use `# type: ignore`
on the `None` fallbacks in the ImportError branch.

## Pyright / type-checker warnings

`from headroom import compress as headroom_compress, CompressConfig` and
falling back to `None` makes Pyright complain about calling `None`:

```python
except ImportError:
    headroom_compress = None  # type: ignore[assignment]
    CompressConfig = None  # type: ignore[assignment,misc]
```

## Expected savings (Strix Halo, qwen36-35b, 131k context)

Long agentic sessions (40+ messages, large tool outputs): **30-65% token
reduction**. The first call after startup is slow (~14s) due to model
downloads and tiktoken init; subsequent calls are <100ms with cache hits.
Cold-cache latency comes from huggingface downloads — pre-warm if possible.

## Observed transforms

Real-world output from a 26-message agentic call:
```
content_router: 26 msgs — 7 compressed (mixed:0.26, ...), 9 skipped (user),
                9 skipped (<50 words), 1 protected (recent code)
Pipeline complete: 96190 -> 34394 tokens (saved 61796, 64.2% reduction)
◈ qwen36-35b compression: 96190 → 34394 tokens (36% saved)
```

## Tuning the internal config knobs

`CompressConfig` is the user-facing surface, but the real knobs live inside
headroom's internal `HeadroomConfig` → `SmartCrusherConfig` / `CCRConfig` /
`ContentRouterConfig`. These are set at pipeline init time, not per-request.

### SmartCrusherConfig defaults (from `headroom/config.py`)

```python
SmartCrusherConfig(
    max_items_after_crush=15,       # ← primary aggressiveness knob
    first_fraction=0.3,             # 30% of K slots from array start
    last_fraction=0.15,             # 15% of K slots from array end
    min_items_to_analyze=5,
    min_tokens_to_crush=200,
    variance_threshold=2.0,         # anomaly-detection strictness
    relevance_threshold=0.25,       # keep items scoring above this (hybrid BM25+embedding)
    similarity_threshold=0.8,       # for clustering similar strings
    dedup_identical_items=True,
    use_feedback_hints=True,        # TOIN learning
)
```

**To make SmartCrusher less aggressive** (the most common complaint):
bump `max_items_after_crush` to 50, increase `first_fraction`/`last_fraction`,
or raise `relevance_threshold`. These require monkeypatching or a custom
pipeline init — they aren't on `CompressConfig`.

### CCRConfig defaults (Compress-Cache-Retrieve)

```python
CCRConfig(
    enabled=True,
    store_ttl_seconds=300,          # 5 minutes — increase for long sessions
    store_max_entries=1000,
    inject_retrieval_marker=True,
    inject_tool=True,               # injects headroom_retrieve tool
    feedback_enabled=True,
    min_items_to_cache=20,
)
```

**To increase TTL to 20 minutes:** set `store_ttl_seconds=1200`.

### ContentRouterConfig — tool exclusions

```python
ContentRouterConfig(
    exclude_tools=None,   # None = use DEFAULT_EXCLUDE_TOOLS below
)
```

`DEFAULT_EXCLUDE_TOOLS` (from `headroom/config.py`):
```python
frozenset({"Read", "Glob", "Grep", "Write", "Edit", "Bash",
           "read", "glob", "grep", "write", "edit", "bash"})
```

**Pitfall:** `exclude_tools` is on `ContentRouterConfig`, NOT on
`CompressConfig`. The `compress()` convenience function doesn't expose it.
To add custom exclusions at the proxy layer, monkeypatch
`headroom.config.DEFAULT_EXCLUDE_TOOLS` BEFORE the pipeline singleton
initializes (before the first `compress()` call):

```python
import headroom.config
headroom.config.DEFAULT_EXCLUDE_TOOLS = frozenset(
    headroom.config.DEFAULT_EXCLUDE_TOOLS |
    {"terminal", "read_file", "web_extract", "execute_code", "browser_snapshot"}
)
```

### Tuning guidance

| Parameter | Conservative (safe) | Moderate | Aggressive (risky) |
|-----------|---------------------|----------|---------------------|
| `target_ratio` | 0.7 | 0.5 | 0.2 |
| `protect_recent` | 8 | 4 | 2 |
| `max_items_after_crush` | 50 | 25 | 15 |
| `store_ttl_seconds` | 1200 | 600 | 300 |

## Status: REMOVED from proxy (2026-06-18)

Headroom on-the-fly compression was **removed** from `model_manager.py` on
2026-06-18. It was too destructive for agentic use — tool outputs, file
paths, and code blocks got mangled, breaking downstream workflows.

Hermes native lossless compression is now the sole compression mechanism.
All headroom code (imports, dataclass fields, config parsing, `_compress_messages`,
`_patch_pipeline_exclude_tools`, CLI flag, YAML config) has been purged from
the proxy. The `headroom-ai` pip package may still be installed in the venv
but is no longer imported or used.

If re-integration is ever needed, this skill documents the v0.24 API.

## Failure modes

- **Pyright ImportError warnings on headroom**: type-ignore on the None fallback.
- **First call downloads HuggingFace tokenizer models**: ~14s cold, but cached.
- **No compression triggered**: check `compression_protect_recent` isn't ≥
  message count, and `min_tokens_to_compress` is below your payload size.
- **API breakage on upgrade**: re-test signature; headroom ships breaking
  changes between minor versions (0.5 → 0.24 changed result fields and
  removed `strategies`).
- **Wrong `model=` arg**: pass the actual model name (e.g. `'qwen36-35b'`), not the default `'claude-sonnet-4-5-20250929'`. The content router calibrates strategy choice to the model.
- **Tool output too heavily crushed**: default `max_items_after_crush=15` is aggressive for arrays with 100+ items. Bump to 50 and check `first_fraction`/`last_fraction`.
- **CCR retrieval fails for older data**: default TTL is 5 minutes. Long agentic sessions need `store_ttl_seconds=1200` (20 min).
- **`exclude_tools` has no effect when set via `CompressConfig`**: it's a `ContentRouterConfig` field, not exposed through the one-function API. Must monkeypatch `DEFAULT_EXCLUDE_TOOLS` or use the full `HeadroomClient` API.

## References

- **[v0.24 API drift](references/v0.24-api-drift.md)** — quick lookup for renames between headroom ≤ 0.5 and v0.24+: `CompressConfig` fields, result field renames, `transforms_applied` semantics, performance baselines, install gotchas on Python 3.14.
- **[Internal config defaults](references/internal-config-defaults.md)** — full dump of `SmartCrusherConfig`, `CCRConfig`, `ContentRouterConfig`, `DEFAULT_EXCLUDE_TOOLS`, and `DEFAULT_TOOL_PROFILES` from v0.24.0 source.
