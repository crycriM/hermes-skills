# File actions on a served listing (trash / keep buttons)

The serving side of a page this skill tests: buttons that act on files in a self-hosted
listing get their work done by a server endpoint, not by a generated shell command the
user has to paste. The `devops` skill's `lan-file-serving` reference covers standing up
the server; this file covers the action contract and how to prove the buttons work.

## Design contract — moves only, fixed destinations

- Expose exactly the actions asked for, each with a **fixed destination folder**
  (`trash/`, `keep/`), created lazily on first use. No free-form "move to…" path prompt,
  and no permanent delete unless it is explicitly requested.
- Every action is a **move (`os.rename`), never `unlink`** — the service stays
  non-destructive and every action stays reversible, the same principle as "trash > rm"
  for shell commands. Never describe a reversible move as "permanent" in UI copy.
- One button per destination, disabled while the selection is empty, with the destination
  named in both the confirm dialog and the result message (count + human size + folder).
- **Dot-name the destinations** (`.trash`, `.keep`): this user's standing choice is a clean
  listing, so the folders stay out of it — not promoted to ordinary rows. Dot-naming also
  settles the odd case where a file already sits in its destination: keep the guard
  (refuse rather than duplicate) even though a hidden folder is rarely browsed into.

## Endpoint contract

- `POST <prefix>/__action`, JSON body `{"action": "trash"|"keep", "paths": ["rel", …]}` —
  the client sends **root-relative** paths; never trust a client-supplied absolute path.
- **CSRF guard, mandatory when the service uses Basic auth:** require both
  `Content-Type: application/json` and a custom header (`X-Docs-Action: 1`), and add no CORS
  headers. Browsers attach Basic credentials automatically to cross-origin requests, so
  authentication alone does not stop a hostile page from posting; a JSON content type and a
  custom header cannot both be produced by a cross-origin simple form.
- Reuse the GET auth check (401 through the existing challenge) plus the failed-login
  throttle, and accept the POST with and without the mount prefix.
- Validate each path: refuse absolute paths outright (do not `lstrip('/')` them and carry
  on), refuse `..` segments, require `realpath` containment in the root, require an existing
  regular file (no directories, no symlink resolving outside the root). Cap the batch
  (~500 paths) and the body (~1 MiB) **before** parsing.
- Per-file errors are collected, never fatal: one bad path must not abort the batch. 200 if
  at least one file moved, 400 if none did.
- Collision-safe naming (`name`, `name.1`, …) and refuse a file already in its destination.
- Journal each action to stderr with client IP, count and resolved destination — that log is
  the audit trail.

## Proving it works

- Endpoint: a stdlib `unittest` that boots the same handler in-process on a spare port
  against a `tempfile` root and drives it over real HTTP (`urllib.request`). Cover traversal
  (`../..`, absolute, percent-encoded `..`), a symlink escaping the root, a directory path, a
  missing CSRF header, a wrong content type, an unauthenticated POST, both prefix forms, and
  both caps. Keep the suite **in the project** — a harness in the scratch dir gets pruned.
- **A cap rejection can look like a transport failure.** Refusing on `Content-Length` alone
  (before draining the body) closes the socket, so `urllib` raises
  `URLError: [Errno 32] Broken pipe` instead of `HTTPError 400` — a test that asserts only
  `HTTPError` fails against a correctly-behaving server. Accept either signal and assert the
  side effect (the file is still in place, nothing landed in the destination).
- **Set the handler's attributes with the types its CLI entry point sets.** A harness that
  assigns the root as a plain `str` passes every path join, then dies in the breadcrumb code
  that reads `root.name` — the failure surfaces nowhere near its cause, and looks like a
  server bug. Mirror production (`Path(os.path.realpath(tmp))`).
- **Assert the retired verbs are refused.** After a design change, `delete` / `move` / `rm` /
  an empty action all returning 400 with the file intact is what stops the destructive path
  from quietly returning during a later refactor.
- **Match a hidden folder in the served HTML by its trailing slash.** The picker's hidden
  input holds an absolute path that *ends* with the destination name, so a bare
  `grep '.trash'` matches the input, not a listing row — grep `.trash/` to test visibility.
- UI: the confirm/alert text, the button enable/disable state and the payload are page
  behaviour — click the real controls in a real engine and then check the filesystem
  (file gone from the listing, present in the destination folder).
- A running service holds the **old** code: restart the unit to activate, and remember the
  unit pins its CLI arguments — a flag missing from `ExecStart` is silently absent in
  production.

## Editing a large single-file server safely

- `patch` can join two lines when an anchor spans a line break; run the project's syntax
  check (`python3 -m py_compile <file>`) after every edit to such a file, before going on.
- `write_file` refuses to overwrite a file last read with offset/limit pagination: read the
  whole file first, or edit with `patch`. Reserve a full rewrite for a genuinely new artifact.
- After a design change, grep for the removed symbols (`doDelete`, `allow_delete`, `'move'`):
  stale references survive in docstrings, CLI help, tests and the unit file.
- When the user simplifies the design mid-flight, retire the superseded verbs and their
  tests in the same pass. A suite still exercising a removed action is red — say so plainly
  instead of presenting the change as finished.
