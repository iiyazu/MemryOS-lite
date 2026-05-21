# phase: phase-1

# Final Contract Plan - Phase 1 Letta Gap Matrix And Contract Decisions

Status: APPROVED for phase-1 contract completion.

This is the final plan-lane contract for Phase 1. It is not an implementation plan for Phase 3, does not direct Phase 1 code/test/docs/benchmark/state/blueprint edits, and does not claim benchmark improvement. It converts the Letta comparison and MemoryOS Phase 0 diagnostics into MemoryOS-native contracts that later phases can turn into RED tests and implementation work.

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Source Of Truth

- `context_bundle.md` defines Phase 1 as contract and evidence planning only.
- `god_dispatch.json` binds the phase to LongMemEval/LoCoMo separation, no Letta runtime, explicit v1 fallback, v3 default verification, and kernel opt-in.
- `research.md` supplies the Letta/MemoryOS observations and separates sampled LongMemEval answer-use pressure from sampled LoCoMo retrieval/scope pressure.
- `letta_gap_matrix.md` is the execute-lane matrix of MemoryOS current behavior, Letta reference behavior, gaps, benchmark impact, priorities, proposed contracts, and future RED anchors.
- `brainstorm.md`, `spec.md`, and `plan.md` provide the approved split-P0 contract route.

## Approved Route

Use the split P0 contract route by observed failure mode:

```text
default v3 route and public case taxonomy
  -> LoCoMo archive scope and passage-role contracts
  -> LongMemEval answer citation and unsupported-answer contracts
  -> rendered evidence survival diagnostics
  -> P1 core-memory/kernel/accounting extensions only after P0 RED tests exist
```

This route borrows Letta semantics selectively: bounded core blocks, archive attachment/scope, passage role and source auditability, selected evidence citation, component accounting, and traceable tool mutation. It rejects a broad Letta port and rejects Letta as a runtime dependency.

## P0 Contracts For Later Phases

### 1. Default v3 Route And v1 Fallback

The real service/public benchmark path must emit v3 diagnostics by default without requiring callers to set `MEMORYOS_MEMORY_ARCH=v3`.

Explicit `MEMORYOS_MEMORY_ARCH=v1` must remain a working fallback and must not masquerade as v3 composer output.

The v3 kernel remains off unless `MEMORYOS_AGENT_KERNEL=v1` is explicitly set.

Future RED anchors:

- `tests/test_public_benchmarks.py::test_default_public_eval_emits_v3_diagnostics_without_memory_arch_env`
- `tests/test_public_benchmarks.py::test_explicit_v1_public_eval_preserves_v1_fallback`

### 2. Public Case-Level Taxonomy

Public benchmark output must keep case-level status visible and must not let aggregate score movement hide regressions.

Required status vocabulary:

- `retrieval_miss`
- `evidence_hit_answer_fail`
- `unsupported_answer`
- `supported_cited_answer`
- `pass` where applicable

`source_hit` remains final projection/source overlap, not pure evidence localization.

Future RED anchors:

- `tests/test_public_benchmarks.py::test_case_level_taxonomy_separates_retrieval_miss_from_answer_fail`
- `tests/test_public_benchmarks.py::test_source_hit_is_reported_as_projection_overlap_not_evidence_localization`
- Phase 0 case anchors across LongMemEval and LoCoMo.

### 3. Archive Attachment Scope

v3 archival retrieval must derive eligible archive scope from session, agent, project, or source attachments when scoped archives exist.

Silent global archival retrieval is not acceptable once attached archive records exist. If no eligible scope exists, diagnostics must state whether retrieval was skipped, explicit global fallback was allowed, or no archive scope was available.

Future RED anchors:

- `tests/test_context_composer.py::test_archival_layer_uses_attached_archive_scope_before_global_matches`
- `tests/test_archival_searcher.py::test_archival_search_requires_explicit_global_fallback_when_scope_exists`
- LoCoMo retrieval/scope anchors: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

### 4. Passage Source-Vs-Agent Role

Every benchmark-eligible v3 passage must declare whether it is source-backed evidence or agent-written archival memory.

Agent-written memory may assist retrieval, but it cannot satisfy source-grounded benchmark evidence unless it carries source refs to the original source/message. Mixed or ambiguous source/agent passage role must be rejected or diagnosed before public evidence metrics consume it.

Future RED anchors:

