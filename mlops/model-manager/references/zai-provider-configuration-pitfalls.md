# Zai Provider Configuration Pitfalls

## Issue: GLM Models Failing While Fallback Works

**Symptom**: Main model (glm-5.1) fails consistently but fallback models work fine.

**Root Cause**: API key configuration mismatch and model name incompatibility.

### Diagnosis Pattern

1. **Check API Key Location**:
   - `config.yaml`: `api_key: ''` (empty)
   - `.env`: `GLM_API_KEY=bdf0ab...NGtM` (actual key)
   - **Fix**: Use environment variable in config.yaml: `api_key: ${GLM_API_KEY}`

2. **Model Name Validation**:
   - Requested model: `glm-5.1` 
   - Provider's default: `glm-5`
   - API error: `{"error":{"code":"401","message":"token expired or incorrect"}}`
   - **Fix**: Use model names that your API key actually supports (often the base model names like `glm-5`, `glm-4.5-air`)

### Verification Steps

```bash
# Test API key directly
curl -s -X POST https://api.z.ai/api/coding/paas/v4/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GLM_API_KEY" \
  -d '{"model": "glm-5", "messages": [{"role": "user", "content": "test"}], "max_tokens": 10}'

# Check fallback provider configuration
grep -A3 -B1 "fallback_providers:" ~/.hermes/config.yaml
```

### Configuration Best Practices

1. **Always validate API keys** with direct curl tests before blaming model names
2. **Use environment variables** for sensitive credentials in config.yaml
3. **Test model names** with your specific API key - some providers return 401 for invalid model names that look valid
4. **Check fallback_providers** for working model names as hints about supported models

### Files to Check

- `~/.hermes/config.yaml` - model configuration
- `~/.hermes/.env` - API keys (GLM_API_KEY)
- Router logs: `journalctl --user -u m5-router.service -f`
- Model manager logs: `journalctl --user -u model-manager -f`