# Instructor SKILL.md Decomposition Plan

Original: ~/.hermes/skills/mlops/inference/instructor/SKILL.md (743 lines)
Strategy: 6 focused nodes, each under 150 lines, covering distinct aspects.

---

## Node 1: 01_overview_quickstart.md
**Title:** Overview & Quick Start
**Description:** Introduction to Instructor, when to use it, installation, and minimal working examples with both Anthropic and OpenAI.
**Original lines:** 1-87 (87 lines)
**Content:**
- Frontmatter / metadata
- "When to Use This Skill" (use cases, stats)
- Installation commands
- Quick Start: basic extraction with Anthropic Claude
- Quick Start: same with OpenAI
**Links to:** Node 2 (models), Node 4 (providers), Node 5 (patterns)

---

## Node 2: 02_response_models.md
**Title:** Pydantic Response Models
**Description:** Defining response schemas with Pydantic -- basic models, nested models, optional fields, and enum-constrained fields.
**Original lines:** 88-188 (101 lines)
**Content:**
- "Core Concepts" intro
- Section 1: Response Models (Pydantic)
  - Basic Model with Field descriptions
  - Nested Models (Address inside Person)
  - Optional Fields and defaults
  - Enums for constrained values (Sentiment)
**Links to:** Node 1 (quickstart), Node 3 (validation)

---

## Node 3: 03_validation_retry.md
**Title:** Validation & Automatic Retry
**Description:** Built-in and custom Pydantic validators, model-level validation, and how Instructor auto-retries on validation failure.
**Original lines:** 189-281 (93 lines)
**Content:**
- Section 2: Validation
  - Built-in validators (Field constraints, EmailStr, HttpUrl)
  - Custom field_validator examples (date format, positive int)
  - Model-level validation with @model_validator
- Section 3: Automatic Retrying
  - max_retries parameter
  - How retry loop works (LLM -> validate -> error feedback -> retry)
**Links to:** Node 2 (models), Node 6 (error handling)

---

## Node 4: 04_streaming_providers.md
**Title:** Streaming & Provider Configuration
**Description:** Streaming partial objects and iterables for real-time UI, plus configuring Instructor with Anthropic, OpenAI, and local/Ollama providers.
**Original lines:** 283-391 (109 lines)
**Content:**
- Section 4: Streaming
  - Streaming partial objects (create_partial)
  - Streaming iterables (create_iterable)
- Provider Configuration
  - Anthropic Claude setup
  - OpenAI setup
  - Local models via Ollama (instructor.Mode.JSON)
**Links to:** Node 1 (quickstart/install), Node 2 (models)

---

## Node 5: 05_common_patterns.md
**Title:** Common Patterns & Examples
**Description:** Ready-to-use patterns for data extraction, classification, multi-entity extraction, structured analysis, and batch processing.
**Original lines:** 393-524 (132 lines)
**Content:**
- Pattern 1: Data Extraction from Text (CompanyInfo)
- Pattern 2: Classification (Category enum + confidence)
- Pattern 3: Multi-Entity Extraction (people, orgs, locations)
- Pattern 4: Structured Analysis (sentiment with aspects)
- Pattern 5: Batch Processing (list comprehension over texts)
**Links to:** Node 2 (models), Node 3 (validation/retry)

---

## Node 6: 06_advanced_bestpractices.md
**Title:** Advanced Features, Best Practices & Reference
**Description:** Union types, dynamic models, custom modes, context management, error handling, best practices, and comparison to alternatives. **Note: original is 218 lines; condense by trimming verbose code blocks to under 150 lines.**
**Original lines:** 526-743 (218 lines -- requires condensation)
**Condensation strategy:**
- Keep Union Types, Dynamic Models, Custom Modes, Context Management examples as-is (~72 lines, 526-597)
- Error Handling: keep ValidationError try/except, drop the Config/examples block (lines 622-641) → saves ~20 lines
- Best Practices: keep all 5 tips but collapse code to minimal snippets → reduce ~64 lines to ~35
- Comparison table: keep as-is (~28 lines)
- Resources + See Also: keep as-is (~14 lines)
- Target: ~145 lines after condensation
**Content:**
- Advanced: Union Types, Dynamic Models, Custom Modes, Context Management
- Error Handling: ValidationError catching
- Best Practices (5 tips, condensed)
- Comparison table (Instructor vs alternatives)
- Resources & See Also links
**Links to:** Node 2 (models), Node 3 (validation), Node 4 (providers)

---

## Dependency Graph

```
Node 1 (Overview)
  ├──> Node 2 (Response Models)
  │       ├──> Node 3 (Validation & Retry)
  │       │       └──> Node 6 (Advanced/Errors)
  │       └──> Node 5 (Common Patterns)
  └──> Node 4 (Streaming & Providers)
```

## Summary

| Node | Filename                      | Lines     | Original Lines | Est. Size |
|------|-------------------------------|-----------|----------------|-----------|
| 1    | 01_overview_quickstart.md     | 1-87      | 87             | ~87       |
| 2    | 02_response_models.md         | 88-188    | 101            | ~101      |
| 3    | 03_validation_retry.md        | 189-281   | 93             | ~93       |
| 4    | 04_streaming_providers.md     | 283-391   | 109            | ~109      |
| 5    | 05_common_patterns.md         | 393-524   | 132            | ~132      |
| 6    | 06_advanced_bestpractices.md  | 526-743   | 218 (condense) | ~145      |

Total coverage: lines 1-743 (complete, with line 282 = blank separator absorbed)
All nodes under 150 lines (Node 6 requires condensation from 218 to ~145 lines).
