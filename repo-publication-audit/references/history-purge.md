# History purge: removing files from a published repo

Companion to §7. Use when a repo is (or was) public and something must stop being retrievable.

## Paths worth purging

Run this first — it lists what is *exposed*, i.e. what the remote actually has, not what the working tree has:

```bash
git ls-files | grep -E '\.db$|\.sqlite$|\.env|\.pem$|\.key$|secret|credential|certs/' 
grep -nE 'PRIVATE KEY|BEGIN RSA|api[_-]?key|secret|password|token' $(git ls-files) | head -40
```

Typical finds: live SQLite databases, `.env`, TLS `key.pem`/`cert.pem` (self-signed or not), webhook URLs, tokens in sample configs. Note that a scan on source files hits a lot of false positives (`webhook_url` as a parameter name); the private-key and database hits are the real ones.

Anything that was a *credential or key still in active use* must be rotated, not merely purged: the purge fixes the future, rotation fixes the past.

## The sequence

```bash
cd <repo>
tar czf ~/backups/<repo>-pre-purge-$(date +%Y%m%d-%H%M).tar.gz -C .. <repo>   # history backup
cp -a <live-data-file> ~/backups/                                            # if a tracked file is live state

git rm --cached <path1> <path2>          # untrack; the files stay on disk
printf '%s\n' '<path-pattern>' >> .gitignore
git add .gitignore && git commit -m "chore: stop tracking <what>"

git filter-repo --path <path1> --path <path2> --invert-paths --force

git remote add origin <url>              # filter-repo removes origin on purpose
git push --force origin main
git branch --set-upstream-to=origin/main main
```

Then confirm the working files that must survive still exist and are unchanged (`md5sum` before and after the rewrite is the cheap proof) — e.g. a live DB the app needs, or the certs nginx loads.

## Verification (always on a fresh clone of the remote)

```bash
git clone --mirror <url> /tmp/mirror && cd /tmp/mirror
git log --all --oneline -- <path1> <path2>        # expect empty
git rev-list --objects --all | grep -cE '<pattern>'   # expect 0
git ls-tree --name-only HEAD                        # expect the paths gone from the tree
```

A clean result here means "not reachable in history". It does NOT mean "gone from GitHub" — see below.

## Residual exposure and what to offer

| Check | Command | Meaning |
| --- | --- | --- |
| Unreachable objects still served | `git fetch origin <old-sha>` in a fresh clone; then `git cat-file -t/-s <blob-sha>` | GitHub keeps unreachable objects; a known SHA still returns the file |
| First real push | `curl -s https://api.github.com/repos/<o>/<r>/events` | first PushEvent date = start of the exposure window |
| Reach | repo JSON `forks_count`, `watchers_count` | whether anyone else could plausibly have a copy |

Options to present, strongest first:

1. **Delete and recreate the repository**, then push the clean history — the only guaranteed result. Needs a credential with admin rights (`gh auth login`, or the web UI).
2. **GitHub Support request** to run GC / drop cached objects on the repo.
3. **Make the repository private** — immediate removal from public view, history unchanged.
4. **Do nothing** — acceptable when the exposure window was short, there are no forks/watchers and the leaked item is rotated anyway. Say the window in hours, not "a while".

Report which option was applied and which remains; never imply the SHA-level copy is gone when only the reachable history was rewritten.

## Safety notes for the rewrite itself

- `filter-repo` needs `--force` on a non-fresh clone and will refuse a dirty tree otherwise; it also rewrites SHAs, so every clone of the repo must be re-cloned or hard-reset afterwards.
- If the dropped path is a *runtime* file (a live DB, an nginx cert), untrack and purge the history, but leave the file on disk and verify the service still runs.
- Do the rewrite before adding new commits you care about, or expect to replay them.
- Commit authors already rewritten by a previous filter-repo stay rewritten; a second pass does not need the `--commit-callback` again.
