# Headroom-ai v0.24.0 — Internal Config Defaults

Extracted from the wheel at `~/.cache/pip/wheels/.../headroom_ai-0.24.0-cp314-cp314-linux_x86_64.whl`.

## SmartCrusherConfig (`headroom/config.py`)

```python
SmartCrusherConfig(
    enabled=True,
    max_items_after_crush=15,       # ← primary aggressiveness knob
    first_fraction=0.3,             # 30% of K from array start
    last_fraction=0.15,             # 15% of K from array end
    min_items_to_analyze=5,
    min_tokens_to_crush=200,
    variance_threshold=2.0,
    uniqueness_threshold=0.1,
    similarity_threshold=0.8,
    preserve_change_points=True,
    factor_out_constants=False,
    include_summaries=False,
    use_feedback_hints=True,        # TOIN learning
    toin_confidence_threshold=0.3,
    dedup_identical_items=True,
    relevance=RelevanceScorerConfig(
        tier="hybrid",              # bm25 | embedding | hybrid
        bm25_k1=1.5, bm25_b=0.75,
        relevance_threshold=0.25,   # keep items above this score
    ),
    anchor=AnchorConfig(
        anchor_budget_pct=0.25, min_anchor_slots=3, max_anchor_slots=12,
        default_front_weight=0.5, default_back_weight=0.4,
        search_front_weight=0.75, logs_back_weight=0.75,
        use_information_density=True, candidate_multiplier=3,
    ),
)
```

## CCRConfig (`headroom/config.py`)

```python
CCRConfig(
    enabled=True,
    store_ttl_seconds=300,          # 5 minutes — bump to 1200 for long sessions
    store_max_entries=1000,
    inject_retrieval_marker=True,
    inject_tool=True,               # injects `headroom_retrieve` tool
    inject_system_instructions=False,
    feedback_enabled=True,
    min_items_to_cache=20,
)
```

## ContentRouterConfig + DEFAULT_EXCLUDE_TOOLS

```python
ContentRouterConfig(
    exclude_tools=None,             # None = use DEFAULT_EXCLUDE_TOOLS
    compress_tagged_content=False,
    read_lifecycle=ReadLifecycleConfig(
        enabled=True, compress_stale=True,
        compress_superseded=False, min_size_bytes=512,
    ),
    tool_profiles=None,             # None = use DEFAULT_TOOL_PROFILES
)

DEFAULT_EXCLUDE_TOOLS = frozenset({
    "Read", "Glob", "Grep", "Write", "Edit", "Bash",
    "read", "glob", "grep", "write", "edit", "bash",
})

DEFAULT_TOOL_PROFILES = {
    "Grep": PROFILE_PRESETS["conservative"],   # bias=1.5, min_k=5
    "Bash": PROFILE_PRESETS["moderate"],        # bias=1.0, min_k=3
    "WebFetch": PROFILE_PRESETS["aggressive"],  # bias=0.7, min_k=3
}
```

## CompressConfig (`headroom/compress.py`)

```python
CompressConfig(
    compress_user_messages=False,
    compress_system_messages=True,
    protect_recent=4,
    protect_analysis_context=True,
    target_ratio=None,              # None = content-router default
    min_tokens_to_compress=250,
    kompress_model=None,
)
```

**Critical pitfall:** `exclude_tools` is NOT a CompressConfig field. It lives on `ContentRouterConfig`. The `compress()` convenience function doesn't expose it — must monkeypatch `headroom.config.DEFAULT_EXCLUDE_TOOLS` before pipeline init or use the full `HeadroomClient` API.

## Other configs (for reference)

```python
PrefixFreezeConfig(enabled=True, min_cached_tokens=1024,
                   session_ttl_seconds=600, force_compress_threshold=0.5)

CacheAlignerConfig(enabled=False, use_dynamic_detector=True,
                   detection_tiers=["regex"], entropy_threshold=0.7)

CacheOptimizerConfig(enabled=True, auto_detect_provider=True,
                     min_cacheable_tokens=1024, enable_semantic_cache=False)

HeadroomConfig(
    store_url="sqlite:///headroom.db",
    default_mode=HeadroomMode.AUDIT,
    output_buffer_tokens=4000,
    intercept_tool_results=False,
    generate_diff_artifact=False,
    smart_crusher=SmartCrusherConfig(),
    ccr=CCRConfig(),
    prefix_freeze=PrefixFreezeConfig(),
    cache_aligner=CacheAlignerConfig(),
    cache_optimizer=CacheOptimizerConfig(),
)
```
