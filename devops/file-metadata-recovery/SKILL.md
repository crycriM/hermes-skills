---
name: file-metadata-recovery
description: "Use when content or metadata vanished after a copy/delete/replace accident."
---

# File state recovery after copy / delete / replace accidents

Two branches, same forensics: recover the *metadata* of files whose mtimes were lost, or recover the *content* of a data file that was silently swapped for an older version.

## 1. Diagnose what actually happened
- Stat the surviving copies: `stat -c '%y  %n' <files>`. If a whole batch shares one nanosecond-close mtime, that instant is the copy time — plain `cp` or a GUI drag-copy overwrote the mtimes. Original values are NOT in the copies; stop looking there.
- Timestamp semantics: `mv` preserves mtime; `cp -p` / `rsync -a` preserve it; plain `cp` and most file-manager copies do NOT. Mixed evidence inside one folder (some files with old per-file mtimes, one batch uniform) shows which entries were moved properly and which were copy+delete accidents.
- The parent directory's mtime records when entries were added/removed — it pins the accident time window, not per-file data.

## 2. Rule out the easy exact sources first
- Git: `git ls-files | grep <name>` AND `git check-ignore <path>`. Gitignored doc trees have zero history; and git never stores mtimes anyway — commit dates only proxy last content change.
- Trash: `ls ~/.local/share/Trash/files`. Also editor swap/backup files and `~/.local/share/recently-used.xbel` (GTK apps log mtimes of opened files).
- Other generations of the same files anywhere on the data mounts: run `find <home> <data> -name '<exact basename>'` per file — a real duplicate may still carry authentic mtimes.

## 3. Reconstruct bounds from stale snapshots + content (the practical answer)
- Look for older bulk-copied archives of the same tree elsewhere on disk (e.g. `proj_private/` sitting next to `proj/`). Their file mtimes are the archive instant, NOT the originals' — but sha256-compare archive content against the surviving copies:
  - content identical to a snapshot dated D => that file's last content edit is ON OR BEFORE D (upper bound);
  - content differs => it was edited after D.
  Two snapshots of different dates narrow each file to a window.
- Mine dates embedded in the documents: "Created/Amended/Last updated" headers, "Reviewed at commit <hash>" lines (resolve the commit date in the repo), internal "as of" references, and dated entries in the project's running status/log file that name the doc.
- Deliver day-level UPPER BOUNDS with explicit confidence ("<= 2026-07-27" vs "window 08-28..09-08"), never fabricated exactness.

## 4. Exact values: inode forensics for METADATA is usually not worth it
- A deleted file's true mtime survives only in its freed inode on the raw block device. ext4 recovery needs root to read the device; extundelete/debugfs want a quiescent or unmounted filesystem — never run recovery tools against a mounted, actively-written data disk. `debugfs lsdel` only lists files deleted while still open, not ordinary `rm`s.
- Freed inodes get reused quickly on busy disks, so the window is short and success is not guaranteed. For *metadata-only* recovery (content already safe in the copies), recommend against it: disruption plus no guarantee. Provide the exact root commands only if the user insists, with the risks stated.
- **Recovering the CONTENT of a small database is a different call — a read-only raw-device carve is cheap, safe, and does work.** It has recovered a 33-row board DB, every text column intact, hours after deletion with the filesystem still in use. Do not tell the user their data is gone in that case; go to §7.

## 5. Restoring estimates onto the copies (only after user approval)
- `touch -m -d 'YYYY-MM-DD' <file>` — `-m` limits the change to mtime; content is untouched.
- Set only files with a tight estimate; leave wide-window files at the copy time rather than guess. State that time-of-day is a neutral placeholder; only the date is the estimate.
- Verify afterwards with `stat -c '%y  %n'`: `touch -d` with a naive datetime may store UTC (a requested 18:00 can display as 20:00 +0200). Only stat confirms what landed; day-level correctness is what matters.
- Never write estimated mtimes silently — label exact bounds vs placeholders per file, and apply estimates only after the user approves the per-file plan.

## 6. When the content itself is reported missing (a data file was replaced)

"My data disappeared" is a file-level question, not an app-level one. Work it in this order.

