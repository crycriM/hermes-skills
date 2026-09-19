---
name: architect-agent-profile
description: "Configure a Hermes agent profile for a planning-only (architect) role — no shell, no git, no code execution. Covers config YAML, SOUL.md writing, provider selection, and the white-list toolset approach."
version: 1.0.0
author: Hermes Agent
tags: [Hermes, Profile, Configuration, Architect, Planning, Multi-Agent]
---
# Architect Agent Profile

Template for setting up a Hermes profile for a planning-only (architect) agent — can read/write files and browse the web, but cannot run shell commands, git, or code.

Trigger when a user asks to set up a non-coding Hermes profile for planning, architecture, or system design.

## Use Case

A planning/architect agent in a multi-agent system. It decomposes requirements, writes specs, designs folder structures and schemas, and delegates implementation to coding agents. It never builds, tests, or deploys.

## Config Template

### Model & Provider

```yaml
model:
  default: <model-name>           # e.g. glm-5.2
  provider: <provider>            # e.g. opencode-go
  base_url: https://opencode.ai/zen/go/v1
  api_mode: chat_completions

# Optional fallback for resilience
fallback_providers:
  - provider: openrouter
    model: <provider-qualified-model>   # e.g. zhipu/glm-5.2
```

### Tools — White-list, not black-list

```yaml
# Only what an architect needs
toolsets:
  - file
  - browser
  - web

agent:
  max_turns: 40                         # no need for 100-turn code iterations
  disabled_toolsets:
    - terminal                          # no shell
    - git                               # no version control
    - code_execution                    # no running code
    - computer_use                      # no desktop control
    - cronjob                           # no scheduled tasks
  reasoning_effort: medium
```

Important: also restrict `platform_toolsets.cli` — the top-level `disabled_toolsets` isn't always sufficient for all platforms:

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
```

### Defense-in-Depth

```yaml
terminal:
  timeout: 30
  persistent_shell: false

approvals:
  mode: auto                             # specs don't need manual approval
  timeout: 30

display:
  compact: true
  tool_progress: result                  # only show tool results, not raw calls
```

### Auxiliary Providers

All auxiliary work through the same provider family — avoid wiring to a local router (`:8079`) so the profile runs anywhere:

```yaml
auxiliary:
  vision:
    provider: <primary-provider>
    model: <vision-model>               # e.g. mimo-v2.5
  web_extract:
    provider: <primary-provider>
    model: <model>
  session_search:
    provider: <primary-provider>
    model: <model>
  compression:
    provider: openrouter                 # compression can use a cheap external model
    model: google/gemini-2.5-flash
```

Keep the `local` provider block even if unused — harmless, prevents missing-provider fallback errors.

## SOUL.md Pattern

```markdown
# <Name> — Architect

You are <name>, the architect agent. You plan and design. You do not build.

## Core Directive
- Analyse requirements and decompose into measurable tasks.
- Design folder structures, schemas, API contracts, component trees.
- Write technical specifications, decision records, interface definitions.
- Ask clarifying questions when requirements are incomplete or ambiguous.
- Output plans and specifications only. Never write implementation code,
  never run build commands, never test, never deploy.

## Design Principles
- Favour modular, evolvable architectures over monolithic ones.
- Use open-source, well-maintained libraries and tools.
- Prefer loose coupling, clear interfaces, and documented contracts.
- When there is a trade-off, prefer the option that keeps future changes localised.

## Constraints
- No shell access — cannot run terminal commands, execute scripts, or manipulate
  the filesystem through CLI tools.
- Cannot write or run code. You design, document, and plan.
- Can read files to understand existing codebases.
- Can write specification files (docs, YAML, JSON, markdown, Mermaid diagrams).
- Can browse the web and read documentation for research.

## Output Style
- Be concise and precise. Deliver working specifications, not prose essays.
- Use Mermaid diagrams for architecture visualisations.
- Use structured formats (YAML, JSON, markdown tables) for specifications.
- When a decision is made, record the rationale and alternatives considered.
```

## Provider Choices

| Need | Recommended |
|------|-------------|
| **Primary model** | GLM-5.2 via opencode-go (`glm-5.2`) — strong reasoning, 1M context, inexpensive |
| **Fallback** | OpenRouter (`zhipu/glm-5.2`) — same model, alternate route |
| **Vision** | mimo-v2.5 via opencode-go |
| **Compression** | google/gemini-2.5-flash via openrouter |

## Generating the Config

Pattern for deriving an architect profile from the main agent config:

1. Read `~/.hermes/config.yaml` to understand the main agent's provider setup
2. Read the existing profile config at `~/.hermes/profiles/<name>/config.yaml`
3. Copy the `model` section from the main config but change model + provider
4. Override `toolsets` with the white-list above
5. Set `disabled_toolsets` for terminal/git/code_execution/computer_use/cronjob
6. Rewrite `platform_toolsets.cli` to only expose architect-relevant tools
7. Point all auxiliary providers to the same provider family (not local router)
8. Set `approvals: auto` and `display: compact`
9. Write a new SOUL.md enforcing the architect role boundary

## Pitfalls

- **Don't use `toolsets: [all]`** for a restricted agent. The `all` toolset includes terminal, and `disabled_toolsets` has complex precedence depending on `_config_version`. Always white-list.
- **`platform_toolsets.cli` must be explicitly restricted.** The top-level `toolsets` and `disabled_toolsets` control tool **availability**, but `platform_toolsets.cli` controls tool **visibility in CLI mode**. If you don't restrict both, the agent can still invoke tools it shouldn't.
- **Keep `_config_version` from a known-good profile.** The file needs a `_config_version` that matches the Hermes Agent version. Start at 12 or whatever the main profile uses.
- **Don't use `terminal: backend: none` or similar hacks** — just disable the toolset and set a fast timeout + `persistent_shell: false` as defense in depth.
- **The local provider block is harmless to keep.** Even if the agent never uses it, having it defined means fallback_model and auxiliary compression can reference it without config errors.
- **Auxiliary compression should not go through the primary provider** if that provider is a reasoning model. Use a cheap/fast model (gemini-flash via openrouter) to keep compression costs low.
