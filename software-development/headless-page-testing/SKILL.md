---
name: headless-page-testing
description: "Use when testing page JS/DOM without a browser."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Testing, Web-UI, JavaScript, Node, Verification]
    related_skills: [devops, software-development, browser-harness]
---

# Headless page testing

Verify the JavaScript a page actually serves — the artifacts it generates and its DOM
logic — without a browser and without hand-copied fixtures.

## When to Use

- A page feature produces an **artifact**: a shell command to paste, a payload, a config
  blob, a query string, a list of filenames.
- A local/LAN page must be checked and a browser is unavailable or awkward: `browser_exec`
  refuses private addresses, and the Playwright MCP tools are for what a browser alone can
  judge (layout, keystroke handlers, console errors, real click flows).
- The server-rendered markup changed (a column added, an attribute renamed) and the client
  logic has to be proven still correct.

The serving side — systemd user unit, root folder, port choice, basic auth — is documented
in the `devops` skill (its `lan-file-serving` reference). Read that before changing a server
this skill tests.

## Procedure (feature that generates an artifact)

1. Get the script the way the server ships it. When a single-file server embeds its JS/CSS
   as string literals (e.g. `JS = r"""…"""` / `CSS = """…"""` in a stdlib Python
   server), extract **that block from the source file** —
   `src.match(/^JS = r"""([\s\S]*?)"""/m)[1]` — no auth, no HTTP, and drift is
   impossible. Otherwise fetch the real page with the same auth a browser uses:
   `curl -s -u "$USER:$PASS" http://127.0.0.1:<port>/ -o page.html` and extract
   `html.match(/<script>([\s\S]*?)<\/script>/)[1]`.
2. When you extract from source, regex the same source for the invariants the page relies
   on (a CSS selector, the server-side default-sort expression) and assert them in the
   harness: one `node harness.js` run then covers the markup/CSS contract and the client
   logic together, and exiting non-zero makes it usable as a gate.
3. Build the stub DOM from the page's **own** values: parse the `data-*` attributes out of
   `page.html` (undoing the server's HTML escaping) so the harness runs on the real path
   set, sizes and order.
4. `eval(js)`, call the page's update function, capture the artifact (read the textarea
   `.value` / the payload variable).
5. Write the artifact to a file, run it **verbatim** in a scratch sandbox, and diff the
   result. Run the real thing only if that is what you mean to do.
6. Check the cheap invariants on the live instance: element count vs
   `find <root> -maxdepth 1 -type f | wc -l`, page title/breadcrumb label, one asset fetch
   with its content type, and the 401-without / 200-with auth pair.

`scripts/page_command_harness.js` does steps 1-5 for checkbox-driven command generation:
`node scripts/page_command_harness.js page.html tick.json out.sh` prints the generated
command and saves it. Rename the ids inside for a page with a different contract.

## Rules

- **Test the served script, not a copy of it.** Extract it from the fetched HTML on every
  run; hand-copied JS drifts from what ships and then certifies nothing.
- **Fixtures come from the page.** Real `data-*` values expose server-side escaping bugs
  (entity-escaped apostrophes, percent-encoded names) that invented filenames hide.
- **Assert the artifact's effect in the shell, not the DOM.** "Only the selected files are
  gone, the decoys survive" is the claim; no DOM assertion covers it.
- **Seed the sandbox with hostile inputs:** spaces, an apostrophe, accents, a name starting
  with `-`, a large file, and untouched decoy files. This is what proves the quoting.
- **Cover both clipboard branches** when the feature has a Copy button: with and without
  `navigator.clipboard` (see the reference).
- **Prove a control's refusal paths before its success path.** For a service-backed button
  the side-effect-free probes are: an invalid parameter → 400 listing the accepted values,
  an action already in effect → 200 no-op, a closed gate → 409 naming the blocker. Each
  leaves the running service alone and together they prove routing, validation and gating.
  Pressing the button for real is the last step, and the proof is the service's own state
  (its `/health` fields), not the HTTP status you got back.
