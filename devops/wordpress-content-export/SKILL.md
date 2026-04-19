---
name: wordpress-content-export
description: Export all content from a WordPress site via REST API + curl when browser automation is unavailable. Handles cookie auth, nonce extraction, paginated content fetch, media download, and admin settings scraping.
version: 1.0
---

# WordPress Content Export via REST API

Export all content from a WordPress site using curl + REST API when browser automation is unavailable or unreliable.

## When to Use
- Client wants to backup/export WordPress site content
- Need to extract posts, pages, media, settings from a WP site
- Browser automation (Playwright) fails (e.g., Ubuntu 26.04 incompatibility)

## Prerequisites
- WordPress admin credentials (username + password)
- curl installed
- Target site has REST API enabled (default for modern WP)

## Step-by-Step

### 1. Authenticate via Cookie Session

```bash
# Get initial cookies
curl -s -c /tmp/wp-cookies.txt 'https://SITE/wp-login.php' > /dev/null

# Login via POST
curl -s -c /tmp/wp-cookies.txt -b /tmp/wp-cookies.txt \
  -L -D /tmp/wp-login-headers.txt \
  -X POST 'https://SITE/wp-login.php' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Referer: https://SITE/wp-login.php' \
  --data-urlencode 'log=USERNAME' \
  --data-urlencode 'pwd=PASSWORD' \
  --data-urlencode 'wp-submit=Log+In' \
  --data-urlencode 'redirect_to=https://SITE/wp-admin/' \
  --data-urlencode 'testcookie=1' \
  -o /tmp/wp-login-response.html
```

Verify: response should be HTTP 302 redirect to wp-admin, cookies should contain `wordpress_sec_*` and `wordpress_logged_in_*`.

### 2. Extract REST API Nonce

The REST API requires an `X-WP-Nonce` header for authenticated requests. Extract it from the admin dashboard:

```bash
curl -s -L -c /tmp/wp-cookies.txt -b /tmp/wp-cookies.txt \
  'https://SITE/wp-admin/' -o /tmp/wp-admin.html
```

Then parse the nonce:
```python
import re
content = open('/tmp/wp-admin.html').read()
nonce_match = re.search(r'"nonce"\s*:\s*"([^"]+)"', content)
# Or: re.search(r"wpApiSettings\.nonce\s*=\s*'([^']+)'", content)
REST_NONCE = nonce_match.group(1)
```

### 3. Fetch Content via REST API

Use cookie + nonce header together:

```bash
COOKIE="-c /tmp/wp-cookies.txt -b /tmp/wp-cookies.txt"
NONCE="EXTRACTED_NONCE"
BASE="https://SITE/wp-json/wp/v2"

# Paginated fetch (100 per page)
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/posts?per_page=100&context=edit&page=1"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/pages?per_page=100&context=edit&page=1"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/media?per_page=100&page=1"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/categories?per_page=100"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/tags?per_page=100"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/plugins"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/themes"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/settings"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/users?context=edit"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/comments?per_page=100"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/templates?per_page=100&context=edit"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  "$BASE/template-parts?per_page=100&context=edit"
```

Use `context=edit` to get raw HTML content (not just rendered).

### 4. Create Application Password (Optional, for Long-Term Access)

```bash
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" \
  -X POST "$BASE/users/me/application-passwords" \
  -H 'Content-Type: application/json' \
  -d '{"name":"ExportTool"}'
```

Then use Basic Auth: `curl -u 'user:APP_PASSWORD' $BASE/...`

### 5. Download Media Files

```python
import json, os
media = json.load(open('media.json'))
for m in media:
    url = m['source_url']
    fname = os.path.basename(url)
    os.system(f"curl -s -L '{url}' -o 'media/{fname}'")
    # Also download thumbnails from media_details.sizes
    for size_name, size_info in m.get('media_details',{}).get('sizes',{}).items():
        surl = size_info.get('source_url','')
        if surl:
            os.system(f"curl -s -L '{surl}' -o 'media/{os.path.basename(surl)}'")
```

### 6. Scrape Admin Settings Pages

For data not exposed via REST API (customizer, theme options, plugin settings):

```bash
for page in customize.php options-general.php options-reading.php options-permalink.php; do
  curl -s -L $COOKIE "https://SITE/wp-admin/$page" -o "settings/${page%.php}.html"
done
```

### 7. Get All Status Variants

```bash
# Include drafts, trashed, pending
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" "$BASE/posts?per_page=100&status=any"
curl -s $COOKIE -H "X-WP-Nonce: $NONCE" "$BASE/pages?per_page=100&status=any"
```

## Pitfalls

- **Playwright on Ubuntu 26.04**: Broken, use curl instead.
- **REST API + cookies alone**: Returns 401 "not logged in". Must include X-WP-Nonce header.
- **Application Password permissions**: May have limited caps even for admin users. Cookie+nonce is more reliable for `context=edit`.
- **Nonce expiry**: Nonces expire after 12-24 hours. Re-fetch from admin dashboard if they stop working.
- **Large media libraries**: Paginate carefully, download in batches to avoid timeouts.
- **Honeypot plugin (WP Armour)**: Login form may have hidden anti-spam fields. Usually not required for curl-based login but watch for changes.
- **Some endpoints require POST nonce**: The `_wpnonce` hidden field in admin forms differs from the REST nonce. Use REST nonce for API calls, form nonce for admin-ajax.php.
- **Custom post types**: Check `/wp-json/wp/v2/types` for available post types; some plugins register their own.
