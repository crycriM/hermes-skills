# Gateway Token Conflict Diagnosis

When multiple Hermes profiles share the same Telegram or Discord bot token, only the first gateway to start claims it. Subsequent gateways log a clear error and skip the platform.

## Diagnosis

### 1. Check which gateways are running

```bash
systemctl --user list-units 'hermes*'
ps aux | grep 'gateway run'
```

Look for multiple `hermes-gateway*.service` units. Each profile has its own unit, typically `hermes-gateway-<profile>.service`.

### 2. Check the journal for conflicts

```bash
journalctl --user -u hermes-gateway --since "5 min ago" --no-pager | grep -i "token already in use"
```

The error is unambiguous:
```
ERROR [Telegram] Telegram bot token already in use (PID <N>). Stop the other gateway first.
```

PID `<N>` points to the gateway that currently holds the token.

### 3. Find which profile owns the winning PID

```bash
ps aux | grep <PID>
```

The command line will show `--profile <name>` if it's a non-default profile.

### 4. Identify where the token is configured

The Telegram/Discord token lives in the profile's **`.env` file**, not `config.yaml`. Check:

```bash
grep -rn 'TELEGRAM_BOT_TOKEN' ~/.hermes/profiles/<profile>/
```

Both profiles pointing to the same bot token is the root cause. Also check the default home:

```bash
grep 'TELEGRAM_BOT_TOKEN' ~/.hermes/.env
```

## Resolution

### Option A: Stop the conflicting profile's gateway (quick fix)

```bash
systemctl --user stop hermes-gateway-<profile>
systemctl --user disable hermes-gateway-<profile>
systemctl --user restart hermes-gateway  # reconnects default
```

### Option B: Remove Telegram from the conflicting profile (permanent)

Remove the Telegram-related lines from the profile's `.env`:

```bash
sed -i '/TELEGRAM/d' ~/.hermes/profiles/<profile>/.env
```

Also strip `platform_toolsets.telegram` if present in `config.yaml` (optional — the real connection is driven by the env var).

Then stop and disable the conflicting gateway service.

### Option C: Use separate bot tokens

Create a second Telegram bot via [@BotFather](https://t.me/BotFather) and give each profile its own token. Both gateways can then run simultaneously.

## Verification

After restarting the gateway, check that the "token already in use" errors are gone:

```bash
systemctl --user restart hermes-gateway
sleep 5
journalctl --user -u hermes-gateway --since "10 seconds ago" --no-pager | grep -i telegram
```

A successful connection shows no errors and the gateway settles with no further output. The health endpoint confirms the gateway is running:

```bash
curl -s http://localhost:8642/health
```

## Notes

- The `platform_toolsets.telegram: []` entry in `config.yaml` controls whether the CLI profile exposes Telegram SEND tools — it does NOT prevent the gateway from connecting to Telegram for message receipt. The actual connection is driven entirely by the presence of `TELEGRAM_BOT_TOKEN` in `.env`.
- The same pattern applies to Discord (`DISCORD_BOT_TOKEN`) and any other platform sharing a bot token between profiles.
- The Discord plugin may also be enabled/disabled in `config.yaml: plugins.enabled/disabled`. A profile that shouldn't have Discord should also have `discord-platform` removed from `plugins.enabled`.
