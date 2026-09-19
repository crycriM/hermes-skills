# WordPress Deployment: Infomaniak Provider Notes

## SSH Access

- Host: `lh7t59.ftp.infomaniak.com`
- User: `[REDACTED]`
- **Pitfall**: SSH password auth is REJECTED. Only SSH key auth is available.
- Command: `ssh [REDACTED]@lh7t59.ftp.infomaniak.com`
- If key auth doesn't work, contact Infomaniak support to add your SSH key

## WordPress REST API

- **Pitfall**: Basic auth with main password is BLOCKED. Use Application Passwords.
- Generate in WP admin: Users → Profile → Application Passwords
- Use with curl: `curl -u "username:app-password" "https://domain.com/wp-json/wp/v2/..."`

## File Locations

- Web root: `/home/[REDACTED]/www/` (via SSH)
- Via FTP: `/www/`

## Browser Automation

- WP admin: `https://aqfinea.net/wp-admin/`
- **Pitfall**: Blank page issue — the page may not load properly in automated browsers
- Try: `page.waitForLoadState('networkidle')` before interactions

## Common Deployment Commands

```bash
# Update page via REST API
curl -X PUT -u "username:app-password" \
  -H "Content-Type: application/json" \
  -d '{"content": "<html>...</html>", "status": "publish"}' \
  "https://domain.com/wp-json/wp/v2/pages/ID"

# Get page IDs
curl -s -u "username:app-password" \
  "https://domain.com/wp-json/wp/v2/pages" | python3 -c "import sys,json; [print(p['id'], p['slug']) for p in json.load(sys.stdin)]"
```