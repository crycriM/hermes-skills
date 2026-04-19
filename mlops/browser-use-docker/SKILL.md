---
name: browser-use-docker
description: "browser-use ecosystem: Docker container for autonomous browser agent + browser-harness for thin CDP control. Which tool to use when."
version: 1.1
---

# browser-use Ecosystem

Three tools for browser automation, each with a distinct niche.

## Which tool to use when

| Scenario | Right tool | Why |
|---|---|---|
| Hermes agent browsing on headless server | **Hermes built-in Playwright** (browser_navigate, etc.) | Stealth fingerprinting bypasses Cloudflare; no Chrome install needed |
| Autonomous LLM-driven browsing (no human) | **browser-use Docker** | Agent loop: LLM decides what to click/type, loops until done |
| Coding agent (Claude Code, Codex) driving real Chrome | **browser-harness** | Thin CDP layer; agent writes Python, harness executes on real Chrome |
| Parallel sub-agents needing separate browsers | **browser-harness + remote browsers** | BU_NAME namespacing + Browser Use cloud API |
| Sites with aggressive bot detection (SSRN, etc.) | **Hermes Playwright** or **browser-harness on real Chrome** | Headless CDP (browser-use) gets blocked; Playwright stealth or real Chrome sessions work |

## browser-use Docker Container

Docker container with browser-use Python package + Chrome for autonomous browser tasks driven by local LLMs.

### Key Facts

- **browser-use does NOT depend on Playwright** — it uses `cdp-use` (Chrome DevTools Protocol), talks to Chrome directly
- **Chrome 147+** installed from Google's official .deb
- **LLM integration**: use `ChatLiteLLM` from `browser_use.llm.litellm`, NOT langchain's `ChatOpenAI` (browser-use v0.12.6 monkey-patches LLM objects, pydantic rejects it)
- **litellm** must be installed separately (pip install browser-use litellm)
- **Headless Chrome gets Cloudflare blocked** — SSRN, some other sites with managed challenges detect headless and refuse. Works fine for sites without aggressive bot detection.

### Build

Dockerfile at `/tmp/browser-use-build/Dockerfile`:

```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq && apt-get install -y -qq \
    python3 python3-pip python3-venv wget gnupg2 curl unzip \
    # clean up apt lists after install

RUN wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update -qq \
    && apt-get install -y -qq /tmp/chrome.deb || apt-get -f install -y -qq \
    # clean up chrome deb and apt lists

RUN python3 -m venv /opt/browser-use-venv \
    && . /opt/browser-use-venv/bin/activate \
    && pip install --quiet browser-use litellm

ENV PATH="/opt/browser-use-venv/bin:$PATH"
CMD ["python3"]
```

Build: `docker build -t browser-use /tmp/browser-use-build/`

### Usage Pattern

```python
import asyncio

async def main():
    from browser_use import Agent
    from browser_use.llm.litellm import ChatLiteLLM

    llm = ChatLiteLLM(
        model="openai/nemotron-cascade2-30b",  # litellm format: provider/model
        api_base="http://host.docker.internal:8080/v1",
        api_key="not-needed",
        temperature=0.0,
    )

    agent = Agent(
        task="Navigate to URL and extract X...",
        llm=llm,
        use_vision=False,       # faster without screenshots
        flash_mode=True,        # faster mode
        enable_planning=False,  # skip planning step
        use_judge=False,        # skip quality judge
    )

    result = await agent.run(max_steps=15)
    print(result.final_result())

asyncio.run(main())
```

Run from host:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway \
  -v /path/to/script.py:/tmp/task.py:ro \
  browser-use bash -c 'source /opt/browser-use-venv/bin/activate && python3 /tmp/task.py'
```

## browser-harness

Thin CDP control layer. You (or a coding agent) write Python, it executes on an already-running Chrome. No LLM in the loop.

### Install (done)

- Cloned to `~/browser-harness/`
- Globally installed: `uv tool install -e .` → `/home/cricri/.local/bin/browser-harness`

### Architecture

```
Chrome / Browser Use cloud -> CDP WS -> daemon.py -> /tmp/bu-<NAME>.sock -> run.py
```

- Agent writes Python snippets, harness sends CDP over Unix socket
- `helpers.py` has all primitives: goto, click, type_text, press_key, scroll, screenshot, js, cdp, list_tabs, etc.
- `domain-skills/` = site-specific knowledge, `interaction-skills/` = UI mechanics (iframes, shadow DOM, dropdowns, etc.)
- Remote browsers via `BROWSER_USE_API_KEY` in `.env` (free tier: 3 concurrent, no card)

### Key constraint

Browser-harness connects to a **real running Chrome** with your sessions. It is NOT useful on a headless server without a display. It belongs on your desktop/laptop where Chrome runs. On headless servers, use Hermes built-in Playwright instead.

## Pitfalls

- **Never use langchain ChatOpenAI with browser-use** — browser-use v0.12.6 calls `setattr(llm, 'ainvoke', ...)` which pydantic rejects. Use `ChatLiteLLM` instead.
- **`llm.provider` attribute** — browser-use checks `llm.provider == 'browser-use'`. ChatLiteLLM has this built in.
- **Cloudflare managed challenges** — headless Chrome via CDP (browser-use) CANNOT solve them. Hermes built-in Playwright browser tools DO get past SSRN's Cloudflare (verified Apr 2026) — Playwright's stealth fingerprinting works where raw CDP doesn't.
- **Page readiness timeout** — browser-use has a 3s page readiness timeout. Heavy pages may need adjustment.
- **Ubuntu 26 host** — Playwright is broken on Ubuntu 26, but browser-use doesn't need Playwright. Docker container sidesteps the issue.
- **Docker image size** — ~1.5GB (Chrome + deps). Not lightweight.
- **browser-harness on headless server** — pointless without real Chrome. Use Hermes Playwright or remote Browser Use cloud browsers instead.
