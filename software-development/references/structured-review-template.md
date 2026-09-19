# Structured Review Feedback Template

Use this template when providing review feedback on architecture/design documents. The header structure ensures every review covers the same dimensions, making it easy for the implementer to process changes systematically.

Reviews commonly come in **two passes**: a Polish Pass (document structure, clarity, visuals) and a Strategic Pass (decision points, parameters, trade-offs). The template covers both.

## Review Format — Polish Pass

```markdown
## Recommendations

### Proposed Changes (by section)
- **Section X.Y**: [specific edit description — e.g., "Render formula as LaTeX", "Rewrite paragraph Y"]

### System Flow Visualization
- Specific sections that would benefit from a Mermaid.js diagram (flowchart, state diagram, sequence diagram)

### Edge Case Coverage
- Gaps identified in the current draft (e.g., "Section X covers normal operation but doesn't define what happens when Y fails")
- Proposed new sections with scope

### Specification Clarity
- Sections that bury their rationale — e.g., "Section 9.4 describes the flow but doesn't state WHY an AI agent would use this"

### Polish Pass (Markdown Improvements)
- Refined versions of key sections showing:
  - Callout blocks (`> [!IMPORTANT]`, `> [!WARNING]`, `> [!NOTE]`)
  - LaTeX inline/block formulas (`$...$` / `$$...$$`)
  - Tables with icon columns (🟢🟡⚪ for status, 🟠🟢🔴 for risk)
  - Column relabeling for scannability (e.g., "Rationale" → "Strategy Focus")

### Technical Fixes
- Auth consistency (e.g., "Ensure Bot API doesn't use cookies — CSRF risk for bot devs")
- Rate limiting annotations (e.g., "Tag backtesting endpoints as Resource Intensive")
- Timestamp precision conventions (e.g., "Upgrade ISO-8601 to millisecond precision")
- Naming or API contract consistency checks
```

## Review Format — Strategic / Architectural Decisions Pass

After the document is structurally sound, a second review pass fills in deferred decisions, parameter calibrations, and deployment strategy. These are the "levers" that the spec deliberately left open.

```markdown
## Strategic Decisions & Parameter Calibration

### 1. Parameter Sensitivity Analysis
- **What:** [e.g., CLS weights, scoring thresholds, turnover caps]
- **Proposed default:** [current values in spec]
- **Alternative considered:** [proposed change with rationale]
- **Recommended action:** [backtest recommendation, decision rule, or conditional adoption]

### 2. Boundary Condition Definitions
- **What:** [e.g., regime classifier labels, suspension thresholds]
- **Problem:** The spec defines categories but not how to seed them during training
- **Proposed initial labels:** [table of human-in-the-loop thresholds]
- **Migration path:** [when to switch from hard labels to self-supervised learning]

### 3. Deployment / Migration Strategy
- **What:** [e.g., which perimeter to launch with, which features to gate]
- **Proposed approach:** [conservative launch with conditions for expansion]
- **Risk addressed:** [specific failure mode the conservative approach avoids]
- **Migration gate:** [measurable condition that must be met before expanding]

### 4. Pricing / Economic Model Calibration
- **What:** [e.g., per-query pricing, tier thresholds]
- **Proposed model:** [value-capture, cost-plus, or competitive benchmark]
- **Math:** [concrete calculation showing monthly cost at expected usage levels]
- **Design rationale:** [how the pricing makes one tier the rational choice vs. another]
```

## Combining Passes

When both polish and strategic feedback arrive together:

1. **Apply polish first** — diagrams, callouts, LaTeX, edge cases, technical fixes. These are self-contained and don't affect architectural decisions.
2. **Apply strategic decisions second** — parameters, thresholds, deployment plans. These change the substance, so they go in after the document reads well.
3. **Use `todo` tracking** for multi-pass work to avoid dropping items between passes.

## Example

See `mvp_architecture_trd.md` at `~/projects/action-plans/business-plan/rankit/` for a worked example where this format was used to apply 11 polish improvements + 5 strategic decisions across two passes in a single session.
