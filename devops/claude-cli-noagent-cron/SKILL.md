---
name: claude-cli-noagent-cron
description: "Run a Hermes cron job that invokes Claude Code CLI directly (not through OpenRouter), using the user's Claude subscription. Covers `no_agent` script pattern, file-only tool restriction, and pipeline from script to dream diary."
version: 1.0.0
tags: [cron, claude, no_agent, subscription, thinking-model, cron-script]
---

# Claude CLI `no_agent` Cron Pattern

When a profile needs a subscription-only model (Claude Opus via `claude` CLI) for a recurring cron task, use a `no_agent` bash script instead of routing through a Hermes provider.

## Architecture

```
Hermes Cron Scheduler
  job: thinker-nightly-dream
  no_agent: true
  script: thinker-dream.sh
  schedule: 0 22 * * *
        │
        ▼ runs script directly
~/.hermes/scripts/thinker-dream.sh
  claude --print --model opus --effort high \
    --allowed-tools "Read,Write" \
    --add-dir ~/projects \
    -p "self-contained prompt"
        │
        ▼ uses YOUR Claude subscription
Claude Code API
  - No Hermes provider involved
  - No OpenRouter token costs
  - Uses your claude subscription or API key
  - stdout → cron delivery
```

## When to Use

- The profile uses a model requiring a **subscription** (Claude Opus via `claude` CLI)
- The user wants direct CLI billing/usage instead of OpenRouter
- The cron job is write-only (appends to a file, `deliver='local'`)

## Implementation

### 1. Write the Script

Save to `~/.hermes/scripts/<name>.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROMPT=$(cat << 'EOF'
Your complete self-contained prompt here.
The script IS the agent — no skills loaded.
EOF
)

claude \
  --print \
  --model opus \
  --effort high \
  --allowed-tools "Read,Write" \
  --add-dir "$HOME/projects" \
  -p "$PROMPT"
```

Key flags:
- `--print` — non-interactive mode, returns output as text
- `--model opus` — Claude Opus via subscription
- `--effort high` — thinking effort (low/medium/high/xhigh/max)
- `--allowed-tools "Read,Write"` — restrict to read/write only
- `--add-dir <path>` — grant file access to specific directories
- `-p "..."` — the prompt

### 2. Make Executable

```bash
chmod +x ~/.hermes/scripts/thinker-dream.sh
```

### 3. Create the Cron Job

```yaml
cronjob(
  action='create',
  name='thinker-nightly-dream',
  schedule='0 22 * * *',
  script='thinker-dream.sh',
  no_agent=True,
  deliver='local'
)
```

`no_agent=True` semantics:
- No Hermes LLM agent — the script IS the job
- Non-empty stdout → delivered as message
- Empty stdout → silent (no notification)
- Non-zero exit / timeout → error alert sent

## Verifying Without Burning Quota

The success and failure branches of the wrapper script can be tested deterministically by pointing `CLAUDE_BIN` at a stub (`printf '#!/bin/bash\necho CLAUDE_DAILY_OK\n'`) via `sed` into a temp copy — no API call, no quota. Only the account-level call needs a live run.

## Pitfalls

- **Prompt must be self-contained.** `no_agent` scripts don't load skills or SOUL.md. Everything goes in the prompt string.
- **Keep scripts in `~/.hermes/scripts/`** — relative paths resolve there.
- **`deliver='local'` saves output without messaging.** Use `deliver='origin'` to send raw stdout to the origin chat.
- **Claude `--print` bypasses workspace trust dialog.** Only use in directories you trust.
- **Never use `--bare` in cron.** It skips keychain reads, so OAuth credentials are never read and the run dies with `Not logged in · Please run /login` (exit 1). Plain `--print` with `HOME` set works.
- **Add `--no-session-persistence`** for throwaway smoke/ping sessions — otherwise every tick leaves a resumable session in Claude's history.
- **Account session limits look like script failures.** `You've hit your session limit · resets <time>` exits 1; that is the subscription quota, not a broken script. Schedule well clear of the reset time.
- **`--allowed-tools` is Claude 2.x+.** Older versions may not support it — fall back to `--tools "Read,Write"` or accept all tools.
- **Don't repeat the SOUL process in the cron prompt.** The prompt IS the process for `no_agent` scripts — but keep it structured with step 1/2/3 markers, not free prose.
