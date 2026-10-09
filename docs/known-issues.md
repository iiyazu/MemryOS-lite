# Known Issues

This file tracks current limitations that are intentionally left for later
work. Historical phase notes have been removed from this baseline document.

## 1. One Context Path: v3 Composer Over v2 Recall

- Episode indexing and v2 recall always run; the v3 layered composer builds
  every context package.
- The v1 architecture (pages, items, paging, conflict detection) was removed,
  so v1 results recorded earlier cannot be re-run.

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

## 3. Public `source_hit` Is Not Pure Retrieval Localization

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

## 4. Curation Is Not an Agent Runtime

`/curate` runs a small LangGraph graph (extract, check, repair, consolidate)
for one request; `demo curate` runs it offline with a scripted LLM. It is not a
production agent runtime.

Current constraints:

- Real agent execution belongs to the host process (`/curate` only returns memory
  versions for the host to store).
- Real LLM usage is optional and requires explicit API keys.
- `/curate` keeps no state and no checkpoint: a request that times out on the
  caller side is simply sent again. Curation quality (missed lessons,
  over-merged lessons) is measured by ModuleMem, not guaranteed.
- The API supports only an optional single shared key (`MEMORYOS_API_KEY`,
  sent as `X-API-Key`; `/health` stays open). Without the key it
  is unauthenticated. There is no per-user identity, rate limiting,
  multi-tenant ownership, or production error model.

Future direction:

- Treat agent behavior as a demo surface until memory retrieval quality is
  stable.
