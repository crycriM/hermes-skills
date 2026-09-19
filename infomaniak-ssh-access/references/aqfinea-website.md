# Aqfinea Website Project

## Local Source
- Path: `~/projects/aqfinea-website/`
- Files: `index.html`, `styles.css`, `assets/aqfinea-og.png`

## Remote Mapping
| Local | Remote |
|-------|--------|
| `index.html` | `sites/aqfinea.net/index.html` |
| `styles.css` | `sites/aqfinea.net/styles.css` |
| `assets/aqfinea-og.png` | `sites/aqfinea.net/assets/aqfinea-og.png` |

## Tech Stack
- Static HTML + CSS (no framework, no build step)
- Google Fonts: Space Grotesk, Inter, JetBrains Mono
- Canvas animations (particle clustering, service section backgrounds)
- Formspree AJAX via `@formspree/ajax@1` CDN (form ID: `mgobjkzz`)
- Email obfuscation via JS (contact@aqfinea.net)

## Design Principles (from user feedback)
- **Visual weight consistency**: Audit card SVGs must use the SAME `.fig-frame` wrapper with window chrome (dots + label bar) as sections 1 & 2. Inline style: `style="max-width:340px;margin:1rem auto 1.25rem;"`. Bare SVGs or custom-sized containers look wrong.
- **Section padding**: Standard sections use `padding: 7rem 0`. Supplementary sections (FAQ, Contact) should NOT have padding overrides — they inherit from `.section`.
- **No decorative tags**: Avoid sub-numbering like "03a"/"03b" — use clean headings with subtle borders instead.
- **Font alignment**: FAQ headings should use `font-family: 'Inter', sans-serif` (not Space Grotesk), `font-weight: 500`, `color: var(--text)` to match service bullet terms. Earlier gold/Space-Grotesk styling was inconsistent.
- **Dark theme**: `--bg: #1a1a2e`, `--gold: #c9a227`, `--muted: #8a8aaa`

## Critical Layout Pitfall: `.main-content` Wrapper
The hero canvas is `position: fixed` with `z-index: 0`. The `.main-content` wrapper has `position: relative; z-index: 2; background: var(--bg)`. **All sections after the hero must be inside `.main-content`** — if the closing `</div>` comes too early (e.g. after About but before FAQ/Contact), those sections will be transparent and show the animated particles behind them, causing a "flashing" effect. Keep FAQ and Contact inside `.main-content`; only the footer goes outside it.

## Deploy-Verify Cycle
1. Patch local files (HTML/CSS)
2. **Upload via `terminal` Python heredoc** (not `execute_code` — paramiko unavailable there)
3. Check live site via `curl -s https://aqfinea.net | grep -A5 'audit-row' | head -40` (JinaReader/Tavily cache can serve stale content)
4. If issues: fix CSS/HTML locally → redeploy → re-verify

## Formspree Integration
- Form ID: `mgobjkzz`
- Method: AJAX via CDN (`@formspree/ajax@1`)
- Data attributes on form elements: `data-fs-field`, `data-fs-error`, `data-fs-submit-btn`, `data-fs-success`
- Init script: `formspree('initForm', { formElement: '#contact-form', formId: 'mgobjkzz' })`
- Endpoint sends to: contact@aqfinea.net

## Key Sections (v5 order — updated 2026-06-23)

**Section swap performed 2026-06-23**: Consulting and Audit swapped positions (nav, body, footer). Consulting is now 01, Audit is now 02.

1. Hero (canvas particle animation)
2. Consulting (01) — SVG: backtest vs live PnL chart in `.fig-frame`
3. Audit & Diagnostics (02) — "How We Find the Leak": method cards (Inputs/Outputs/Infrastructure) + two deliverable cards (Quant/Trading + AI/LLM), each with 4×4 mirrored rows + pipeline SVG in `.fig-frame`
4. Training (03) — SVG: orchestrator node graph in `.fig-frame`
5. About — Stats cards, LinkedIn link
6. FAQ — 4 questions in 2x2 grid
7. Contact — Formspree form with RGPD notice
8. Footer — Email, LinkedIn, services

