---
name: infomaniak-ssh-access
description: SFTP/SCP upload to Infomaniak hosting for aqfinea.net via paramiko
---

# Infomaniak SSH / SFTP Access

## Connection Details

- **FTP hostname:** lh7t59.ftp.infomaniak.com (use for SFTP uploads)
- **Server IP:** [REDACTED] (SSH only — hostname times out on SSH)
- **User:** [REDACTED]
- **Password:** [REDACTED]
- **Port:** 22
- **Site root:** `sites/aqfinea.net/`
- **Main page:** `sites/aqfinea.net/index.html` (static HTML, not WordPress)

## Filesystem Layout

- **Home:** `/home/[REDACTED]/`
- **Site root:** `sites/aqfinea.net/`
- **Main HTML:** `sites/aqfinea.net/index.html` (custom static page)
- **WordPress:** REMOVED (July 2026). Was causing GSC indexing issues — wp-login.php
  had `noindex` meta tag, `/?p=1` served duplicate content. All wp-* files, dirs,
  and config deleted. `.htaccess` has 301 rules blocking any residual WP URLs.

## Known Working: SFTP Upload via paramiko Transport

Use `paramiko.Transport` + `SFTPClient.from_transport` against `lh7t59.ftp.infomaniak.com`.
This is the confirmed working method for file uploads.

```python
import paramiko

transport = paramiko.Transport(('lh7t59.ftp.infomaniak.com', 22))
transport.connect(username='[REDACTED]', password='[REDACTED]')
sftp = paramiko.SFTPClient.from_transport(transport)
sftp.put('local/path/file.html', 'sites/aqfinea.net/path/file.html')
sftp.put('projects/aqfinea-website/index.html', 'sites/aqfinea.net/index.html')
print('uploaded')
sftp.close()
transport.close()
```

Note: direct SSH to the server IP with paramiko password auth does NOT work —
the server requires publickey auth on that endpoint. The Transport→SFTP route
on the FTP hostname IS the working method.

## Pitfalls

- **SFTP: use `lh7t59.ftp.infomaniak.com`**. Direct SSH to 185.125.27.130
  rejects password auth (publickey only). The FTP hostname handles SFTP with
  password auth fine.
- **SSH: use the server IP directly** — hostname times out on direct SSH connections.
- **No sshpass available** — use paramiko instead.
- **No root access** — can't apt-get install packages on the server.
- **paramiko not in Hermes venv by default** — `terminal()` runs under the Hermes
  venv Python (`/home/cricri/.hermes/hermes-agent/venv/bin/python3`, 3.11), which
  does NOT include paramiko. `pip install --break-system-packages` targets system
  Python (3.14), not the venv — it "succeeds" but paramiko stays unimportable.
  Fix once: `uv pip install paramiko --python /home/cricri/.hermes/hermes-agent/venv/bin/python3`.
  Then use `terminal` with a Python heredoc: `python3 << 'EOF' ... import paramiko ... EOF`.
- **Recursive SFTP deletes of large dirs timeout at 60s** — `wp-includes/` has
  thousands of files. Use `terminal(background=True, notify_on_complete=True)`
  and a recursive `rmdir` function. Split into separate calls per top-level dir
  if needed. See `references/seo-indexing-troubleshooting.md` for the script.
- Paramiko channel close deallocator AttributeError — harmless, ignore.
- The site is a static HTML site. No WordPress, no PHP framework.
- This is NOT WordPress FTP — no WordPress deployment plugin needed. It's a
  plain SFTP put of static files.

## Linked Files

- `references/aqfinea-website.md` — Website project structure, deploy-verify cycle, design principles, Formspree integration details, section ordering (v5), large HTML restructure technique
- `references/aqfinea-deployment-recipe.md` — Paramiko deploy script pattern for aqfinea.net (quick copy-paste), including correct paramiko install command for the Hermes venv
- `references/seo-indexing-troubleshooting.md` — Google Search Console indexing diagnostics: duplicate page / noindex / canonical URL troubleshooting, curl verification commands, post-fix GSC actions
- `references/static-site-pitfalls.md` — CSS gotchas: `.main-content` z-index wrapper, prefers-reduced-motion, email obfuscation, Formspree AJAX pattern, SVG card sizing
- `references/ai-audit-positioning.md` — AI/LLM audit reframing guideline: integrity vocabulary not MLOps ops, quant↔AI crosswalk, 4×4 mirrored row titles, demoted Production Hygiene footnote, supporting evidence (Kapoor & Narayanan)
- `templates/htaccess-apache.conf` — Ready-to-deploy `.htaccess` with 301 redirects (www→non-www, http→https, /index.html→/), security headers, and static asset caching
- `scripts/verify-structure.py` — Post-edit structural verification: section order (consulting→audit→training), nav links, numbering, tag balance, zebra striping, SVG count, mirrored audit row titles (Quant 4 + AI 4), Production Hygiene footnote check, stale headline check
