# Aqfinea Static Site Deployment Recipe

## Quick Deploy Script (paramiko)

```python
import paramiko

FTP_HOST = 'lh7t59.ftp.infomaniak.com'
USER = '[REDACTED]'
PASS = '[REDACTED]'
SITE_ROOT = 'sites/aqfinea.net'

transport = paramiko.Transport((FTP_HOST, 22))
transport.connect(username=USER, password=PASS)
sftp = paramiko.SFTPClient.from_transport(transport)

# Ensure subdirs exist
try:
    sftp.stat(f'{SITE_ROOT}/assets')
except FileNotFoundError:
    sftp.mkdir(f'{SITE_ROOT}/assets')

# Upload files
for local, remote in files:
    sftp.put(local, remote)
    print(f"  Uploaded: {remote}")

sftp.close()
transport.close()
```

## Common Deploy Set

- `index.html` → `sites/aqfinea.net/index.html`
- `styles.css` → `sites/aqfinea.net/styles.css`
- `assets/*.png` → `sites/aqfinea.net/assets/`

When both `index.html` and `styles.css` change (e.g. new CSS classes added), upload both
in a single SFTP session. The SFTP `put` call is per-file; loop over a list if needed.

## paramiko Install

The Hermes venv Python (`/home/cricri/.hermes/hermes-agent/venv/bin/python3`, 3.11)
does NOT have paramiko by default. `pip install --break-system-packages` targets the
system Python (3.14), not the venv Python — so it "succeeds" but paramiko remains
unimportable from terminal() heredocs, which run under the venv interpreter.

Correct fix — install into the venv with uv:

```bash
uv pip install paramiko --python /home/cricri/.hermes/hermes-agent/venv/bin/python3
```

This is a one-time install; the venv persists across sessions.

## Notes

- `terminal()` runs under the Hermes venv Python (3.11), not system Python (3.14).
  Always install Python deps into the venv with `uv pip install ... --python <venv-path>`.
- Do NOT use the server IP directly for SFTP — password auth is rejected there.
