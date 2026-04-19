---
name: research-agent-benchmark
description: Run the research agent benchmark — evaluate local models as autonomous research subagents on a structured academic topic. Generates GLM 5.1 reference, runs contenders, evaluates with composite scoring.
version: 1.0
---

# Research Agent Benchmark

Evaluate local LLMs as autonomous research subagents. Single-shot prompt, no follow-up, no clarification. Models use search tools to produce a structured research deliverable.

## Location

`~/llm-server/research_agent_bench/`

## Design Document

`DESIGN.md` — full spec including prompt, phases, evaluation metrics, composite score formula.

## Phases

### Phase 1: Generate Reference (GLM 5.1 cloud)

Run the P2 prompt through GLM 5.1 with web, arXiv, SSRN tools. Output becomes the baseline for comparison.

**CRITICAL: Do NOT guide the subagent.** The prompt must be the original P2 text verbatim. Do not inject method names, specific search queries, or hints about what papers to find. The whole point is testing whether the model discovers relevant methods independently. "Encourage broad searching" is fine; "search for ROCKET and MiniRocket" is not.

**CRITICAL: Subagents fail at this task.** In testing, delegate_task subagents burned all iterations on terminal curl searches without ever synthesizing or writing the output file. Two failures confirmed:
1. First attempt: 22 terminal calls, 0 file writes
2. Second attempt: 34 terminal calls, 0 file writes (even with explicit "budget your iterations" instruction)

**Working approach:** Run Phase 1 directly with execute_code. Use arXiv API + Semantic Scholar API + web search via terminal curl, then write_file the reference. Orchestrator controls iteration budget directly.

### Phase 2: Run Contenders

Runner script: `~/llm-server/research_agent_bench/run_bench.py`

```bash
python3 -u run_bench.py --models nemotron-120b holo3-35b cascade2-30b
python3 -u run_bench.py --all
python3 -u run_bench.py --no-load --models nemotron-cascade2-30b  # model already loaded
```

**Mode: direct API** (not subagent — subagents fail to write files). The runner manages multi-turn conversation itself:
1. Loads model on router via `/models/load` + `/models/unload`
2. Sends P2 prompt with system instructions for structured JSON search queries
3. Model outputs `{"search": {"source": "arxiv|ssrn|web", "query": "..."}}` blocks
4. Runner extracts search/fetch intent via tiered parsing (fenced JSON → raw JSON → plain text regex → fetch pattern)
5. Runner executes searches and paper fetches, condenses results via source-specific condensers, feeds to model
6. Two-phase budget: 15 rounds research, then forced synthesis with full findings buffer injected
7. Forces final output if approaching timeout, context limit, or max rounds (25 rounds, 1h timeout)
8. Saves `response_<model>.md`, `meta_<model>.json`, `tool_log_<model>.json`
9. Skips models that already have output >1KB (resumable)
10. On API error, saves last assistant message as fallback (critical for large models that OOM on synthesis)

**SSRN enforcement:** Prompt requires all 3 sources with curl examples. Meta output tracks `search_breakdown` per source.

**Anti-fabrication prompt:** System prompt includes 5 rules:
1. ONLY cite sources found in search results or fetched and read. Do NOT invent paper titles, authors, URLs, or arXiv IDs.
2. For each paper cited, you should have EITHER fetched and read it OR seen its abstract in search results. Papers NOT read must be marked "(abstract only)".
3. If you have not found enough real sources, say so explicitly.
4. It is far better to have 5 real, well-summarized sources than 20 fake or shallow ones.
5. No search/fetch JSON in the final response.
This reduced cascade2 from 25K chars of pure fiction to citing real papers (with some detail errors). Models that still fabricate after this instruction are revealing a genuine flaw.

**Search-per-round cap:** Max 8 searches per round (models like nemotron-120b dump 24 queries in one response, causing 60K+ findings buffer even after condensing). This prevents context explosion on the synthesis call.

