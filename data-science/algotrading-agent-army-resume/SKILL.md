---
name: algotrading-agent-army-resume
description: Resume the Algo Trading Agent Army project — two-agent system for alpha generation signal research.
triggers:
  - "Algo Trading Agent Army"
  - "agent army"
  - "signal research project"
  - "feature generation agents"
---

# Algo Trading Agent Army — Resume Project

## Project Location

`~/algo-trading-army/`

## Directory Layout

```
algo-trading-army/
  agents/
    idea-sourcer/         # Agent Alpha: SOUL.md + config.yaml
    feature-implementer/  # Agent Beta: SOUL.md + config.yaml
  ideas/                  # Idea artifacts from Agent Alpha (YAML+MD)
  features/               # Feature implementations from Agent Beta (Python)
  config/                 # Shared config (query templates, etc.)
  logs/                   # Agent run logs
  README.md               # Project overview
```

## Agent Assignments

| Agent | Role | Model | Router Slot |
|-------|------|-------|-------------|
| Alpha | Idea Sourcer (research, paper analysis) | qwen35-27b-opus (Opus-distilled, strong reasoning) | localhost:8080 |
| Beta | Feature Implementer (code, TDD) | devstral-24b (code-specialized Mistral) | localhost:8080 |

Note: Router only serves one model at a time (models-max = 1). To run both agents concurrently, one would need a second router instance or sequential loading.

## Spawning

```bash
# Agent Alpha (one-shot research)
hermes chat -q --config ~/algo-trading-army/agents/idea-sourcer/config.yaml "Search ArXiv for..."

# Agent Beta (interactive implementation)
hermes --config ~/algo-trading-army/agents/feature-implementer/config.yaml

# Or spawn from orchestrator via hermes-agent skill with tmux
```

## Design Documents (Original Specs)

- `~/voicemails/2026-03-28_1125-algo-trading-agent-army.md` — High-level concept
- `~/voicemails/agent_idea_sourcer_expanded.md` — Agent Alpha detailed spec (~994 lines, 33KB)

## Feature Interface

All features implement a unified Protocol (name, category, required_inputs, lookback, compute). See Agent Beta's SOUL.md for full spec.

## Status

Profiles created, agents not yet spawned. Next: implement the Feature base protocol and registry, then first Alpha research run.