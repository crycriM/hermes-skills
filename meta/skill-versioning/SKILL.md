---
name: skill-versioning
description: Commit whitelisted skills to git. Use when skills change and need versioning.
version: 1.0.0
category: meta
tags: [git, versioning, whitelist, skills]
---

# Skill Versioning

Commit user-developed skills to git using the whitelist gate. Only whitelisted skills are tracked — bundled/hub skills are excluded.

## When to Use

- After creating or significantly updating a skill
- When asked to "version skills", "commit skills", or "save skills to git"
- Periodically (weekly/monthly) to capture accumulated changes

## How It Works

The whitelist at `~/.hermes/skills/.skill-whitelist` is the gate. Only paths listed there are committed. The whitelist is rebuilt from `hermes curator usage` (agent provenance only) to exclude bundled/hub skills.

## Procedure

1. **Check whitelist integrity**
   ```bash
   cd ~/.hermes/skills
   wc -l .skill-whitelist  # should be ~95 lines
   grep -c "^test-" .skill-whitelist  # should be 0
   ```

2. **Stage whitelisted paths only**
   ```bash
   git add -f $(grep -v '^#' .skill-whitelist | grep -v '^$')
   git add .skill-whitelist .gitignore
   ```

3. **Verify staged content**
   ```bash
   git diff --cached --name-only | wc -l  # count staged files
   git diff --cached --name-only | grep -E "^\.(archive|hub|locks|curator|bundled|usage)"  # should be empty
   ```

4. **Commit with descriptive message**
   ```bash
   git commit -m "skills: update whitelisted skills ($(date +%Y-%m-%d))"
   ```

5. **Push (optional)**
   ```bash
   git push origin main
   ```

## Whitelist Maintenance

The whitelist should be rebuilt when:
- New skills are created
- Skills are archived/deleted
- Bundled/hub skills leak into the whitelist

Rebuild procedure:
```bash
cd ~/.hermes/skills
hermes curator usage 2>&1 | grep "agent" | awk '{print $2}' > /tmp/agent_names.txt
# then map names to paths and rewrite .skill-whitelist
```

## Pitfalls

- **Never use `git add .`** — this stages bundled/hub/curator artifacts
- **Never commit `.curator_*`, `.hub/`, `.archive/`** — these are runtime state
- **Test artifacts** (`test-curator-create` etc.) are not user skills — exclude them
- **Blank lines in whitelist** break the `grep` pipeline — keep it clean
- **Whitelist drift** — if skills are created but not added to whitelist, they won't be versioned

## Integration

- Works with `skill-factory` (auto-generates skills, should add to whitelist)
- Works with `rag-auto-lookup` (versioned skills are searchable in RAG)
- Whitelist source of truth: `hermes curator usage` (agent provenance)

## Verification

After committing:
```bash
git log --oneline -1  # should show your commit
git ls-files | wc -l  # should match whitelist * ~5 files/skill avg
git status  # should be clean (no untracked whitelisted skills)
```
