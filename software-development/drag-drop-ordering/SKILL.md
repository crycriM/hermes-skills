---
name: drag-drop-ordering
description: "Use when drag-drop reordering does not persist in a board."
version: 1.0
---

# Drag-and-drop ordering (web boards and lists)

Trigger: "cards don't update position", reordering looks fine but reverts on reload, a drop
silently does nothing, or a card lands in a column but not where it was dropped.

## Always-on rules

1. **Two fields, not one.** A single `position` integer cannot mean both "which column" and
   "where in the column": make it `status` ('todo'/'doing'/'done') plus `position` = 0-based
   index *inside its own column*. A lone `position` used as a status flag is the classic root
   cause — every card in a column ends up sharing one value, ties break on row id, and any
   reorder is a no-op.
2. **The server owns ordering.** One idempotent endpoint (`PUT /api/<items>/{id}/move` with
   `{status, index}`): exclude the moved item, renumber the target column to `0..n-1`, renumber
   the source column when the status changed, treat `null`/negative/over-range index as append,
   and return the reordered list. Leave the plain update endpoint for titles and deadlines.
3. **Mirror any legacy flag** (`done = status == 'done'`) and translate legacy writes on the way
   in (`done=true -> 'done'`, `done=false -> 'doing' if position>0 else 'todo'`) so webhooks,
   reports and old clients keep working.
4. **New items append** to the end of their column (`position = count(status)`); otherwise every
   new record lands on top of the first one.
5. **Derive new columns exactly once**, gated on a marker (`PRAGMA user_version`, a
   `schema_migrations` row). Re-running the backfill on every boot re-derives `position>0` as
   "in progress" and drags legitimately-ordered items into the wrong column.
6. **The drop index comes from the pointer**, not from the column: compare `clientY` against the
   midpoint of each card, skipping the element currently being dragged, and append when no
   midpoint is passed.
7. **Render grouped by status, sorted by `(position, id)`.** Never rely on `Object.values()` of
   a map keyed by integer id for ordering — integer-like keys enumerate numerically, in id
   order, discarding the order you just persisted.
8. **The insertion indicator must be inert.** Use one persistent indicator with
   `pointer-events: none`, moved only when the target index changes, cleared on `drop`,
   `dragend` and delete-zone drops.
9. Send `dataTransfer.setData('text/plain', id)` in `dragstart` — some browsers will not start
   a drag without it.
10. **Verify on a copy of the production data, with real drags.** Copy the data file, run the
    app on a spare port from a scratch directory, and assert DOM order, API order, and DOM
    order again after a reload. Cover three gestures: onto the top half of a card, onto the
    bottom half, and onto empty column space — the top-half case is where the indicator bug hides.
11. A multi-column board is usually wider than the viewport: widen it before dragging
    (`Emulation.setDeviceMetricsOverride`), because `elementFromPoint` is null off-viewport and
    synthetic mouse events there are silently discarded.

## Procedure

1. **Read the field's real meaning, not its name** — grep the render logic, then query the live
   data: several rows in one column sharing the same `position` value proves it is a flag, not an
   index, and no amount of frontend work will fix it.
2. **Stand up an isolated instance**: copy the data file into a scratch directory, run the app
   there on a spare port, and adjust any relative DB URL. Never experiment against the user's
   live board (and never against a file that is also tracked in git — see the pitfalls).
3. **Write the API contract tests first**: reorder within a column, insert in the middle,
   cross-column move that reindexes the source column, append/`null` index, out-of-range
   clamping, idempotent same-spot move, contiguous `0..n-1` per column, plus legacy
   `done`/`position` compatibility.
4. **Backend**: add the column + marker-gated backfill, add the move endpoint, reuse one
   serialiser for "items of a board" so list order is canonical.
5. **Frontend**: drop-index helper, single indicator, render from the sorted list, and reload the
   board from the API after every move instead of patching the DOM by hand.
6. **Real-browser verification** with `templates/cdp_drag_probe.py` (adapt the config block; run
   it through the browser-harness CLI). It records the drag events and the requests the app
   sends, which is what distinguishes "the drop was refused" from "the handler ran with the
   wrong index".
7. **Report what the user has to do**: a browser hard-reload (JS/CSS are cached), and restarting
   the service is their call when it runs under systemd.

## Pitfalls

- **An indicator that can be hit, or that is recreated on every `dragover`, kills the drop.**
  It becomes the drag target itself, so Chrome never validates the real target and drops are
  swallowed — and only when the pointer happens to sit on the indicator, which makes it look
  intermittent. `pointer-events: none` plus moving the element only when the index changes.
- **No `drop` event in the event log means the drop was refused, not that the logic is wrong.**
  Instrument `dragstart/dragenter/dragover/drop/dragend` (capture phase) and wrap `window.fetch`
  to see what the app actually sent, before touching application code again.
- **Failing drops on the top half of a card, succeeding on the bottom half**, is the signature of
  the indicator pitfall above — not of an off-by-one in the index maths.
- **A live SQLite DB tracked in a git working tree is rewritten by `checkout`/`restore`/`clean`/
  `stash`**, and the app then serves the stale snapshot with no error anywhere. Gitignore live
  data files; version dumps or copy-based backups instead.
- **An already-open tab keeps running the old JS.** After editing frontend files, ask for a hard
  reload before believing a "still broken" report.