**Context size:** All models now at 131072+ (bumped from 65536 in router-preset.ini). Condensers keep findings buffer under 30K chars (~9K tokens). Synthesis injection capped at 30K chars. Runner estimates token count and forces final at ~110K tokens.

**API timeout:** 1200s (20 min) per call — large/thinking models (120B, cascade2) need 5-15 minutes per round.

#### Three Core Fixes (v2 runner)

**Fix 1 — Tiered search extraction:** Models output search intent in unpredictable formats. Three tiers:
- Tier 1: ````json {"search":{"source":"arxiv","query":"..."}} ``` (fenced)
- Tier 2: `{"search":{"source":"arxiv","query":"..."}}` (raw JSON, no fences — common for thinking models)
- Tier 3: Plain text regex — "Search arxiv for QUERY", "Let me look up ssrn: QUERY"
If none match, check if the model is attempting a deliverable (>2K chars with research keywords) and guide it to format headers, rather than blindly asking for JSON.

**Fix 2 — Findings buffer with condensers:** Raw search results (3-5K chars per source) cause context explosion over 20 rounds. Three condensers:
- `_condense_arxiv()`: Parses Atom XML → one line per paper (date, title, URL, abstract[:200]). 10 papers → ~2K chars vs 22K raw.
- `_condense_ssrn()`: Extracts paper titles from HTML via regex (title class or abstract_id links). ~1K chars vs 5K raw.
- `_condense_ddg()`: Extracts `result__snippet` and `result__a` from DDG HTML. ~1K chars vs 5K raw.
Buffer stays under 30K chars with oldest-entry merging. Only last 8 searches injected per round. Max 8 searches executed per round (prevents models like nemotron-120b from dumping 24 queries at once).

**Fix 3 — Two-phase approach:** Don't rely on deliverable detection heuristics. Instead:
- Phase 1 (rounds 0-14): Research — accept searches or spontaneous deliverables
- Phase 2 (rounds 15+): Forced synthesis — inject full condensed findings buffer as `=== FINDINGS ===` block with explicit header instructions
This guarantees a synthesis attempt even if the model never spontaneously writes headers correctly.

**DSPy ReAct decision:** Considered and rejected for benchmarking. ReAct adds framework overhead that confounds model capability measurement. Cascade2 couldn't follow basic JSON — that's a finding, not something to paper over. If this evolves into a production research agent, revisit DSPy. See `NOTES.md`.

### Phase 3: Evaluate

Two tracks:
- **Track A:** Reference comparison (Jaccard overlap, coverage ratio, novel sources)
- **Track B:** Intrinsic quality (citation validity, specificity, implementation depth, hallucination rate)

Composite score: `0.30*coverage + 0.20*source_overlap + 0.15*specificity + 0.15*implementation_depth + 0.10*citation_validity + 0.10*(1-hallucination_rate)`

### Phase 4: Tool Usage Analysis

Diagnostic only — which tools each model used, call counts, search depth, redundancy.

## File Structure

```
~/llm-server/research_agent_bench/
  DESIGN.md                    ← full spec
  prompt.txt                   ← P2 prompt text
  reference_response.md        ← Phase 1 output
  reference_tool_log.json      ← Phase 1 tool calls
  reference_meta.json          ← Phase 1 metadata
  responses/
    response_<model>.md
    tool_log_<model>.json
    meta_<model>.json
  evaluation/
    scores.md
    summary.md
```

## arXiv Search Pattern

```python
import xml.etree.ElementTree as ET

def arxiv_search(query, max_results=15):
    r = terminal(f"curl -sL 'http://export.arxiv.org/api/query?search_query=all:{query}&max_results={max_results}&sortBy=relevance' 2>&1", timeout=30)
    ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
    root = ET.fromstring(r["output"])
    results = []
    for entry in root.findall('atom:entry', ns):
        title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
        summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')[:500]
        authors = [a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)]
        published = entry.find('atom:published', ns).text[:10]
        link = entry.find('atom:id', ns).text
        results.append({'title': title, 'authors': authors, 'date': published, 'url': link, 'abstract': summary})
    return results
