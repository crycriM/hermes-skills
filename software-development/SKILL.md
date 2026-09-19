---
name: software-development
description: "Software development workflows: TDD, debugging, code review, planning, cleanup, refactoring, and subagent-driven development."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Software-Development, TDD, Debugging, Code-Review, Planning, Cleanup, Refactoring, Subagent, Testing]
    related_skills: [test-driven-development, systematic-debugging, simplify-code, codebase-cleanup, writing-plans, subagent-driven-development]
---

# Software Development

Software development workflows: TDD, debugging, code review, planning, cleanup, refactoring, and subagent-driven development.

## 1. Test-Driven Development (TDD)

Enforce RED-GREEN-REFACTOR cycle: write tests before code.

See: `references/test-driven-development.md`

## 2. Customizing ML Model Training

- **LambdaRank with Spearman Early Stopping**: Train LambdaRank models with
  early stopping on per-group Spearman CORR (the real-world metric) instead of
  the built-in NDCG training metric. Uses `feval` to inject a custom evaluation
  function and disables built-in metrics so early stopping fires on Spearman.
  Valid for any ranking problem where evaluation != NDCG.

See: `references/lambdarank-spearman-early-stop.md`

## 3. Systematic Debugging

4-phase root cause debugging: understand bugs before fixing.

See: `references/systematic-debugging.md`

## 4. Code Review & Requesting

- **Requesting Code Review**: How to request and receive code reviews
- **Simplify Code**: Parallel 3-agent cleanup of recent code changes

See: `references/requesting-code-review.md`
See: `references/simplify-code.md`

## 5. Planning & Design

- **Writing Plans**: Structured planning for software projects
- **Design Doc with Review**: Design document creation and review workflow

See: `references/writing-plans.md`
See: `references/design-doc-with-review.md`

## 6. Codebase Management

- **Codebase Cleanup**: Systematic codebase audit and cleanup — review, plan, and execute in phases
- **Codebase Skeleton**: Project skeleton creation
- **Build System Pitfalls**: Common CMake / C++ build pitfalls discovered during scaffold

See: `references/codebase-cleanup.md`
See: `references/codebase-skeleton.md`
See: `references/build-system-pitfalls.md`

## 7. C++ Numerical Development

- **CppAD Template Pitfalls**: `operator==` on `CppAD::AD<double>` returns `AD<bool>`, not `bool` — corrupts AD tapes in templated code. Fix: overloaded extractor with `CppAD::Value()`. Also covers Jacobian via Reverse (per-column vs projected), `CppAD::Value()` assertion on independent variables, FD-noise-safe Jacobian comparison, logistic shrinkage formula, and DLV boundary conditions for mass conservation.

See: `references/cppad-template-pitfalls.md`

## 8. Subagent-Driven Development

Delegate tasks to subagents for parallel development work.

See: `references/subagent-driven-development.md`

## 9. Local Model Code Generation

Use local llama.cpp model's OpenAI-compatible API for code generation.

See: `references/local-model-codegen.md`

## 10. Hermes-Specific Development

- **Hermes Agent Skill Authoring**: Writing and managing Hermes skills
- **Hermes Model Debugging**: Debugging models within Hermes
- **Hermes S6 Container Supervision**: Container supervision for Hermes
- **Hermes Task Management**: Task management within Hermes
- **Debugging Hermes TUI Commands**: TUI command debugging
- **Python Debugpy**: Python debugging with debugpy
- **Node Inspect Debugger**: Node.js debugging
- **Async Migration Sync Compat**: Async migration compatibility
- **Implementation Audit**: Codebase implementation auditing
- **Spike**: Rapid prototyping and exploration

See: `references/hermes-agent-skill-authoring.md`
See: `references/hermes-model-debugging.md`
See: `references/hermes-s6-container-supervision.md`
See: `references/hermes-task-management.md`
See: `references/debugging-hermes-tui-commands.md`
See: `references/python-debugpy.md`
See: `references/node-inspect-debugger.md`
See: `references/async-migration-sync-compat.md`
See: `references/implementation-audit.md`
See: `references/spike.md`

## 11. FastAPI Dashboard

Build a data-driven web dashboard with FastAPI + Jinja2 templates + Chart.js.

See: `references/fastapi-jinja-dashboard.md`

## 12. Open-Core / Plugin Architecture

Split a monolithic open-core module into a stable protocol + naive default
(open core) + sophisticated implementation (proprietary plugin). Covers
boundary identification, protocol stability, registry defaults, language tier
decision (Python vs C++), separate-repo layout, doc updates, and test
restructuring.

See: `references/open-core-plugin-split.md`
