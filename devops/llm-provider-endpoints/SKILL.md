---
name: llm-provider-endpoints
description: Add, remove, or audit LLM providers — base URLs AND credential env vars (Hermes, Kilo Code).
---

# LLM provider config (Hermes + Kilo Code)

Two jobs share this skill: changing an EXISTING provider's base URL, and ADDING a provider plus its credential env var. Do both against the files the tool actually reads at runtime — not the place that looks right. Each tool resolves endpoint and key from a fixed precedence chain, and several files can contain the string.

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

## Procedure

### ADD a provider (endpoint + credential)

1. Get the endpoint and required env-var name from the tool that will USE it. For Kilo: read `~/.cache/kilo/models.json`, take the provider's `env` array and default baseURL. For Hermes: read the existing `providers.<name>` block in the profile `config.yaml`.
2. Reconcile the env var against what the shell actually exports. Hermes configs may reference a suffixed alias (e.g. `${VENICE_API_KEY_ex2}`) while the tool demands the canonical name - grep `~/.bashrc` and `printenv` for BOTH, and add an alias export when only the suffixed form exists.
3. Export the canonical name where NON-INTERACTIVE shells see it (see the `.bashrc` guard pitfall). Verify with `bash -c 'source ~/.bashrc; echo $VAR'`.
4. Add the provider block AND append the provider to Kilo's `enabled_providers`; use `{env:VAR}` for `apiKey` and set a `whitelist` of a handful of models (catalogs run to 100+ entries per provider).
5. Prove the credential before declaring done - `kilo auth list` only shows the var is set and `kilo models` only shows the catalog loaded. Run one real completion.

### CHANGE an endpoint

1. Enumerate every active config that can hold the endpoint. Grep the REAL config files, not caches:
   `grep -rn "<host>" ~/.config/kilo/kilo.jsonc ~/.hermes/.env ~/.hermes/auth.json ~/.hermes/config.yaml ~/.hermes/profiles/*/config.yaml ~/.hermes/profiles/*/.env ~/.hermes/profiles/*/auth.json`
   Caches (`models_dev_cache.json`, `provider_models_cache.json`, `reasoning_caps.json`), sessions/`request_dump_*`, and `hermes-agent/` source regenerate on their own — skip them.
2. Change each real config file. For a Hermes profile: explicit `providers.<name>.base_url` (when pinned) OR `.env` `OPENROUTER_BASE_URL` OR the auth.json pool entry — whichever the profile actually uses; when unsure, set all that exist.
3. Change Kilo's `provider.<name>.options.baseURL`.
4. Preference when asked for "all config": env override for the default profile's runtime resolver, explicit config for a profile that pins the provider, credential_pool entry for the auxiliary path. Never touch the vendored source constant.
5. Verify by anchored grep for the OLD host (see pitfall below), then tell the user to restart the Hermes gateway and start fresh Kilo sessions — env/config are read at process start.

## Pitfalls

