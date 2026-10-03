# Known Issues

This file tracks current limitations that are intentionally left for later
work. Historical phase notes have been removed from this baseline document.

## 1. v2 Recall and v3 Composer Are Defaults

Default behavior now uses `v3`.

- Episode indexing and v2 recall are enabled by default through
  `MEMORYOS_RECALL_PIPELINE=v2`; `v1` remains an explicit compatibility path.
- The v3 layered composer is the default memory architecture.
- `MEMORYOS_MEMORY_ARCH=v1` remains available as an explicit fallback.
- The kernel is `off` by default. `external` runs maintenance analysis in
  advisory-only mode, exposing source-backed proposals through
  `/sessions/{id}/advisories` for a host (such as xmuse) to accept or ignore
  without MemoryOS mutating its own authority. The in-process kernel
  execution stack was removed.

Why this is acceptable:

- Existing API/eval behavior stays stable when callers pin `v1`.
- v1 compatibility can still be evaluated explicitly without changing the default route.
- v3 public smoke now emits layered diagnostics and is the default path.

Future direction:

- Keep the kernel advisory-only; any broader adoption should wait for larger
  LongMemEval/LoCoMo slices and a host process that owns execution.

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

## 5. Curation Is Not an Agent Runtime

`/curate` runs a small LangGraph graph (extract, check, repair, consolidate)
for one request; `demo curate` runs it offline with a scripted LLM. It is not a
production agent runtime.

Current constraints:

- Real agent execution belongs to the host process (`MEMORYOS_AGENT_KERNEL=external`
  only emits advisories; `/curate` only returns memory versions).
- Real LLM usage is optional and requires explicit API keys.
- `/curate` keeps no state and no checkpoint: a request that times out on the
  caller side is simply sent again. Curation quality (missed lessons,
  over-merged lessons) is measured by ModuleMem, not guaranteed.
- The API supports only an optional single shared key (`MEMORYOS_API_KEY`,
  sent as `X-API-Key`; `/health` and `/metrics` stay open). Without the key it
  is unauthenticated. There is no per-user identity, rate limiting,
  multi-tenant ownership, or production error model.

Future direction:

- Treat agent behavior as a demo surface until memory retrieval quality is
  stable.
