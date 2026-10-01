---
name: hermes-messaging-platforms
description: Wire a messaging platform into Hermes (creds, plugin).
metadata:
  hermes:
    tags: [hermes, gateway, messaging, matrix, telegram, discord, plugins]
    related_skills: [hermes-agent, llm-provider-endpoints, devops]
---

# Wiring a messaging platform into Hermes

Applies to any adapter Hermes ships (Telegram, Discord, Matrix, Slack, ~20 more). Four things
must all be true before a platform works: credentials present, adapter plugin enabled, adapter
library installed, gateway restarted. Miss any one and the platform is silently absent.

## Procedure

1. **Credentials are the on-switch.** A platform is enabled by the presence of its keys in
   `~/.hermes/.env` — there is no enable flag. Take the canonical key names from the platform's
   docs page (`hermes-agent.nousresearch.com/docs/user-guide/messaging/<platform>`) or from
   `OPTIONAL_ENV_VARS`, and mirror the shape of a platform that already works (grep `.env` for
   `^<PLATFORM>_`). Under a profile the keys belong in **that profile's** `.env`
   (`profiles/<name>/.env`), and each profile needs its **own** bot account: one credential is
   polled once, so under `gateway.multiplex_profiles` the default profile claims it and the
   secondary's adapter is parked `fatal / duplicate_credential`.

2. **Enable the bundled adapter plugin.** Platform adapters ship as bundled plugins and most are
   disabled by default. `hermes plugins list | grep -i <platform>` →
   `hermes plugins enable <platform>-platform`. Correct credentials will not load a disabled
   plugin.

3. **Install the adapter library into the Hermes venv.** Adapter deps are optional extras, absent
   from a base install. Take the exact pins from `~/.hermes/hermes-agent/pyproject.toml` →
   `[project.optional-dependencies]` → `[<platform>]`, install with
   `uv pip install --python ~/.hermes/hermes-agent/venv/bin/python <pins>`, then prove it imports:
   `~/.hermes/hermes-agent/venv/bin/python -c "import <lib>"`. If an extra needs a system C
   library you do not have (E2EE needs `libolm`), install the plain client instead and note the
   downgrade — a working non-E2EE adapter beats a failed install.

4. **Set behaviour keys with the CLI, never by editing config.yaml.** `config.yaml` is
   write-protected against the agent. Use `hermes config set <dotpath> <value>` and confirm with
   `hermes config get <dotpath>`.
   **Trap:** `hermes config set` writes unrecognized keys anyway, warning only
   (`not a recognized config key — it was saved anyway`). When it suggests another root
   (`session.<platform>.<key>`), that suggestion IS the real path — write there and
   `hermes config unset` the bogus key, or you leave dead config behind.
   Registered platform keys (`MATRIX_HOME_ROOM`, `TELEGRAM_BOT_TOKEN`, …) route to `.env` instead
   of `config.yaml`: `hermes -p <name> config set <KEY> <value>` writes that profile's `.env`, and
   `hermes config unset <KEY>` removes a credential cleanly. Use both rather than hand-editing
   `.env` — it is the one file a stray edit silently changes what the adapter polls, and the
   agent's file tools are guarded away from it anyway.

5. **Restart the gateway deliberately.** The gateway process hosts the running session, so a
   restart kills the turn in flight and the reply with it. Ask the user before restarting a
   service (their standing rule). To restart without cutting your own reply, schedule it
   detached — `systemd-run --user --on-active=25 --collect <hermes> gateway restart` — or hand
   the user the one-liner. Never restart mid-turn and assume the reply still lands. The restart is
   not always required: see *Moving a platform between profiles (multiplexer)* for when it is.

6. **Verify against the external system, not the log.** A log line proves the adapter started,
   not that it works. Read back real state on the platform side (membership, message fetch), then
   confirm one message the bot actually sent.
   **Where the logs actually are:** under `gateway.multiplex_profiles` the host unit
   (`journalctl --user -u hermes-gateway`) only carries the *default* profile's adapters — a
   secondary profile's adapter logs nothing there, and grepping the host journal for the platform
   name returns empty, which reads as "not connected" but is not. The adapter's own lines
   (`<Platform>: using access token…`, `initial sync complete, joined N rooms`) land in
   `~/.hermes/profiles/<name>/logs/agent.log` and `…/logs/gateway.log` (plus `errors.log` for the
   `fatal / duplicate_credential` refusals, which also appear in the host journal from
   `gateway.run`).

7. **Hand off copy-able items as separate messages.** When the user must paste a command, a URL,
   or a password into a client, send it alone in its own message inside a code block — never
   buried in a paragraph alongside other content. This user asks for it explicitly for commands,
   links, and credentials alike.

## Moving a platform between profiles (multiplexer)

One credential is polled once. Under `gateway.multiplex_profiles` the default profile's adapters
connect first and claim each `(platform, credential-hash)`; a secondary reusing the same token is
parked `fatal / duplicate_credential` and stays silent (the log names both profiles). So "this
profile talks on <platform>" means either the profile gets its **own** bot account, or the channel
moves to it wholesale.

