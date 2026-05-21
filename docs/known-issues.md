# Known Issues

This file tracks current limitations that are intentionally left for later
work. Historical phase notes have been removed from this baseline document.

## 1. v2 Recall And v3 Composer Are Opt-In

Default behavior remains `v1`.

- Episode indexing and v2 recall are enabled only when
  `MEMORYOS_RECALL_PIPELINE=v2`.
- The v3 layered composer is enabled only when `MEMORYOS_MEMORY_ARCH=v3`.
- The v3 kernel is enabled only when `MEMORYOS_AGENT_KERNEL=v1`.

Why this is acceptable:

- Existing API/eval behavior stays stable.
- v2 can be evaluated without changing default persistence or trace behavior.
- v3 public smoke now emits layered diagnostics, but the evidence is not strong
  enough to promote v3 to default.

Future direction:

- Promote v2/v3 only after larger LongMemEval/LoCoMo slices show stable gains
  and answer-quality regressions are understood.

## 2. LoCoMo Remains Hard

Current v2 smoke improves raw episode evidence access, but LoCoMo still trails
LongMemEval:

- LongMemEval smoke: `episode_source_hit_at_10 = 8/10`.
- LoCoMo smoke: `episode_source_hit_at_10 = 5/10`.

Likely causes:

- Multi-session reasoning needs better evidence planning and neighbor policy.
- Answer generation may not use retrieved evidence reliably.
- Some cases need temporal/session-aware reasoning beyond BM25 episode search.

Future direction:

- Add larger fixed v2 eval slices.
- Improve evidence planner ordering and context packing before adding broader
  memory layers.

## 3. Items Are Supporting Diagnostics In Phase 1

`MemoryItem` exists, but current v2 success is gated on raw episode/planned
evidence metrics. In the latest smoke, `item_source_hit_at_10 = 0/10`.

Why this is acceptable:

- Phase 1 deliberately prioritizes source-grounded raw evidence.
- Page-derived items remain useful for support and future semantic retrieval.

Future direction:

- Revisit item extraction/search after episode recall and context packing are
  stable.

## 4. Public `source_hit` Is Not Pure Retrieval Localization

Public benchmark reports include several source metrics. Final `source_hit` can
mix projected answer/source attribution with context evidence, so it should not
be the only gate for evidence-first recall.

Preferred v2 metrics:

- `episode_source_hit_at_10`
- `planned_evidence_source_hit_at_5`
- `budget_dropped_relevant`
- `source_not_indexed`

Preferred v3 report fields:

- `memory_arch`
- `v3_layer_counts`
- `v3_budget_decisions`
- `v3_diagnostics`

Future direction:

- Keep final answer/source projection separate from retrieval-only diagnostics.

## 5. Agent Demo Is Experimental

The LangGraph path demonstrates Think-Act-Observe style memory control, but it
is not a production agent runtime.

Current constraints:

- Scripted/fake paths are used for deterministic demos and tests.
- Real LLM usage is optional and requires explicit API keys.
- The API has no auth, rate limiting, multi-tenant ownership, or production
  error model.

Future direction:

- Treat agent behavior as a demo surface until memory retrieval quality is
  stable.