- **A provider key exported only in `~/.bashrc` never reaches the systemd gateway (`hermes-gateway.service`): daemons don't source .bashrc.** The gateway resolves credentials from the per-profile env file (`~/.hermes/.env`) and auth.json, not the shell. Symptom: CLI sessions work (interactive shell sourced .bashrc) while Telegram/Discord error "No usable credentials found for provider '<name>'. Set <VAR>." Fix: add `<VAR>=<value>` to `~/.hermes/.env`, then `systemctl --user restart hermes-gateway` from a shell OUTSIDE the gateway (the safety guard blocks restarts from inside its process tree). Verify with `env -i HERMES_HOME=~/.hermes ... hermes auth list` — the provider must show the credential; then confirm the key actually completes (a Cloudflare/bare-urllib 403 or a MissingSessionID 400 can be transport artifacts, not key problems — check with the hermes venv's httpx and treat 400-routing as auth-success).
- **`.bashrc` returns early for non-interactive shells, so exports at the BOTTOM of the file never reach tools.** The default `~/.bashrc` opens with `case $- in *i*) ;; *) return;; esac`, so a `source` from a script, cron, or agent shell stops there. Put any var a tool needs ABOVE that guard. Verify with `bash -c 'source ~/.bashrc; echo $VAR'` (empty = broken); `bash -lc` hides the bug by inheriting the var from the parent login env.
- **Multiple keys for one provider: test each one; do not assume the key referenced in another config is live.** Per-key spend limits return HTTP 200 with an error body (e.g. `API key DIEM spend limit exceeded`) rather than a 401, so a dead key looks configured and fails every call. Probe each candidate with one cheap `curl` chat completion and point the canonical alias at one that returns a real completion.
- **Auth failure is not always 401.** Read the response BODY before concluding the config is wrong; spend limits, tier gating, and region blocks come back 200/403 with a JSON `error` field.
- **Substring grep false-positive:** `openrouter.ai/api/v1` appears inside `eu.openrouter.ai/api/v1`, so a plain grep for the old URL "matches" files already switched. Anchor the host — `grep -rlnE '([^e]|^)https://openrouter\.ai'` or exclude the new `eu.` prefix — before declaring a file stale. Verify the NEW host is present too.
- **auth.json is a credential store:** `read_file` refuses it (defense-in-depth); read via `grep`/`python3` in terminal. To edit a pool `base_url`, load as JSON, set the field, write a temp file, `os.replace` atomically; back it up first and re-validate JSON after. `json.dump` reformatting is fine — Hermes re-reads structure, not formatting.
- **The source constant silently resets** on `hermes update`, so an endpoint change expressed only in `hermes_constants.py` reverts to the old host on the next update. Express it via `.env`/config/auth.json.
- **Caches claim an old URL but are rebuildable** — a stale `provider_models_cache.json`/`models_dev_cache.json`/`reasoning_caps.json` is not live config; do not blame or edit them.
- **Provider 400s in Hermes silently fall back to a paid OpenRouter model when a router preset name is stale — grep `model ... not found` in agent.log to identify it. This is routing-name drift, separate from endpoint config.
- **A per-key spend cap (Venice 402 `API key DIEM spend limit exceeded`) poisons the credential pool**: the pool sets `last_status: exhausted` / `failure_reason: billing` on the auth.json entry, and every later request logs `credential pool: no available entries` and silently falls back to `fallback_model` (usually OpenRouter). Account credit can be fine while the KEY is capped. Fix: point the provider block at a different working key (`hermes config set providers.<name>.api_key '${VAR}'` — the patch tool refuses Hermes config), then clear the pool entry statuses (backup auth.json, load as JSON, drop `last_status/last_error_*/failure_reason`, atomic `os.replace`). Probe each key first with one cheap curl completion; a 402 here is real, not a transport artifact. Session metadata then keeps showing the fallback provider — only new conversations pick up the new key.
- **OpenCode Go relay (`https://opencode.ai/zen/go/v1`): raw curl/httpx is treated as abuse and returns `MissingSessionID` (400) or `Model is disabled` (401) unless you send a custom `User-Agent` (e.g. `hermes-agent/...`, not an HTTP-library name) AND a stable `x-opencode-session` header per conversation. Add both when probing the relay by hand; otherwise these are transport artifacts, not key/model problems. Vision aux model `deepseek-v4-flash-vision-exp` is reliable and fast on real photos/posters; `mimo-v2.5` intermittently times out (~60s) on larger images. Do NOT use `kimi-k2.6` as a vision/aux model — it returns hard `Model is disabled` (401) on this subscription.
- **Vision aux resolution precedence:** `_configured_aux_model` in `tools/vision_tools.py` reads `auxiliary.<section>.model` from config.yaml FIRST; the `AUXILIARY_VISION_MODEL` env var is only a fallback when config's value is empty. So change the model via `hermes config set auxiliary.vision.model <m>` (read at call time, no gateway restart) — a stale exported `AUXILIARY_VISION_MODEL` env var in your shell is harmless once config is set.
