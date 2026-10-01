---
name: agent-output-audit
description: Verify agent output against system artifacts.
version: 1.0.0
---

# Agent Output Audit

## When to use

- Someone asks "what did that session actually accomplish?" and you need to verify against evidence
- A gateway restart lost the session context and you need to reconstruct what happened
- A standing goal session ran autonomously and you need to audit its output before reporting
- You suspect a session may have spun its wheels without delivering tangible results
- A session or profile blames its failure on its own environment ("can't read /tmp", "the sandbox blocks me", "the tool can't reach the file") and you need to test that claim before changing any config

## Workflow

### 1. Find the session

When a gateway restart has wiped session context, the agent.log has rotated:

```bash
ls -la ~/.hermes/logs/agent.log*
```

The current log starts fresh after restart. Older sessions are in `.1`, `.2`, etc. Find the right one by date:

```bash
grep '<session-id>' ~/.hermes/logs/agent.log.*
```

Session IDs look like `20260919_114057_93ebfc` (date_time_hash). The first log line shows the user's message and the model used.

### 2. Verify claimed work against tangible artifacts

**Do NOT trust the session's self-report.** A session with a standing goal may say "building fork X" but only write config files. Audit each claim:

| Claim | How to verify |
|---|---|
| "Built a fork" | `git log --oneline --since=<session-start>` in the repo — are there new commits? |
| "Created a binary" | Check mtime: `ls -la build/bin/llama-server` — did the mtime change during the session? |
| "Downloaded a model" | `ls -la ~/models/<dir>/` — check mtime of the file, compare to session timeframe |
| "Created a distrobox" | `distrobox list` or `podman ps -a` — does it actually exist? |
| "Started a service" | `systemctl --user status <service>` — is it active, inactive, or failed? Check journal: `journalctl --user -u <service>` |
| "Wrote scripts" | `ls -la ~/llm-server/` — check mtimes. `diff` against any pre-existing versions |

### 3. Distinguish old artifacts from new work

Files with mtimes before the session started are NOT the session's output. Always check:

```bash
# Files created/modified during the session
find <dir> -newer <reference-file-from-before-session> -not -path '*/.git/*'
```

Or compare timestamps directly:
```bash
stat -c '%Y %n' <file>  # unix timestamp
```

### 4. Check for hidden failures

- **Timed-out commands**: Look for `sequential tool terminal timed out after` in the session's log lines
- **API failures**: Look for `API call failed` with `HTTP 402` (spend limit), `HTTP 429` (rate limit), or `HTTP 500`
- **Turn liveness watchdog**: `Turn liveness watchdog fired` means the session was force-interrupted on a long-running command
- **Failed file writes**: `Refusing to overwrite` means the agent tried to modify a file without reading it first

### 5. Verify claims about the agent's own environment (permissions, sandbox, "can't read X")

An agent's explanation of why its tool failed is a hypothesis, not evidence: a model that emitted a bad argument reliably narrates a permission wall. Test the operation yourself before touching config.

```bash
# a. Which terminal backend? local = every host path is readable; a remote/sandboxed
#    backend confines reads to the profile's media cache instead.
hermes -p <profile> config get terminal.env

# b. Re-run the failing operation under the profile's OWN home. Profiles are isolated
#    islands: their config/.env/cache are not inherited, so resolving under the default
#    home proves nothing about the profile that reported the failure.
cd ~/.hermes/hermes-agent && HERMES_HOME=~/.hermes/profiles/<profile> venv/bin/python - <<'PY'
import asyncio
from tools.image_source import resolve_image_source, ResolveContext
r = asyncio.run(resolve_image_source("/tmp/f.png", ResolveContext(task_id=None)))
print("OK", r.origin, r.mime, len(r.data))
PY

# c. Ground truth for what the model actually sent — the stored assistant message,
#    not the log prose and not the agent's summary.
sqlite3 -readonly ~/.hermes/profiles/<profile>/state.db \
  "select role, tool_name, tool_calls from messages where tool_calls like '%<fragment>%' limit 5"

# d. Same filesystem? A user service with no PrivateTmp shares the host /tmp.
systemctl --user cat <service> | grep -i privatetmp   # no output = host /tmp
ls -l /proc/<service-pid>/ns/mnt /proc/$$/ns/mnt      # equal inode = same mount namespace
```

Then classify by counting, not by judging one call: `search_files` with `output_mode="count"` on `<tool> completed` vs `<tool> returned error` across the session separates a systematic argument-fidelity problem (one failure mode, zero successes) from an intermittent one worth retrying.

Only after that, match the knob to the mechanism: `gateway.strict` / `gateway.media_delivery_allow_dirs` / `trust_recent_files` decide whether an OUTBOUND attachment may be delivered, never whether a read succeeds — under the default `strict: false`, adding `/tmp` to the allow dirs is a no-op. Read reach is set by the terminal backend alone, and the only read denylist is credential/system paths (`/etc/passwd`, `~/.ssh`, `*.env`, `auth.json`).

## Pitfalls

- **A standing goal session can spin for hours without delivering.** 143 tool turns, 4 hours of wall time, and zero git commits is not "building a fork" — it's config scaffolding that couldn't execute. Always check git and binary mtimes before reporting "the session built X."
- **Logs rotate.** After a gateway restart, the current agent.log only has post-restart entries. The old session is in `agent.log.N` files. Grep all of them.
- **`distrobox create` inside a session is a red flag.** It pulls a container image and can take 30-60+ minutes, exhausting the session's timeout budget. If you see this in the log, the session was blocked there for most of its runtime.
- **A systemd service file existing does not mean the service runs.** Check `systemctl --user status` — the service may be `inactive (dead)` because the binary never started or the distrobox was never created.
- **"Config was written" ≠ "work was completed."** Creating a `start-<model>.sh` script takes seconds. Building a llama.cpp fork takes hours. Don't conflate the two.
- **File mtimes tell the truth.** If a model file's mtime is from last week, the session didn't download or modify it. If a script's mtime matches the session start time, that's new. If it matches last month, it's pre-existing.
- **An agent's self-diagnosis of its own environment is the least reliable line in the log.** "The file exists but the tool can't reach it from its own filesystem" is what a model says after it fabricated the path. Reproduce the operation under that profile's own `HERMES_HOME` before editing any config — a permission story and a bad argument look identical in the transcript, and only the direct run tells them apart.
- **Zero successes on one step is systematic, not flaky.** Count `<tool> completed` against `<tool> returned error` for the whole session. A long literal argument (path, filename, hash) that the model keeps truncating or char-swapping is a model-fidelity problem; the fix is making the agent list the directory and copy the exact literal, or using a stronger model for that lane — never a config permission.
- **Per-profile logs are not in the journal, and profiles are isolated islands.** A profile's platform and agent logs live under `~/.hermes/profiles/<p>/logs/`; `journalctl -u hermes-gateway` shows nothing for them, so an empty host journal is not "the adapter never ran". Likewise a profile with no `gateway:` section is on defaults — don't infer a per-profile restriction from a missing key.
