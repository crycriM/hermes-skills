---
name: multi-agent-profile-config
description: Configure Hermes multi-agent teams with per-profile roles, models, tool restrictions, SOULs, and cron. Covers the design patterns used in the Algo Trading Agent Army (Imhotep, Nicolaus, Pita, Medor, August).
tags:
  - hermes
  - profile
  - multi-agent
  - configuration
  - tool-restrictions
  - role-based
triggers:
  - "create a profile"
  - "configure agent"
  - "multi-agent setup"
  - "specialized role"
  - "agent permissions"
  - "hermes profile config"
---

# Multi-Agent Profile Configuration

Configure Hermes profiles as specialized agents with distinct roles, models, and tool permissions. Each profile is a full Hermes home at `~/.hermes/profiles/<name>/` with its own config, SOUL, skills, cron, sessions, and state.

## Design Principles

1. **One role per profile** — architect, builder, reviewer, researcher, thinker. Never blend roles.
2. **Model matches the task** — cheap local for high-volume work, cloud coding for complex implementation, thinking model for creative/deep reasoning.
3. **Tool restrictions enforce the role** — builders get full shell, everyone else gets file/browser/web or file only.
4. **Turn limits protect the budget** — expensive models (Claude Opus) get `max_turns: 10`. Cheap local models get `max_turns: 100`.
5. **SOUL.md encodes the process** — not just personality, but exact steps with guardrails against runaway scope.

## Profile Config Patterns

### Tool Restriction Design

Each profile restricts tools by role:

```yaml
# Builder (full access — can run code, git, deploy)
toolsets: [all]
agent:
  disabled_toolsets: []

# Reviewer / Architect / Researcher (no destructive tools)
toolsets: [file, browser, web]
agent:
  disabled_toolsets: [terminal, git, code_execution, computer_use, cronjob]
terminal:
  timeout: 30
  persistent_shell: false

# Thinker (file only — expensive model, tight leash)
toolsets: [file]
agent:
  max_turns: 10
  reasoning_effort: high
  disabled_toolsets: [terminal, git, code_execution, computer_use, cronjob, browser, web]
```

### Model Assignment Strategy

| Purpose | Model | Provider | Cost Profile |
|---------|-------|----------|--------------|
| Cheap local work | `qwen36-27b` | local (:8079) | Free (local GPU) |
| Deep local reading | `qwen36-35b` | local (:8079) | Free (local GPU) |
| Cloud coding/planning | `glm-5.2` | opencode-go | ~$1-4/1M tokens |
| Fast cloud fallback | `deepseek-v4-pro` | opencode-go | ~$2-3/1M tokens |
| Cheap cloud reasoning | `deepseek-v4-flash` | opencode-go | ~$0.14-0.28/1M tokens |
| Deep thinking | `claude-opus-4.8` | openrouter | ~$2-10/1M tokens |

### Aux Model Assignment

Wire aux sub-models to the cheapest option that works:

```yaml
auxiliary:
  vision:           { provider: opencode-go,  model: mimo-v2.5 }
  compression:      { provider: openrouter,   model: google/gemini-2.5-flash }
  web_extract:      { provider: local,        model: qwen36-27b }
  session_search:   { provider: local,        model: qwen36-27b }
  skills_hub:       { provider: local,        model: qwen36-27b }
  mcp:              { provider: local,        model: qwen36-27b }
  approval:         { provider: local,        model: qwen36-27b }
  flush_memories:   { provider: local,        model: qwen36-27b }
```

For profiles without local router access (August, Pita), all aux models point to the main cloud provider.

### Delegation Model

Subagents typically use a cheaper model than the parent:

```yaml
# Local parent → cloud subagents (local GPU isn't shared)
delegation:
  model: deepseek-v4-pro
  provider: opencode-go
  default_toolsets: [terminal, file, web]

# Cloud parent → same model (subagents are rare)
delegation:
  model: anthropic/claude-opus-4.8
  provider: openrouter
  max_iterations: 5
  default_toolsets: [file]
```

### Display for Non-Interactive Agents

```yaml
display:
  compact: true
  personality: helpful
  resume_display: compact
  show_reasoning: true
  show_cost: true
  streaming: false
  background_process_notifications: errors
  tool_progress: result
  busy_input_mode: block
```

