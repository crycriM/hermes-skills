# OpenWebUI Follow-up Question Request Flood

Observed 2026-05-31 on step37 (Step-3.7-Flash, 197B, IQ4_XS, port 47219)

## Timeline

| Time | Event |
|------|-------|
| 08:48:13 | Router spawns step37 on port 47219 (loads in ~100s) |
| 08:50:44 | First proxy request to step37 (user task) |
| 08:53:38 | Requests jump to ~5s intervals — OpenWebUI follow-up gen starts |
| 08:55:42 | "→ step37 stream" — user's actual streaming task |
| 08:55:42 – 09:02:19 | ~6.5 min gap — slot 2 generates 5251→7989 tokens |
| 09:02:19–09:04:35 | Two sync requests complete: 1217 tokens (3395 prompt), 1000 tokens (3455 prompt) |
| 09:04:35 | "→ step37 sync" with 3455 prompt tokens — starts the stuck request |
| 09:06:35 | "Proxy error: timed out" — 2 minute timeout hits |
| 09:04:35–09:11:06 | 60 proxy requests to step37 + 36 to qwen35-9b |
| 09:11:06 | "Unloading step37 for swap → qwen35-9b" |
| 09:11:17 | "force-killing model instance name=step37 after 10 seconds timeout" |
| 09:11:17 | "instance name=step37 exited with status 1" |

## Log Signatures

### Model-manager: the sync-after-completion pattern (hallmark of follow-up gen)
```
08:55:41 INFO ◆ step37 reasoning: 3004 chars, 27 lines | tokens: 806 completion, 366 prompt
08:55:42 INFO → step37 stream                          ← user's actual task

09:04:35 INFO ◆ step37 reasoning: 3762 chars, 1 lines | tokens: 1000 completion, 3455 prompt
09:04:35 INFO → step37 sync                             ← OpenWebUI follow-up question request
```

### Model-manager: the swap trigger
```
09:06:35 ERROR Proxy error: timed out
09:11:06 INFO Unloading step37 for swap → qwen35-9b
```

### Router: the force-kill
```
962.29.892.240 I srv        unload: stopping model instance name=step37
962.32.343.742 I srv        unload: stopping model instance name=step37
962.40.344.395 W srv    operator(): force-killing model instance name=step37 after 10 seconds timeout
962.40.693.045 I srv    operator(): instance name=step37 exited with status 1
```

### Router: request flood (99 in 11 min → ~5s intervals)
```
962.07.692.602 I srv  proxy_reques: proxying request to model step37 on port 47219
962.12.685.128 I srv  proxy_reques: proxying request to model step37 on port 47219
962.17.419.445 I srv  proxy_reques: proxying request to model step37 on port 47219
...
```

### Backend slot: stuck generation
```json
{
  "id": 2,
  "is_processing": false,
  "next_token": [{"n_decoded": 7989}]
}
```
And concurrently:
```json
{
  "id": 3,
  "is_processing": true,
  "next_token": [{"n_decoded": 7237, "has_next_token": true}]
}
```

## VRAM at time of crash
```
Total:  536870912  (512MB)
Used:   463810560  (432MB, ~80%)
```

## Prevention
- OpenWebUI: Settings → Interface → uncheck "Show suggested questions after chat response"
- This is a per-browser localStorage setting, not server-side configurable
- The follow-up gen sends a sync request with full conversation history as prompt
