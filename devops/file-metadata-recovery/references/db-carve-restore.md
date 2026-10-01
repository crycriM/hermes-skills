# DB carve triage, restore and backup recipe

Companion to §7 of the skill. Use when a database file was deleted or replaced and you are recovering it from the block device.

## Candidate triage

Run `scripts/carve-sqlite-from-device.sh`, then read `report.txt` top to bottom. A real 1 TB scan on a busy laptop disk yields a few dozen candidates; only a handful are databases, and usually just one is the target.

| Candidate signature | What it is | Action |
| --- | --- | --- |
| Tables `Packages`, `Name`, `Basenames`, `Providename` | RPM database (often from inside a container) | ignore |
| Tables `files2` / Chrome-style history tables | browser or tool cache | ignore |
| Tables `sessions`, `messages`, `messages_fts*` | Hermes/other agent session store — contains your own tool output, so it matches app markers by accident | ignore for recovery; useful as an independent record of what the data looked like |
| `strategies`, `fills`, `orders` | some other trading/tool DB | ignore |
| Target app's tables (e.g. `projects`, `tasks`, `subtasks`) | the application database | carve candidate — verify content and pick the generation |

Then pick the generation:

1. `pragma integrity_check` — must return `ok` before you trust a candidate.
2. Row counts and creation timestamps of a few rows, compared against the newest independent evidence of the state (an app webhook/relay log, an audit trail, a snapshot).
3. The newest candidate may legitimately be *missing* rows that an older one has (rows deleted in between) and *have* rows the old one lacks — that is the normal case for a later generation, not corruption. Expect and explain the delta, and offer to re-add anything the user still wants.
4. `sqlite3 broken.db ".recover" | grep "INSERT INTO"` for malformed candidates; no rows out means the pages were reused.

Copy the chosen candidate (and one or two alternates) into the user's backup directory before touching anything live.

## Normalise before installing

```bash
cp carved-<off>.db board-restored.db
sqlite3 board-restored.db "vacuum; pragma integrity_check;"   # rewrites to a clean, exactly-sized file
sqlite3 board-restored.db "pragma foreign_key_check;"        # expect silent
```

Carves are written at a fixed window (often 32 KiB) and can carry trailing slack past the declared page count; the VACUUM normalises that away.

## Restore into a running service

```bash
TS=$(date +%Y%m%d-%H%M%S)
cp -a live.db ~/backups/<app>/pre-restore-$TS.db      # never skip this
systemctl --user stop <app>           # or systemctl stop, if it needs root
rm -f live.db-wal live.db-shm         # stale side files would be replayed over the restored DB
cp restored.db live.db && chmod 664 live.db
systemctl --user start <app>
```

- A unit under `~/.config/systemd/user/` restarts with no sudo. Check with `systemctl --user cat <app>.service` before assuming you need privileged access.
- Verify through the application's own HTTP API, not only with `sqlite3`: query per-parent collections and confirm counts and the field values the user cares about (titles, status/column, descriptions). Both a green service and sane row counts have been true while the app served a stale file, so check the actual payload.
- If an endpoint returns `{"detail":"Method Not Allowed"}`, it is the wrong verb/path — read `/openapi.json` for the real routes instead of guessing.

## Backup recipe that cannot produce torn copies

```bash
#!/usr/bin/env bash
set -euo pipefail
DB="$HOME/projects/<app>/live.db"; DEST="$HOME/backups/<app>"; KEEP=30
SQLITE=/usr/bin/sqlite3                     # absolute path: cron PATH is stripped
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"
"$SQLITE" "$DB" ".backup '$DEST/<app>-$STAMP.db'"
"$SQLITE" "$DEST/<app>-$STAMP.db" "pragma integrity_check;" > /dev/null
echo "<app>-backup: ok ($("$SQLITE" "$DEST/<app>-$STAMP.db" 'select count(*) from <table>;') rows)"
ls -1t "$DEST"/<app>-*.db | tail -n +$((KEEP + 1)) | while read -r old; do rm -f "$old"; done
```

- `cp` on a live SQLite file can capture a torn snapshot; `.backup` uses the online-backup API and is consistent under concurrent writes.
- For a Hermes cron job, the script must live in `~/.hermes/scripts/` and the job's `script` field takes the bare filename — an absolute path is rejected.
- Keep the snapshots out of any git working tree, and verify a snapshot opens (`pragma integrity_check`) rather than trusting the file size.
