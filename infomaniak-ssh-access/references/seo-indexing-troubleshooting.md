# SEO Indexing Troubleshooting for aqfinea.net

## Google Search Console Indexing Issues

When Google Search Console reports indexing problems, diagnose by checking
all URL variants for duplicate content, redirect chains, and noindex signals.

### Diagnostic Procedure

1. **Check all URL variants return 200 or redirect:**
   ```bash
   curl -sI -o /dev/null -w '%{http_code} %{redirect_url}\n' http://aqfinea.net/
   curl -sI -o /dev/null -w '%{http_code} %{redirect_url}\n' https://www.aqfinea.net/
   curl -sI -o /dev/null -w '%{http_code} %{redirect_url}\n' https://aqfinea.net/index.html
   curl -sI -o /dev/null -w '%{http_code} %{redirect_url}\n' https://aqfinea.net/
   ```
   All variants should 301-redirect to `https://aqfinea.net/`.
   If any returns 200 directly, it's a duplicate page.

2. **Check for X-Robots-Tag header (server-level noindex):**
   ```bash
   curl -sI https://aqfinea.net/ | grep -i 'x-robots'
   ```
   No output = no X-Robots-Tag (correct for indexable pages).

3. **Check for meta noindex in HTML:**
   ```bash
   curl -s https://aqfinea.net/ | grep -i 'noindex'
   ```

4. **Verify canonical link tag:**
   ```bash
   curl -s https://aqfinea.net/ | grep 'rel="canonical"'
   ```
   Should output: `<link rel="canonical" href="https://aqfinea.net/">`

5. **Verify robots.txt is not blocking:**
   ```bash
   curl -s https://aqfinea.net/robots.txt
   ```
   Should have `User-agent: *` and `Allow: /`.

6. **Verify sitemap is accessible and correct:**
   ```bash
   curl -s https://aqfinea.net/sitemap.xml
   ```

7. **Check the GSC URL Inspection report** — the "Page d'origine" (origin page)
   field reveals which URL Google actually crawled. This is critical: the
   origin page may be a different URL than the one you submitted (e.g.
   `wp-login.php` instead of `/`), revealing hidden duplicate content sources.

### Common Issues and Fixes

#### "Page en double sans URL canonique sélectionnée" (Duplicate without canonical)
**Cause:** Multiple URL variants (www, http, /index.html) all return 200 OK
with identical content. Google sees duplicates and may not respect the
canonical link tag.

**Fix:** Add 301 redirects in `.htaccess` to collapse all variants to
`https://aqfinea.net/`. See `templates/htaccess-apache.conf`.

#### "Exclue par la balise noindex" (Excluded by noindex)
**Cause:** Either a `<meta name="robots" content="noindex">` tag in HTML,
or an `X-Robots-Tag: noindex` HTTP header. Can also appear as a side-effect
of Google's duplicate handling on non-canonical URL variants.

**Fix:** Remove the noindex tag/header if present. If no noindex is found
in source, the exclusion is likely a duplicate-page side-effect — fixing
the redirect issue (above) resolves both.

#### Dormant WordPress causing both issues (experienced July 2026)
**Symptom:** GSC reports both "duplicate without canonical" AND "excluded by
noindex", but the static `index.html` has a correct canonical tag and no
noindex meta. The GSC URL Inspection "Page d'origine" field shows
`https://aqfinea.net/wp-login.php` instead of `/`.

