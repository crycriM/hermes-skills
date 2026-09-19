The proxy on port 8079 has a ~120s hard timeout on requests. This is
configurable in the model-manager source but defaults tight for safety.
When generating long code or running multi-turn conversations through the
proxy, this timeout can fire as:

```json
{"error": {"message": "timed out", "type": "proxy_error"}}
```

**Workaround:** Bypass the proxy by calling the model's direct llama-server
port (extracted from `/v1/models` status output — look for `--port` in the
`args` array). The direct port has no timeout beyond the llama-server's
built-in limits and `curl --max-time` / `terminal(timeout=...)`.

This is most commonly hit when:
- Using a local model for code generation (long output)
- Running inference with very long prompts
- Using models with thinking/reasoning enabled (generates many hidden tokens)
