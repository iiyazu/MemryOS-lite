# Public Benchmark Diagnosis

This document records the current benchmark interpretation for MemoryOS Lite.
It is a baseline note, not a full history log.

## Current Positioning

MemoryOS Lite is an eval-driven, source-attributed Agent/RAG memory prototype.
The current default path is `v3`; `v1` remains an explicit fallback, and
episode-first recall is still available with `MEMORYOS_RECALL_PIPELINE=v2`.

The benchmark goal for the current phase is evidence recall and diagnostic
clarity. Answer pass rate is tracked separately because answer quality can fail
even when the right source message is available.

## Baseline Metrics

Verified current local baseline:

| Check | Result |
|---|---:|
| Full pytest | `352 passed, 1 warning` |
| Hard eval, `memoryos_lite` | `accuracy 1.00`, `source_hit 1.00` |

v2 public smoke, no LLM answer/judge:

| Benchmark | Cases | `item_source_hit_at_10` | `episode_source_hit_at_10` | `planned_evidence_source_hit_at_5` | `budget_dropped_relevant` | `source_not_indexed` |
|---|---:|---:|---:|---:|---:|---:|
| LongMemEval | 10 | 0/10 | 8/10 | 8/10 | 0 | 0/10 |
| LoCoMo | 10 | 0/10 | 5/10 | 5/10 | 0 | 0/10 |

v3 public smoke, no LLM answer/judge:

| Benchmark | Cases | Status |
|---|---:|---|
| LongMemEval | 10 | report includes `memory_arch`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics` |
| LoCoMo | 10 | report includes `memory_arch`, `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics` |

Commands:

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite

MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge

MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge

MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

## Metric Scope

Use the metrics for different questions:

| Metric | Meaning |
|---|---|
| `episode_source_hit_at_10` | Did raw-message episode retrieval find the expected source? |
| `planned_evidence_source_hit_at_5` | Did evidence planning keep the source near the top? |
| `budget_dropped_relevant` | Was a relevant planned source dropped by context budget? |
| `source_not_indexed` | Was the expected source absent from the v2 indexed source set? |
| `v3_layer_counts` | Which v3 layers contributed selected context items? |
| `v3_budget_decisions` | Which v3 layers fit or dropped items under budget? |
| `v3_diagnostics` | Per-item v3 inclusion/drop reason, score, tokens, and source refs. |
| `source_hit` | Final deterministic source projection; useful, but not pure retrieval localization. |

Do not use page-level overlap or final projected `source_hit` alone as proof
that the evidence-first path localized a specific message. For v2 recall
progress, prefer `episode_source_hit_at_10`,
`planned_evidence_source_hit_at_5`, and `budget_dropped_relevant`.

## Open Limitations

- The smoke results are only 10-case checks. Larger fixed slices are needed
  before claiming benchmark improvement.
- `item_source_hit_at_10` is currently zero in the smoke runs because Phase 1
  treats existing page-derived items as supporting diagnostics, not the success
  gate.
- LoCoMo remains harder than LongMemEval. Current work improves raw evidence
  access, but answer quality and multi-hop reasoning still need later phases.
- Real LLM answer/judge runs are optional and should be reported separately
  from retrieval-only diagnostics.