**Root cause:** A full WordPress installation sits alongside the static site
in the same directory. `wp-login.php` has `<meta name='robots'
content='noindex, noarchive'>` (WP's default for login pages). `/?p=1`
returns 200, creating duplicate content. Google crawls these WP URLs and
flags them.

**Diagnosis:**
```bash
# Check if WP is active
curl -sI https://aqfinea.net/wp-login.php    # 200 = WP is live
curl -s https://aqfinea.net/wp-login.php | grep 'noindex'  # confirms the tag
curl -sI 'https://aqfinea.net/?p=1'          # 200 = WP serving permalinks
```

**Fix — three steps:**

1. **Block WP URLs via .htaccess** (immediate, while WP files still exist):
   ```apache
   RewriteRule ^wp-login\.php$ / [R=301,L]
   RewriteRule ^wp-admin(/.*)?$ / [R=301,L]
   RewriteRule ^wp-signup\.php$ / [R=301,L]
   RewriteRule ^wp-activate\.php$ / [R=301,L]
   RewriteRule ^wp-trackback\.php$ / [R=301,L]
   RewriteRule ^wp-mail\.php$ / [R=301,L]
   RewriteRule ^wp-links-opml\.php$ / [R=301,L]
   RewriteRule ^wp-cron\.php$ / [R=301,L]
   RewriteRule ^xmlrpc\.php$ / [R=301,L]
   RewriteCond %{QUERY_STRING} ^p=[0-9]+
   RewriteRule ^$ /? [R=301,L]
   ```

2. **Update robots.txt** to disallow WP paths:
   ```
   Disallow: /wp-admin/
   Disallow: /wp-login.php
   Disallow: /wp-includes/
   Disallow: /wp-content/
   Disallow: /*.php$
   Disallow: /wp-
   Disallow: /?p=
   ```

3. **Delete the WordPress installation** via SFTP (see script below).

### WordPress Removal Script

Recursive SFTP delete of WP files and directories. `wp-includes/` has
thousands of files — must run as a background process with
`notify_on_complete=True` to avoid 60s timeout.

```python
import paramiko, stat

transport = paramiko.Transport(('lh7t59.ftp.infomaniak.com', 22))
transport.connect(username='[REDACTED]', password='[REDACTED]')
sftp = paramiko.SFTPClient.from_transport(transport)

base = 'sites/aqfinea.net/'

# WP files to remove (flat files in site root)
wp_files = [
    'wp-activate.php', 'wp-blog-header.php', 'wp-comments-post.php',
    'wp-config-sample.php', 'wp-config.php', 'wp-cron.php',
    'wp-links-opml.php', 'wp-load.php', 'wp-login.php',
    'wp-mail.php', 'wp-settings.php', 'wp-signup.php',
    'wp-trackback.php', 'xmlrpc.php', 'index.php',
    'readme.html', 'license.txt',
    '.user.ini', '_index.html', '.infomaniak-maintenance.html',
]

# WP directories (recursive delete)
wp_dirs = ['wp-admin', 'wp-content', 'wp-includes']

def rmdir_recursive(sftp, path, depth=0):
    try:
        entries = sftp.listdir(path)
    except FileNotFoundError:
        return
    for entry in entries:
        full = f"{path}/{entry}"
        try:
            st = sftp.stat(full)
            if stat.S_ISDIR(st.st_mode):
                rmdir_recursive(sftp, full, depth+1)
            else:
                sftp.remove(full)
        except:
            pass
    try:
        sftp.rmdir(path)
    except:
        pass

# Remove files
for f in wp_files:
    try:
        sftp.remove(base + f)
        print(f"deleted {f}")
    except FileNotFoundError:
        pass

# Remove dirs — run as background=True, notify_on_complete=True
for d in wp_dirs:
    print(f"removing {d}/ ...")
    rmdir_recursive(sftp, base + d)
    print(f"deleted {d}/")

sftp.close()
transport.close()
```

**Important:** Split into separate `terminal(background=True)` calls if the
total delete takes over 2-3 minutes. `wp-content` is fast; `wp-includes`
is slow (thousands of files). Run them as separate background jobs.

### Post-Fix Actions

1. Upload `.htaccess` to `sites/aqfinea.net/.htaccess` via SFTP.
2. Verify all redirects with the curl commands above.
3. In Google Search Console: URL Inspection → paste `https://aqfinea.net/` →
   "Request indexing".
4. Resubmit sitemap from Search Console → Sitemaps. GSC may report
   "Aucun sitemap référent détecté" even when sitemap.xml exists — you must
   explicitly submit it in the Sitemaps section.
5. Wait 3-7 days for Google to process redirects and clear duplicate flags.

### Infomaniak-Specific Notes

- Infomaniak uses Apache with `.htaccess` support enabled by default.
- `mod_rewrite` is available; `RewriteEngine On` works without server restart.
- The `.htaccess` file must be uploaded to `sites/aqfinea.net/.htaccess`
  (the site root, not the home directory).
- HSTS is already set by Infomaniak (`strict-transport-security` header),
  so no need to add it in `.htaccess`.
- Infomaniak may install WordPress by default in new hosting accounts —
  always check for dormant WP files when diagnosing SEO issues.