```

URL-encode quotes as `%22`, spaces as `+`. Searches return XML with Atom namespace.

## Semantic Scholar API

```python
r = terminal(f"curl -s 'https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=5&fields=title,authors,year,venue,abstract' 2>&1", timeout=15)
```

Good for finding non-arXiv papers (NIPS, ICML proceedings).

## Key Pitfalls

1. **Subagents burn iterations on searching** — they don't self-regulate. Run Phase 1 directly with execute_code, not via delegate_task. Phase 2 uses direct API mode (run_bench.py) instead of delegate_task for the same reason.
2. **f-string backslash syntax error** — in execute_code, you can't use `q.replace(" ", "+")` inside f-strings. Pre-compute the query string first.
3. **Don't guide the prompt** — the benchmark tests independent discovery. Adding method names to search instructions defeats the purpose.
4. **Deduplicate by title prefix** — multiple arXiv queries return overlapping results. Use `title[:60].lower()` as dedup key.
5. **SSRN was initially skipped in Phase 2 runner** — user caught this. The prompt.txt and runner now explicitly require all 3 sources (arXiv, SSRN, web) with curl examples. Prompt says "at least 15-20 total searches."
6. **Context size matters for multi-turn** — Search results must be capped at 3000 chars per source. Over 20 rounds with 20K char results, nemotron-120B hit a 500 API error (likely OOM) on the synthesis round. Runner now estimates tokens and forces final at ~110K.
7. **Model warmup after load** — after `/models/load`, the model needs ping-loop verification (3s intervals, 30 attempts) before it reliably responds to full prompts.
8. **Thinking models put content in `reasoning_content`** — not `content`. The runner must fall back: `content = c.get('content','') or c.get('reasoning_content','')`. Without this, the runner sees empty responses.
9. **Models output literal `arxiv|ssrn|web`** — some models copy the system prompt's source format verbatim instead of picking one. Runner must validate and fix: if `"|" in source: source = source.split("|")[0]`.
10. **Deliverable detection must be flexible** — models use varied header formats: `## Sources`, `## 1. Sources`, `# Sources`. Also accept any response >10K chars with 3+ `##` headers. Without this, the runner loops forever on models that produce complete deliverables on round 0.
11. **Background process stdout capture** — Hermes `terminal(background=true)` may not capture stdout from long-running Python scripts even with `-u` flag. Redirect to log file: `python3 -u run_bench.py ... > run_bench.log 2>&1` and `tail` the log to check progress.
12. **Fallback save on API error** — if the synthesis round fails (OOM, timeout), save the last assistant message from the conversation as fallback output. Without this, you lose all the search work.
13. **Confident hallucinators** — some models (cascade2-30b) produce polished 25K char deliverables with zero actual searches. Every source is fabricated (fake arXiv IDs, fake authors, fake repos). This is valuable benchmark data — it measures hallucination vs research ability.
14. **Mixed real/fake sources** — models that do search (holo3-35b) still mix real papers (ROCKET) with fabricated ones. The evaluation must check citation validity carefully.
15. **Fallback saves raw queries, not deliverables** — if round 0 is just search JSON (no assistant message >1K chars with real content), the fallback save captures raw queries. Fix: check for actual prose content in the fallback, not just message length. The two-phase approach (fix 3) prevents this by guaranteeing a synthesis round.
16. **Condensers must handle empty/malformed responses** — SSRN HTML structure varies, DDG sometimes returns captcha pages. Each condenser has 3 fallback tiers (specific class → generic pattern → strip all HTML). Test condensers independently before trusting them in the runner loop.
17. **SSRN is completely dead for curl** — `papers.ssrn.com` returns a Cloudflare JS challenge page to all curl/wget requests. Even with authenticated session cookies from `~/.hermes/.ssrn-cookies.json`, curl gets 403. Only Hermes Playwright browser tools (`browser_navigate`) bypass Cloudflare for paper pages. `hq.ssrn.com` does work with cookies via curl (200). The fix applied (Apr 2026): replaced direct curl with `ssrn_via_scholar.py` which uses a 4-step pipeline: (1) direct SSRN with cookies (likely 403), (2) Semantic Scholar API, (3) OpenAlex API, (4) Google Scholar snippet fallback. Updated `prompt.txt`, `run_bench.py build_subagent_prompt()`, and `ssrn_via_scholar.py` itself to reference this pipeline instead of dead curl commands.
17. **Findings buffer is per-run, not per-model** — declared inside `run_direct()`, so each model gets a fresh buffer. Don't hoist to module level or models will see each other's search results.
18. **Anti-fabrication prompt is effective but not foolproof** — cascade2 went from 100% fabricated sources to citing real papers (with some wrong arXiv IDs). Holo3 went from mixed real/fake to all-real sources. The instruction "only cite what you found" is fair for benchmarking research skill, not honesty.
19. **Thinking models batch all searches in round 0** — nemotron-120b outputs 20-30 JSON search queries with zero prose. The runner executes them, builds a massive findings buffer, and the synthesis call then OOMs or times out. The 8-search-per-round cap prevents this.
20. **V2 results (with anti-fabrication + condensers + two-phase):** cascade2-30b: 249s, 21 searches (7a/7s/7w), 18K chars, real papers. holo3-35b: 160s, 7 searches (3a/1s/3w), 12K chars, all real. nemotron-120b: fixed in v3 with search cap.
21. **Paper fetching (v3):** The runner now has a `fetch_paper` tool. Models can request `{"fetch": {"arxiv_id": "2309.08499"}}` to read full text. arXiv HTML is fetched via `arxiv.org/html/{id}` — newer papers (2023+) have compiled HTML (often >1MB, capped to 8000 chars of extracted text). Older papers (pre-2022) fall back to the abstract page (~600 chars). The system prompt tells models to fetch 3-5 most relevant papers, especially recent ones, and mark papers not read as "(abstract only)".
22. **Training cutoff as hallucination trap** — a model trained on 2023 data cannot fabricate convincing details about a 2025 paper unless it reads it. The fetch tool creates a natural test: does the model know to read papers it wants to summarize? Models that summarize fetched papers accurately demonstrate genuine tool use + comprehension. Models that summarize papers they only saw the abstract for are relying on training recall (which may be wrong).
23. **fetch_arxiv_paper implementation:** Try HTML first (`arxiv.org/html/{id}`). If response is <20KB or non-200, fall back to abstract page (`arxiv.org/abs/{id}`). Extract title via `citation_title` meta or `<h1>` with class containing "title". Strip HTML with regex. For abstract pages, extract `<blockquote class="abstract">`. Returns `{title, text, chars, mode}` where mode is "full paper" or "abstract only". `requests` must be imported at module level (not inside functions) — the condenser functions are called outside `run_direct()`.
24. **Router OOM under 120B + full context** — nemotron-120b with 128K context + large findings buffer caused the llama.cpp router to crash (ConnectionError: Remote end closed connection without response). The runner needs ConnectionError handling with fallback save. On crash, restart router with `systemctl --user restart m5-router.service`, wait ~15s for model reload, then retry.
25. **Cascade2 fetches irrelevant papers** — the thinking model grabbed arXiv:2009.03800 (an astrophysics paper) when trying to read time series papers. Thinking models may hallucinate arXiv IDs in their reasoning and request wrong papers. The fetch results do get injected into the findings buffer, potentially confusing synthesis.
26. **More searches ≠ better output.** Holo3 won v2 with 7 focused searches. Nemotron-120b's 24 scattergun queries produced lower coverage. Search quality and query specificity matter more than volume.
27. **Qwen35-122b refused to search** — produced entire deliverable from training data (zero searches). Got broad generic kernel methods (Random Fourier Features, TCNs) but missed the core topic (ROCKET, MiniRocket). Valuable negative data point.
28. **Paper fetching separates models by tool-use sophistication** — models that know to fetch and read papers (qwopus) produce more accurate summaries than those that reconstruct from training memory (cascade2) or abstracts only (holo3). The fetch tool is the key differentiator in v3.
29. **MiniMax-M2.7 (110GB IQ4_XS) cannot load on this hardware** — llama.cpp router has a hardcoded 10-second model spawn timeout. The 103GB model takes longer than 10s to load from NVMe, causing `ErrorOutOfHostMemory` followed by `force-killing model instance after 10 seconds timeout`. The load succeeds but the process is killed before tensor loading completes. No config option exists to increase this timeout (`--timeout` is request timeout, not model load timeout). To fix: patch llama.cpp source to increase the spawn deadline, or enable mmap to speed up loading.
30. **Router `models` endpoint shows ghost "loading" state** — after a failed model load, the `/models` endpoint may report `status: loading` indefinitely. Fix by calling `/models/unload` to clear the ghost state before retrying.
31. **ConnectionError crash in runner is unhandled** — the runner needs a `requests.exceptions.ConnectionError` catch block in the main loop (alongside the existing Timeout catch). Without it, a router crash mid-bench causes an uncaught exception that kills the entire batch run. Save fallback from last assistant message before breaking.
32. **arXiv `sortBy=relevance` biases toward old papers** — all models returned pre-2023 papers because the arXiv API call hardcodes `sortBy=relevance`. This surfaces highly-cited classics (ROCKET 2019, MiniROCKET 2020) over recent work. Models never add date terms to queries either. Consider: adding `sortBy=submittedDate` queries, requiring at least one search with "2024" or "2025" in the query, or mixing relevance + recency in the prompt instructions.
33. **MoE models fail at agentic research** — gemma4-26b-moe (26B/4B active) scored perfectly on coding (0.88) and JSON (1.0) benchmarks but produced zero searches in the research bench, hallucinating the entire report. The model simulated searches ("I will now process the results...") without actually calling any tools. This is a general MoE weakness: too few active parameters to follow multi-step search-instrumented workflows. Dense models at similar total size (gemma4-31b) handle the same task fine (17 real searches).
34. **Gemma4-31b V4 results** — 17 searches (5 arXiv, 3 SSRN via ssrn_via_scholar.py pipeline, 8 web), 682s, 7K chars output. Found the key papers (ROCKET, MiniROCKET, S-Rocket, POCKET, RFF signatures) with accurate summaries. First run with the updated SSRN pipeline (replacing dead curl).
35. **llama.cpp HTTP server drops long non-streaming connections** — thinking models (Opus distill, etc.) that generate 6500+ tokens over 10+ minutes cause the llama.cpp HTTP server to report "Failed to read connection" and return 500. The `requests.post(timeout=1200)` doesn't help because the server-side disconnect happens during generation. **Fix:** convert to SSE streaming (`"stream": True` in the request, `stream=True` in requests, then iterate `resp.iter_lines()` assembling `delta["content"]` and `delta["reasoning_content"]`). This keeps the TCP connection alive with incremental data. The fix was applied to `run_bench.py` around line 421. Consider applying the same pattern to coding and JSON bench runners if they hit similar timeouts with slow thinking models.
36. **Post-streaming `data` variable crash** — after converting to streaming, the old code that accesses `resp.json()` / `data["usage"]` will crash with `NameError: name 'data' is not defined`. After the streaming loop, you have `content` and `reasoning` strings assembled from deltas — there is no `data` dict. Replace `data.get("usage", {}).get("total_tokens", 0)` with a rough estimate like `len(content) // 4` or parse the final SSE chunk for usage data. Applied to `run_bench.py` line ~527.
37. **Delete old response files before re-running** — `run_bench.py` skips models that already have a `response_<model>.md` file >1KB. If re-running after a failed attempt, delete the old response file first: `rm responses/response_<model>.md responses/meta_<model>.json responses/tool_log_<model>.json`. The runner will not overwrite existing files by design (resumability), but stale files from old model versions will cause incorrect skips.