- **The app's own logs prove nothing.** 200s, sane row counts and a green service only show requests were served — they do not describe which bytes the process is reading. Never answer "no data was lost" from logs.
- **`stat <file>` and read `Birth`, not just `Modify`.** A recent birth time with an old-looking mtime means the file was *recreated* at that instant (`rm`+write, `mv` over the path, temp+rename, an archive-restore copy, `VACUUM`) rather than edited in place — in-place writers (`git checkout`/`restore`, `cp` onto an existing path, truncate) keep the inode and its original birth time. The birth time pins the swap instant; everything between the last known-good snapshot and it is the lost window.
- **Bound the content against every snapshot you already have.** `git show <sha>:<path> > /tmp/x` for each commit touching the file, then compare row sets/queries against the live file. Content identical to commit X proves the live file *is* that snapshot — and that it has been frozen since X, so every later change is gone with the old inode.
- **Look for a still-open inode before writing anything off:** `ls -l /proc/[0-9]*/fd | grep -i deleted`, then `grep -i <name> /proc/[0-9]*/fd`. A process still holding the old file lets you copy it out through `/proc/<pid>/fd/<n>` with no root and no unmount. Check this BEFORE restarting or killing the service that holds the data.
- **Sweep for other copies, and verify each candidate is real:** Trash (`~/.local/share/Trash/files`), sibling backup dirs, cloud mounts — confirm they are actually mounted (`mount | grep <name>`) before trusting a path — plus any sqlite file with the same table anywhere on the data mounts (`find ... -type f -size -20M | while read f; do sqlite3 "$f" ".tables"; done`), git stashes and dangling blobs (`git stash list`, `git fsck --dangling`), and text exports/transcripts that mention known row contents.
- **Report at file level:** the instant the file was replaced, which snapshot its content equals, and the exact window that is unrecoverable. Then offer reconstruction (re-create the missing rows from a list the user provides) as the honest fallback.
- **Prevention that holds:** never `cp` a live SQLite file for backup — a concurrent write yields a torn copy. Use the online-backup API, `sqlite3 live.db ".backup 'snap.db'"`, then check it with `pragma integrity_check` and rotate the snapshots outside the repo. Wire it to a scheduled script whose binaries are absolute-pathed (`/usr/bin/sqlite3`) so a stripped cron PATH cannot break it.
- **Snapshot before you repair:** copy a live data file aside BEFORE any migration, backfill or repair, and keep the copy OUTSIDE the repo — a `.bak` inside the working tree is clobbered by the same git operations you are recovering from. If a migration already ran, say plainly that the pre-migration state exists only in whatever copy was made earlier.
- **Prevention pitfall:** a live SQLite DB tracked in a git working tree is rewritten by any `git checkout` / `git clean` / `git stash` / `git filter-repo` that touches it, and the app then keeps serving the old snapshot with no error anywhere. Keep live data files out of git (gitignore them), and version dumps or copy-based backups instead.

## 7. Carving a deleted database off the raw device (content recovery that works)

A small SQLite file (tens of KB) deleted hours ago is usually still on disk whole — nothing rewrites freed blocks while the filesystem just keeps running. Read-only carve, needs root, ~500 MB/s, so a 1 TB device is ~30 min. Start it early and keep other writes minimal until it finishes.

1. **Check for a still-open inode first** — `ls -l /proc/[0-9]*/fd | grep -i deleted`. A process still holding the file keeps its blocks allocated; copy it out through `/proc/<pid>/fd/<n>` with no root at all. Restarting that service frees the blocks, so do this BEFORE any restart.
2. **One grep pass for headers plus markers** — `sudo grep -a -b -o -E 'SQLite format 3|markerA|markerB' /dev/<part>`. `-b` yields the byte offsets carving needs, and extra patterns cost no extra read. Pick marker strings that exist only in the lost data (row text, URLs, ids); they are the only way to tell the real candidate from the many unrelated databases on the same disk.
3. **Carve from every header** — read `page_size` at header+16 and `page_count` at header+28 (big-endian) for the exact length, copy that many bytes, then validate by opening with sqlite3.
4. **Validate by SCHEMA, never by marker.** Marker strings also live in session stores, chat caches, logs and skill files on the same disk — only a candidate whose `sqlite_master` lists the application's tables is the database. Enumerate every candidate and print its table list.
5. **Damaged candidates** — `sqlite3 broken.db ".recover"` salvages rows from truncated or partly overwritten carves; empty output means those pages were genuinely reused.
6. **Read root-owned carves without sudo** — `sqlite3 "file:carved.db?immutable=1" …`: read-only, and it creates no `-shm`/`-wal` side files next to the carve.
7. **A carve run that looks interrupted may have completed.** An apparent idle shell, an unrelated reboot claim, or a detached process is not evidence the scan died: `ls` the output directory and inspect every `carved-*.db` before concluding the data is lost. Then pick the newest generation by comparing candidates' row counts and per-row content against the last known snapshot, and against any independent log of changes (a webhook/relay log, an app audit trail) to confirm which generation is current.
8. **Restore deliberately** — snapshot the live file, stop the service, remove stale `-wal`/`-shm`, install the recovered file, start, then verify through the application's own API (not just `sqlite3`). A user-scoped unit in `~/.config/systemd/user/` restarts without sudo.

`scripts/carve-sqlite-from-device.sh` runs steps 2-6 in one pass. `references/db-carve-restore.md` holds the candidate triage table, the restore procedure and a backup recipe that cannot produce torn copies.
