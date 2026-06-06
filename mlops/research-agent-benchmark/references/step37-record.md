# step37 (Step-3.7-Flash IQ4_XS) — Research Bench Record

## Result: Composite 1.035 (new record, beats minimax27's 0.990)

Run: 2026-05-31, 2022s (~34 min), 25 tool calls (9 arxiv, 5 ssrn, 2 web, 9 fetch).

## Key metrics

| Metric | Score | Note |
|--------|-------|------|
| Composite | **1.035** | Highest ever recorded |
| Coverage | 1.76 | 72 sources vs 41 in reference |
| Source overlap (Jaccard) | 0.286 | Good overlap |
| Citation validity | 0.80 (8/10) | 2 unverified, 1 suspect |
| Specificity | 4/5 | 10 methods, 3 datasets named |
| Implementation depth | **5/5** | Pipeline + params + complexity + code |
| Hallucination | **0.0** | No fabricated sources |
| Novel sources | 4 | Papers not in reference |
| Output | 16087 chars | Structured markdown with sections |

## Paper lineage discovered

ROCKET (1910.13051) → MiniRocket (2012.08791) → MultiRocket (2102.00457) → HYDRA (2203.13652) → S-Rocket (2203.03445) → SPROCKET (2512.08246)

All core papers fetched and summarized. The model also found interpretable kernel learning (Chen 2024), kernel HMM, and dynamical systems papers.

## Deliverable structure

1. Sources table (15 sources, properly formatted)
2. Detailed article summaries per paper
3. Implementation guidelines with code skeleton
4. Kernel parameter choices and their effects
5. Computational complexity analysis
6. Approach selection guide by use case (univariate, multivariate, seasonal, irregular, edge, financial)
7. Practical recommendations

## key observation

step37 was the first model to systematically search AND fetch ALL core papers in the ROCKET lineage before synthesizing. Previous models either fetched partial sets (qwopus35-27b), grabbed wrong papers (cascade2-30b), or relied on abstracts only (holo3-35b). The combination of thorough search + disciplined paper fetching + zero hallucination is unique.
