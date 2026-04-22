---
name: xurl-headless-oauth
version: 1.0.0
category: social-media
description: Headless OAuth 2.0 setup for xurl when no browser is available. Manual PKCE flow + known xurl 1.1.0 token storage issues.
tags: [twitter, x, xurl, oauth2, headless, pkce]
---

# xurl Headless OAuth 2.0 Setup

Companion to the `xurl` skill. Use when setting up xurl on a headless machine (no browser) or when `xurl auth oauth2` fails due to port conflicts or token storage bugs.

## Problem

`xurl auth oauth2` tries to: (1) open a browser, (2) bind a local HTTP listener on the redirect URI port. Both fail on headless servers.

## Manual PKCE Flow

### 1. Register app with free port

Check which ports are in use: `ss -tlnp | grep -E '808[0-9]|9999'`

Pick a free port (e.g. 9999) and register:
```bash
xurl auth apps add my-app --client-id CLIENT_ID --client-secret CLIENT_SECRET --redirect-uri https://localhost:FREEPORT/callback
xurl auth default my-app
```

Also set the same redirect URI in the X developer portal.

### 2. Generate PKCE verifier + challenge (Python)

```python
import hashlib, base64, secrets, urllib.parse, json

client_id = "YOUR_CLIENT_ID"
redirect_uri = "https://localhost:9999/callback"
verifier = secrets.token_urlsafe(64)[:128]
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
scopes = "tweet.read users.read bookmark.read like.read offline.access"
state = secrets.token_urlsafe(32)
auth_url = f"https://twitter.com/i/oauth2/authorize?{urllib.parse.urlencode({'response_type':'code','client_id':client_id,'redirect_uri':redirect_uri,'scope':scopes,'state':state,'code_challenge':challenge,'code_challenge_method':'S256'})}"
# Save verifier + state for step 4
with open("/tmp/xurl_pkce.json", "w") as f:
    json.dump({"verifier": verifier, "state": state}, f)
```

### 3. User authorizes on another device

Send the auth URL to the user. They open it, authorize, then copy the full redirect URL from the browser address bar (it'll fail to load but contains `?code=XXX&state=YYY`).

### 4. Exchange code for tokens (Python)

```python
import httpx, json, urllib.parse

with open("/tmp/xurl_pkce.json") as f:
    pkce = json.load(f)

params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(CALLBACK_URL).query))
assert params["state"] == pkce["state"]

# POST to the X OAuth2 token endpoint
# Use grant_type=authorization_code, code, redirect_uri, code_verifier
# Use basic auth with (client_id, client_secret)
# Response contains: access_token, refresh_token, expires_in
```

### 5. Write to ~/.xurl

xurl expects this YAML structure:
```yaml
apps:
  my-app:
    client_id: ...
    client_secret: ...
    redirect_uri: ...
    oauth2_tokens:
      USERNAME:  # fetch via /2/users/me with the access_token
        access_token: ...
        token_secret: ""
        refresh_token: ...
```

Get the username first by calling the X API /2/users/me endpoint with the Bearer token.

### 6. xurl-read wrapper

xurl 1.1.0 has a bug where manually injected tokens show up in `auth status` but still return 401. A wrapper script is at `~/.local/bin/xurl-read` that reads the token from `~/.xurl` YAML and calls the API directly. Use this as the primary read method when xurl commands fail.

## Pitfalls

- **Port 8080 conflict:** llama-server or other services commonly use 8080. Always check before registering.
- **Redirect URI must match exactly** between xurl registration and X developer portal.
- **Consumer key != Client ID:** X dashboard has separate OAuth 1.0a (consumer key/secret) and OAuth 2.0 (client ID/secret) sections. xurl only uses OAuth 2.0 credentials.
- **Token refresh:** OAuth 2.0 tokens expire in 2 hours. The refresh_token can be used to get new access tokens. xurl handles refresh automatically when its internal flow works; for the manual approach, POST to the token endpoint with grant_type=refresh_token.
