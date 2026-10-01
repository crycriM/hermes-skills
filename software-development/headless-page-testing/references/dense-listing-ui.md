# Dense listing UI: the contract these pages are held to

Invariants for a local table-listing page (file browser, render output, index) served by a
small stdlib server. They are what the stub-DOM harness asserts and what a headless
measurement pass confirms.

## 1. Row density — one line per row, no exceptions

The house style for these pages is dense, not spacious. Spacious rows and a date/time
column that wraps onto a second line read as defects, not taste.

- 13 px table font, `line-height: 1.2`, `1px 8px` cell padding -> ~19 px rows; body text
  14 px/1.4; checkbox 14 px.
- The first thing to suspect when rows look tall: `padding` on `th,td` (7 px vertical is a
  full extra line) and `line-height` inherited from `body`.
- The second thing: a column that wrapped. Count line boxes, do not guess:
  `const r = document.createRange(); r.selectNodeContents(cell); r.getClientRects().length`
  must be `1`.

## 2. A wrapped column is a layout bug with a known cause

`td.name{width:100%}` makes the name cell greedy in an auto-layout table, so every other
column is squeezed to its minimum content width and the longest one wraps. Fix the pair,
not the symptom:

```css
th,td{white-space:nowrap}                 /* columns take their natural width */
td.name{width:100%;max-width:0;overflow:hidden}
td.name a{display:flex;gap:7px;align-items:baseline;max-width:100%}
td.name a .ic{flex:0 0 auto}              /* icon never shrinks */
td.name a .nm{overflow:hidden;text-overflow:ellipsis;min-width:0}  /* name ellipsizes */
```

A single flex child needs `min-width:0` to shrink below its content width — without it the
flex item refuses to go under `min-content` and the table widens instead. Put the full
name in the anchor's `title` so truncation stays recoverable.

## 3. Default sort is explicit, and the DOM carries it

- Server side: order the emitted rows in the code that builds them, e.g.
  `rows.sort(key=lambda r: (-r[1], r[0]))` -> most recently modified first, files and
  folders interleaved. Folder-first grouping is a deliberate choice to state, not a default
  to fall back on.
- The client toggles by reversing the whole comparison: first click on a column gives
  descending, second ascending, ties follow the same direction. Say so when a user asks why
  equal keys flipped.
- Seed the state so a click on the already-active header reverses instead of no-op'ing:
  `<tbody id="tb" data-d="<colindex><type>">` filled by the server (the index counts a
  conditionally rendered checkbox column), with the active header pre-marked `class="desc"`
  and `aria-sort` kept in sync.
- Cell sort types are per cell (`data-t="s|n|d"`), never a positional array such as
  `['n','n','s','d'][j]`: the moment a column is added or appears conditionally, sizes start
  comparing as strings (`"10 KB" < "2 KB"`) and nothing throws.
- Show the direction on the active header (`th.asc::after` / `th.desc::after`) — without a
  marker the user cannot tell a reversed list from a stale one.

## 4. Verify, do not eyeball

In headless Chromium (`mcp__playwright__browser_*`, against a throwaway instance with auth
disabled so credentials stay out of the tool call):

- `[...new Set(rows.map(r => r.offsetHeight))]` — a one-element set proves uniform rows.
- Line-box count per date cell (see 1).
- Inject an over-long synthetic name and require `el.scrollWidth > el.clientWidth` while
  `table.offsetWidth` and `document.documentElement.scrollWidth` stay put — clipping must
  not become page overflow.
- Click the real headers and read the row order, marker class and `data-d` in the same
  evaluation; assert monotonicity, not specific row names.
- Repeat at a narrow viewport: a column usually only wraps under pressure.
