---
name: file-metadata-recovery
description: "Use when copy/delete accidents lose file mtimes."
---

# File metadata recovery (lost mtimes after copy/delete)

Goal: recover the date of last modification of original files whose copies were made without timestamp preservation and whose originals were deleted.

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

## 4. Exact values: only inode forensics — usually not worth it
- A deleted file's true mtime survives only in its freed inode on the raw block device. ext4 recovery needs root to read the device; extundelete/debugfs want a quiescent or unmounted filesystem — never run recovery tools against a mounted, actively-written data disk. `debugfs lsdel` only lists files deleted while still open, not ordinary `rm`s.
- Freed inodes get reused quickly on busy disks, so the window is short and success is not guaranteed. For metadata-only recovery (content already safe in the copies), recommend against it: disruption plus no guarantee. Provide the exact root commands only if the user insists, with the risks stated.

## 5. Restoring estimates onto the copies (only after user approval)
- `touch -m -d 'YYYY-MM-DD' <file>` — `-m` limits the change to mtime; content is untouched.
- Set only files with a tight estimate; leave wide-window files at the copy time rather than guess. State that time-of-day is a neutral placeholder; only the date is the estimate.
- Verify afterwards with `stat -c '%y  %n'`: `touch -d` with a naive datetime may store UTC (a requested 18:00 can display as 20:00 +0200). Only stat confirms what landed; day-level correctness is what matters.
- Never write estimated mtimes silently — label exact bounds vs placeholders per file, and apply estimates only after the user approves the per-file plan.
