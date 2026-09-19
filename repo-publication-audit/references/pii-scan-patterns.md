# PII / Secret Scan Patterns

Use these grep patterns for pre-publication audits. Adjust personal identifiers per project.

## Personal Identifiers

Replace the names/IDs with the relevant ones for the project:

```bash
grep -rn 'christian\|marzolin\|ba386b10\|personal-name\|personal-id' . \
  --include='*.html' --include='*.js' --include='*.css' \
  --include='*.md' --include='*.json' --include='*.xml' \
  --include='*.svg' --include='*.yaml' --include='*.yml'
```

## Secrets & API Keys

```bash
grep -rn 'api_key\|API_KEY\|secret\|password\|token' . \
  --include='*.html' --include='*.js' --include='*.css' \
  --include='*.md' --include='*.json' --include='*.yaml' \
  --include='*.yml' --include='*.env'
```

Note: The word "token" often appears in benign context (e.g. "token-cost drift" for LLMs). Always review matches, don't auto-suppress.

## Token-specific patterns

```bash
grep -rn 'ghp_\|xoxb-\|xoxp-\|sk-\|AIza\|AKIA\|aws_' . \
  --include='*.html' --include='*.js' --include='*.css' \
  --include='*.md' --include='*.json' --include='*.yaml' \
  --include='*.yml' --include='*.env' --include='*.py'
```

## JSON-LD sameAs arrays

Common leakage in structured data. Check for personal profile URLs:

```bash
grep -rn '"sameAs"' . --include='*.html' --include='*.json'
```

## Stale email domains

Old content drafts often reference deprecated email domains:

```bash
grep -rn '@example\.com' . --include='*.md' --include='*.html'
```

Replace with the current public email or remove.

## Network Infrastructure PII

Infrastructure details that reveal network topology, device identity, or access credentials. Scan markdown, scripts, config files, and log excerpts.

### Public IPs (hosting providers, VPS, home static)

```bash
grep -rnE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' . --include='*.md' --include='*.py' --include='*.sh' --include='*.yaml' --include='*.yml' --include='*.json'
```

Filter out safe examples: `0.0.0.0`, `127.0.0.1`, `255.255.255.*`, `192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`, example IPs in docs. Anything remaining is a real public IP — redact to `[REDACTED]`.

### Private / Tailscale IPs (RFC1918 + CGNAT)

```bash
grep -rnE '\b(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.)' . --include='*.md' --include='*.py' --include='*.sh' --include='*.yaml'
```

The `100.64.0.0/10` range is Tailscale/CGNAT — reveals mesh membership. Redact all private IPs to `[REDACTED]`.

### MAC addresses

```bash
grep -rnE '\b([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b' . --include='*.md' --include='*.py' --include='*.sh' --include='*.yaml'
```

Filter out `00:00:00:00:00:00` and `ff:ff:ff:ff:ff:ff`. MACs reveal device manufacturers (OUI prefix) and can fingerprint specific hardware. Redact to `[REDACTED]`.

### WiFi SSIDs

```bash
grep -rnE 'SSID.*["\x27][^"\x27]+["\x27]|ssid[_-]?name' . --include='*.md' --include='*.py' --include='*.sh' --include='*.yaml'
```

SSID names are personal identifiers (often the user's name, address, or inside joke). Redact to `[REDACTED]`.

### IPv6 addresses (link-local, ULA, global)

```bash
grep -rnE '[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}' . --include='*.md' --include='*.py' --include='*.sh' --include='*.yaml'
```

`fe80::` (link-local) and `fd00::/8` (ULA) reveal local network topology. Redact to `[REDACTED]`.

### SSH passwords in code

```bash
grep -rnE 'password[=:]["\x27][^"\x27]{6,}["\x27]' . --include='*.md' --include='*.py' --include='*.sh'
```

Replace literal passwords with `[REDACTED]`. Never commit plaintext credentials.
