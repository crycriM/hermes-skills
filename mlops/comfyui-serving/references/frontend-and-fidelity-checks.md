# Verifying ComfyUI changes: live frontend probe and pixel-fidelity A/B

Two checks that answer the questions users actually ask — *"where is that setting, did my file render?"* and *"is the faster setting still the same image?"* — without asking them to click anything.

## 1. Probe the live frontend headlessly

Use when a shipped workflow file or a newly installed node must be confirmed in the real UI: which widgets exist and what they hold, whether the node renders its widgets at all, a screenshot of one node.

- Drive a **private** Chromium through the Playwright node module that `playwright-mcp` already installed: `require('/home/cricri/.local/share/playwright-mcp/node_modules/playwright')`, executable `/home/cricri/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome`, launched with `args: ['--no-sandbox']` and `~/.local/bin/node`.
- **Do not reach for the playwright MCP tools to do this.** They attach to a shared profile and refuse with `Browser is already in use for ~/.cache/ms-playwright-mcp/<profile>, use --isolated` — another session owns that browser. Launching a separate instance from the node module avoids hijacking it.
- Wait for the app, not the document: `page.waitForFunction(() => window.app && window.app.graph && window.app.graph._nodes)`.
- Load a saved workflow with the frontend's own loader — this doubles as proof the file is loadable:

```js
const r = await fetch('/api/userdata/workflows%2F<file>.json');   // the userdata path is URL-encoded
await window.app.loadGraphData(await r.json());
const n = window.app.graph.getNodeById(<id>);
n.widgets.map(w => [w.name, w.value]);                            // the real widget rows
```

  A null node or a shorter widget list than the file declares is the cached-node-definition failure: hard reload, then *Refresh Node Definitions*.
- Screenshot exactly one node: frame it with `canvas.centerOnNode(n)` + `canvas.setZoom(1.4)`, then convert world → screen and clip in the browser: `screen = canvasRect.{x,y} + (world + canvas.ds.offset) * canvas.ds.scale`, where `canvasRect = document.querySelector('canvas#graph-canvas').getBoundingClientRect()`; then `page.screenshot({ clip: { x, y, width, height } })`. Clipping beats cropping a full-page shot by guesswork.
- A clipped PNG of the node is the fastest end to "I did not see where": it shows the field, its value and its neighbours in the user's own UI.
- **Sanity-check the capture numerically before sending** (mean, std, distinct-colour count via the ComfyUI venv's PIL/numpy): a blank or mis-clipped capture still looks like a successful tool call.

## 2. Pixel-fidelity A/B for a speed/fidelity knob

Use when a setting trades speed for fidelity — prediction, caching, quantisation, a sampler change — and the user wants quantitative evidence before trusting it. Harness: `scripts/image_fidelity_ab.py`.

- Vary one thing, hold the seed and every other widget, submit each variant as its own API job.
- **Validate the harness before trusting any diff: re-run one identical config and assert the pixels match** (`np.array_equal`, max abs diff 0). PNG *bytes* differ between identical renders because metadata is embedded, so compare decoded pixels, never file hashes.
- **Only compare warm timings.** The first job after a ComfyUI restart carries the model load (~45 s here) and makes the baseline look roughly 2× slower than it is.
- Report PSNR, SSIM, mean |Δ|, p99, and the share of pixels above 8/255 and 16/255. As a reading: PSNR > 39 dB with SSIM > 0.98 and ~2 % of pixels above 8/255 is texture-level noise, not a different image.
- Deliver a three-panel strip (A | B | 6× amplified diff) alongside the numbers: the metrics convince, the strip lets the user confirm.
- `cv2` and `scipy` are in the ComfyUI venv and there is no scikit-image — SSIM is ~10 lines of `scipy.ndimage.gaussian_filter`, and `cv2.PSNR` does the rest.
- **Run comparison scripts through `/mnt/data2/ComfyUI/.venv/bin/python`.** `execute_code`'s interpreter has neither cv2 nor the ComfyUI venv, and its failure reads like a missing library rather than a wrong interpreter.
- Capture the pack's own per-run log line (full/predicted call counts, attention calls) as the second source of truth — the API response says *a* run succeeded, the log says the intended branch ran.

## 3. Patching a third-party pack's guard

When a pack's validation refuses a configuration the user needs — a hard-coded floor, a fixed range — it is usually a conservative guard, not an algorithmic limit: read the function, keep the body, move the constant out and prove the new value with the generator alone before rendering anything.

- Keep the original as `<file>.orig`, state the reason next to the new constant, and name the cost in the handover: the pack can no longer be `git pull`ed cleanly.
- **Custom node code is imported at startup, so the change needs a restart**: `systemctl --user restart comfyui`, then poll `/system_stats`. There is no hot reload, and report the restart — it reads as "you touched my setup" otherwise.
- **Re-run the case the guard was protecting.** Widening one gate can silently disable the next one; submit the configuration that must still be refused and cite its error message as evidence that only the intended limit moved.
- Offer the choice *before* editing installed source, as a short numbered list with the cost of each: bypass the node (`enabled=false` on a pass-through node is zero-risk and often enough), patch the guard, or split by job (this sampler/short run without the accelerator, the longer run with it).
