#!/usr/bin/env python3
"""Evaluate Hermes tool-availability gates for a profile the way a LIVE TURN would.

Why: provider-based gates (vision, video) resolve the main provider, so a probe from a bare
interpreter with no turn bound reports False while the live turn reports True. This script binds
the runtime first, then evaluates the gates.

Usage:
    HERMES_HOME=~/.hermes/profiles/<name> \
      <runtime python> profile_tool_gate_probe.py <main-provider> <model> <base_url>

Example (local router profile):
    HERMES_HOME=~/.hermes/profiles/<name> \
      ~/.hermes/tools/python-*/bin/python3 profile_tool_gate_probe.py \
      custom <local-model> http://localhost:8079/v1

Run it with the interpreter the `hermes` launcher names (~/.hermes/tools/python-*/bin/python3).
`hermes-agent/venv/bin/python` is not the runtime interpreter and its imports fail.
"""
import importlib
import os
import sys

HERMES_AGENT = os.path.expanduser("~/.hermes/hermes-agent")
if HERMES_AGENT not in sys.path:
    sys.path.insert(0, HERMES_AGENT)

# tool -> (module, check_fn). Extend as needed. A gate that returns False here while the profile's
# turns log no "returned False" registry line means the probe is not turn-bound.
GATES = {
    "vision_analyze": ("tools.vision_tools", "check_vision_requirements"),
    "video_analyze": ("tools.vision_tools", "check_video_requirements"),
}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    provider, model, base_url = argv[0], argv[1], argv[2]

    from agent import auxiliary_client as ac

    print("HERMES_HOME          :", os.environ.get("HERMES_HOME", "<unset>"))
    print("main provider/model  :", ac._read_main_provider(), "|", ac._read_main_model())
    print("model reports vision :", ac._main_model_supports_vision(provider, model))

    print("\n-- gates WITHOUT a bound runtime (what a bare probe sees) --")
    for tool, (mod, fn) in GATES.items():
        print(f"  {tool:16s} {getattr(importlib.import_module(mod), fn)()}")

    ac.set_runtime_main(provider, model, base_url=base_url,
                        api_key="no-key-required", session_id="gate-probe")
    prov, client, resolved = ac.resolve_vision_provider_client(provider="auto")
    print("\n-- with the turn runtime bound --")
    print("  resolve_vision_provider_client(auto):", prov, client is not None, resolved)
    for tool, (mod, fn) in GATES.items():
        print(f"  {tool:16s} {getattr(importlib.import_module(mod), fn)()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
