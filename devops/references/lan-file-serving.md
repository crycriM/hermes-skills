# Serving a local folder over HTTP (LAN testing, file browsers)

Pattern for publishing a folder (documents, build output, assets) to the LAN in
minutes, plus how to actually verify a local web UI.

## Recipe: stdlib server + systemd user unit

1. Single-file stdlib server (no framework, no root):
   `~/.config/systemd/user/<name>.service` with `%h` paths, `WantedBy=default.target`.
2. `systemctl --user daemon-reload; systemctl --user enable --now <name>.service`.
   `Linger=yes` (check `loginctl show-user $USER | grep Linger`) makes it survive logout.
3. Verify from a *second* address, not just 127.0.0.1: `curl -o /dev/null -w '%{http_code}' http://<lan-ip>:<port>/`.
4. Optional niceties: `EnvironmentFile=-%h/.config/<name>.env` + HTTP basic auth,
   `--bind 127.0.0.1` + `tailscale serve --bg --https=8443 http://127.0.0.1:<port>`
   when the service should be tailnet-only with real TLS.

Reference implementation on this box: `~/projects/docs-web/` (serves `~/Documents`
on 0.0.0.0:8190, `docs-web.service`, HTTP basic auth from
`~/.config/docs-web.env`, mode 600). Stdlib only, plus a venv with
`python-markdown` for rendering `.md` (system python is PEP-668 externally managed:
`pip install` needs a venv, `--break-system-packages` otherwise).

### "Start a new document server" — check first, then instantiate

There is already a document server on this box (**docs-web**, `~/Documents` on
8190). "New" therefore means a **second instance for another folder**, not a
fresh install: before building anything, `systemctl --user list-units 'docs-*'`
and `ss -ltn`, and ask which root folder + port if the request does not name one.
Reinstalling over the existing unit is the failure to avoid — the running
service holds the port, so the second bind dies with "address already in use"
and the original ends up restarted or the wrong folder served.

Second instance (example: renders on 8191):

```bash
sed -e 's/docs-web/docs-web-renders/g' \
    -e 's|%h/Documents|/mnt/data2/ComfyUI/output|' \
    -e 's/--port 8190/--port 8191/' \
    ~/.config/systemd/user/docs-web.service \
    > ~/.config/systemd/user/docs-web-renders.service
systemctl --user daemon-reload
systemctl --user enable --now docs-web-renders.service
```

The copy inherits `EnvironmentFile=-%h/.config/docs-web.env` (the `-` makes a
missing file non-fatal, so the new instance silently starts **unauthenticated**
if it points at a different env file that does not exist — check the startup line
says `(basic auth)` or make a second env file) and inherits
`ProtectSystem=strict` + `ProtectHome=read-only`, so a root outside `$HOME`
(e.g. under `/mnt/data2`) still needs no hardening change but a root *inside*
another user's home would. Verify per instance, never per project: unique port in
`ss -ltn`, `curl -w '%{http_code}'` returns 401 unauthenticated and 200 with the
credentials, and a listing row count that matches `find <root> -maxdepth 1`.
Keep a new port out of the 8080-8099 LLM band and off 8190 itself.

## Pitfalls learned the hard way

- **Check the port against the whole box before binding, and never squat an
  existing service's port.** On this host the PE prompt rewriters own
  8090/8091 (`~/models/pe/start-pe-t2i.sh` = 127.0.0.1:8090,
  `start-pe-heretic35b.sh` = 127.0.0.1:8091), and `~/llm-server/test-laguna.sh`
  plus the stale `~/llm-server/gui/server.py` also claim 8090. A server bound to
  `0.0.0.0:8090` blocks a later `127.0.0.1:8090` bind (plain SO_REUSEADDR does not
  bridge wildcard vs. specific), so the PE rewriter dies with "address already in
  use" — and a client pointing at that port silently talks to the wrong service.
  docs-web therefore lives on **8190**. Always: `ss -ltn` + grep the scripts and
  systemd units for the candidate port (`grep -rIn '809[0-9]' ~/llm-server ~/models
  ~/.config/systemd/user`) before committing to it, and keep new servers out of the
  8080-8099 LLM test band.
- Port 80 (and 8443/8444) is already taken by the **root-owned system nginx**; a user
  service cannot bind it and `patch`/reload of `/etc/nginx` needs sudo. Pick a free
  high port (8090 was free; 8000/8001/8079/8080/8081/8088/8188/3000/9000 are busy).
- `python3 -m http.server` shows an ugly listing and no Range support. A ~200-line
  stdlib handler gets breadcrumbs, sort, filter, inline preview and byte ranges.
- **Hiding dotfiles from the listing is not enough** — block them in the URL→path
  resolver too, or `/.env` is still downloadable: reject any path component starting
  with `.` unless `--all-files`.
- Path-traversal defence: `os.path.realpath(join(root, rel))` must equal root or start
  with `root + os.sep`; return 403. Test with `curl --path-as-is`
  (`/../x`, `/%2e%2e%2f...`) — plain curl otherwise normalises the `..` away.
- Serve `Content-Disposition: attachment` for binaries, `inline` for
  `image/* video/* audio/* text/* application/pdf`, and always send
  `Accept-Ranges: bytes` + 206 handling so video/audio seeking works.

## Verifying a local web UI (do not skip this)

`browser_exec` (Browser Use CLI) **refuses private/internal addresses** —
`http://localhost`, `127.0.0.1`, `10.x`, tailnet IPs all return
`{"error": "Blocked: URL targets a private or internal address"}`. To drive and
assert on a local page, use the Playwright MCP tools instead:
`mcp__playwright__browser_navigate` then `mcp__playwright__browser_evaluate`,
`mcp__playwright__browser_console_messages`.

- Keep `browser_evaluate` to **one** JS expression; a navigation triggered inside it
  destroys the execution context (`Execution context was destroyed`) — re-evaluate
  after the navigation instead of returning values across it.
- `browser_navigate` reports the console error count; check it. On this build a
  page that looks fine can still throw on every keystroke (e.g. a filter reading an
  attribute that was never emitted) — assert on real behaviour
  (`rows.filter(r => r.style.display !== 'none').length`) against a server-side truth
  (`find <dir> -maxdepth 1 -type f -name '*<q>*' | wc -l`), not on the HTML.
- `tool_call` accepts exactly one local tool per call; batch only `connectors__` names.
- Cleanup: run one-off test instances on a scratch tree (`$TMPDIR`/scratch dir) with a
  separate port, then kill the background process and remove the tree — never test
  subdirectory/dotfile behaviour inside the real served folder.
