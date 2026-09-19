# Bundled Skill "isn't installed in this profile" — Diagnosis and Repair

Symptom: a warning like "The hermes-agent skill isn't installed in this profile" appears
even though the skill verifiably ships with the Hermes install. `hermes skills list` shows no
entry for it.

## Root cause: bundled skill sync treats missing-on-disk as user-deleted

Hermes bundles skills inside the install tree (repo `skills/<category>/<skill>/`) and syncs
copies into the profile (`~/.hermes/skills/<category>/<skill>/`) using
`~/.hermes/skills/.bundled_manifest`:

```
skill-name:<md5 of skill directory contents>
```

The hash is md5 over each file's relative path + bytes (sorted rglob), NOT a plain file hash
(`tools/skills_sync.py::_dir_hash`).

**The sync NEVER re-seeds a skill whose name is in `.bundled_manifest` but whose directory is
gone.** The loop hits the "In manifest but not on disk — user deleted it" branch and just skips.
So a missing directory (failed update, manual cleanup, etc.) means every subsequent
`hermes update` / gateway startup silently keeps ignoring it, with a stale manifest hash.

Observed case: the `hermes-agent` skill (bundled at `skills/autonomous-ai-agents/hermes-agent/`).
Manifest tracked it, profile copy was gone, and the bundled source had been updated upstream
after the manifest was written.

## Fix: `hermes skills reset <name> --restore`

The supported, no-hand-surgery path:

```bash
hermes skills reset hermes-agent --restore --yes
```

`reset_bundled_skill(name, restore=True)` drops the stale manifest entry, then re-runs the sync,
which re-copies the CURRENT bundled version and records a fresh hash. `--yes` skips the
confirmation prompt (needed for non-interactive use).

Do NOT work around it by copying the directory manually — the manifest hash would be stale and
the skill would be misclassified as user-modified on the next sync. Reset is the clean path.

## Verification

1. Hash parity: profile copy hash must equal bundled source hash, and the manifest entry must
   carry that same hash.
2. Load test: `skill_view(name='hermes-agent')` returns `readiness_status: available`.

Verification snippet (mirrors `_dir_hash`):

```python
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
```

## Related CLI surface

- `hermes skills reset <name>` (no `--restore`) — clears user-modified tracking, keeps your copy.
- `hermes skills list-modified` — bundled skills the user has edited.
- `hermes skills diff <name>` — compare your copy to the bundled version.
- `hermes skills opt-out` / `opt-in` — stop/start bundled-skill seeding for the profile.
- `hermes skills repair-official` — backfills provenance for OPTIONAL skills only
  (`optional-skills/`), NOT regular bundled skills under `skills/`. Use `reset` for those.