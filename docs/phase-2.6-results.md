# Phase 2.6 Results — LongMemEval Retrieval Optimization

## Summary

Phase 2.6 optimized MemoryOS Lite's retrieval pipeline against LongMemEval (50-case manifest).
Final result: **source_hit 16% → 92%** through infrastructure fixes, not algorithmic changes.

## Progression

| Phase | Change | source_hit | Mechanism |
|-------|--------|-----------|-----------|
| 2.5 baseline | — | 16% (8/50) | Initial measurement |
| 2.6 budget fix | `_run_baseline` budget 90→4800 | 30% (15/50) | Eval infra bug |
| 2.6b metrics fix | session ID + field name | 30% | Visibility only |
| 2.6c fastembed | BM25→hybrid embedding | 30% | No gain |
| 2.6d budget ablation | 4800→8000 | 30% | No gain |
| Phase 3 iter 1 | rewrite+rerank+multi-query | 30% | No gain |
| 2.6e projection fix | include retrieved_message in sources | 92% (46/50) | Eval projection bug |

## Key Lessons

1. **page_source_overlap_at_k** (58%) = page retrieval recall (did the engine find the right page?)
2. **source_hit** (92%) = final retrieved evidence source coverage (did the right source enter context?)
3. The earlier 30% ceiling was an **eval projection artifact**: `_select_evidence` picked only 1 item
   (often a noise page summary), masking that the engine already retrieved the correct source.
4. Advanced RAG (query rewrite, multi-query expansion, LLM rerank, embedding) produced **zero gain**
   on this benchmark — the bottleneck was never retrieval quality.

## Remaining Failures (4/50)

| Case | Failure Mode | Root Cause |
|------|-------------|-----------|
| 58bf7951 | item_source_overlap_at_k_zero | Item search hits wrong session |
| 25e5aa4f | item_source_overlap_at_k_zero | Item search hits wrong session |
| 75499fd8 | promoted_but_budget_dropped | Evidence found but item budget cap |
| ccb36322 | page_source_overlap_at_k_zero | Page retrieval complete miss |

## Decision

- **Stop further LongMemEval tuning** to avoid overfitting to this benchmark.
- 92% source_hit with 0 regressions on hard eval is sufficient.
- **Move to Phase 3**: structured Think-Act-Observe demo with answer accuracy evaluation.