1. `hermes -p <name> config set <PLATFORM_KEY> <value>` for every key — a registered platform key
   routes into `profiles/<name>/.env`, never into `config.yaml`.
2. `hermes config unset <KEY>` on the default profile for each key, then confirm with
   `grep -E '^<PLATFORM>_' ~/.hermes/.env` (empty output = gone). Nothing is lost; the secondary's
   `.env` holds the values now.
3. **Restart the gateway — required for this direction.** The hot-rescan watcher reconciles
   *secondary* profiles only (`gateway/run_profile_reconcile.py` filters `n != active`), so the
   default profile's adapter set is a boot snapshot: a credential removed from the default's `.env`
   keeps polling until a restart, and the secondary stays parked as the duplicate until it does.
   A secondary's own `.env` change needs no restart (~30 s rescan).
4. Declare the profile's toolsets for that platform, or its sessions inherit the platform's full
   core bundle:

```yaml
platform_toolsets:
  cli: [terminal, file, vision, web, skills, memory, todo, session_search, clarify]
  matrix: [terminal, file, vision, web, skills, memory, todo, session_search, clarify]
```

   The key is the short platform name (`cli`, `matrix`, `telegram`), not the bundle name
   (`hermes-cli`). `agent.disabled_toolsets` is a separate global suppression list applied last.
5. The handed-over room starts a fresh agent session under the new profile's namespace
   (`agent:<profile>:<platform>:…`); the old profile's session for the same room stays on disk,
   unused. Report that — the user sees the same chat with none of its memory.

## A platform's dependency gate: lazy install is often blocked (pm layout)

A platform plugin declares a pyproject extra (`platforms/matrix/adapter.py::ensure_matrix_deps`
-> `pm.extras.ensure_and_bind("matrix", ...)`); the *only* thing the gate checks is
`pm.available(extra)` = every anchor in `pm/extras.py::ANCHORS[extra]` importable. Which anchors
matter: `ANCHORS["matrix"] = ("mautrix", "asyncpg", "aiosqlite", "markdown", "aiohttp_socks")`.

1. **Check the anchors in the environment the gateway actually boots into, not in
   `~/.hermes/hermes-agent/venv`.** That venv is a stale generation and lies (it held mautrix while
the live env did not). The live one is recorded in
`~/.hermes/installs/<install-id>/facts.json` -> `packages.venv.environment` (+ `extras`), and pushed
onto 3.14 processes by `~/.local/lib/python3.14/site-packages/zz-hermes-runtime-deps.pth`.
2. **A lazy install can be architecturally impossible.** `pm/client.py::sync_venv` refuses a
non-explicit sync when `running_from_selected_environment()` is False — "this process is not
running from the install's dependency environment" — even with
`security.allow_lazy_installs: true`. The gateway runs the tools interpreter + the env's
site-packages, so it is not that env's own interpreter: the lazy path is dead there. The error's
own remedy is the fix: an explicit install.
3. **`[all]` deliberately excludes `[matrix]`** (pyproject), so every venv rebuild silently drops
the matrix deps and the adapter is refused on the next boot. Same class of silence for any extra
excluded from `[all]`: the platform looks configured, the credential is right, and the lane is
simply gone.
4. **Explicit install, with the build fixes when an extra needs a C library.**

