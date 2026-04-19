---
name: obsidian-rag
description: Unified memory system combining Obsidian vault (human-readable notes) with ChromaDB RAG (semantic search). Use for storing facts, project context, and lessons learnt. Automatically retrieves relevant context when needed.
version: 1.0.0
dependencies: []
metadata:
  hermes:
    tags: [memory, rag, obsidian, chromadb, semantic-search, persistence]
---

# Obsidian-RAG Memory System

Unified memory combining Obsidian vault for human-readable notes with ChromaDB for AI semantic search.

## When to Use

**Search memory when:**
- User asks about past decisions, preferences, or projects
- User says "remember", "we decided", "last time", "previously"
- Context about user's environment/setup is needed
- Working on a project that may have existing notes

**Write to memory when:**
- User explicitly asks to remember/record something
- Completing a complex task (5+ tool calls) with lessons learnt
- User corrects you or shares a preference
- Discovering environment facts worth persisting

## Architecture

```
~/memory-index/           # Vault root (OBSIDIAN_VAULT_PATH)
├── index.md, log.md, schema.md  # Wiki navigation triad
├── facts/               # Technical facts, decisions, preferences
├── projects/            # Per-project context and notes
├── lessons/             # Date-stamped lessons (YYYY-MM-DD-slug.md)
├── infrastructure/      # Service configs, hardware, networking
├── models/              # Model catalog (sub-wiki: index/log/schema)
├── skill-graphs/        # Structured decision trees for skills
├── raw/                 # Immutable source material
│   ├── articles/        # Web articles, blog posts
│   ├── papers/          # Research papers, whitepapers
│   ├── transcripts/     # Voice transcripts, chat logs
│   └── assets/          # Images, diagrams, configs
└── *-tracker.md         # Multi-phase project trackers

    │
    │  vault_indexer.py (indexing) → restart rag-service after!
    v

ChromaDB (port 8001)     # Vector embeddings for semantic search
```

## Commands

### Search Memory (RAG)

```bash
# Semantic search across all indexed documents
curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "search query here", "n_results": 5}'
```

Returns JSON with:
- `documents`: Matching content
- `ids`: Document IDs
- `distances`: Similarity scores (lower = better match)
- `metadatas`: Source info, type, etc.

### Write Note to Obsidian

Every vault page requires YAML frontmatter. Full spec is in `~/memory-index/schema.md`.

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/memory-index}"

# Create fact note WITH frontmatter
cat > "$VAULT/facts/topic-name.md" << 'EOF'
---
title: "Topic Name"
created: 2026-04-07
updated: 2026-04-07
type: fact
tags: [technical-fact, m5, hardware]
sources: []
---
# Topic Name

Content here. Use markdown formatting.

## Section

- Bullet points
- Key information
EOF

# Create lesson note WITH frontmatter (date-stamped filename)
cat > "$VAULT/lessons/2026-04-07-topic.md" << 'EOF'
---
title: "Topic"
created: 2026-04-07
updated: 2026-04-07
type: lesson
tags: [lesson, debugging, configuration]
sources: []
---
# Lesson: Topic

## Context
What situation triggered this lesson.

## Solution
What worked.

## Key Takeaway
The actionable insight.
EOF

# Create project note WITH frontmatter
cat > "$VAULT/projects/project-name.md" << 'EOF'
---
title: "Project Name"
created: 2026-04-07
updated: 2026-04-07
type: project
tags: [project, active, trading]
sources: []
---
# Project Name

## Overview
Brief description.
EOF
```

### Index New/Updated Notes

```bash
# Index all folders (skips unchanged files)
~/llm-server/obsidian_ingest.py

# Force re-index everything
~/llm-server/obsidian_ingest.py --force

# Index specific folder
~/llm-server/obsidian_ingest.py --folder facts

# Check status
~/llm-server/obsidian_ingest.py --status
```

### Combined Write + Index

After writing a note, immediately index it:

```bash
# 1. Write the note
cat > "$VAULT/facts/new-fact.md" << 'EOF'
...content...
EOF

