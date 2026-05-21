# phase: phase-1

# Plan - Phase 1 Contract Draft And Future TDD Path

## Phase 1 Status

Phase 1 itself is no-code contract work. This plan replaces stale Phase 3 core-memory implementation content and must not modify `src/`, `tests/`, `docs/`, `alembic/`, benchmark data, `.hermes-loop/state.json`, or `.hermes-loop/blueprint.md`.

Future implementation phases should execute the contracts below with TDD. Each P0 contract uses the same loop:

```text
RED -> GREEN -> REFACTOR -> smoke -> review
```

Commits are not part of Phase 1. Future phases may commit only if their dispatch permits it.

## Future File Map

- `tests/test_public_benchmarks.py`: default v3 route, public taxonomy, case-level diagnostics, rendered/citation report fields.
- `tests/test_context_composer.py`: v3 composer route behavior, archive attachment scope, rendered evidence survival.
- `tests/test_archival_searcher.py`: archive-scoped search eligibility and silent-global-fallback prevention.
- `tests/test_v3_contracts.py`: passage role/source-vs-agent invariants and answer artifact schema contracts.
- `tests/test_agent_answer_eval.py`: answer citation/unsupported classification from selected evidence.
- `tests/test_agent_kernel.py`: opt-in kernel guard coverage when future P1 kernel work starts.
- `src/memoryos_lite/config.py`, `src/memoryos_lite/engine.py`, `src/memoryos_lite/context_composer.py`, `src/memoryos_lite/retrieval/archival_searcher.py`, `src/memoryos_lite/v3_contracts.py`, `src/memoryos_lite/public_benchmarks.py`, and `src/memoryos_lite/agent_answer_eval.py`: likely future implementation surfaces.

## P0 Contract 1 - Default v3 Route And Public Taxonomy

Goal: prove the real default service/public benchmark path exercises v3, while explicit v1 fallback remains available and public taxonomy remains case-level.

- [ ] RED: Add a future focused test in `tests/test_public_benchmarks.py` named `test_default_public_eval_emits_v3_diagnostics_without_memory_arch_env`.
  - Shape: construct the public eval path the same way the CLI does, without setting `MEMORYOS_MEMORY_ARCH`, run a tiny fixture or one deterministic case, and assert `memory_arch == "v3"`, `v3_context` exists, `v3_diagnostics` exists, and `kernel_trace_events == []`.
  - Anchor: Phase 0 default check says v3 diagnostics were present in refreshed reports, but research flagged a possible service routing mismatch.
- [ ] RED: Add a future focused fallback test named `test_explicit_v1_public_eval_preserves_v1_fallback`.
  - Shape: set `MEMORYOS_MEMORY_ARCH=v1`, run the same tiny fixture path, and assert the report does not masquerade as v3 composer output.
- [ ] GREEN: Adjust only the minimal future service/config/public benchmark routing needed so default `Settings()` and CLI/public eval both reach v3, while explicit v1 remains v1.
- [ ] REFACTOR: Keep routing logic in one small boundary; avoid dataset-specific case rules.
- [ ] smoke: Run `uv run pytest tests/test_public_benchmarks.py tests/test_context_composer.py -q`.
- [ ] review: Check that no test requires `MEMORYOS_MEMORY_ARCH=v3` for default behavior and no kernel trace appears without `MEMORYOS_AGENT_KERNEL=v1`.

## P0 Contract 2 - Archive Attachment Scope

Goal: prevent silent global archival retrieval when attached archive scope exists, especially for LoCoMo retrieval/scope failures.

- [ ] RED: Add `tests/test_context_composer.py::test_archival_layer_uses_attached_archive_scope_before_global_matches`.
  - Shape: create two archives; attach only archive A to the relevant session/agent/project; place a stronger lexical passage in unattached archive B; build v3 context; assert selected archival evidence comes only from archive A and diagnostics name the eligible archive ids.
  - Anchors: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.
- [ ] RED: Add `tests/test_archival_searcher.py::test_archival_search_requires_explicit_global_fallback_when_scope_exists`.
  - Shape: scoped query must not return unattached archive hits unless the caller passes an explicit global fallback flag or equivalent future contract.