### Phase 3: Evaluation Script

`evaluate.py` — automated scoring:

```bash
python3 evaluate.py                                  # all responses
python3 evaluate.py --models nemotron-120b holo3-35b # specific
```

Extracts sources via regex, computes Jaccard overlap with reference, validates citations against known-good arXiv IDs, scores specificity/implementation depth/hallucination. Writes `evaluation/scores.md` (markdown report) and `evaluation/scores.json`.

### V2 Rankings (anti-fabrication + condensers + two-phase + search cap, no paper fetching)

| Rank | Model | Composite | Time | Searches | Key Finding |
|------|-------|-----------|------|----------|-------------|
| 1 | holo3-35b | 0.847 | 160s | 7 (3a/1s/3w) | Focused searches, perfect citations |
| 2 | cascade2-30b | 0.808 | 249s | 21 (7a/7s/7w) | Some unverified arXiv IDs (0.42 citation score) |
| 3 | qwopus35-27b | 0.786 | 774s | 21 (10a/2s/9w) | Best source overlap, found novel niche papers |
| 4 | nemotron-120b | 0.737 | 728s | 24 (14a/6s/4w) | Most searches, lowest coverage — scattered |
| — | qwen35-122b | N/A | 306s | 0 (0a/0s/0w) | Zero searches, off-topic, excluded from eval |

