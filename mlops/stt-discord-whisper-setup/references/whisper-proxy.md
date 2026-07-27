# Whisper Post-Processing Proxy

A lightweight FastAPI wrapper that proxies requests to whisper-server and post-processes text responses.

## Architecture

```
Client (Pelemello, curl, etc.)
  → nginx :8444/whisper/ (auth_basic)
    → whisper-proxy :9001
      → whisper-server :9000
```

The proxy only post-processes `/inference` responses. All other paths (root `/`, `/load`, health) pass through transparently.

## Files

| Path | Purpose |
|---|---|
| `~/scripts/whisper-proxy.py` | FastAPI proxy server |
| `~/.config/systemd/user/whisper-proxy.service` | Systemd user service |
| `~/.local/venvs/whisper-proxy/` | Python venv (uv-managed, Python 3.11, deps: fastapi uvicorn httpx) |

## Service management

```bash
systemctl --user start whisper-proxy.service
systemctl --user stop whisper-proxy.service
systemctl --user enable whisper-proxy.service
systemctl --user status whisper-proxy.service
```

Depends on `whisper-server.service` (via `After=` and `Requires=` in the unit file).

## Post-processing rules

Applied in order by `post_process_text()`:

### 1. Filler word → "..."

Regex: `\b[Hh]mm\b`, `\b[Uu]m\b`, `\b[Uu]h\b`, `\b[Oo][Mm]\b`, `\b[Hh]m\b` — all replaced with `...`

These are common whisper mis-transcriptions of verbal hesitations. The user specifically called out "OM" (capital O, capital M) as how "hmmm" gets transcribed.

Examples:
- `"Hmm, let me check"` → `"..., let me check"`
- `"OM that's strange"` → `"... that's strange"`
- `"Um well hmm..."` → `"... well ..."`
- `"Hmm? Are you sure?"` → `"? Are you sure?"` (question mark after filler is preserved)

### 2. Newline collapse

All `\r?\n` sequences within the message body are replaced with a single space. Trailing/leading newlines are stripped.

This prevents whisper from splitting a single utterance across multiple lines.

### 3. Dot cleanup

- `"...."` → `"..."` (when filler already ended with a period)
- `"...?"` → `"?"`, `"...!"` → `"!"` (question/exclamation after filler)

## Adding a new rule

Open `~/scripts/whisper-proxy.py` and add to `post_process_text()`:

```python
def post_process_text(text: str) -> str:
    text = text.strip()
    text = _FILLER_RE.sub("...", text)
    text = _collapse_newlines(text)
    # ↑ existing rules above

    # New rule: pattern → replacement
    text = re.sub(r"some-pattern", r"replacement", text)

    text = re.sub(r"\.\.\.\.+", "...", text)
    text = re.sub(r"\.\.\.([!?;])", r"\1", text)
    return text.strip()
```

Then restart the service: `systemctl --user restart whisper-proxy.service`

## Testing

```bash
# Proxy health check
curl -s http://127.0.0.1:9001/health

# Through nginx (with auth)
curl -sk -u "stt_user:SttWhisper2026!" \
  -F "file=@test.wav;type=audio/wav" \
  -F "temperature=0.0" \
  -F "response_format=text" \
  https://127.0.0.1:8444/whisper/inference

# Direct to proxy (no auth)
curl -s \
  -F "file=@test.wav;type=audio/wav" \
  -F "temperature=0.0" \
  -F "response_format=text" \
  http://127.0.0.1:9001/inference
```
