---
name: llm-provider-endpoints
description: Add, remove, diagnose LLM providers — Hermes/Kilo creds
---

# LLM provider config (Hermes + Kilo Code)

Three jobs share this skill: changing an EXISTING provider's base URL, ADDING a provider plus its credential env var, and DIAGNOSING a provider that stopped working (read-only: prove which key is in play, then classify why the provider refused it). Do all three against the files the tool actually reads at runtime — not the place that looks right. Each tool resolves endpoint and key from a fixed precedence chain, and several files can contain the string.

Editing these same config files to enable/disable agent tools and verifying config edits (JSONC validation, `debug config`/`debug agent`, fake-provider probe): `references/agent-tool-config.md`.

**Adding a provider: the endpoint is half the job.** The credential env-var NAME is the other half, and each tool has its own required name. Copying a provider into a config without the exact env var yields a provider that lists models but 401s.

## Config-file map (who reads what)

**Kilo Code** — `~/.config/kilo/kilo.jsonc`. A provider's endpoint lives at `provider.<name>.options.baseURL` (the `openrouter` block is the one to change). Add the provider to `enabled_providers` too, or the block is inert. `.kilocode/` and `~/.local/share/kilo` are node_modules/state, not config.

**Kilo Code — required env-var name per provider:** authoritative source is the bundled registry `~/.cache/kilo/models.json`; each provider entry has an `env` array of the var names Kilo reads. Verify there, not from memory. Kilo also accepts `{env:VAR}` templating inside `kilo.jsonc` config values (resolved from `process.env`), which keeps secrets out of the config file. Confirm with `kilo auth list` — it lists detected "Environment" credentials by provider name. For reference: Venice = `VENICE_API_KEY`, npm `venice-ai-sdk-provider`, default baseURL `https://api.venice.ai/api/v1`. Full Kilo config shapes, the verification ladder, and a multi-key probe: `references/kilo-provider-setup.md`.

**Hermes — per profile.** A profile is an independent island (`~/.hermes/` default, `~/.hermes/profiles/<name>/`). An endpoint can be set in any/all of:
- `~/.hermes/<profile>/.env` → `OPENROUTER_BASE_URL` (recognized override, highest in the runtime resolver)
- `~/.hermes/<profile>/config.yaml` → `providers.<name>.base_url` (explicit config; highest precedence)
- `~/.hermes/<profile>/auth.json` → `credential_pool.<provider>[].base_url` (credential store; governs the pool/auxiliary path)

**Hermes — model-provider plugins.** A provider whose profile ships in `~/.hermes/hermes-agent/plugins/model-providers/<name>/__init__.py` (or a user plugin dir) declares its credential in the `ProviderProfile(...)` constructor's `env_vars=(...)` tuple, NOT in config.yaml. The resolver (`hermes_cli/auth.py::_register_plugin_provider`) reads that tuple at load. To centralize one key across clients, point the plugin's `env_vars` at the general var (e.g. `OPENCODE_API_KEY`) rather than a dedicated suffixed one; to change which var it reads, edit the tuple in source (back up first). Grep the plugin file for `env_vars=(...)` to find the real var — a config grep will not surface it.

**Hermes — source default:** `~/.hermes/hermes-agent/hermes_constants.py` defines `OPENROUTER_BASE_URL` as a hard default. Do NOT edit source; it resets on every `hermes update`. Cover it via the config/env/pool overrides instead.

## Hermes endpoint-resolution precedence

`_resolve_openrouter_runtime` in `hermes_cli/runtime_provider_backends.py`: explicit base_url beat `CUSTOM_BASE_URL` beat trusted `model.base_url` beat `OPENROUTER_BASE_URL` (env) beat the `hermes_constants` default.

The auxiliary/compression and credential-pool paths (`agent/auxiliary_client.py`, `agent/credential_pool.py`) read the SOURCE CONSTANT or the auth.json pool entry directly — the env override does NOT reach them. To redirect those, edit the profile's auth.json pool `base_url` (and the aux config's `base_url` if set).