- **A control must not be able to act on a service that is mid-work.** Expose the busy state
  in the status the page reads and have the refusing side be the gate, not your memory: a
  restart/replace path runs while a request is in flight it truncates that request, and the
  page has no way to know. Check the service before the first attempt too — idle-looking is
  not idle.
- **Re-run the harness after any markup change.** Adding a column to a table whose JS sorts
  or filters on `cells[i]` breaks it silently: route every access through one offset helper
  (`function off(){return document.querySelector('th.pick')?1:0}`), keep the header
  `onclick` index logical, and re-check that sorting still reorders and the filter still
  hides rows.
- **Derive a cell's sort type from the cell, never from a positional table.**
  `k = ['n','n','s','d'][j]` mis-sorts silently the moment a column is added or appears
  conditionally (a pick checkbox shifts every index), and no assertion notices: sizes then
  compare as strings (`"10 KB" < "2 KB"`). Emit `data-t="s|n|d"` on each cell, read it off
  `rows[0].cells[j]`, and key the persisted sort state the same way.

## When only a real engine can answer

The stub DOM proves logic; it cannot see layout, and a screenshot proves nothing to a
text-only reader. Measure instead, in headless Chromium (`mcp__playwright__browser_*`):

- **Wrapped lines** — the failure that reads as "too much spacing":
  `const r = document.createRange(); r.selectNodeContents(cell); r.getClientRects().length`
  is the number of line boxes. Assert `1`, do not eyeball it.
- **Density** — `row.offsetHeight`, and `[...new Set(rows.map(r => r.offsetHeight))]` (a
  one-element set proves the rows are uniform) checked against the padding/font you set.
- **Clipping instead of widening** — set an over-long synthetic value on the element, then
  require `el.scrollWidth > el.clientWidth` while `table.offsetWidth` and
  `document.documentElement.scrollWidth` stay unchanged; read back
  `getComputedStyle(el).textOverflow === 'ellipsis'`.
- **Interaction order** — click the real headers (`th.click()`) and, in the same
  evaluation, read the resulting row order, the marker class and the persisted sort state;
  assert monotonicity (`a.every((v,i) => !i || a[i-1] >= v)`) rather than naming rows.
- **Re-measure at a narrow viewport** (`browser_resize`): a column usually only wraps under
  pressure, so the wide-viewport pass is the one that lies.
- One expression per `browser_evaluate`, and never `location.reload()` inside it — the
  context is destroyed; navigate, then evaluate.

**Auth-protected page:** start a throwaway duplicate of the same server with auth disabled
on a spare port (`--no-auth --bind 127.0.0.1 --port <free>`), point the browser at that, and
keep the real password out of the tool call. Launch it with the terminal tool's
`background=true` (shell-level `&`/`nohup` is refused) and kill it through the process
manager afterwards. Serve the same root so the listing is real data, not a fixture.

**After editing a page's JS/CSS, first establish which deployment shape you have.** If the
HTML is read from disk per request, the edit is live on the next fetch and no restart is
needed; if the block is embedded in the service's own code, restart the unit
(`systemctl --user restart <unit>`) — a service holding the old block serves the old page.
Either way verify on the SERVED page, not the source: fetch it and grep for **both** the new
element id and the new handler call site (`grep -o "toggleX('[a-z]*')"`), because a button
whose `onclick` still calls the old signature is a half-deploy that renders perfectly — plus
`py_compile` for Python. `node --check` on the extracted block is the cheapest syntax gate
and needs no stub DOM: extract the `<script>` blocks to a file and check them before
building a harness at all.

## Pitfalls (each costs a debugging round)

- **`navigator` is a getter-only global in node >= 18.** `global.navigator = {...}` silently
  no-ops, so the code under test finds no `navigator.clipboard` and takes its fallback
  branch — you debug the wrong path. Use
  `Object.defineProperty(global, 'navigator', {configurable: true, writable: true, value: {...}})`.
- Stub rows need a `style` object (`style: {}`): filter/sort code writes `r.style.display`
  and throws on a bare object.
