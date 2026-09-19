# AI/LLM Audit Positioning — Integrity, Not MLOps

## Core Problem

The AI audit bullets read generic when written in operations vocabulary (experiment tracking,
model registry, data versioning, CI/CD) — the language of every platform shop (MLflow, W&B,
Evidently, Arize). The quant bullets read differentiated because they use integrity/attribution
vocabulary (look-ahead, survivorship, backtest-vs-live decomposition). Same author, two
disciplines. Fix the framing, not the scope.

## The Moat

Generic MLOps answers "does the pipeline run reliably?"
Aqfinea answers "does the number in the report survive contact with reality?"

Position as: the validation standards of money, applied to AI — not "we also do MLOps."

## Key Decision: Emphasize, Don't Split

Two offerings let the AI track drift back to commodity MLOps. Keep one method / two domains
so the quant rigor stays the through-line. Quant = proof-of-rigor; AI = the larger market
that rigor unlocks.

## Quant↔AI Crosswalk (the differentiation)

| Quant integrity failure | AI analogue (reframe as this) |
|--------------------------|-------------------------------|
| Look-ahead contamination | Train/test leakage, temporal contamination |
| Survivorship bias | Eval-set selection bias; benchmark contamination (test data in pretraining) |
| Overfit to backtest | Eval-set memorization / benchmark gaming |
| Backtest ≠ live PnL | Offline metric ≠ online behavior (the eval–prod gap) |
| Slippage / execution decay | Distribution shift, embedding drift, latency/cost drift in prod |

## Two Anti-MLOps Assets

1. **Delivery = forensic diagnostic report, then you leave.** "What you do afterward is your
   business" vs. MLOps shops that embed and run your platform.
2. **0 access to weights/alpha** — black-box, metrics-only auditing. Trust-building and unusual;
   commodity MLOps needs deep access.

## Supporting Evidence

- Kapoor & Narayanan, "Leakage and the Reproducibility Crisis in ML-based Science," Patterns (2023)
- The routine finding that benchmark/data contamination inflates LLM eval scores
- Tooling vendors don't assess this — it requires knowing how metrics lie, not how to wire a registry

## Rewritten AI-Audit Rows (integrity vocabulary — 4×4 mirrored, updated 2026-06-23)

The old 5-bullet list was restructured into 4 mirrored rows paired with the Quant column.
Each row: **bold title + gold payoff line (always visible) + dim example line (always visible)**.
No `<details>`/disclosure — static two-tier keeps the section light and scannable while
keeping all keywords in-DOM for SEO.

1. **Eval Integrity** — Payoff: "The contamination that inflates an eval."
   Examples: train/test leakage, temporal contamination, benchmark data bleeding into
   pretraining, eval-set memorization.

2. **Offline vs. Online** — Payoff: "Why production drifts from the eval set."
   Examples: distribution shift, eval–prod mismatch, prompts/contexts the benchmark never saw.

3. **Prompt & Retrieval Risk** — Payoff: "Where retrieval and prompts quietly fail."
   Examples: prompt-injection surface, context-window overflow, RAG similarity decay,
   embedding drift across model versions.

4. **Output Reliability** — Payoff: "Reproducible outputs, schema-safe, stress-tested."
   Examples: hallucination-rate benchmarking, schema-validation failures, token-cost drift,
   reproducibility across inference runs.

**Production Hygiene** — demoted from a 5th bullet to a muted footnote (`.audit-footnote`,
opacity:0.4) under the AI four: "Plus production hygiene — experiment tracking, registry,
versioning, CI/CD determinism — as baseline, not headline."

## Mirror Titles with Differentiated Payoffs (Quant ↔ AI)

The parallelism lives in the **titles** (Data Integrity ↔ Eval Integrity), not in identical
sentences. Each domain gets its own payoff line so the columns don't read as copy-paste
side-by-side.

| Quant | Quant Payoff | AI | AI Payoff | Shared Concept |
|-------|-------------|-----|----------|----------------|
| Data Integrity | The biases that inflate a backtest. | Eval Integrity | The contamination that inflates an eval. | Integrity |
| Backtest vs. Live | Why live PnL drifts from research. | Offline vs. Online | Why production drifts from the eval set. | The gap |
| Execution & Latency | Where fills and milliseconds bleed alpha. | Prompt & Retrieval Risk | Where retrieval and prompts quietly fail. | In transit |
| Pipeline Architecture | Deterministic flows, reproducible results. | Output Reliability | Reproducible outputs, schema-safe, stress-tested. | Reliability |

Rows 1–2 mirror concept-for-concept, making "one discipline, two domains" legible at a glance.
Row 3 maps execution latency (quant) → retrieval latency/risk (AI). Row 4 maps pipeline
determinism (quant) → output reliability (AI). The titles mirror; the payoffs differentiate.

## Formatting Rules (hard-won)

- Each audit row = three lines: bold title (`.audit-row-title`), gold payoff (`.audit-row-payoff`),
  dim example line (`.audit-row-examples`, opacity:0.55, no "e.g." prefix — repeats as visual noise 8×)
- No `<details>`, no `<summary>`, no default browser triangles. Static always-visible layout
  is lighter and the examples remain scannable without interaction.
- No "e.g." prefix on the example line — the context makes it obvious, and repeating "e.g." 8×
  down the section turns it into visual noise.

## What Was Removed

- "MLOps & Reproducibility" as a headline bullet. The word "MLOps" anchors to the red ocean
  of commodity platform shops. If retained at all, it must be folded into a single
  de-emphasized line that doesn't lead.
- `<details>` disclosure pattern (replaced with static two-tier, lighter and no triangle noise)
- "e.g." prefix on example lines (redundant 8× repetition — context alone makes it clear)
- Identical payoff sentences across both columns (parallelism lives in titles, not verbatim copy)
