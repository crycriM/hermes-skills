#!/usr/bin/env python3
"""Probe Hermes model capabilities exactly as the desktop picker computes them.

Run from the repo root with the repo venv:

    cd ~/.hermes/hermes-agent
    venv/bin/python scripts/probe-model-caps.py opencode-go
    venv/bin/python scripts/probe-model-caps.py opencode-go deepseek-v4-flash
    venv/bin/python scripts/probe-model-caps.py --picker

Modes:
  <provider> [model]  -> capability map for one provider (all models, or one).
  --picker            -> full build_model_options_payload: providers, models,
                         capabilities, pricing, current model/provider.

Exit code is non-zero when the provider is unknown or payload build fails.
"""
from __future__ import annotations

import json
import sys


def dump_caps(provider: str, model: str | None) -> int:
    from hermes_cli.inventory import build_model_options_payload, load_picker_context

    payload = build_model_options_payload(load_picker_context())
    row = next((p for p in payload.get("providers", []) if p.get("slug") == provider), None)
    if row is None:
        print(f"provider not in picker payload: {provider}")
        print("known providers:", ", ".join(p.get("slug", "") for p in payload.get("providers", [])))
        return 1

    caps = row.get("capabilities") or {}
    models = row.get("models") or []
    if model is not None:
        if model not in caps:
            print(f"model {model!r} not in {provider} catalog")
            return 1
        print(json.dumps(caps[model], indent=2))
        return 0

    for m in models:
        print(f"{m}: {json.dumps(caps.get(m, {}))}")
    return 0


def dump_picker() -> int:
    from hermes_cli.inventory import build_model_options_payload, load_picker_context

    payload = build_model_options_payload(load_picker_context())
    print("current:", payload.get("model"), "/", payload.get("provider"))
    for p in payload.get("providers", []):
        caps = p.get("capabilities") or {}
        models = p.get("models") or []
        print(f"--- {p.get('slug')} ({len(models)} models) ---")
        for m in models[:12]:
            print(f"  {m}: {json.dumps(caps.get(m, {}))}")
        if len(models) > 12:
            print(f"  ... +{len(models) - 12} more")
    return 0


def main() -> int:
    args = sys.argv[1:]

    if not args or args[0] == "--picker":
        return dump_picker()

    provider = args[0]
    model = args[1] if len(args) > 1 else None
    return dump_caps(provider, model)


if __name__ == "__main__":
    sys.exit(main())