**Which credential is actually in play.** Several env vars can hold DIFFERENT keys of one provider, so never infer the live key from the config file alone. auth.json pool entries carry `secret_fingerprint: sha256:<first 16 hex>`; compare it to the sha256 of each candidate env value to prove which var the client sends, without printing any secret. The canonical var may itself be a shell REFERENCE to a suffixed one (`export VENICE_API_KEY=$VENICE_API_KEY_ex3`), so resolve it before fingerprinting. Recipe plus the full read-only diagnosis ladder: `references/credential-diagnosis.md`.

## Procedure

### ADD a provider (endpoint + credential)

1. Get the endpoint and required env-var name from the tool that will USE it. For Kilo: read `~/.cache/kilo/models.json`, take the provider's `env` array and default baseURL. For Hermes: read the existing `providers.<name>` block in the profile `config.yaml`.
2. Reconcile the env var against what the shell actually exports. Hermes configs may reference a suffixed alias (e.g. `${VENICE_API_KEY_ex2}`) while the tool demands the canonical name - grep `~/.bashrc` and `printenv` for BOTH, and add an alias export when only the suffixed form exists. The canonical name may itself be a shell REFERENCE to a suffixed var (`export VENICE_API_KEY=$VENICE_API_KEY_ex3`) - resolve the value (`bash -c 'source ~/.bashrc; echo $VAR'`) instead of assuming two names mean two keys.
3. Export the canonical name where NON-INTERACTIVE shells see it (see the `.bashrc` guard pitfall). Verify with `bash -c 'source ~/.bashrc; echo $VAR'`.
4. Add the provider block AND append the provider to Kilo's `enabled_providers`; use `{env:VAR}` for `apiKey` and set a `whitelist` of a handful of models (catalogs run to 100+ entries per provider).
5. Prove the credential before declaring done - `kilo auth list` only shows the var is set and `kilo models` only shows the catalog loaded. Run one real completion.

### DIAGNOSE a provider that stopped working (read-only)

1. Fingerprint the credential the client actually sends against every candidate env value (auth.json `secret_fingerprint` vs sha256 of the value).
2. Reproduce it OUTSIDE the client with one `curl` completion. The same failure from bare curl clears the client of blame, and the status code classifies the cause.
3. Read the key's own state — for Venice, `GET /api/v1/api_keys/rate_limits` gives `accessPermitted`, `balances`, `nextEpochBegins`.
4. **When the fault is a field the CLIENT should be sending (an effort/variant picker, a `limit`, a header), capture the wire — do not read the client's bundled code.** A client knob can be cosmetic: the request field is built from the client's own metadata about the model, so a custom model entry it knows nothing about gets NOTHING sent, and the control silently no-ops while the endpoint runs its own default. Run `scripts/api-logging-proxy.py --listen <spare> --upstream <real endpoint> --log ./captured.jsonl`, point a SCRATCH config at the proxy port, drive the client headlessly, read the captured key sets. For Kilo, isolate the scratch config with `XDG_CONFIG_HOME=<scratch>/kilocfg KILO_CONFIG_DIR=<scratch>/kilocfg/kilo XDG_DATA_HOME=<scratch>/kilodata` plus `--pure`, so the user's `kilo.jsonc`, state DB and plugins are untouched; a copy of their config with only the baseURL changed is enough. Prove the same input reaches the endpoint before blaming the client, and poll the client's own `--log-level DEBUG` only as a second resort — it does not print request bodies.
5. Report findings and ASK before repointing a key or editing auth.json. Diagnosis stays read-only; the user decides on config changes.

Field meanings, the response-classification table, and the balance-reading technique: `references/credential-diagnosis.md`.

### CHANGE an endpoint

1. Enumerate every active config that can hold the endpoint. Grep the REAL config files, not caches:
   `grep -rn "<host>" ~/.config/kilo/kilo.jsonc ~/.hermes/.env ~/.hermes/auth.json ~/.hermes/config.yaml ~/.hermes/profiles/*/config.yaml ~/.hermes/profiles/*/.env ~/.hermes/profiles/*/auth.json`
   Caches (`models_dev_cache.json`, `provider_models_cache.json`, `reasoning_caps.json`), sessions/`request_dump_*`, and `hermes-agent/` source regenerate on their own — skip them.