- [ ] GREEN: Thread attachment-derived eligible archive ids into v3 archival retrieval and diagnostics with the smallest MemoryOS-native change.
- [ ] REFACTOR: Keep archive scope derivation separate from lexical scoring so ranking does not own authorization/scope decisions.
- [ ] smoke: Run `uv run pytest tests/test_context_composer.py tests/test_archival_searcher.py tests/test_archival_store.py -q`.
- [ ] review: Verify no benchmark case id or expected answer string is used in retrieval code.

## P0 Contract 3 - Passage Source-Vs-Agent Role

Goal: make benchmark evidence auditably source-backed and prevent agent-written memory from counting as source evidence without source refs.

- [ ] RED: Add `tests/test_v3_contracts.py::test_archival_passage_requires_unambiguous_benchmark_evidence_role`.
  - Shape: construct source-backed, agent-written, and ambiguous passage fixtures; assert benchmark-eligible source evidence has a source role and source refs, agent-written archival memory has an agent role, and mixed/ambiguous role is rejected or marked ineligible for source-grounded evidence.
  - Anchors: LoCoMo retrieval misses `conv-26_qa_002` through `conv-26_qa_005`; LongMemEval `51a45a95` where source overlap alone was not enough.
- [ ] RED: Add a public diagnostic test shape in `tests/test_public_benchmarks.py` that verifies source-backed evidence and agent-written memory are reported separately.
- [ ] GREEN: Add MemoryOS-native role metadata or validation in the v3 contract layer and propagate it through archival search/public diagnostics.
- [ ] REFACTOR: Preserve existing `source_refs`; do not copy Letta's exact storage split unless a later implementation phase proves it is needed.
- [ ] smoke: Run `uv run pytest tests/test_v3_contracts.py tests/test_public_benchmarks.py tests/test_archival_searcher.py -q`.
- [ ] review: Verify agent summaries cannot satisfy source-grounded evidence metrics without original source refs.

## P0 Contract 4 - Answer Citation And Unsupported Contract

Goal: bind final public answers to selected evidence ids/source ids, and expose unsupported/refusal outcomes instead of uncited answers.

- [ ] RED: Add `tests/test_public_benchmarks.py::test_answer_artifact_requires_selected_evidence_citations_for_supported_answer`.
  - Shape: feed selected evidence that contains the expected fact; assert the answer artifact includes final answer text, cited selected evidence ids, cited source ids, and status `supported_cited_answer`.
  - Anchors: LongMemEval `e47becba`, `118b2229`, `51a45a95`; LoCoMo `conv-26_qa_001`.
- [ ] RED: Add `tests/test_public_benchmarks.py::test_empty_or_insufficient_selected_evidence_is_unsupported`.
  - Shape: selected evidence is empty or irrelevant; assert status `unsupported_answer` or refusal and no false supported citation.
  - Anchors: LongMemEval retrieval miss `58bf7951`; LoCoMo retrieval misses `conv-26_qa_002` through `conv-26_qa_005`.
- [ ] GREEN: Introduce the smallest answer artifact/schema/report change that records cited selected evidence ids, cited source ids, support status, and refusal reason.
- [ ] REFACTOR: Keep deterministic substring projection separate from support/citation status; do not make `source_hit` imply support.
- [ ] smoke: Run `uv run pytest tests/test_public_benchmarks.py tests/test_agent_answer_eval.py -q`.
- [ ] review: Confirm no prompt-only wording change is counted as success without cited selected evidence ids.

## P0 Contract 5 - Rendered Evidence Survival

Goal: prove selected evidence survives into the rendered answer prompt/context component that answer generation actually uses.

- [ ] RED: Add `tests/test_context_composer.py::test_rendered_answer_context_reports_selected_evidence_ids_included_and_dropped`.
  - Shape: create selected recall/archival evidence where budget admits one item and drops another; assert diagnostics expose selected evidence ids included in the rendered answer component and selected evidence ids excluded with reasons.
  - Anchors: LongMemEval `e47becba`, `118b2229`, `51a45a95`; LoCoMo `conv-26_qa_001`.
