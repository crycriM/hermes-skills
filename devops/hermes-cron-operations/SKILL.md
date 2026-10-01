---
name: hermes-cron-operations
description: Use when managing or triaging Hermes cron jobs.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Cron, Scheduling, Triage, Gateway, Hermes]
    related_skills: [devops]
---

# Hermes cron operations (scheduling + triage)

## When to Use

- The user asks to move, add, pause, or resume a scheduled job ("move the wake-up
  call to 7:05", "run this every morning").
- A job produced nothing, its `last_status` is `error`, or the user reports that
  jobs "stopped running".
- The user reports a recurring brief/report that never arrived: a job can run
  every fire, write its output, and still deliver nothing (see "Triage: the job
  ran, but nothing arrived").
- After any gateway restart or runtime/interpreter change, before trusting any
  schedule.
- NOT for authoring the job's payload (its script or prompt) — this covers the
  store, the schedule, and why a fire produced nothing.

Covers the two things that go wrong around scheduled jobs: the schedule is not
where anyone thought it was, or the jobs do not actually run and say so only in
the store. Both are store-first problems, not prompt problems.

## Moving a schedule

1. **List first, then update by id.** `cronjob_manage action=list` → take the
   `job_id`; never guess one.
2. **One local tool call per op** — `tool_call` rejects a batch of two
   `cronjob_manage` entries ("takes exactly one entry for local tools"). Issue
   them as separate calls.
3. `cronjob_manage action=update job_id=<id> schedule='5 7 * * *'` (cron syntax
   or the natural forms the schema lists). Never hand-edit the store to move a
   schedule — the tool keeps the derived fields consistent.
4. **Verify against the store, not the reply.** Read `next_run_at` back out of
   `<hermes_home>/cron/jobs.json`. The update reply is a promise; `next_run_at`
   is the fact.

### Several jobs may be the same task at different hours

Job names often carry the hour of their run (e.g. a base name plus `-1310`,
`-1815` siblings), so one task can exist as several jobs. When the user names a
single time ("move the wake-up call to 7:05"):

- enumerate ALL jobs of that task, list their schedules, and pick only the group
  the stated time selects (the early one, for a wake-up);
- change that group, then say explicitly in the reply which sibling jobs you left
  alone — the user sees several and will otherwise assume all moved;
- if the stated time is ambiguous between two groups, do the obvious one and name
  the alternative rather than asking a question you can answer from the list.
- **After a move, the job NAME can lie.** A name carrying the hour (`-1310`,
  `-1815`) keeps the old hour in its text once the expr changes. Verify each
  schedule in the store, then state the drift and offer the rename — check
  `context_from`/`depends_on` in the store first, so "nothing references the name"
  is a checked claim rather than an assumption.

## Triage: one job is silent, or every job stopped

1. **Sweep every job in ONE pass** — a systemic break reads as "everything after
   time T failed", whereas one bad job fails alone. `<hermes_home>/cron/jobs.json`
   carries `last_run_at`, `last_status`, `last_error` (execution) and
   `last_delivery_error` (delivery only):

   ```bash
   python3 - <<'PY'
   import json, os
   p = os.path.expanduser('~/.hermes/cron/jobs.json')
   jobs = json.load(open(p))
   jobs = jobs if isinstance(jobs, list) else jobs['jobs']
   for j in sorted(jobs, key=lambda x: x.get('last_run_at') or ''):
       print(f"{j['name'][:32]:34} {j.get('last_run_at')} {j.get('last_status')} "
             f"{(j.get('last_error') or '').splitlines()[:1]}")
   PY
   ```

   `last_delivery_error` set with `last_status: ok` = the job RAN, only the send
   failed. That is a delivery problem, not an execution one.
2. **Correlate the first failure with a gateway restart.** A restart that changed
   the runtime interpreter breaks every later fire at once:
   `systemctl --user show hermes-gateway -p ExecMainStartTimestamp --value`.
3. **Read the fire record, not the schedule.** `cron external worker exited
   before ownership acknowledgement (exit 1); worker stderr: <traceback>` means
   the worker died at IMPORT: the job's own script never ran and no new file
   appears under `<hermes_home>/cron/output/<job_id>/`. The newest file there
   dates the last fire that really produced output — for a `no_agent` job that
   file IS the deliverable; empty stdout sends nothing by design, so "silent job"
   and "dead worker" look identical from the outside.
4. **Reproduce with the worker's own command.** The worker is spawned as
   `sys.executable -m cron.scheduler` (`cron/scheduler_worker*.py`) — run that,
   from the source tree, with the gateway's environment:

   ```bash
   cd ~/.hermes/hermes-agent
   PYTHONPATH=~/.hermes/hermes-agent <the gateway's interpreter> -m cron.scheduler --help
   ```

   Running the JOB's script by hand proves nothing: it succeeds while the
   scheduler still cannot start a worker.
5. **Gateway imports it, worker does not → compare the two resolution paths.**
   The gateway starts through the `hermes` shim
   (`~/.hermes/hermes-agent/.hermes/bin/hermes` = the bundled
   `tools/python-<v>/bin/python3 -I -c …`, which pops `PYTHONPATH` and inserts
   only the source tree on `sys.path`), while the worker resolves whatever the
   interpreter it is launched with can see — which is not the same set of paths.
   Never assume the user site; enumerate both candidates:

   ```bash
   ls ~/.local/lib/python<X.Y>/site-packages | wc -l   # user site, if it is used
   <interpreter> -c "import <module>; print(<module>.__file__)"   # the bare answer
   ```

   **Where the worker's deps are supposed to come from — usually not the user
   site.** On a self-managed/PM install the interpreter is the managed BASE python
   and its own site-packages holds almost nothing; the dependencies live in the
   selected environment
   (`~/.hermes/installs/*/environments/<hash>/venv/lib/python<X.Y>/site-packages`),
   and the launcher injects that directory into
   `sys.path` in-process (`hermes_bootstrap` →
   `pm.environments.activate_dependencies`). A child that starts as
   `<interpreter> -m <module>` gets none of that: the child-env sanitizer strips
   Hermes-owned site-packages entries and the worker spawn re-pins only the repo
   root, so the worker imports the tree but none of its dependencies. Identify the
   layout before touching anything:

   ```bash
   <interpreter> -c 'import sys; print(sys.executable, sys.prefix)'   # base python?
   <interpreter> -c 'import ruamel.yaml'                              # bare answer: FAIL here
   ls ~/.hermes/installs/*/environments/*/venv/lib/python*/site-packages/ruamel
   ```

   `pip install --user <pkg>` only helps when the deps really are expected in the
   user site; on this layout it duplicates a dependency the runtime already has.
   The requirement is that the worker's interpreter can import the runtime
   dependency environment — fix at the spawn/import path, then prove it with step
   4. **No gateway restart is needed** — every fire spawns a fresh worker; prove it
   end-to-end with one `cronjob_manage action=run` on a cheap job and read its new
   output file.

   **Fix that works without patching core: pin the environment site-packages in
   the interpreter's USER site.** The environment venv is a real Python entry
   point (`bin/python` is a symlink to the managed base python), so running the
   worker as `<env>/venv/bin/python -m cron.scheduler` already works — sys.prefix
   becomes the venv. A `.pth` in the user site reproduces that for the bare
   interpreter every spawn uses:

   ```python
   # ~/.local/lib/python<X.Y>/site-packages/zz-hermes-runtime-deps.pth (one line)
   import json, os, sys; _f = os.path.expanduser('~/.hermes/installs/<id>/facts.json');
   _v = ((json.load(open(_f)).get('packages', {}).get('venv') or {}).get('environment')
         if os.path.isfile(_f) else None);
   _s = _v and os.path.join(_v, 'lib', 'python%d.%d' % sys.version_info[:2], 'site-packages');
   _s and os.path.isdir(_s) and _s not in sys.path and sys.path.append(_s)
   ```

   Read the path out of `facts.json` instead of hard-coding the hash: every
   dependency sync rotates the environment hash. A plain path line goes stale
   silently on the next sync; a managed-python version bump moves the user-site
   directory itself and the file must be recreated there.

## Triage: the job ran, but nothing arrived (delivery)

A delivery failure is recorded as `last_status: delivery_failed` with
`last_delivery_error` set — the run itself succeeded. Check the deliverable on
disk before theorising: `jobs.json` carries the job's `workdir`, and a job that
writes reports has the newest file there. The last successful send is not the last
run, and the last run is not the last send.

`no delivery target resolved for deliver=<platform>` means target RESOLUTION
failed, so nothing was sent (a warning in the log, not a failed run):

1. A bare platform token (`deliver: discord`, no `chat_id`) is a HOME-TARGET
   address, not the conversation the job was created in. Resolution order:
   `<PLATFORM>_HOME_CHANNEL` read through the profile secret scope (i.e. that
   profile's `.env`) → the gateway config's `home_channel` for that platform.
2. The classic cause is a legacy top-level `<PLATFORM>_HOME_CHANNEL: '<id>'` key
   sitting in `config.yaml`. That resolver does not read it, and the config load
   says so:

   ```bash
   hermes config get DISCORD_HOME_CHANNEL
   # (note: DISCORD_HOME_CHANNEL is a stale top-level config.yaml copy; ...)
   ```

   Any home channel configured before the env-routing change can be in this state
   while chat traffic still works — only cron delivery dies.
3. Fix with the supported writer, which lands in `.env`:
   `hermes config set <PLATFORM>_HOME_CHANNEL <chat_id>`.
4. Verify by replaying the tick's own resolution, never by "the config looks right
   now": `scripts/probe_cron_delivery.py` (docstring holds the `--run-module`
   invocation) builds the profile secret scope exactly as the tick does and prints
   the resolved targets. Good output names the chat id with
   `_resolved_from: home`; `NONE` means the send is still dropped. No gateway
   restart is needed — each fire resolves the home target again.
5. **Backfill the missed deliverable by hand — the file on disk IS the delivery.**
   `hermes send` reuses the gateway's platform credentials with no LLM and no
   running gateway:

   ```bash
   hermes send --to <platform> --list          # known chats/topics (ids, no names)
   hermes send --to discord --subject "[Catch-up] <job> <date>" --file <newest output>
   ```

   A bare `--to <platform>` is the home channel; thread/topic targets are
   `platform:chat_id:thread_id`. Long bodies are split by the platform's own limit
   (a 7k-char brief arrives as four messages) and `--json` returns the
   `message_id` of the last chunk. Verify by reading the send BACK from the
   platform — a zero exit code only says the first request was accepted. Recipes
   per platform: `references/delivery-targets.md`.
6. **Prove a fix without disturbing the schedule.** A manual
   `cronjob_manage action=run` does NOT shift `next_run_at`, so firing the affected
   job by hand tests the machinery while the schedule stays where the user put it.
   Prefer it over waiting for the next tick when the user is watching. For
   `no_agent` jobs stdout is the payload, so an empty result is not a failure —
   the receipt is the script's own log or `cron/output/<job_id>/`.

## Pitfalls

- **Never restart the gateway from inside a turn.** The agent runs in that
  process — `systemctl --user restart hermes-gateway` kills the in-flight reply.
  Neither fix in this skill needs a restart (the tick rebuilds the profile secret
  scope per fire, the worker is a fresh process per fire): fix, verify, then offer
  the user a restart.
- **A dependency fix that "obviously" works must be attribution-tested.** Move the
  `.pth` (or whatever was added) away, re-run step 4's worker command, and confirm
  the traceback comes back. A stale environment path from a previous generation can
  sit on `sys.path` and mask the real cause.

- **`last_delivery_error` can name a platform the job never used.** `deliver:
  origin` with no captured origin falls back through every home-target platform in
  table order (`matrix` first), so a job whose `deliver` is `discord`/`telegram`
  can report an unrelated platform's home-room read error. Diagnose from the job's
  own `deliver` value, not from the platform in the message.
- **A dependency or runtime update breaks every bare `-m` entry point first.**
  Gateway and CLI imports are injected in-process by the launcher; cron workers,
  kanban workers and `execute_code` kernels start as
  `<interpreter> -m <module>` and get nothing. After any update or interpreter
  change, run step 4's worker command before trusting any schedule.
- **`VIRTUAL_ENV` in the gateway's environment does not tell you what the worker
  imports.** `sys.executable` is the shim's bundled interpreter, and a venv on
  `PATH`/in `VIRTUAL_ENV` is inherited env, not the resolution path. Ask the
  interpreter, not the environment.
- **Do not restart the gateway to "fix" cron before reading `last_error`.** A
  worker-side import error is an interpreter/dependency problem, and a restart
  does not change which interpreter is used — it only costs downtime (and, on
  this box, reloads every `load-on-startup` model).
- **A moved schedule is not a working schedule.** Verify both: `next_run_at` in
  the store (the move landed) AND `last_status` of one cheap job (the machinery
  runs). A wake-up call that fires on time into a dead worker produces nothing at
  all.
- **After any gateway restart or runtime/interpreter change, sanity-check one
  cheap job's `last_status` before trusting any schedule.** The failure mode is
  every job at once, and for `no_agent` jobs it is invisible outside the store.
- **A Telegram forum topic id is not discoverable by the agent.** The Bot API has
  no list-topics call, and `hermes send --list telegram` prints ids with no names —
  only for topics the bot has already been active in, so a topic the user names may
  not appear at all. Topic names surface only in a message the bot received there
  (`forum_topic_created` in the reply chain). Do NOT call `getUpdates` to
  enumerate: it fights the gateway's long poll and can drop the user's updates.
  Ask for one word posted in that topic (read the thread id off the next inbound
  log line) or the topic link (`t.me/c/<internal>/<id>`), then address it as
  `platform:<chat_id>:<thread_id>`.
- **A `no_agent` script that works in a login shell can still die in cron from
  INHERITED env.** The worker runs inside Hermes's own interpreter and leaks its
  environment into the job. `PYTHONPATH` points at Hermes's site-packages, so a
  script that shells out to a DIFFERENT project's interpreter (`uv run python3 …`,
  an explicit venv `python`) loads Hermes's packages first and breaks on version
  skew — e.g. the worker's py3.14 `cffi` against the project's py3.12
  `_cffi_backend` → `Version mismatch: this is the 'cffi' package version …
  check your installation`. `PATH` is likewise stripped down to system dirs, so
  unqualified binaries 404 (`command not found`, exit 127). Harden every `no_agent`
  script at the top: `unset PYTHONPATH` (when the payload's project does not need
  it) and `export PATH="<absolute dirs>:$PATH"`. Reproduce the failure by running
  the script under the leaked env — a clean login shell does not show it.