# 2. Index it
~/llm-server/obsidian_ingest.py --folder facts
```

## Response Format for Search Results

When presenting search results, format as:

```
Found N relevant documents:

1. [source-name] (distance: X.XX)
   > First 200 chars of content...

2. [source-name] (distance: X.XX)
   > First 200 chars of content...
```

## Best Practices

1. **Search first** - Check if information already exists before writing
2. **Frontmatter required** - Every page needs title, created, updated, type, tags, sources
3. **Tags from taxonomy** - Only use tags from the controlled vocabulary in schema.md
4. **Unique IDs** - Use descriptive filenames (e.g., `m5-setup.md`, not `note1.md`)
5. **Structured content** - Use headers, bullets, and markdown for readability
6. **Raw sources** - Put immutable source material in raw/, reference via sources field
7. **Incremental indexing** - Run ingest after writing to make content searchable
8. **Review existing** - Check `~/memory-index/facts/` and `~/memory-index/projects/` for context

## Example Workflow

### Storing a Lesson

```bash
# 1. Check if similar lesson exists
curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "chromadb venv broken symlink", "n_results": 3}'

# 2. Write the lesson
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/memory-index}"
cat > "$VAULT/lessons/2026-03-18-chromadb-venv-fix.md" << 'EOF'
# Lesson: Fixing Broken Python Venv Symlinks

## Context
RAG service failing with exit code 203 (EXEC) because venv python3 symlink
pointed to /usr/sbin/python3 instead of /usr/bin/python3.

## Solution
1. Check symlink: `ls -la venv/bin/python*`
2. Fix symlink: `rm venv/bin/python3 && ln -s /usr/bin/python3 venv/bin/python3`
3. Restore pip: `venv/bin/python -m ensurepip`
4. Reinstall deps: `venv/bin/pip install -r requirements.txt`
5. Restart service

## Key Takeaway
Python venv symlinks can break after system updates. Always verify the
target exists before debugging module import errors.
EOF

# 3. Index it
~/llm-server/obsidian_ingest.py --folder lessons
```

### Retrieving Context

```bash
# User asks: "What did we decide about ROCm on M5?"

curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "ROCr M5 kernel decision", "n_results": 3}'
```

## Multi-Collection Architecture

ChromaDB should hold two collections:

| Collection | Content | Purpose |
|------------|---------|---------|
| `memory-index` | Curated vault notes (facts, projects, lessons) | High-signal, human-quality knowledge |
| `sessions` | Raw user+assistant exchanges from session JSONL files | Full recall, catches anything not curated |

When querying, search both collections and merge. Curated notes rank higher (already distilled), but raw sessions catch anything that wasn't explicitly written up.

## Session Backfill

### JSONL Format

Hermes session files live in `~/.hermes/sessions/*.jsonl`. Each line is a JSON object:
- `role`: "session_meta" (tool schemas), "user", "assistant", "tool"
- `content`: text (string or list of content blocks)
- `model`, `platform`, `timestamp`: metadata

### Backfill Process (two layers)

**Layer 1 — Curated notes (manual, high quality):**
1. Read each session JSONL, extract substantive exchanges
2. Write structured markdown to vault (lessons/, facts/, projects/)
3. Re-index with `obsidian_ingest.py`

**Layer 2 — Raw session indexing (automated script):**
1. Parse all JSONL files, extract user+assistant text pairs (skip session_meta, tool calls)
2. Chunk into ~500-1000 token segments keeping conversational context
3. Add metadata: session_id, date, platform, model
4. Index into "sessions" collection in ChromaDB via POST to localhost:8001

### Querying Sessions Collection

```bash
# Search raw session history
curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "router preset fix", "n_results": 5, "collection": "sessions"}'
```

## LLM Wiki Pattern (Karpathy-style)

The vault IS a persistent, compounding knowledge wiki. Three navigation files govern it:

| File | Purpose | When to read |
|------|---------|-------------|
| `index.md` | Catalog of every page with one-line summaries and [[wikilinks]] | Start of any conversation involving vault content |
| `log.md` | Append-only chronological record of every vault mutation | To check what's new since last session |
| `schema.md` | Naming conventions, frontmatter rules, create/update/when-not-to-write, RAG integration reference | Before writing any new vault page |

**Directory structure:**
```
~/memory-index/
├── index.md, log.md, schema.md   # Wiki navigation (you are here)
├── facts/                        # Stable knowledge (decisions, preferences, technical)
├── lessons/                      # Date-stamped debugging/building records (YYYY-MM-DD-slug.md)
├── projects/                     # Per-project context and status
├── infrastructure/               # Service configs, hardware, networking
├── models/                       # Model catalog (has own sub-wiki with index/log/schema)
├── skill-graphs/                 # Structured decision trees for skills
├── raw/                          # Immutable source material (articles, papers, transcripts, assets)
└── *-tracker.md                  # Project trackers for multi-phase work
```

**Frontmatter:** Every page MUST have YAML frontmatter. No exceptions.

```yaml
---
title: "Page Title"
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: fact|lesson|project|infrastructure|model-ref|skill-graph|meta|raw
tags: [tag1, tag2]      # From controlled vocabulary in schema.md
sources: []             # [[raw/slug]] references or external URLs
---
```

**Tag taxonomy:** 5 categories defined in schema.md:
- Domain: rag, models, router, hardware, networking, trading, blockchain, deployment, agents, memory-system, tools, coding, voice, messaging
- Activity: debugging, setup, configuration, architecture, migration, performance, research, design, testing, automation
- Entity: service, llm, gguf, framework, protocol, platform, skill, decision, preference, technical-fact, lesson, project
- Status: active, complete, exploring, blocked, dormant, deprecated, recurring-issue
- Cross-cutting: security, m5, chromadb, llama-cpp, hermes, telegram, discord, vulkan, rocm

**Bulk frontmatter injection:** When adding frontmatter to many files at once, use execute_code with this pattern:

```python
from hermes_tools import read_file, write_file

def add_frontmatter(filepath, title, created, updated, ptype, tags):
    raw = read_file(filepath)["content"]
    # read_file returns content WITH line number prefixes — strip them
    lines = raw.split("\n")
    clean = []
    for line in lines:
        if "|" in line:
            parts = line.split("|", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                clean.append(parts[1])
            else:
                clean.append(line)
        else:
            clean.append(line)
    content = "\n".join(clean)
    if content.strip().startswith("---"):
        return  # already has frontmatter
    fm = f'---\ntitle: "{title}"\ncreated: {created}\nupdated: {updated}\ntype: {ptype}\ntags: [{", ".join(tags)}]\nsources: []\n---\n'
    write_file(filepath, fm + content)
```

**PITFALL:** When using hermes_tools read_file then write_file on the SAME file in execute_code, the second read_file call may return a caching message ("File unchanged since last read...") instead of actual content. This silently corrupts the file. Always verify the written file after, or avoid reading the same file twice in one execute_code block.

**Operations:**
- **Ingest**: new info → write page following schema.md → add to index.md → add to log.md → add wikilinks from related pages → reindex ChromaDB → restart rag-service
- **Query**: read index.md first → follow wikilinks to specific pages → or curl RAG for semantic search
- **Lint**: periodic health check for orphans, broken wikilinks, contradictions, stale claims

**Note**: rag_service.py uses lazy collection fetching (`get_collections()` per request) that auto-recovers from collection recreation on disk. Service restart after indexing is no longer strictly required, but cron jobs still do it as belt-and-suspenders (and to free any leaked memory from the long-running Flask process).

## Integration with Hermes Memory Tool

Three memory layers, each serving a different purpose:

| Tool | Use Case | Storage |
|------|----------|---------|
| `memory` | User preferences, quick facts | JSON in ~/.hermes/ |
| `obsidian-rag` | Long-form notes, projects, lessons | Markdown + ChromaDB |
| `session_search` | Recall specific past conversations | Session JSONL files |

Use `memory` for compact facts injected every turn. Use `obsidian-rag` for rich searchable documents. Use `session_search` when you need exact past exchanges.
