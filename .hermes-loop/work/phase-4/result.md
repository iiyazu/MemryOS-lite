# phase: phase-4

# Execute Result

Context bundle: `.hermes-loop/work/phase-4/context_bundle.md`.
Plan: `.hermes-loop/work/phase-4/plan_final.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Changed Files

- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/store.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `tests/test_archival_store.py`
- `tests/test_archival_searcher.py`
- `tests/test_context_composer.py`
- `tests/test_engine.py`
- `tests/test_public_benchmarks.py`
- `.hermes-loop/work/phase-4/result.md`

Unrelated existing dirty Hermes/control files were preserved and not edited by this execute pass.

## Implementation Summary

- Added MemoryOS-native `ArchiveEligibilityScope` and `ArchiveEligibilityResult`.
- Added store-side scoped archive resolution from session, identity scope, source IDs, and explicit archive IDs.
- Added `list_archival_passages_for_scope(...)`, which returns only attached-archive passages plus explicitly scoped source passages and records scope-excluded passage IDs.
- Enforced passage identity invariants at the store write boundary: archive passages cannot also set `source_id`, and persisted passages must have either `archive_id` or `source_id`.
- Updated legacy/source passage helpers to keep source provenance in `source_refs` and avoid archive/source identity mixing on persisted helper output.
- Replaced global v3 archival search with scoped eligibility in `V3ContextComposer`.
- Added append-only `metadata["archival_eligibility"]` and archival diagnostics for selected, eligible-no-match, scope-excluded, and no-attached-archive cases.
- Passed v3 archival eligibility through `MemoryOSService.build_context()` metadata and public case diagnostics without changing scoring or movement fields.

## Real Chain Components

- ingest: verified unchanged.
- store: changed for scoped archive eligibility and write-time passage invariants.
- retrieval: changed at the v3 composer call site to search eligible passages only; archival searcher remains the existing lexical/vector/hybrid helper.
- context_composer: changed to emit scoped archival eligibility metadata and diagnostics.
- answer_projection: verified unchanged; public scoring fields were not modified.
- kernel_loop: verified unchanged; `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off.
- public_eval: changed only append-only case diagnostics for archival eligibility.

## RED Evidence

- `uv run pytest tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope -q` -> RED exit 1: selected global unattached passage before attached scoped passage.
- `uv run pytest tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility -q` -> RED exit 1: `KeyError: 'archival_eligibility'`.
- `uv run pytest tests/test_archival_store.py::test_archival_passage_invariants_and_attachment_scope_helper -q` -> RED exit 4: missing `ArchiveEligibilityScope` import/contract.
- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only -q` -> RED exit 1: missing `case_diagnostics["archival_eligibility"]`.
- `uv run pytest tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q` -> guard/non-RED exit 0: `1 passed in 1.58s`.

## GREEN Evidence

- `uv run pytest tests/test_context_composer.py::test_v3_composer_filters_archival_passages_by_attached_scope -q` -> exit 0, `1 passed in 2.78s`.
- `uv run pytest tests/test_context_composer.py::test_v3_composer_reports_archival_scope_eligibility -q` -> exit 0, `1 passed in 2.78s`.
- `uv run pytest tests/test_archival_store.py::test_archival_passage_invariants_and_attachment_scope_helper -q` -> exit 0, `1 passed in 1.33s`.
- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only -q` -> exit 0, `1 passed in 4.06s`.
- `uv run pytest tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q` -> exit 0, `1 passed in 1.45s`.
- Compatibility fix after full-suite failure: `uv run pytest tests/test_archival_store.py::test_archival_passage_invariants_and_attachment_scope_helper tests/test_v3_contracts.py::test_page_and_item_are_legacy_inputs_not_archival_targets tests/test_v3_contracts.py::test_archival_contracts_include_chunk_attachment_and_first_class_metadata -q` -> exit 0, `3 passed in 0.40s`.
- Review-fix regression: `uv run pytest tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected -q` -> exit 0, `1 passed in 0.91s`.
- The review-fix regression covers the review reproduction where a budget-dropped archival hit was incorrectly reported in `archival_eligibility.selected_passage_ids`. The current implementation derives selected archival IDs/source refs from post-budget `ContextPackageV3.items`, and emits no `archival_selected` diagnostic for budget-dropped archival passages.

