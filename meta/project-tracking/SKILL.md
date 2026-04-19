---
name: project-tracking
description: Maintain a project tracker file for any multi-session, multi-phase project. Prevents context drift between sessions.
version: 1.0.0
metadata:
  hermes:
    tags: [meta, project, tracking, continuity]
---

# Project Tracking

When a conversation involves a multi-phase project (3+ phases, likely spanning sessions), create a project tracker file immediately. Do not wait until asked. Do not assume you'll remember the state next session.

## When to Create

- User outlines a phased plan (Phase 1, Phase 2, etc.)
- Task involves architecture decisions that need to survive across sessions
- Work has dependencies between phases (can't do X before Y)
- User expresses frustration about lost context (that's a signal you're already late)

## Where to Put It

`~/memory-index/<project-name>-tracker.md`

This puts it in the RAG vault so future sessions can find it via search even if memory is full.

## Required Sections

```
# Project Name — Tracker

**Started:** date
**Status:** In progress / Paused / Complete

## Architecture Decisions
What was decided and why. Not what was discussed — what was *decided*.

## Phase Plan
Numbered phases with original numbering. Checkbox per deliverable. Status per phase.

## Session Log
Date + time + what happened. What was tried, what failed, what was deferred. Be honest.

## Known Issues
Current blockers, bugs, things that need fixing before proceeding.

## Next Steps
Ordered list of what to do next. This is your handoff to the next session.
```

## Rules

1. **Create it at the start**, not after the first session ends
2. **Update it during the session** when phases complete or issues surface
3. **Never renumber phases** — keep original numbering even if you implement out of order
4. **Mark what's NOT done**, not just what is — the gaps are what matter
5. **Log failures honestly** — "tried X, failed because Y, deferred" is valuable
6. **Reference the tracker in memory** — add a line pointing to the file location
7. **Read it at the start of every continuation** — session_search the project name, find the tracker, load it before responding

## Why This Exists

Without a tracker, multi-phase projects drift: phases get renumbered, deliverables get skipped, the agent can't reconstruct what was decided vs discussed vs done. Session search is archaeology — a tracker is a living document. The cost of creating it is 2 minutes. The cost of not having it is a confused user and lost hours.
