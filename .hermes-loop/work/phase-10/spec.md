# phase: phase-10

# Phase 10 Spec: Recall Memory Reliability

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`.

Read-order confirmation: `.hermes-loop/work/phase-10/context_bundle.md` was read first, followed by `.hermes-loop/work/phase-10/brainstorm.md`, then `.hermes-loop/work/phase-10/god_dispatch.json`, then the relevant Phase 9 evidence, MemoryOS recall/eval code, tests, and Letta design references named by the bundle.

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

decision=recommend_narrow_session_aware_recall_packets

## Chosen Design

Implement a narrow session-aware recall packet improvement inside the existing v3/public benchmark recall path:

- Keep SQLite store, episode backfill, v3 `ContextComposer`, public benchmark loading, answer projection, scoring, v1 fallback, and kernel default behavior unchanged.
- Extend `RecallMemorySearcher` only enough to select and annotate bounded evidence packets around real recall hits. A packet is an anchor hit plus same-`benchmark_session_id` neighbors already available through episode position and temporal metadata.
- Add bounded session diversification before top-k truncation only when entries carry `benchmark_session_id` and the caller explicitly requests session preservation. The intent is to keep weak but real same-session anchors from being crowded out by many high-overlap wrong-session hits.
- Carry packet metadata through `RecallPipeline`, v3 `ContextComposer`, `MemoryOSService._context_package_from_v3`, and public benchmark diagnostics using append-only metadata fields.
- Use Letta only as a semantic reference for passage-like evidence units, provenance/scope metadata, and component accounting. Do not add Letta as a runtime dependency and do not port Letta internals.

Rationale:

- Phase 9 showed 9 LoCoMo `session_localization_miss` cases and 3 broader `retrieval_miss` cases. The repeated failure shape is missing or wrong-session evidence before answer generation, not kernel execution.
- The brainstorm recommendation is directionally safe only if narrowed. A broad packet architecture or query-facet expansion would be easy to overfit. This phase should instead add the smallest packet semantics needed for source/session-auditable recall behavior.
- Existing v3 diagnostics already expose candidate, planned, selected, rendered, neighbor, and final-context trace data. The implementation should build on that rather than invent a separate reporting plane.

## Scope

In scope:

- `src/memoryos_lite/retrieval/episode_searcher.py`: direct-hit selection, same-session neighbor expansion guards, packet metadata on hits, and diagnostics for packet membership.
- `src/memoryos_lite/retrieval/recall_pipeline.py`: propagation of packet metadata into `ContextEvidence.metadata` and `ContextPackage.metadata`.
- `src/memoryos_lite/context_composer.py`: propagation of packet metadata into v3 recall layer items and component accounting.
- `src/memoryos_lite/engine.py`: preservation of packet metadata when converting v3 context packages into the public/eval `ContextPackage`.
- `src/memoryos_lite/public_benchmarks.py` and `src/memoryos_lite/public_case_diagnostics.py`: append-only exposure of packet/session diagnostics only if existing `v3_context.metadata` is insufficient for case-level reporting.
- Tests in `tests/test_episode_retrieval.py`, `tests/test_recall_pipeline.py`, and `tests/test_public_benchmarks.py`.
- Phase-local reports produced by execute/review lanes under `.hermes-loop/work/phase-10/`.

Out of scope:

- No answer prompt, answer projection, LLM judge, scoring semantic, or expected-answer logic changes.
- No `MEMORYOS_MEMORY_ARCH=v1` fallback changes.
- No default enablement of `MEMORYOS_RECALL_PIPELINE=v2` or `MEMORYOS_AGENT_KERNEL=v1`.
- No Letta dependency, Letta schema import, or broad rewrite into Letta architecture.
- No case-id, expected-source, expected-answer, benchmark-file-position, or fixed QA-string hacks.
- No production-readiness claim.
- No commits from this lane.

## Behavioral Contracts

Recall/session-localization reliability:

- A LoCoMo-like weak same-session direct anchor must remain eligible for selection even when multiple wrong sessions have stronger lexical overlap, provided the weak anchor has real token overlap and a `benchmark_session_id`.
- Session diversification is allowed only for recall entries with benchmark session metadata and only on the v3/public benchmark recall path that already requests neighbor preservation.
- Direct high-quality hits remain stable. A strong LongMemEval-like exact hit must stay first and rendered after session-aware packet behavior is enabled.
- Neighbor expansion must never cross `benchmark_session_id` when both anchor and neighbor have one.
- Packet children must be bounded by existing neighbor window settings: `memoryos_evidence_context_neighbors_before` and `memoryos_evidence_context_neighbors_after`.
- Packet behavior must not synthesize evidence. Every packet member must correspond to a stored message/episode and a real `SourceRef`.
- A recall improvement is usable only if at least one repeated LoCoMo retrieval/session class improves or is converted into a more precise downstream class through candidate, selected, rendered, or diagnostic movement.

## Data And Metadata Contracts

Evidence packet metadata on each planned recall evidence item:

- `evidence_packet_id`: deterministic string derived from anchor message id and packet session id.
- `packet_anchor_message_id`: message id of the direct hit that anchored the packet.
- `packet_session_id`: `benchmark_session_id` when available.
- `packet_member_message_ids`: ordered message ids included in the same packet and selected by the bounded packet rules.
- `packet_member_source_ids`: source ids for those message ids, when available.
- `packet_reason`: one of `direct_anchor`, `same_session_neighbor`, or `session_diversified_anchor`.
- `packet_rank_features`: rank features copied from the anchor plus packet-level fields.

Package/report metadata:

- `recall_evidence_packets`: append-only list of packet summaries with packet id, anchor id, member ids, session id, score, reason, and source refs.
- `recall_candidate_session_ids`: candidate benchmark sessions from recall hits before budget filtering.
- `recall_planned_session_ids`: benchmark sessions that survive into planned evidence.
- Existing fields remain authoritative and unchanged in meaning: `episode_candidate_message_ids`, `planned_evidence_message_ids`, `indexed_source_ids`, `v3_diagnostics`, `v3_final_context_trace`, `locomo_neighbor_diagnostics`, `source_hit`, `episode_source_hit_at_10`, and `planned_evidence_source_hit_at_5`.

Diagnostics:

- Packet diagnostics must use existing `DiagnosticEvent` shape with `layer="recall"`.
- Packet events should use reason codes such as `packet_anchor`, `packet_member`, `session_diversified_anchor`, and `neighbor`.
- Public reports must continue to separate retrieval/source movement from judged answer quality. `source_hit` remains final projection source overlap, not a pure retrieval-localization metric.
- If expected sources remain absent, diagnostics must make the remaining bottleneck visible as retrieval miss, selected-context miss, rendered-context miss, answer failure, or diagnostic gap.

## Anti-Overfitting Rules

- Do not branch on `conv-26`, `qa_003`, `qa_004`, `D1`, `D2`, expected answer strings, or expected source ids.
- Do not add LoCoMo-only lexical boosts for Caroline, Melanie, counseling, education, adoption, relationship, camping, pride, or other known failed-case terms.
- Do not promote evidence solely because it is expected by a benchmark row.
- Do not improve aggregate score by hiding pass-to-fail cases or changing failure classification semantics.
- Do not increase recall breadth without budget and LongMemEval guards.
- If a focused fixed-slice improvement cannot be explained case by case, treat it as insufficient for ACK.

## Test Acceptance Criteria

Before production changes:

- At least one RED test fails for a LoCoMo-like weak same-session anchor lost to stronger wrong-session lexical hits.
- At least one RED or existing regression guard proves unrelated session neighbors are not pulled in.
- At least one guard proves a LongMemEval-like strong direct hit remains stable.
- At least one public/v3 diagnostic test proves packet metadata is visible through the real public benchmark path.

Focused GREEN criteria:

- `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q` passes.
- `uv run pytest tests/test_public_benchmarks.py -q` passes.
- `uv run ruff check .` passes.

Baseline GREEN criteria:

- `uv run pytest -q` passes.
- `uv run ruff check .` passes.

## Eval Acceptance Criteria

Deterministic smoke:

- Run LoCoMo no-LLM fixed-slice diagnostics for repeated Phase 9 session-localization cases and record candidate, planned, selected, rendered, and packet movement.
- Produce case-level artifacts that list fail-to-pass, pass-to-fail, unchanged-fail, retrieval/source movement, failure-class movement, and explanation for every moved case.

Full-chain gate:

- Run LongMemEval 30 and LoCoMo 30 with `MEMORYOS_MEMORY_ARCH=v3`, `--llm-answer`, and `--llm-judge`.
- Use heartbeat files while long evals run:
  - `.hermes-loop/work/phase-10/eval_heartbeat_longmemeval.json`
  - `.hermes-loop/work/phase-10/eval_heartbeat_locomo.json`
- ACK is allowed only if LoCoMo 30 has same-case explainable signal, LongMemEval 30 has no material collapse, every pass-to-fail is listed with cause and disposition, kernel trace remains default-off unless explicitly enabled, and review confirms no overfitting.

If LLM provider access is unavailable, record the blocker, run deterministic no-LLM smoke, and do not mark the full-chain milestone gate satisfied.
