---
category: mlops
name: router-troubleshooting
description: Fix m5-router.service issues - orphaned INI entries, rogue llama-server processes blocking port 8080
---
# Router Troubleshooting

## When router won't start or GUI shows no models

### Quick diagnostics
```bash
# Check service status
systemctl status m5-router.service

# Find what's on port 8080
lsof -i :8080
```

### Common issues & fixes

**1. Orphaned INI entries (most common)**
The router-preset.ini can accumulate bare filenames without `key = value` pairs.

```bash
# Check for orphan lines
grep -v '^#' /home/cricri/llm-server/router-preset.ini | grep -v '=' | head
```

**Fix:** Remove any line that's just a filename (no equals sign). The router only recognizes `key = value` format.

```bash
# Quick cleanup - remove orphan lines
grep -v '^#' /home/cricri/llm-server/router-preset.ini | grep '=' > ~/router-preset.tmp && mv ~/router-preset.tmp /home/cricri/llm-server/router-preset.ini
```

**2. Rogue llama-server process hogging port 8080**
A standalone server can block the router from binding.

```bash
# Kill all llama-server processes and free port
pkill -f "llama-server" && lsof -ti:8080 | xargs kill -9
```

### Full recovery sequence
```bash
# 1. Stop everything
systemctl stop m5-router.service
lsof -ti:8080 | xargs kill -9

# 2. Fix INI if needed (see above)

# 3. Start fresh
systemctl start m5-router.service
sleep 5
systemctl status m5-router.service
```

### Verification
- Check logs: `journalctl -u m5-router.service -f`
- Router should show all models in GUI on port 8088
- No duplicate processes on port 8080 (only router, not standalone llama-server)

## Notes
- INI file is at `/home/cricri/llm-server/router-preset.ini`
- Only `llama-server --help` flags are valid
- Never add timestamps or extra formatting to INI lines
- The router can load multiple models simultaneously (3+ on 128GB VRAM)

## Prevention
After any manual edits, verify:
```bash
grep -c '=' /home/cricri/llm-server/router-preset.ini  # Should be > 0
```