- [ ] RED: Add a public benchmark report test shape that checks rendered evidence inclusion is emitted per case, not only in internal composer objects.
- [ ] GREEN: Add rendered evidence survival metadata at the boundary between v3 context package and public answer/report construction.
- [ ] REFACTOR: Keep existing v3 layer budget decisions; add rendered-component evidence survival without replacing current diagnostics.
- [ ] smoke: Run `uv run pytest tests/test_context_composer.py tests/test_public_benchmarks.py -q`.
- [ ] review: Verify evidence-hit-answer-fail cases cannot be labeled solved merely because evidence existed before rendering.

## P0 Contract 6 - Public Benchmark Diagnostics

Goal: keep case-level regressions visible and label `source_hit` conservatively.

- [ ] RED: Add `tests/test_public_benchmarks.py::test_case_level_taxonomy_separates_retrieval_miss_from_answer_fail`.
  - Shape: use fixtures or Phase 0 report rows for all anchor statuses and assert each row preserves retrieval evidence metrics, final source overlap, answer support/citation status, v3 diagnostics, rendered evidence inclusion, and kernel trace presence separately.
  - Anchors: `e47becba`, `118b2229`, `51a45a95`, `58bf7951`, `1e043500`, `conv-26_qa_001`, `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.
- [ ] RED: Add `tests/test_public_benchmarks.py::test_source_hit_is_reported_as_projection_overlap_not_evidence_localization`.
  - Shape: construct a row with `source_hit=true` and missing expected answer fact, and assert taxonomy remains `evidence_hit_answer_fail` rather than retrieval success.
  - Anchor: LongMemEval `51a45a95` and LoCoMo `conv-26_qa_001`.
- [ ] GREEN: Extend public report/taxonomy fields only as needed to preserve the separate metrics.
- [ ] REFACTOR: Keep field names backward-compatible where practical; if a new label is needed, document it in the report schema/tests in the future phase.
- [ ] smoke: Run `uv run pytest tests/test_public_benchmarks.py tests/test_evals.py -q`.
- [ ] review: Compare per-case movement before any aggregate score claim.

## Phase 1 Verification Commands

Run these after writing Phase 1 contract files:

```bash
python -m json.tool .hermes-loop/work/phase-1/god_dispatch.json
test "$(sed -n '1p' .hermes-loop/work/phase-1/context_bundle.md)" = "# phase: phase-1"
test "$(sed -n '1p' .hermes-loop/work/phase-1/spec.md)" = "# phase: phase-1"
test "$(sed -n '1p' .hermes-loop/work/phase-1/plan.md)" = "# phase: phase-1"
rg -n "source_hit|LoCoMo|LongMemEval|MEMORYOS_AGENT_KERNEL|Letta|contract" .hermes-loop/work/phase-1/spec.md .hermes-loop/work/phase-1/plan.md
git diff -- .hermes-loop/work/phase-1/spec.md .hermes-loop/work/phase-1/plan.md
```

Expected Phase 1 result: commands pass, only the two plan-lane files are modified by this lane, and no code/test/docs/benchmark/state/blueprint file is changed.

## Future Smoke And Milestone Commands

Future implementation phases should use focused tests first, then milestone commands:

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_context_composer.py tests/test_archival_searcher.py tests/test_v3_contracts.py -q
uv run pytest tests/test_agent_kernel.py tests/test_public_benchmarks.py tests/test_context_composer.py tests/test_evals.py -q
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Future public benchmark smokes:

```bash
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge
```

Future hard/milestone commands:

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
uv run memoryos eval run --baseline all
make lint
make eval
```

Do not claim benchmark-usability improvement from future runs unless LongMemEval and LoCoMo case-level regressions remain visible and the relevant P0 contract tests pass.

## Review Checklist

- [ ] Phase 1 stayed no-code and modified only `spec.md` and `plan.md`.
- [ ] Every P0 contract has RED, GREEN, REFACTOR, smoke, and review steps.
- [ ] Every RED names a future test file/test shape or concrete Phase 0 case anchor.
- [ ] LongMemEval and LoCoMo anchors stay separated.
- [ ] No Letta runtime dependency is proposed.
- [ ] `source_hit` remains final projection/source overlap, not evidence localization.
- [ ] v1 fallback, v3 default verification, and kernel opt-in constraints are explicit.
- [ ] The plan contains no stale Phase 3 core-memory implementation content.