```
CMAKE_POLICY_VERSION_MINIMUM=3.5 CXX=g++ CC=gcc hermes pm install --extra matrix
```

   - `python-olm` (pulled by `mautrix[encryption]`) vendors libolm and dies twice on a modern box:
     `CMake Error ... Compatibility with CMake < 3.5 has been removed` (cmake >= 4) and
     `No such file or directory: 'clang++'` (its setup.py hardcodes clang++; only g++ is installed).
     `CMAKE_POLICY_VERSION_MINIMUM=3.5` + `CXX=g++ CC=gcc` cure both; the wheel then builds and
     imports. pm hands the ambient env to its uv build (`pm/environment.py::_base_environment` keeps
everything except `PYTHON*`/`VIRTUAL_ENV`/non-forwarded `UV_*`), so exporting the vars is enough.
     The built wheel lands in the uv cache, so later rebuilds reuse it — a cache prune re-breaks it.
   - E2EE is not a requirement to fix this: `MATRIX_E2EE_MODE=off` on an unencrypted room needs no
     olm, but the extra still installs `mautrix[encryption]`, so the build must succeed anyway.
   - **`hermes pm install` restarts running gateways** (systemd scheduled restart, "restarted on
     client request"). Expect the whole fleet to bounce and every profile's session to drop — do not
     run it mid-conversation expecting otherwise.
5. **Hot rescan retries a failed *creation*, never a failed *reconnect*.**
`_profile_failed_platforms` parks only reconnects, so a platform whose `_create_adapter` returned
None is not skipped by `run_adapters.py::_start_one_profile_adapters` and a rescan re-probes the
(now satisfied) dep gate. Trigger one without touching services: `touch` a secondary profile's
`.env` (metadata only — `profile_serve_signature` = mtime_ns/size/inode/ctime_ns) and wait ~30 s for
`_profile_reconcile_watcher`. Confirm per-profile liveness in `gateway_state.json` under the
**`<profile>:<platform>` key with `writer_pid` == the live gateway PID** — the plain platform row
keeps a dead process's pid and reads "connected" forever.

## Pitfalls

- **A plugin platform's deps live in a per-install environment, not in the repo venv.** Read
  `pm/extras.py::ANCHORS` for the platform's anchor set and check it against
  `installs/<id>/facts.json -> packages.venv.environment`; the repo venv is often a stale generation
  and reports the opposite of the truth. Full dependency-gate procedure above.
- **A client that cannot connect is not necessarily an adapter problem.** Once the adapter is
  verified server-side (adapter lines present, room joined, one message actually sent), and the
  host reaches the service itself, the remaining failure is client-side name/TLS — and a local
  curl through the tailnet URL proves nothing about a remote device, because MagicDNS names are
  answered by tailscaled locally and traffic to the node's own tailnet IP never leaves the host.
  Split it with the tailscaled journal while the user retries:
  `journalctl -u tailscaled -f | grep -E '<client tailnet ip>|handshake'` — no lines means the
  device never resolved the name, `no SNI ServerName` means it dialed the IP, which
  `tailscale serve` cannot serve (it routes by SNI, certificates are valid for the MagicDNS name
  only). Hand clients `https://<magicdns name>`: Element X and other modern clients require https
  with a hostname-matching certificate, so an IP URL can never work for them, while http-tolerant
  clients (Element classic, FluffyChat, Cinny) can talk to the homeserver bound on the tailnet IP.
  Two more traps on that path, both in `references/self-hosted-matrix.md` §6: the coordinator pushes
  clients a split-DNS route for the whole `ts.net.` zone to Tailscale's **public** nameservers,
  which answer NXDOMAIN (authoritatively) for a node name unless Funnel is on — so a lookup that
  leaks there gives the client NXDOMAIN while the host resolves the same name fine; and tailnet
  "Override local DNS" is not the fix, because it does nothing for a client that ignores VPN DNS
  and breaks bare LAN names for every device (`m5:8081` → `m5.lan` → Tailscale → public resolver →
  NXDOMAIN).
- **Prove the sync loop is alive by socket, not by the last log line.** A logging adapter writes
  nothing between events, so "no recent lines" proves nothing. Check that the gateway PID holds an
  ESTABLISHED socket to the homeserver: read `/proc/<gateway pid>/fd` for `socket:[inode]` entries
  and intersect with `/proc/net/tcp`. Two traps: when `MATRIX_HOMESERVER` is the **tailnet HTTPS
  URL** the adapter's socket is on **:443**, not the homeserver's real port, and the sockets you
  see on the homeserver port belong to root/`docker-proxy` port-forward pairs (invisible to
  `ss -p`), so attributing those to the gateway is wrong.
- **A disabled platform plugin is silent.** Symptom: every other platform works, the new one
  produces nothing and logs no error. Check plugin state before debugging credentials.
- **A missing adapter library fails at gateway start** — after the restart you just spent. Import-test
  inside the venv first.
- **A gateway restart kills background processes the agent launched** (tool-managed background
  processes live in the gateway's cgroup). Decide what may die before restarting; anything that
  must survive belongs in a systemd unit or a detached scope.
- **Never persist credentials** (bot password, access token) into memory files, a README, or a
  skill. Record where they live (`.env`, password manager) and tell the user to rotate.
- **"Which platform is uncensored?" is three layers, not one.** Platform moderation, model-provider
  content filtering, and Hermes' own config are independent. Check whether Hermes itself filters
  (`security` / guardrail settings) and whether the refusal came from the model before
  recommending a platform change — changing platforms does not defeat a provider filter.
- **A placeholder in a paste-ready block comes back as a real value.** Printing
  `MATRIX_HOME_ROOM=!<room id>` puts a non-room into `.env`, and that key feeds cron and
  notification delivery. When the real value exists (a room the account is already in), print the
  real value; when it does not, label the line as must-fill instead of leaving an angle-bracket
  placeholder. After the user reports adding credentials, grep for placeholder shapes (`<`, `TODO`,
  `xxx`) before verifying the adapter.
- **Verify an adapter by writer PID, not by the rows in `gateway_state.json`.** That file keeps
  platform rows written by dead processes; a row is live only when `writer_pid ==` the gateway PID
  (readers filter on exactly that). Pair it with the adapter's own lines (`Matrix: using access
  token for @user (device X)`, `initial sync complete, joined N rooms`) and one message the bot
  actually sent.

Self-hosted, moderation-free deployment recipe (own homeserver + Tailscale ingress):
`references/self-hosted-matrix.md`.
