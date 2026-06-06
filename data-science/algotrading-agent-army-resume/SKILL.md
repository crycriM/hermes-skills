---
name: algotrading-agent-army-resume
description: Resume the Algo Trading Agent Army project — five-agent system (August, Zero, Nicolaus, Imhotep, Pita) for alpha generation signal research.
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
    august/              # Agent August — strategist config + soul
    zero/                # Agent Zero — overseer config + soul
    nicolaus/            # Agent Nicolaus — research config + soul
    imhotep/             # Agent Imhotep — coding config + soul (opencode)
    pita/                # Agent Pita — code review config + soul
  topics/                # August output — curated topic candidates
  ideas/                 # Idea artifacts from Nicolaus
  features/              # Feature implementations from Imhotep
  reviews/               # Code review reports from Pita
  config/
    source-list.yaml           # Curated source list (August maintains)
    topic-taxonomy.yaml        # Research theme taxonomy (August maintains)
    data_inventory.yaml        # What data we have
    query_templates.yaml       # Research prompt templates
    test_thresholds.yaml       # IC / hit rate / significance thresholds
  scripts/               # react-loop.sh, night-research.sh
  logs/                  # Agent run logs
```

## Agent Assignments

| Agent | Role | Type | Model | Profile | When |
|-------|------|------|-------|---------|------|
| **August** | Strategy / Curation / Gate | Hermes | minimax27 (230B MoE, local) | august | Evening (cron) |
| **Zero** | Overseer / QA / Coordination | Hermes | glm-5.1 (Z.AI cloud) | zero | On demand |
| **Nicolaus** | Research / Paper analysis | Hermes | minimax27 (230B MoE, local) | nicolaus | Night (cron) |
| **Imhotep** | Feature implementation (coding) | OpenCode | qwen36-35b (35B MoE, no thinking) | — | Day |
| **Pita** | Code review / Recommendations | Hermes | nemotron-cascade2-30b (30B MoE, local) | pita | Day |

Pipeline: August ideates/gates → topics/ → Nicolaus researches → ideas/ → Imhotep implements → features/ → Pita reviews → reviews/ → Zero oversees all.

## Agent August — Details

Most cerebral agent. Sits upstream of everyone. Three modes:
- **EXPLORATION**: Browse web/GitHub, discover sources, create topic candidates
- **GATE**: Evaluate topics, assign priority, produce research-brief.md for Nicolaus
- **REFLECTION**: When backlog is large, read and improve existing topics + taxonomy

Priority domain: time series methods for price series + alpha generation, crypto only.
Self-reflects when pipeline is saturated. Can start deploying now.

## Day/Night Schedule

- **Evening (cron):** minimax27 loaded → August explores/gates/reflects → topics/ + research-brief.md
- **Night (cron):** minimax27 stays loaded → Nicolaus reads research-brief → ideas/
- **Day (supervised):** 3 models loaded concurrently on router (qwen36-35b + cascade2-30b + one more), model-manager routes by request
- Zero is cloud-based (glm-5.1), never blocked by GPU

## ReAct Loop (Daytime)

Imhotep → Pita, max 2 iterations. Zero orchestrates from cloud.
1. Imhotep implements signal from idea
2. Pita reviews code + test methodology
3. Verdict: SHIP → done | NEEDS_CHANGES + iter<2 → Imhotep fixes → Pita re-reviews
4. After iter 2, final verdict regardless

Scripts: `scripts/night-research.sh`, `scripts/react-loop.sh`

## Research Workflow

Stage 0: August ideates + gates → Stage 1: Nicolaus discovers → Stage 2: Zero data checks → Stage 3: Imhotep implements → Stage 4: Signal test → Stage 5: Pita reviews.

3 research domains: alpha features, risk management, trading ideas. Each idea artifact declares data needs (frequency, symbols, min history).

Spec: `~/algo-trading-army/docs/research-workflow.md`

## Spawning

```bash
# August (evening exploration)
hermes chat --profile august --config ~/algo-trading-army/agents/august/config.yaml \
  "Run evening session: explore, gate topics, reflect as needed"

# Agent Zero (one-shot status check)
hermes chat -q --profile zero --config ~/algo-trading-army/agents/zero/config.yaml "Check status"

# Nicolaus (research run, uses August's research brief)
hermes chat --profile nicolaus --config ~/algo-trading-army/agents/nicolaus/config.yaml \
  "Read topics/research-brief.md and execute top-priority research topic"

# Imhotep (OpenCode, one-shot)
opencode run 'PROMPT' --model custom/qwen36-35b --workdir ~/algo-trading-army

# Pita (code review)
hermes chat --profile pita --config ~/algo-trading-army/agents/pita/config.yaml "Review features/"

# Or spawn from orchestrator via hermes-agent skill with tmux
```

## Hermes Profiles

```bash
hermes profile create august
hermes profile create zero
hermes profile create nicolaus
hermes profile create pita
hermes profile list
```

## Feature Interface

All features implement a unified Protocol (name, category, required_inputs, lookback, compute). See Agent Imhotep's SOUL.md for full spec.

## Status

Five-agent army configured. Agent August added — first agent ready to deploy. Profiles need Hermes profile creation (`hermes profile create <name>`). Next: create profiles, first August exploration run.
