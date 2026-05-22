# phase: phase-4

# Review: Phase 4 - Archive Eligibility And Passage Scope

Verdict: PASS.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Evidence

- Context bundle was read first, and `god_dispatch.json`, `plan_final.md`, `result.md`, `execute_review.md`, prior `review_verdict.json`, `reviews/codex-review-rerun.md`, git diff, and changed source/tests were reviewed.
- The prior blocking finding `archival-selected-before-budget` is fixed: `V3ContextComposer.build()` now derives `selected_passage_ids`, `selected_source_refs`, `selected_passage_count`, and `archival_selected` diagnostics from post-budget archival items in `package.items`, after `_try_add_layer()` has dropped over-budget items (`src/memoryos_lite/context_composer.py:83`, `src/memoryos_lite/context_composer.py:90`, `src/memoryos_lite/context_composer.py:96`, `src/memoryos_lite/context_composer.py:111`).
- The budget-drop regression is covered by `tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected`, including empty selected IDs/source refs/count and no `archival_selected` event for the dropped passage.
- Scoped archival eligibility is in the real v3 path: `MemoryOSService.build_context()` passes `IdentityScope(session_id=session_id)` into `ContextComposerRequest`, and the composer calls `store.list_archival_passages_for_scope()` before archival search (`src/memoryos_lite/engine.py:1981`, `src/memoryos_lite/context_composer.py:183`, `src/memoryos_lite/context_composer.py:189`).
- Store eligibility resolves session/identity/source attachments and filters passages before search; unscoped `list_archival_passages()` remains available for explicit store/admin/test use but is no longer the v3 composer search input (`src/memoryos_lite/store.py:1114`, `src/memoryos_lite/store.py:1149`).
- Public benchmark diagnostics are append-only: `build_case_diagnostics()` copies `v3_context.metadata.archival_eligibility` into `case_diagnostics["archival_eligibility"]` without changing scoring/movement fields (`src/memoryos_lite/public_case_diagnostics.py:44`, `src/memoryos_lite/public_case_diagnostics.py:73`, `src/memoryos_lite/public_case_diagnostics.py:97`).
- v1 fallback, v3 default, and kernel default-off are preserved: defaults are `memoryos_memory_arch="v3"` and `memoryos_agent_kernel="off"`, and the explicit v1 guard test excludes archival eligibility metadata (`src/memoryos_lite/config.py:29`, `src/memoryos_lite/config.py:30`, `tests/test_engine.py:247`).
- No changed production source showed benchmark case-id hacks, expected-answer retrieval leaks, Letta runtime dependency, Qdrant/new production DB requirement, or broad storage rewrite.

## Verification

- Fresh targeted review command: `uv run pytest tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off -q` -> `6 passed in 7.33s`.
- Fresh focused phase-4 suite: `uv run pytest tests/test_archival_store.py tests/test_archival_searcher.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q` -> `76 passed in 94.05s`.
- Fresh lint: `uv run ruff check .` -> `All checks passed!`.
- Execute evidence records full suite: `uv run pytest -q` -> `378 passed, 1 warning in 600.25s`.

## Benchmark Evidence

- LongMemEval report `.memoryos/evals/public_20260522_010216_longmemeval.json`: 30 cases, 17 pass / 13 fail, `movement_status=new_case_no_baseline` for all cases, retrieval misses `58bf7951`, `6ade9755`, `75499fd8`, archival totals selected/scope-excluded/no-match all zero because benchmark cases did not seed attached archives.
- LoCoMo report `.memoryos/evals/public_20260522_011335_locomo.json`: 30 cases, 0 pass / 30 fail, `movement_status=new_case_no_baseline` for all cases, retrieval misses include `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, and archival totals selected/scope-excluded/no-match all zero because benchmark cases did not seed attached archives.
- LoCoMo 0/30 remains visible and is not converted into an aggregate improvement claim.

## ACK Notes

- Current `reviews/codex-review.md` and `review_verdict.json` supersede the stale phase-4 review artifacts and the prior FAIL rerun.
- Existing `.hermes-loop/work/phase-4/ack.json` is stale Archival Memory Store evidence and must not be used as the current ACK basis. God should replace it with a new ACK that cites this PASS verdict, the post-budget regression fix, separated LongMemEval/LoCoMo case-level results, and LoCoMo 0/30.