- `tests/test_v3_contracts.py::test_archival_passage_requires_unambiguous_benchmark_evidence_role`
- public diagnostic test separating source-backed evidence from agent-written memory.
- LoCoMo retrieval/scope anchors and LongMemEval `51a45a95` as a source-overlap-not-enough guard.

### 5. Answer Citation And Unsupported Behavior

A supported public answer must cite selected evidence ids and source ids.

Empty, missing, or insufficient selected evidence must produce an explicit unsupported/refusal artifact instead of uncited content.

`source_hit=true` is not proof of answer support.

Future RED anchors:

- `tests/test_public_benchmarks.py::test_answer_artifact_requires_selected_evidence_citations_for_supported_answer`
- `tests/test_public_benchmarks.py::test_empty_or_insufficient_selected_evidence_is_unsupported`
- LongMemEval evidence-hit-answer-fail anchors: `e47becba`, `118b2229`, `51a45a95`.
- LoCoMo evidence-hit-answer-fail anchor: `conv-26_qa_001`.
- Retrieval-miss guards: `58bf7951`, `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

### 6. Rendered Evidence Survival

Future answer artifacts must expose whether selected evidence ids survived into the rendered answer prompt/context component used by the answerer.

Diagnostics must distinguish selected context items from rendered answer-prompt evidence and must list included and dropped selected evidence ids with reasons.

Future RED anchors:

- `tests/test_context_composer.py::test_rendered_answer_context_reports_selected_evidence_ids_included_and_dropped`
- public benchmark report test proving rendered evidence inclusion is emitted per case.
- LongMemEval `e47becba`, `118b2229`, `51a45a95`.
- LoCoMo `conv-26_qa_001`.

## P1 Reservations

These are approved as later reservations, not P0 gates and not Phase 1 implementation work:

- Core-memory write policy: add explicit read-only or write-policy semantics before kernel core-memory mutation expands; source-backed or approved provenance remains mandatory.
- Rendered component accounting: extend current v3 layer budget diagnostics with rendered component token estimates after P0 evidence-survival exists.
- Opt-in kernel/tool result expansion: keep kernel tooling opt-in; future v3 memory mutation through tools must emit trace events, approval state, source refs, and tool result diagnostics; legacy v1 page/item tools must not be presented as v3 source-backed kernel tools.

## Benchmark Binding

LongMemEval must remain separated from LoCoMo:

- LongMemEval evidence-hit-answer-fail: `e47becba`, `118b2229`, `51a45a95`.
- LongMemEval retrieval miss: `58bf7951`.
- LongMemEval stable pass: `1e043500`.
- LoCoMo evidence-hit-answer-fail: `conv-26_qa_001`.
- LoCoMo retrieval/scope misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.

Answer/citation work must not reclassify retrieval misses as solved until evidence is recovered. Retrieval/scope work must not claim benchmark usability unless answer-use and citation failures remain visible at case level.

## Constraints

- No Letta runtime dependency, imports, schema inheritance, manager reuse, service reuse, database provider reuse, or agent runtime reuse.
- No benchmark case-id rules, expected-answer leaks, or dataset-specific string hacks.
- No default kernel enablement.
- No removal of v1 fallback.
- No aggregate-only benchmark claims.
- No prompt-only architecture claims unless selected-evidence citation and case-level support diagnostics prove the answer path used the evidence.
- No Phase 1 edits to `src/`, `tests/`, `docs/`, `alembic/`, benchmark data, `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, or commits.

## Phase 1 Verification

Required checks for the plan-lane files:

```bash
python -m json.tool .hermes-loop/work/phase-1/god_dispatch.json
test "$(sed -n '1p' .hermes-loop/work/phase-1/context_bundle.md)" = "# phase: phase-1"
test "$(sed -n '1p' .hermes-loop/work/phase-1/plan_review.md)" = "# phase: phase-1"
test "$(sed -n '1p' .hermes-loop/work/phase-1/plan_final.md)" = "# phase: phase-1"
rg -n "source_hit|LoCoMo|LongMemEval|MEMORYOS_AGENT_KERNEL|Letta|contract" .hermes-loop/work/phase-1/plan_review.md .hermes-loop/work/phase-1/plan_final.md
git diff -- .hermes-loop/work/phase-1/plan_review.md .hermes-loop/work/phase-1/plan_final.md
```

Expected result: both plan-lane self-review files are phase-bound, the review is PASS, the final plan is contract-first, and only `plan_review.md` plus `plan_final.md` are written by this self-review lane.
