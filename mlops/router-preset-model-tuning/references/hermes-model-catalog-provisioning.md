# Hermes Model Catalog Provisioning

Whitelist models per provider in Hermes so they appear in the model picker (`hermes model`) and can be selected by name.

## Technique: `model_catalog.providers`

The `model_catalog` section in `~/.hermes/config.yaml` fetches available models from a catalog URL. To **add** or **whitelist** specific models per provider, use the `providers` sub-key:

```yaml
model_catalog:
  enabled: true
  url: https://hermes-agent.nousresearch.com/docs/api/model-catalog.json
  ttl_hours: 24
  providers:
    opencode-go:
    - minimax-m3
    - minimax-m2.7
    openrouter:
    - minmax/minimax-m3
```

This ensures those models appear in `hermes model` even if the auto-catalog doesn't include them.

## When needed

- A provider (e.g. OpenCode Go, Custom endpoint) has models that aren't in the central catalog
- You want to restrict the model picker to a curated subset rather than showing all provider models
- Adding models from a custom/local provider that has no catalog entry

## Provider name in `model_catalog.providers`

The key under `providers` must match the provider name as used in Hermes config. Common names:

| Provider | Config key |
|---|---|
| OpenCode Go | `opencode-go` |
| OpenRouter | `openrouter` |
| Custom local | `custom` |
| Anthropic | `anthropic` |
| OpenAI | `openai` |

Check the `provider:` field in `~/.hermes/config.yaml` or run `hermes config show | grep provider` to see active providers.

## Effect

After adding models to `model_catalog.providers`, they appear in:
- `hermes model` interactive picker
- `hermes config set model.default <model>` validation
- The `/v1/models` endpoint on the Hermes gateway

No restart needed for most changes — the catalog is re-read periodically (TTL). To force refresh: `hermes config set model_catalog.ttl_hours 0`, then back to your desired value.