### Content versioning
- `content-v4.md` — pre-merge layout (How It Works as standalone section, Audit as 03)
- `content-v5.md` — current: Consulting=01, Audit=02, 4×4 mirrored audit rows
- Nav order: Consulting, Audit, Training, About, FAQ, Contact
- Footer services: Consulting, Audit & Diagnostics, Training

### AI/LLM audit reframing principle
The AI audit rows must use integrity/attribution vocabulary (not MLOps/ops vocabulary).
The moat is one discipline, not two domains: "does the number survive contact with reality?"
Quant↔AI crosswalk: look-ahead→train/test leakage, survivorship→benchmark contamination,
overfit→eval-set memorization, backtest≠live→offline≠online, slippage→distribution shift.
"Production Hygiene" is a muted footnote under the AI column (`.audit-footnote`, opacity:0.4),
not a 5th bullet. See `references/ai-audit-positioning.md` for the full guideline.

### Audit card structure (4×4 mirrored rows with differentiated payoffs — v5.1, updated 2026-06-23)

The old bullet-list layout (5 AI bullets vs 4 Quant) was replaced with a 4+4 mirrored grid.
The parallelism lives in the **titles**, not in identical payoff sentences. Each domain gets
its own payoff. Each row has **three static lines**: bold title + gold payoff (always visible)
+ dim example line (always visible). No `<details>`, no "e.g." prefix — the examples are
unlabelled to avoid visual noise.

**Row pairing (Quant ↔ AI, differentiated payoffs):**
| Quant | Quant Payoff | AI | AI Payoff |
|-------|-------------|-----|----------|
| Data Integrity | The biases that inflate a backtest. | Eval Integrity | The contamination that inflates an eval. |
| Backtest vs. Live | Why live PnL drifts from research. | Offline vs. Online | Why production drifts from the eval set. |
| Execution & Latency | Where fills and milliseconds bleed alpha. | Prompt & Retrieval Risk | Where retrieval and prompts quietly fail. |
| Pipeline Architecture | Deterministic flows, reproducible results. | Output Reliability | Reproducible outputs, schema-safe, stress-tested. |

**CSS classes**: `.audit-rows`, `.audit-row`, `.audit-row-title`, `.audit-row-payoff`,
`.audit-row-examples` (dim static line, opacity:0.55, no "e.g."), `.audit-footnote`.
Rows use `border-left: 2px solid rgba(201,162,39,0.2)` as a visual divider.

**Key formatting rules (hard lessons):**
- NO `<details>` or `<summary>` — default browser triangles make the section heavier, not lighter.
  Static two-tier layout (title + payoff always visible + examples always visible in dim text)
  is lighter, scanable without interaction, and keeps 100% of content in-DOM for SEO.
- NO "e.g." prefix on the example line — repeating "e.g." 8× down the section turns it into
  visual noise. The context (bold title + payoff) makes it obvious the third line is examples.
- Differentiate payoffs per domain — identical sentences side-by-side read as a copy-paste bug,
  even if the table view looked clever. The parallelism lives in the titles, not verbatim copy.

### Large HTML restructure technique
When reordering sections in a single-file static site, use `execute_code` with Python
to read the file, find section markers, swap blocks, and write back. After writing, run
`scripts/verify-structure.py` to check structural integrity. The verify script checks
mirrored audit row titles (Quant: 4 rows, AI: 4 rows) and the Production Hygiene footnote.

When swapping sections: extract blocks by HTML comment markers, swap the blocks, then
renumber service labels (01/02/03) and update nav/footer link order. Don't forget to
update the hero "View Services" button href to point to the new first service section.

**When restructuring content (not just reordering):** update the verify script's expected
content (row titles, bullet terms, footnote text) before running — or the script will fail
on stale expectations and you'll chase false negatives during deploy.

### Live verification pitfall
Jina Reader and Tavily extract may cache/serve stale content. After deployment, verify
with direct `curl -s https://aqfinea.net | grep 'audit-row'` to confirm the live HTML
matches expectations. The direct curl check is reliable.