- `document.querySelector` must answer the probes the script makes **before** it touches
  rows (an existence check feeding a column-offset helper) as well as the tbody lookups.
- Ids must match the served HTML exactly: a missing id yields `undefined` and the script's
  early-return path makes the harness look like it passed.
- **A non-2xx response raised as an exception hides the diagnosis.** `urllib`/`httpx` raise
  on 4xx/5xx, and the traceback shows the status while discarding the body that says what
  happened — for a local service the entire explanation is in that body. Catch the error and
  print the parsed body; a probe that crashes on the status hides the answer it exists to
  find.
- **The HTTP reply is the source of truth, not the journal.** A service's own log lines are
  often buffered to stdout, so an error it just produced may not be readable yet, and an
  empty journal is not evidence that nothing happened. Drive the endpoint, read what it
  returns.
- **Never `pkill -f` a pattern that also appears in your own command line.**
  `pkill -f "port 8199"` matches the shell running it and kills the session (exit `-15`,
  output lost). Bracket a character (`pkill -f "[s]erver.py.*scratch"`) or `pgrep -a` first
  and kill by pid.
- **Do not `rm -rf` a directory that is the shell's cwd** — later commands fail with
  `getcwd: cannot access parent directories`. `cd` out or pass an explicit workdir, and use
  absolute paths afterwards.
- **A mock `classList` must accept varargs.** Real `classList.remove('a','b')` drops both;
  a stub `remove: c => set.delete(c)` drops only the first, so a stale class survives and
  the failure is your harness, not the page — cost: a debugging round spent on working
  code. Use `add/remove: (...cs) => cs.forEach(...)`.
- **Assert the behaviour you actually implemented, direction included.** When the
  comparator multiplies the tiebreak by the same direction factor (`return c * dir`), ties
  reverse with the primary key too. An expectation written for "ties are always ascending"
  reports a code bug that does not exist.
- **A harness that assigns library/class attributes directly must mirror production types.**
  Handing a handler a `str` where the entry point hands it a `Path` passes every path join,
  then throws in an accessor only the rendered page reaches (`.name`). A harness bug that
  reads as a server bug: assert on the served page too, not only on the endpoint.
- **A failing harness assertion is a hypothesis about the stub, not proof of a page bug.**
  Adjudicate it in the real engine before editing code, because stub DOM semantics are not
  the browser's: `tbody.rows[0]` is a *data* row (the header lives in `thead`), so a sort key
  read off `rows[0].cells[j]` inherits the first row's cell type, and any stub whose rows sit
  in a different order flips the expected direction. Click the real header, read the resulting
  row order plus the marker class, then decide which side is wrong — "fixing" the page to
  satisfy a stub is how working sort code gets broken.
- **Reading a harness's exit status through a pipe reports the pipe's status.**
  `node harness.js | tail -30` exits 0 even when the harness failed; use
  `node harness.js; echo $?` or `${PIPESTATUS[0]}`, otherwise a red suite reads as green.
- **Read optional DOM inputs defensively in the page's JS.** When a handler reads a hidden
  input (`var h = g('trashpath'), d = (h && h.value) ? h.value : DEFAULT`) it must fall back
  instead of throwing: a stale page, a trimmed-down harness or a variant of the page that
  omits the element otherwise breaks the whole action instead of degrading.
- **A harness parked in the scratch dir is pruned after ~24 h idle.** If it is meant to be
  re-run (README quotes its path, the fix is not finished), put it in the project it tests
  and let the scratch copy be the throwaway.

## Support files

- `references/dense-listing-ui.md` — the UI contract for a table-listing page (row density,
  no-wrap columns + name ellipsis, seeded default sort) and how to measure each claim.
- `references/paste-ready-shell-commands.md` — shape and quoting rules for commands a UI
  hands to the user, plus the generate-don't-execute policy.
- `references/served-app-file-actions.md` — when buttons (not pasted commands) act on files:
  the move-only design contract, the CSRF guard a Basic-auth service needs, path containment
  and caps, and how to prove endpoint + buttons.
- `scripts/page_command_harness.js` — the stub-DOM harness described above.
