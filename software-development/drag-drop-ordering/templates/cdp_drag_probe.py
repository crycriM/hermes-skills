#!/usr/bin/env python3
"""Real-drag probe for a board/list UI, run through the browser-harness CLI.

Usage:
    cd ~/browser-harness
    export BU_CDP_WS=$(curl -sf http://localhost:9222/json/version \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['webSocketDebuggerUrl'])")
    browser-harness -c "$(cat templates/cdp_drag_probe.py)"

Adapt the CONFIG block. It performs native drags (press/move/dwell/release) and prints:
  - the card order per column (DOM) before and after each drag,
  - the recorded drag events (no `drop` => the drop was refused),
  - every request the app sent (=> handler ran, wrong index).
"""
import json

# ---------------- CONFIG ----------------
URL = "http://127.0.0.1:3111/static/index.html"   # isolated instance, never the live service
PROJECT_SELECTOR = '#project-list li[data-id="%s"]'  # "" if there is only one board
PROJECT_ID = None                                  # None = first project in the list
COLUMN_SELECTOR = ".column"                        # status read from data-status
BODY_SELECTOR = ".column-body"
CARD_SELECTOR = ".task-card"
CARD_TITLE_SELECTOR = ".task-title"
VIEWPORT = (1600, 1000)                            # wide enough for every column
MOVES = [("D", "todo", "A", "top"), ("B", "doing", None, "body")]  # (card, column, anchor, half)
# ----------------------------------------

cdp("Network.setCacheDisabled", cacheDisabled=True)
new_tab(URL)
wait_for_load()
cdp("Emulation.setDeviceMetricsOverride", width=VIEWPORT[0], height=VIEWPORT[1],
    deviceScaleFactor=1, mobile=False)
wait(1.0)

# record drag events + the requests the page makes
js("""(() => {
  window.__ev = [];
  for (const t of ['dragstart','dragenter','dragover','dragleave','drop','dragend']) {
    document.addEventListener(t, (e) => {
      const el = e.target;
      window.__ev.push(t + ' ' + (el.id || el.className) + ' y=' + Math.round(e.clientY));
    }, true);
  }
  window.__req = [];
  const of = window.fetch;
  window.fetch = function(...a) {
    const u = typeof a[0] === 'string' ? a[0] : (a[0] && a[0].url);
    if (u) window.__req.push(((a[1] && a[1].method) || 'GET') + ' ' + u + ' ' + ((a[1] && a[1].body) || ''));
    return of.apply(this, a);
  };
  return 1;
})()""")


def select_project():
    if not PROJECT_SELECTOR:
        return
    sel = PROJECT_SELECTOR % PROJECT_ID if PROJECT_ID else '#project-list li'
    js("(() => { const li = document.querySelector('%s'); if (li) li.click(); return 1; })()" % sel)
    wait(1.5)


JSTATE = """(() => {
  const cols = {};
  for (const c of document.querySelectorAll('%s')) {
    cols[c.dataset.status] = [...c.querySelectorAll('%s')].map(d => {
      const r = d.getBoundingClientRect();
      return {title: d.querySelector('%s').textContent, x: r.x + r.width/2,
              top: r.top, bottom: r.bottom};
    });
  }
  const bodies = {};
  for (const c of document.querySelectorAll('%s')) {
    const r = c.querySelector('%s').getBoundingClientRect();
    bodies[c.dataset.status] = {x: r.x + r.width/2, top: r.top};
  }
  return JSON.stringify({cols: cols, bodies: bodies});
})()""" % (COLUMN_SELECTOR, CARD_SELECTOR, CARD_TITLE_SELECTOR, COLUMN_SELECTOR, BODY_SELECTOR)


def state():
    return json.loads(js(JSTATE))


def order():
    return {k: [c["title"] for c in v] for k, v in state()["cols"].items()}


def locate(title):
    for cards in state()["cols"].values():
        for c in cards:
            if c["title"] == title:
                return c
    raise AssertionError("card not found: " + title)


def drag(src_title, column, anchor_title, half):
    src = locate(src_title)
    if anchor_title:
        tgt = locate(anchor_title)
        tx = tgt["x"]
        ty = tgt["top"] + 3 if half == "top" else tgt["bottom"] - 3
    else:
        body = state()["bodies"][column]
        tx, ty = body["x"], body["top"] + 40
    print("   target (%s -> %s/%s) %d,%d | elementFromPoint: %s" % (
        src_title, column, half, tx, ty,
        js("(() => { const e = document.elementFromPoint(%f, %f); return e ? (e.id || e.className) : 'null'; })()" % (tx, ty))))
    sx, sy = src["x"], (src["top"] + src["bottom"]) / 2
    cdp("Input.dispatchMouseEvent", type="mousePressed", x=sx, y=sy, button="left", clickCount=1, buttons=1)
    for i in range(1, 11):
        cdp("Input.dispatchMouseEvent", type="mouseMoved", x=sx + (tx - sx) * i / 10,
            y=sy + (ty - sy) * i / 10, button="left", buttons=1, clickCount=0)
        wait(0.08)
    for j in range(6):  # dwell: Chrome must dispatch a dragover at the target before release
        cdp("Input.dispatchMouseEvent", type="mouseMoved", x=tx + (j % 2), y=ty + (j % 2),
            button="left", buttons=1, clickCount=0)
        wait(0.22)
    cdp("Input.dispatchMouseEvent", type="mouseReleased", x=tx, y=ty, button="left", clickCount=1, buttons=0)
    wait(1.5)


select_project()
print("BEFORE:", json.dumps(order()))
for src, column, anchor, half in MOVES:
    js("window.__ev = []; window.__req = []; 1")
    drag(src, column, anchor, half)
    print("AFTER :", json.dumps(order()))
    print("   drag events:", js("window.__ev.slice(-12)") or [])
    print("   requests:", js("window.__req") or [])

# persistence: the order must survive a page load
goto_url(URL)
wait_for_load()
wait(1.0)
select_project()
print("AFTER RELOAD:", json.dumps(order()))