2. Change each real config file. For a Hermes profile: explicit `providers.<name>.base_url` (when pinned) OR `.env` `OPENROUTER_BASE_URL` OR the auth.json pool entry — whichever the profile actually uses; when unsure, set all that exist.
3. Change Kilo's `provider.<name>.options.baseURL`.
4. Preference when asked for "all config": env override for the default profile's runtime resolver, explicit config for a profile that pins the provider, credential_pool entry for the auxiliary path. Never touch the vendored source constant.
5. Verify by anchored grep for the OLD host (see pitfall below), then tell the user to restart the Hermes gateway and start fresh Kilo sessions — `.env` and endpoint config are read at process start. A `model.*` ROUTE change is the one exception: the gateway re-resolves the model route and credentials every turn and rebuilds the cached agent when the route changes (see *POINT a profile at a different provider*), so no restart is needed there.

### POINT a profile at a different provider or model (including a local one)

1. **Target the profile with `-p`, not the env var.** `hermes -p <profile> config get|set` operates on `~/.hermes/profiles/<profile>/config.yaml`; `HERMES_PROFILE=<profile> hermes config path` still prints the DEFAULT home, so a change made that way lands in the wrong profile — check `config path` first if you are unsure which file you are editing.
2. Set the route as three keys and nothing else: `hermes -p <p> config set model.provider <name>`, then `model.default <model>`, then `model.base_url <url>`. Use the CLI rather than a hand edit of the YAML (it validates and bumps `_config_version`), and back the file up first.
3. A `provider: local` route needs no key at all, but the endpoint must serve the exact model id: `curl -s http://localhost:<port>/v1/models` prints what the router accepts. Confirm the model is loaded/servable (`status.value`) and remember the single-entry auto-detect rule in the pitfalls — naming the model explicitly is what makes a multi-model router work. A local llama.cpp router ignores the `Authorization` header, so a dummy key is harmless.
4. Verify in three ascending steps and stop at the first failure: `hermes -p <p> config get model.provider` / `model.default` (config landed) → `hermes -p <p> -z "Reply with exactly: OK"` (credential + endpoint + one real generation through the profile) → `hermes doctor -p <p>` (prints `✓ <profile>: gateway running, <model>` for every profile, which is the fastest way to see the whole fleet's routes at once).
5. **A route change needs no gateway restart; an `.env` change does.** Restart only after the credential file changes, then confirm on the next inbound message in the lane's own log. If a config-only switch still fails, restart the gateway as the fallback.

### REMOVE a model reference and repoint its callers (same endpoint)

A model name sits in several INDEPENDENT wirings, so dropping it from one leaves the rest calling a lane
that no longer exists (those failures show up per call, not at startup). Enumerate before editing:

```bash
grep -rn -i '<model>' ~/.hermes/config.yaml ~/.hermes/profiles/*/config.yaml ~/.hermes/cron/jobs.json
```

Keys that wire a model to an endpoint: `model.default` (with `model.provider` / `model.base_url`),
`providers.<name>.default_model`, `model_aliases.<alias>.{provider,base_url,model}`, `delegation.model`,
`auxiliary.<tool>.model` (one entry PER aux tool — vision, compression, skills_hub, title_generation,
mcp, approval, flush_memories, session_search, web_extract, …), and per-job `"model"` in
`cron/jobs.json` (`null` = inherit). Set the replacement with `hermes [-p <p>] config set <key> <value>`,
and verify the target id is really served at that base_url (`curl -s <base_url>/models`) before pointing
anything at it — a model alias that resolves to an unserved id fails silently at call time.

**"Hermes config is clean" is not "the model is gone".** The lane may still be declared by the SERVER
behind a `local` provider (a llama.cpp router preset, its per-model tuning file). Sweep the serving side
too, in the order and with the verification in `llamacpp-router-preset-ops` →
`references/lane-retirement-sweep.md`, and phrase the report as pending until that server restarts.

Caches and records are not config: `provider_models_cache.json`, `models_dev_cache.json`, `state.db`
(FTS index over every past session), `sessions/`, `logs/`, `backups/`, `state-snapshots/` keep old model
names by design. Leave them and say which ones you left.

## Pitfalls

- **A provider key exported only in `~/.bashrc` never reaches the systemd gateway (`hermes-gateway.service`): daemons don't source .bashrc.** The gateway resolves credentials from the per-profile env file (`~/.hermes/.env`) and auth.json, not the shell. Symptom: CLI sessions work (interactive shell sourced .bashrc) while Telegram/Discord error "No usable credentials found for provider '<name>'. Set <VAR>." Fix: add `<VAR>=<value>` to `~/.hermes/.env`, then `systemctl --user restart hermes-gateway` from a shell OUTSIDE the gateway (the safety guard blocks restarts from inside its process tree). Verify with `env -i HERMES_HOME=~/.hermes ... hermes auth list` — the provider must show the credential; then confirm the key actually completes (a Cloudflare/bare-urllib 403 or a MissingSessionID 400 can be transport artifacts, not key problems — check with the hermes venv's httpx and treat 400-routing as auth-success).
- **A secondary profile's credentials are its own: the default profile's `.env` does not reach it, even under one gateway process.** Symptom: every message in that lane gets the gateway's generic *"I couldn't connect to the AI model service, so this message wasn't processed"* reply with `api_calls=0`, while the lane's own log carries `Model resolution failed for session …: No usable credentials found for provider '<name>'. Set <VAR>.` The named var is authoritative and provider ids map one-to-one to env names — `opencode-go` needs `OPENCODE_GO_API_KEY`, which is a DIFFERENT var from the `OPENCODE_API_KEY` that may sit in the same file (they can even hold the same value; compare lengths/equality without printing the secret to tell a rename from a genuinely absent key). Fix in `~/.hermes/profiles/<p>/.env` and restart the gateway, or point the profile at a keyless local provider. With several profiles on one host, a key present in the default `.env` proves nothing about a secondary lane.
- **Read a secondary lane's log where the profile writes it** (`~/.hermes/profiles/<p>/logs/gateway.log`, plus `agent.log` / `errors.log`) — a multiplexed profile logs its platform traffic and model-resolution failures there, so `journalctl -u hermes-gateway` having no such lines is not evidence the lane is broken. The inbound line (`inbound message: platform=… user=… msg='…'`) followed by the WARNING is the whole diagnosis in two lines.
- **A lane that breaks "suddenly" usually started running its new route at the last gateway restart.** Date the change before hunting a regression: compare the profile `config.yaml` mtime against the gateway's start time (`ps -o lstart= -p $(systemctl --user show hermes-gateway -p MainPID --value)`) and against the last successful reply in the lane's own `gateway.log`. A config written while an older gateway process was already up sits inert — the running process keeps resolving the previous provider from memory — so the first message after the next restart is the first one that can fail, and the gap in the log (quiet hours, then only failures) is an artifact of that restart, not the cause. Check the plugin too: a provider whose `env_vars=(...)` tuple names a DIFFERENT var than the one the profile exports fails exactly this way (see the model-provider-plugin section above).
- **`.bashrc` returns early for non-interactive shells, so exports at the BOTTOM of the file never reach tools.** The default `~/.bashrc` opens with `case $- in *i*) ;; *) return;; esac`, so a `source` from a script, cron, or agent shell stops there. Put any var a tool needs ABOVE that guard. Verify with `bash -c 'source ~/.bashrc; echo $VAR'` (empty = broken); `bash -lc` hides the bug by inheriting the var from the parent login env.
- **Multiple keys for one provider: test each one; do not assume the key referenced in another config is live.** Per-key spend limits do NOT come back as 401: expect a 402 with a JSON `error` body (Venice), or a 200 carrying an error body on some gateways. Either way a dead key still looks configured and fails every call. Probe each candidate with one cheap `curl` chat completion AND read its `balances` (see `references/credential-diagnosis.md`) before pointing the canonical alias at one that returns a real completion.
- **Auth failure is not always 401.** Read the response BODY before concluding the config is wrong; spend limits, tier gating, and region blocks come back 200/403 with a JSON `error` field.
- **A model-name grep across `~/.hermes` returns mostly history.** Live wiring is only `config.yaml`, `profiles/*/config.yaml`, `cron/jobs.json` (plus `auth.json` pools and `.env` for endpoints/credentials); `state.db`, `sessions/`, `logs/`, `backups/`, `state-snapshots/` and skill incident logs hold the name by design. Rewriting those destroys evidence and is not part of "remove the reference" — report the layers you deliberately did not touch.
- **Substring grep false-positive:** `openrouter.ai/api/v1` appears inside `eu.openrouter.ai/api/v1`, so a plain grep for the old URL "matches" files already switched. Anchor the host — `grep -rlnE '([^e]|^)https://openrouter\.ai'` or exclude the new `eu.` prefix — before declaring a file stale. Verify the NEW host is present too.
- **auth.json is a credential store:** `read_file` refuses it (defense-in-depth); read via `grep`/`python3` in terminal. To edit a pool `base_url`, load as JSON, set the field, write a temp file, `os.replace` atomically; back it up first and re-validate JSON after. `json.dump` reformatting is fine — Hermes re-reads structure, not formatting.
- **The source constant silently resets** on `hermes update`, so an endpoint change expressed only in `hermes_constants.py` reverts to the old host on the next update. Express it via `.env`/config/auth.json.
- **Caches claim an old URL but are rebuildable** — a stale `provider_models_cache.json`/`models_dev_cache.json`/`reasoning_caps.json` is not live config; do not blame or edit them.
- **Provider 400s in Hermes silently fall back to a paid OpenRouter model when a router preset name is stale — grep `model ... not found` in agent.log to identify it. This is routing-name drift, separate from endpoint config.
- **A per-key spend cap (Venice 402 `API key DIEM spend limit exceeded`) poisons the credential pool**: the pool sets `last_status: exhausted` / `failure_reason: billing` on the auth.json entry, and every later request logs `credential pool: no available entries` and silently falls back to `fallback_model` (usually OpenRouter). Account credit can be fine while the KEY is capped. Fix: point the provider block at a different working key (`hermes config set providers.<name>.api_key '${VAR}'` — the patch tool refuses Hermes config), then clear the pool entry statuses (backup auth.json, load as JSON, drop `last_status/last_error_*/failure_reason`, atomic `os.replace`). Probe each key first with one cheap curl completion; a 402 here is real, not a transport artifact. The key's REMAINING balance is the authoritative number, not the dashboard's used/allowance counter: read `GET /api/v1/api_keys/rate_limits` → `balances.DIEM` + `accessPermitted`, and re-read it a few minutes apart (a balance that MOVES proves enforcement is live rather than a stale display). Session metadata then keeps showing the fallback provider — only new conversations pick up the new key.
- **OpenCode Go relay (`https://opencode.ai/zen/go/v1`): raw curl/httpx is treated as abuse and returns `MissingSessionID` (400) or `Model is disabled` (401) unless you send a custom `User-Agent` (e.g. `hermes-agent/...`, not an HTTP-library name) AND a stable `x-opencode-session` header per conversation. Add both when probing the relay by hand; otherwise these are transport artifacts, not key/model problems. Vision aux model `deepseek-v4-flash-vision-exp` is reliable and fast on real photos/posters; `mimo-v2.5` intermittently times out (~60s) on larger images. Do NOT use `kimi-k2.6` as a vision/aux model — it returns hard `Model is disabled` (401) on this subscription.
- **Vision aux resolution precedence:** `_configured_aux_model` in `tools/vision_tools.py` reads `auxiliary.<section>.model` from config.yaml FIRST; the `AUXILIARY_VISION_MODEL` env var is only a fallback when config's value is empty. So change the model via `hermes config set auxiliary.vision.model <m>` (read at call time, no gateway restart) — a stale exported `AUXILIARY_VISION_MODEL` env var in your shell is harmless once config is set.
- **A local provider whose `/v1/models` lists more than one entry defeats model auto-detection.** Hermes' `local` provider (and any client that discovers the model name from the endpoint) accepts an auto-detected model ONLY when the list has exactly one entry; against a multi-model router it returns nothing and reports `No model detected on local (<base_url>)` — `_auto_detect_local_model` in `hermes_cli/runtime_provider.py` is where that single-entry rule lives. That is the client's constraint, not an outage: confirm with `curl -s <base_url>/models`, then pass the model explicitly (`/model <name> --provider <p>`), or point the provider at a single-model endpoint — a standalone server on its own port — where auto-detection resolves on its own.