### Messaging Platforms

Strip messaging (discord, telegram, whatsapp) from non-interactive agents:

```yaml
platform_toolsets:
  cli:
    - browser
    - clarify
    - delegation
    - file
    - memory
    - session_search
    - skills
    - todo
    - web
  discord: []
  telegram: []
```

### Approval Mode

Non-destructive agents use auto-approvals:

```yaml
approvals:
  mode: auto
  timeout: 30
```

## SOUL Template

Each SOUL.md follows this structure:

```
# [Name] — [Role Tagline]

You are [name], the [role]. [One-liner.]

## Identity

[2-3 sentences establishing who the agent is.]

## Core Directive

- [Primary responsibility]
- [What they must always do]
- [What they must never do]

## [Role-Specific Section: Review Dimensions / Typical Tasks / Principles]

[Operational guidelines specific to the role.]

## Constraints

- [No shell access / Full shell access / File only]
- [No implementation / No deployment / No code editing]
```

Each SOUL must include PROHIBITIONS (what the agent must NOT do) — not just permissions.

## August: Nightly Cron (Expensive Model Pattern)

When a profile uses an expensive model with recurring cron:

| Pattern Element | Value |
|----------------|-------|
| Model | Cloud thinking model (claude-opus-4.8) |
| Max turns | 10 (hard cap) |
| Process | Encoded in SOUL.md, NOT in cron prompt |
| Step 1 | Read existing output (observe) |
| Step 2 | Internal reasoning (no web research) |
| Step 3 | Write structured output (append-only) |
| Tools | file only |
| Cron schedule | `0 22 * * *` or similar off-peak |
| Cron delivery | local (file write only, no messaging) |
| Cron toolsets | [file] |

The cron prompt should be a one-line invocation referencing the SOUL process — not repeating the process steps.

## Per-Profile Config Checklist

| Config Key | Notes |
|------------|-------|
| `model.default` | Primary model + provider |
| `model.base_url` | Provider endpoint |
| `fallback_providers` | Cloud fallback entries |
| `toolsets` | Match role (all / file+browser+web / file) |
| `agent.disabled_toolsets` | Opposite of toolsets — explicit block |
| `agent.max_turns` | 10 for expensive, 60-100 for cheap |
| `agent.reasoning_effort` | high for thinking models, low for research |
| `terminal.persistent_shell` | false for non-builders |
| `terminal.timeout` | Short (15-30s) for no-shell agents |
| `auxiliary.*` | Cheapest reliable model per task |
| `delegation.model` | Often cheaper than parent |
| `delegation.default_toolsets` | Match subagent task |
| `approvals.mode` | auto for non-destructive agents |
| `display.compact` | true for agentic/non-interactive use |
| `logging.level` | WARNING for unattended cron agents |
| `timezone` | Required when cron is used |
| `platform_toolsets` | Strip messaging platforms |
| `memory.memory_enabled` | false for cron-only agents (diary is memory) |

## Common Pitfalls

- **No fallback provider**: If local router is down, the agent is stuck. Always add at least one cloud fallback.
- **Delegation model same as parent model on local**: Subagents queue behind parent on the same GPU. Use a different provider for delegation.
- **Aux models point to unavailable provider**: If the local router is the only provider configured and it's down, vision/compression/session_search all break. Use opencode-go or openrouter for critical aux paths.
- **No max_turns on expensive model**: Claude Opus can run indefinitely. Always set `agent.max_turns` when using expensive cloud models.
- **Cron prompt duplicates SOUL**: Don't repeat the process in the cron prompt — the SOUL.md is injected at cron runtime. Keep the prompt as a one-line invocation.
- **Tool bloat**: Importing `toolsets: [all]` on a reviewer/architect gives them shell access they shouldn't have. Be explicit.
- **Personalities / skins / TTS / STT on non-interactive agents**: Strip these. They waste context and config space.
- **Shared gateway tokens between profiles**: If two profiles configure the same Telegram bot token (via `TELEGRAM_BOT_TOKEN` in `.env`), only the first gateway to start claims it. The second logs `Telegram bot token already in use (PID X)`. The token lives in `.env`, not `config.yaml` — removing `platform_toolsets.telegram` from config is not enough. See `references/gateway-conflict-diagnosis.md`.
