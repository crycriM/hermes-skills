# Pushing an Existing Project to a New GitHub Repo (no gh, SSH available)

Step-by-step from real session: pushed `numerai-crypto-bot` (6 branches) to a fresh repo.

## Pre-flight checks

```bash
# 1. Verify SSH works for push
ssh -T git@github.com
# Expected: "Hi <user>! You've successfully authenticated..."

# 2. Check for SSH config (custom keys)
cat ~/.ssh/config | grep -A3 "Host github.com"
# Look for IdentityFile — e.g. ~/.ssh/deploy_key

# 3. Get GitHub username
curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user | python3 -c "import sys,json; print(json.load(sys.stdin)['login'])"

# 4. Verify token is real (not a '***' placeholder from .env)
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
# Must be 200. 401 = placeholder or expired.
```

## Step 1: Commit everything locally

```bash
cd /path/to/project
# Check .gitignore covers secrets (.env, credentials)
cat .gitignore | grep -E "\.env|secret|token"
git add -A
git status  # verify .env NOT staged
git commit -m "Initial commit with README"
```

## Step 2: Create empty repo on GitHub

```bash
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user/repos \
  -d '{"name":"repo-name","description":"...","private":false,"has_issues":true,"has_wiki":false}'
```

## Step 3: Push via SSH

```bash
git remote add origin git@github.com:$GH_USER/repo-name.git
# Push all branches at once
git push -u origin --all
```

## Step 4: Fix default branch (if needed)

GitHub creates repos with `main` as default. If your primary branch is `master`:

```bash
# Delete the empty 'main' ref if it exists
git push origin --delete main 2>/dev/null

# Or set 'master' as default via API
curl -s -X PATCH \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$GH_USER/repo-name \
  -d '{"default_branch":"master"}'
```

## Pitfalls

- **Placeholder tokens**: `~/.hermes/.env` may contain `GITHUB_TOKEN=***` — literal obfuscation, not a real token. Always verify with a GET /user call before using.
- **Token goes stale**: Tokens may work for repo creation (POST) but fail for subsequent PATCH calls. Check x-oauth-scopes header to confirm repo+workflow scopes.
- **SSH key not id_rsa**: `ls ~/.ssh/id_*.pub` misses custom-named keys like `deploy_key`. Check `~/.ssh/config` for IdentityFile directives.
- **Don't install gh**: If `gh` isn't available, use git+curl+SSH — do not attempt to download/install it. The user's machine has what it needs.
