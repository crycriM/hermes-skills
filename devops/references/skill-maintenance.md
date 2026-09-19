# Skill Maintenance

Maintain and update skills — versioning, cleanup, quality checks, and recovery when a bundled skill goes missing.

## Bundled Skill Missing / "skill isn't installed in this profile" Warning

### Symptom

A bundled skill (e.g. `hermes-agent`) is present in the Hermes install directory
(`~/.hermes/hermes-agent/skills/...`) and listed in the sync manifest
(`~/.hermes/skills/.bundled_manifest`), but the live copy under
`~/.hermes/skills/<category>/<name>/` is gone. Sessions warn that the skill
"isn't installed in this profile" even though `hermes update` keeps running.

### Root Cause

The skills sync (`tools/skills_sync.py` in the install dir) treats
**"in manifest but not on disk" as a user deletion** and skips the skill forever
(no re-seed). This is intentional — the curator can prune bundled skills and they
must stay pruned. But it also bites when the on-disk copy disappears for other
reasons (failed update, interrupted copy, manual cleanup), and after an upstream
skill update the manifest hash can be stale, so nothing self-heals.

### Diagnosis

```bash
# 1. Is the bundled source present? (repo copy)
ls ~/.hermes/hermes-agent/skills/autonomous-ai-agents/hermes-agent/

# 2. Is it tracked in the manifest but missing on disk?
grep hermes-agent ~/.hermes/skills/.bundled_manifest
ls ~/.hermes/skills/autonomous-ai-agents/            # copy not here ⇒ missing

# 3. Confirm not curator-archived or suppressed
ls ~/.hermes/skills/.archive/ | grep -i hermes
cat ~/.hermes/skills/.curator_suppressed 2>/dev/null | grep -i hermes
```

### Fix (supported path — no manual file surgery)

```bash
hermes skills reset <name> --restore
```

This drops the stale manifest entry and re-copies the current bundled version,
so future `hermes update` runs track it normally again. Use `--yes` to skip the
confirmation prompt. (`hermes skills reset <name>` without `--restore` only
clears the manifest entry, keeping any user-modified copy.)

### Verification

- Skill directory exists with `SKILL.md` + references/templates
- Manifest hash matches the bundled source exactly:

```python
# md5 over sorted relative paths + file bytes (tools/skills_sync.py _dir_hash)
import hashlib
from pathlib import Path
def dir_hash(d):
    h = hashlib.md5()
    for f in sorted(Path(d).rglob('*')):
        if f.is_file():
            rel = f.relative_to(d)
            h.update(str(rel).encode())
            h.update(f.read_bytes())
    return h.hexdigest()
# compare profile copy vs bundled source — must be equal
```

- `skill_view(name='<skill>')` returns `readiness_status: available`

### Pitfalls

- `hermes skills reset <name> --restore` fails with `bundled_missing` if the
  skill was removed upstream — then the manifest entry is preserved and there's
  nothing to restore.
- Never manually copy the directory without resetting the manifest: the stale
  hash makes the copy look "user-modified", which permanently blocks future
  bundled updates.
- Curator-pruned skills stay pruned: deletion while `curator.prune_builtins`
  is enabled writes `.curator_suppressed`, and re-seeding is correctly skipped.
  If the user actually wants it back, remove its entry from
  `~/.hermes/skills/.curator_suppressed` first, then `hermes skills reset --restore`.
- After a bundled upstream update, the manifest hash is refreshed only when the
  sync runs and the copy exists on disk — a missing copy keeps the stale hash
  (another reason the warning persists across `hermes update` runs).

## Versioning / Cleanup

- Bundled skills: never edit them directly — edits mark them `user-modified`
  and block upstream updates. If you must customize, see
  `hermes skills diff <name>` / `hermes skills reset <name>` for the workflow.
- Local skills: keep one consolidated umbrella skill per domain rather than
  many small overlapping ones (user preference). Merge new content into the
  existing skill and delete the new one.
- After a difficult/iterative skill-debugging session, offer to save the
  procedure as a skill (or merge into an existing one).