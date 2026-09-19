# Model options flow — full code map

Verified 2026-08-25 against `~/.hermes/hermes-agent` (commit a0ca7c1920-era). File/line anchors drift; grep by function name.

## Desktop renderer (Electron, `apps/desktop/src`)

| Concern | File | Notes |
|---|---|---|
| Plain picker dialog | `components/model-picker.tsx` | `ModelPickerDialog` — search + grouped list + prices only. No options. |
| Live catalog menu | `app/shell/model-catalog-menu.tsx` | `ModelCatalogMenu` — provider groups, model families, hover submenu per row. |
| Options submenu | `app/shell/model-edit-submenu.tsx` | `showThinkingToggle = reasoning && canDisableReasoning !== false`. Effort radio `REASONING_EFFORTS` (minimal..ultra); `none` belongs to the Thinking switch, not the radio. |
| Controller | `app/shell/model-menu-panel.tsx` | `patchReasoning`: optimistic UI write, then gateway `config.set {key:'reasoning', session_id, value}`; on error rolls back + `updateFailed` toast. |
| Model pill | `app/chat/composer/model-pill.tsx` | Live menu if `model.modelMenuContent` exists, else opens the dialog. |
| Settings → Model | `app/settings/model-settings.tsx` | Profile default `agent.reasoning_effort` select incl. `none`. Gated by `mainCaps?.reasoning ?? true`. |
| Effort helpers | `lib/reasoning-effort.ts` | `isThinkingEnabled` (effort != 'none'), `resolveReasoningEffort`, `DEFAULT_REASONING_EFFORT = 'medium'`. Backend mirror: `hermes_constants.VALID_REASONING_EFFORTS`. |
| Composer effort store | `store/session.ts` | `COMPOSER_EFFORT_KEY`; `$defaultReasoningEffort` from config. |

## Backend capability computation

- `hermes_cli/inventory.py::_apply_capabilities` — per model row, per provider:
  - `reasoning = bool(get_model_capabilities(slug, model).supports_reasoning)` from models.dev; **defaults True** when unknown or raising.
  - Then, ONLY for aggregators with a reasoning catalog (`_reasoning_catalog_reader`: slugs `nous`, `openrouter`): if catalog says `supports_reasoning: False` → `reasoning = False` (serving route outranks models.dev); elif catalog present → `can_disable_reasoning = not detail.get('mandatory')`.
  - `supported_efforts` is deliberately NOT forwarded (under-reports; Portal honors more).
- Behavior pinned by `tests/hermes_cli/test_inventory_reasoning_caps.py`.

## Gateway write path

- `tui_gateway/server.py`, `config.set` handler, `if key == "reasoning"`:
  - `show/on` / `hide/off` / `full` / `clamp` → display settings (`display.show_reasoning`, `display.sections.thinking`), NOT effort.
  - Anything else → `parse_reasoning_effort(value)`; `None` → 4002 error.
  - Session-scoped write → `session["create_reasoning_override"]`; live agent → `agent.reasoning_config` + `session.info` emit. Global only with `scope=global`/no session → `agent.reasoning_effort` in config.yaml.
- `hermes_constants.parse_reasoning_effort`: `none → {enabled: False}`; `minimal|low|medium|high|xhigh|max|ultra → {enabled: True, effort}`.

## Provider wire translation

- Provider profiles implement `build_api_kwargs_extras(reasoning_config=...)`:
  - `plugins/model-providers/opencode-zen/__init__.py` — OpenCodeGoProfile: GLM-5.2 → top-level `reasoning_effort` (high/max); Kimi K2 → `extra_body.thinking` + `reasoning_effort` but never both; DeepSeek V4 family (deepseek-v4-flash etc.) → `extra_body.thinking={type:enabled|disabled}` or top-level `reasoning_effort`, never both ("cannot specify both 'thinking' and 'reasoning_effort'" HTTP 400 from the relay).
  - `plugins/model-providers/kimi-coding/__init__.py`, `meta-ai`, `ollama-cloud` carry similar per-provider quirks (some reject specific efforts with 400).

## Runtime serving (desktop backend)

- `hermes serve --isolated --host 127.0.0.1 --port 0 --ssh-session-token-file ...` processes per profile; port in `backend.lock.json` next to the token path. Token files are transient (deleted after handoff) → curl 401s. `GET /api/model/options` (hermes_cli/web_server.py) needs that auth; when blocked, reproduce via `inventory.build_model_options_payload(load_picker_context())` in-process.
- Capability payload shape: `providers[].capabilities[model] = {fast, reasoning, can_disable_reasoning?}`.