---
name: svg-print-layout
description: Use when editing SVG print layouts (posters, flyers).
---

# SVG print-layout editing

Procedure for modifying SVG print documents (Inkscape-style posters/flyers with mm units, layered groups, linked raster backgrounds). Core loop: edit source geometry → render via browser CDP → verify on pixels.

## Workflow

1. **Read the SVG source first.** It is plain text: every text element carries x/y, font size, weight, anchor, and fill. All geometry decisions come from the source, not from squinting at a render. Inkscape files use `inkscape:groupmode="layer"` groups — edit whole layers as units and keep `sodipodi:namedview` / guides intact.
2. **Stage a render dir**: copy the SVG plus every linked raster (check both `xlink:href` and `href` on `<image>`; filenames may differ from the attachment names — copy under the referenced name too).
3. **Render via browser CDP** (no local rasterizer needed): open the file:// URL, then `Emulation.setDeviceMetricsOverride` with width/height matching the document aspect (A3 at 96dpi ≈ 1123×1588), then `Page.captureScreenshot` with an explicit `clip` rect — a plain screenshot captures only the viewport and silently crops the page.
4. **Place text on artwork by measured luminance, not by eye.** Crop candidate zones from the rendered PNG, downscale each, and compute mean luminance (0.299R+0.587G+0.114B). Dark text needs a zone ≥ ~180; below ~140 it drowns. Scan a grid (e.g. every 10mm vertically, 25mm horizontally) to find the readable band before committing coordinates.
5. **Apply edits by rewriting whole `<text>`/layer blocks** in Python over the source string (read file, `str.replace` on unique spans, write new version file). Bump the version in the filename (v3→v4); never overwrite the user's original.
6. **Update reserved-zone/guide rects** when a block moves — the dashed planning layer must track reality or the next edit session misplaces things.
7. **Verify on the render, then verify again programmatically.** Vision for overall sanity; pixel math for alignment and collisions (below).

## Verification pitfalls

- **vision_analyze cannot read SVG** — rasterize to PNG/JPEG first.
- **Large images time out the vision API** — downscale to a ~500–900px JPEG under ~100KB before calling; a 1–2MB render will just error out repeatedly. Retry smaller, never re-send the same big file.
- **Verify text collisions with pixels, not vision.** For aligned pairs (e.g. right-aligned name | left-aligned title), scan each row band in the rendered PNG for dark pixels left/right of the divider x-position and assert the rightmost ink of the left column stays left of the divider and vice versa. Vision models miss 1–2mm overlaps; the pixel scan is exact.
- **browser_exec runs a bare interpreter**: no `hermes_tools` import — use stdlib (`shutil`, `base64`) and the pre-imported browser helpers (`new_tab`, `cdp`, `capture_screenshot`).

## Typography conventions the user asked for (choir poster)

- Program entries: composer **bold, right-aligned** to a fixed x, a `|` separator at x+3.5, piece title *italic, left-aligned* from x+7. Sub-lines (work collection, attribution) in smaller italic under the piece.
- Serif display face (Cormorant Garamond) for titles/composers/pieces, sans (Jost) for meta; muted red accent reserved for separators and headings.
- Footer and small print: raise contrast aggressively (darkest palette brown, weight 600) — footers sit on mid-luminance artwork.