### V3 Run (with paper fetching)

Same 4 models + paper fetch tool. Models can now `{"fetch": {"arxiv_id": "..."}}` to read full text before summarizing.

| Model | Time | Searches (a/s/w/f) | Fetched | Key Finding |
|-------|------|---------------------|---------|-------------|
| cascade2-30b | 243s | 5a/3s/3w/1f | 1 (wrong paper — astrophysics) | Fetched irrelevant paper, still produced deliverable |
| holo3-35b | 285s | 11a/3s/5w/5f | 5 papers fetched | Good search expansion from 7→24 searches vs v2 |
| qwopus35-27b | 882s | 9a/2s/5w/4f | 4 papers (ROCKET, MiniRocket, S-Rocket, Hydra) | Best fetch discipline — read the core papers before summarizing |
| nemotron-120b | 1313s | 8a/1s/1w/3f | 3 papers (ROCKET, MiniRocket, POCKET) | Slow but methodical — read papers one by one |

**Fetch tool observations:**
- Qwopus is the only model that systematically fetched the core papers (ROCKET family) before summarizing. This is the desired behavior.
- Cascade2 fetched one paper but chose the wrong arXiv ID (an astrophysics paper) — demonstrates poor tool-use judgment.
- Holo3 did the most fetching (5 papers) but many were abstract-only (older papers without compiled HTML).
- Models don't always distinguish between "I read this paper" and "I saw the abstract" — the (abstract only) marking rule is unevenly followed.

**Minimax-M2.7 (minimax27)** scored 0.990 composite — the highest ever recorded. 35 tool calls (12a/5s/10w/8f) in 590s. Coverage 1.51 (beat the cloud reference). Zero hallucinations. Fetched and read 8 core papers systematically. At 101GB it's expensive but unmatched for research quality.

### V3 Rankings (with paper fetching)

| Rank | Model | Composite | Time | Searches (a/s/w/f) | Key Finding |
|------|-------|-----------|------|---------------------|-------------|
| 1 | holo3-35b | 0.840 | 285s | 11a/3s/5w/5f | Best balance, highest source overlap (0.27) |
| 2 | cascade2-30b | 0.808 | 243s | 5a/3s/3w/1f | Most sources (46) but low overlap, fetched wrong paper |
| 3 | qwopus35-27b | 0.790 | 882s | 9a/2s/5w/4f | Perfect citations (1.0), best fetch discipline, slow |
| 4 | nemotron-120b | 0.655 | 1313s | 8a/1s/1w/3f | Too slow, searched too little, lowest coverage |