## Final Verification

- `uv run pytest tests/test_archival_store.py tests/test_archival_searcher.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q` -> exit 0, `76 passed in 56.57s`.
- `uv run pytest -q` -> exit 0, `378 passed, 1 warning in 600.25s`.
- `uv run ruff check .` -> exit 0, `All checks passed!`.

## Review-Fix Status

- Blocking review item `archival-selected-before-budget` is fixed in the current tree by computing `selected_passage_ids`, `selected_source_refs`, and `archival_selected` diagnostics from budget-included archival items only.
- Stale `reviews/codex-review.md`, `review_verdict.json`, and `ack.json` must be regenerated from this result before usable ACK.
- The saved milestone reports remain valid as phase-4 case-level evidence because both public benchmark runs reported `archival_selected=0`, `archival_scope_excluded=0`, and `archival_no_match=0`; benchmark cases did not seed attached archives, so the post-budget diagnostic fix does not create a new score or movement claim.

## Full-Chain Milestone Eval

LongMemEval:

- Command: `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30`
- Exit: 0.
- Report: `.memoryos/evals/public_20260522_010216_longmemeval.json`.
- Cases: 30.
- Pass/fail: 17 pass / 13 fail.
- Failure classes: `context_missing_evidence=12`, `evidence_hit_answer_fail=4`, `retrieval_miss=3`, `supported_cited_answer=11`.
- Movement: `new_case_no_baseline=30`; no fail-to-pass or pass-to-fail claim.
- Retrieval miss: `58bf7951`, `6ade9755`, `75499fd8`.
- Context missing evidence: `e47becba`, `118b2229`, `58ef2f1c`, `5d3d2817`, `7527f7e2`, `94f70d80`, `66f24dbb`, `af8d2e46`, `c8c3f81d`, `8ebdbe50`, `0862e8bf`, `853b0a1d`.
- Evidence-hit-answer-fail: `51a45a95`, `f8c5f88b`, `3b6f954b`, `dccbc061`.
- Unsupported answer: none.
- Judge questionable: none.
- Archival eligibility: `archival_scope_excluded_total=0`, `archival_no_match_total=0`; benchmark cases did not seed attached archives, so this is diagnostic plumbing evidence, not an archive-quality improvement claim.

LoCoMo:

- Command: `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30`
- Exit: 0.
- Report: `.memoryos/evals/public_20260522_011335_locomo.json`.
- Cases: 30 loaded from the local file despite the `locomo10.json` name.
- Pass/fail: 0 pass / 30 fail.
- Failure classes: `evidence_hit_answer_fail=9`, `retrieval_miss=11`, `context_missing_evidence=10`.
- Movement: `new_case_no_baseline=30`; no fail-to-pass or pass-to-fail claim.
- Retrieval miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_014`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_028`.
- Context missing evidence: `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`.
- Evidence-hit-answer-fail: `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`, `conv-26_qa_012`, `conv-26_qa_017`, `conv-26_qa_018`, `conv-26_qa_022`, `conv-26_qa_027`.
- Unsupported answer: none.
- Judge questionable: none.
- Archival eligibility: `archival_scope_excluded_total=0`, `archival_no_match_total=0`; benchmark cases did not seed attached archives, so this is diagnostic plumbing evidence, not an archive-quality improvement claim.

## Case-Level Status Placeholders

- LongMemEval phase-4 review should compare `.memoryos/evals/public_20260522_010216_longmemeval.json` against any accepted phase-2/phase-3 baseline before claiming movement.
- LoCoMo phase-4 review should compare `.memoryos/evals/public_20260522_011335_locomo.json` separately; current result remains weak at `0/30`.
- No usable ACK is claimed by execute_lane. The implementation is ready for EXECUTE_SELF_REVIEW to check scoped retrieval, source grounding, stale artifacts, LoCoMo risk, and benchmark overfitting.
