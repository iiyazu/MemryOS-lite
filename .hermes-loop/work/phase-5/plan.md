# phase: phase-5

# Plan: Context Composer And Accounting

> For agentic workers: implement task by task with RED, GREEN, REFACTOR, focused smoke, full verification, milestone eval, and review. Do not edit Hermes active runtime artifacts. Do not enable the v3 kernel by default.

## Goal

Add benchmark-usable v3 component accounting, final-context trace metadata, and LoCoMo temporal/session neighbor diagnostics to the real MemoryOS Lite v3 context path.

## Files To Modify

- `src/memoryos_lite/context_composer.py`: build component accounting and final-context trace from actual v3 inclusion/drop decisions.
- `src/memoryos_lite/retrieval/episode_searcher.py`: keep LoCoMo neighbors within the same `benchmark_session_id` when metadata exists; emit neighbor diagnostics.
- `src/memoryos_lite/retrieval/recall_pipeline.py`: carry neighbor metadata into `ContextEvidence.metadata`.
- `src/memoryos_lite/engine.py`: propagate v3 accounting metadata to legacy-compatible `ContextPackage.metadata` and `context_built` traces.
- `src/memoryos_lite/evals.py`: carry append-only v3 accounting fields into `BaselineOutput`.
- `src/memoryos_lite/public_benchmarks.py`: add append-only public report fields and compute expected-vs-final-trace overlaps.
- `src/memoryos_lite/public_case_diagnostics.py`: read nested `source_refs` and new `final_context_trace` ids when classifying selected context.
- `tests/test_context_composer.py`: composer RED/GREEN tests.
- `tests/test_engine.py`: service-path metadata and v1 fallback tests.
- `tests/test_public_benchmarks.py`: public report and diagnostics tests.

## Tests To Add

- `tests/test_context_composer.py::test_v3_composer_records_component_accounting_for_included_and_budget_dropped_items`
- `tests/test_context_composer.py::test_v3_composer_final_context_trace_flattens_selected_source_refs`
- `tests/test_context_composer.py::test_v3_composer_keeps_locomo_neighbor_in_same_benchmark_session`
- `tests/test_context_composer.py::test_v3_composer_records_locomo_neighbor_budget_drop`
- `tests/test_engine.py::test_v3_build_context_trace_includes_component_accounting_and_final_context_trace`
- `tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_component_accounting`
- `tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_component_accounting_append_only`
- `tests/test_public_benchmarks.py::test_public_case_diagnostics_uses_v3_final_context_trace_source_refs`
- `tests/test_public_benchmarks.py::test_public_benchmark_reports_locomo_neighbor_diagnostics`
- Preserve and rerun existing guard tests named in `.hermes-loop/work/phase-5/context_bundle.md`.

## RED

1. Add `test_v3_composer_records_component_accounting_for_included_and_budget_dropped_items`.
   - Arrange one short recall message and one over-budget archival passage with a message `SourceRef`.
   - Build v3 context with a budget that includes task/recall but drops archival.
   - Assert `package.metadata["component_accounting"]` contains rows for included recall and dropped archival.
   - Assert the dropped row has `component == "archival"`, `item_id == "apsg_budget_dropped"`, `source_ids == ["msg_archival"]`, `estimated_tokens > 0`, `included is False`, `dropped is True`, and `reason_code == "budget_drop"`.
   - RED command:
     ```bash
     uv run pytest tests/test_context_composer.py::test_v3_composer_records_component_accounting_for_included_and_budget_dropped_items -q
     ```
   - Expected RED: fails because `component_accounting` is absent or does not include flat dropped source ids.

2. Add `test_v3_composer_final_context_trace_flattens_selected_source_refs`.
   - Arrange a recall message with id `msg_selected`.
   - Build v3 context.
   - Assert `package.metadata["final_context_trace"]` has an included recall row with `source_ids == ["msg_selected"]`, `rendered_index` as an integer, and no dropped rows marked as rendered.
   - RED command:
     ```bash
     uv run pytest tests/test_context_composer.py::test_v3_composer_final_context_trace_flattens_selected_source_refs -q
     ```
   - Expected RED: fails because final-context trace does not exist or source refs are only nested.

3. Add `test_v3_composer_keeps_locomo_neighbor_in_same_benchmark_session`.
   - Arrange three LoCoMo-shaped messages in one MemoryOS session:
     - `msg_d1_1` metadata `benchmark_session_id="D1"`, content with temporal setup.
     - `msg_d1_2` metadata `benchmark_session_id="D1"`, content with queried marker.
     - `msg_d2_1` metadata `benchmark_session_id="D2"`, distractor immediately adjacent by global position.
   - Query for the marker in `msg_d1_2`.
   - Assert recall/final trace includes a neighbor row for `msg_d1_1`, records `neighbor_of == "msg_d1_2"`, and does not record `msg_d2_1` as a neighbor of `msg_d1_2`.
   - RED command:
     ```bash
     uv run pytest tests/test_context_composer.py::test_v3_composer_keeps_locomo_neighbor_in_same_benchmark_session -q
     ```
   - Expected RED: fails if neighbor metadata is missing or neighbor policy ignores `benchmark_session_id`.

4. Add `test_v3_composer_records_locomo_neighbor_budget_drop`.
   - Arrange direct hit plus same-session neighbor where neighbor text is too large for the remaining budget.
   - Assert `locomo_neighbor_diagnostics` records the neighbor item id, source id, `neighbor_of`, `included is False`, `dropped is True`, and `reason_code == "budget_drop"`.
   - RED command:
     ```bash
     uv run pytest tests/test_context_composer.py::test_v3_composer_records_locomo_neighbor_budget_drop -q
     ```
   - Expected RED: fails because dropped neighbor information is not summarized.

5. Add service-path and public-report RED tests:
   ```bash
   uv run pytest \
     tests/test_engine.py::test_v3_build_context_trace_includes_component_accounting_and_final_context_trace \
     tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_component_accounting \
     tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_component_accounting_append_only \
     tests/test_public_benchmarks.py::test_public_case_diagnostics_uses_v3_final_context_trace_source_refs \
     tests/test_public_benchmarks.py::test_public_benchmark_reports_locomo_neighbor_diagnostics \
     -q
   ```
   Expected RED: v3 metadata is not fully propagated, v1 exclusion may be missing for new fields, and public diagnostics do not yet flatten nested `source_refs`.

## GREEN

1. Implement source-id flattening in `src/memoryos_lite/context_composer.py`.
   - Add `_source_ids_from_refs(source_refs: list[SourceRef]) -> list[str]`.
   - Add `_accounting_row(item, included, dropped, rendered_index=None, reason_code=None)`.
   - The row must include only JSON-serializable values.

2. Update `_try_add_layer()` in `src/memoryos_lite/context_composer.py`.
   - Keep the existing budget behavior.
   - Ensure every included and dropped item has a diagnostic with `budget_tokens`, `source_refs`, and a reason.
   - Keep dropped items out of `package.items`.
   - Do not mark dropped archival passages as selected in `archival_eligibility`.

3. Add `_refresh_component_accounting(package)` in `src/memoryos_lite/context_composer.py`.
   - Build `component_accounting` from diagnostics.
   - Build `final_context_trace` from included diagnostics and selected `package.items`.
   - Compute `component_token_totals`, `component_drop_counts`, and `component_included_counts`.
   - Build `locomo_neighbor_diagnostics` from rows where metadata contains `benchmark_session_id`, `neighbor_of`, or reason starts with `neighbor_of=`.
   - Call this after all layers and archival eligibility diagnostics are finalized.

4. Tighten same-benchmark-session neighbors in `src/memoryos_lite/retrieval/episode_searcher.py`.
   - In `_add_neighbors()`, when both direct hit and neighbor have `temporal_scope["benchmark_session_id"]`, require equality.
   - Preserve same-session behavior when benchmark metadata is absent.
   - Include `benchmark_session_id` and `benchmark_date` in neighbor diagnostics metadata when present.

5. Carry neighbor fields in `src/memoryos_lite/retrieval/recall_pipeline.py`.
   - Add to `ContextEvidence.metadata`: `neighbor_of`, `neighbor_offset`, `benchmark_session_id`, `benchmark_date`, `rank_features`.
   - Keep existing `episode_candidate_message_ids` and `planned_evidence_message_ids` semantics.

6. Propagate metadata in `src/memoryos_lite/engine.py`.
   - In `_context_package_from_v3()`, add metadata keys:
     - `v3_component_accounting`
     - `v3_final_context_trace`
     - `v3_component_token_totals`
     - `v3_component_drop_counts`
     - `locomo_neighbor_diagnostics`
   - In the v3 `context_built` trace payload, include these same keys.
   - Do not add these keys on the v1 branch.

7. Add append-only public fields.
   - In `src/memoryos_lite/evals.py`, add fields to `BaselineOutput` and populate them from `context.metadata`.
   - In `src/memoryos_lite/public_benchmarks.py`, add matching fields to `PublicBenchmarkResult` and `_to_public_result()`.
   - Preserve all current report fields and partial/final report behavior.

8. Update `src/memoryos_lite/public_case_diagnostics.py`.
   - Extend `_selected_context_ids()` to read `v3_context["metadata"]["final_context_trace"]`.
   - Extend `_ids_from_v3_context()` and diagnostic parsing to flatten nested `source_refs[*]["source_id"]`.
   - Add diagnostics keys:
     - `selected_context_overlap_ids`
     - `final_context_trace_source_ids`
     - `component_drop_counts`
     - `locomo_neighbor_diagnostics`
   - Keep existing `failure_class` values unchanged.

9. Run each RED command again and make it pass before moving to refactor.

## REFACTOR

1. Keep helper methods private and local unless tests prove repeated parsing belongs in `v3_contracts.py`.
2. Remove duplicate source-id flattening inside one file by using small private helpers.
3. Keep row keys stable and lower_snake_case.
4. Do not introduce Letta imports or runtime dependencies.
5. Do not change default settings in `src/memoryos_lite/config.py`.

## Focused Smoke

Run the phase-4 guard before relying on old behavior:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q
```

Run the focused Phase 5 smoke:

```bash
uv run pytest tests/test_context_composer.py tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_context_diagnostics tests/test_public_benchmarks.py::test_public_benchmark_case_diagnostics_separate_retrieval_miss_and_answer_fail -q
```

Run the new tests explicitly:

```bash
uv run pytest \
  tests/test_context_composer.py::test_v3_composer_records_component_accounting_for_included_and_budget_dropped_items \
  tests/test_context_composer.py::test_v3_composer_final_context_trace_flattens_selected_source_refs \
  tests/test_context_composer.py::test_v3_composer_keeps_locomo_neighbor_in_same_benchmark_session \
  tests/test_context_composer.py::test_v3_composer_records_locomo_neighbor_budget_drop \
  tests/test_engine.py::test_v3_build_context_trace_includes_component_accounting_and_final_context_trace \
  tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_component_accounting \
  tests/test_public_benchmarks.py::test_public_benchmark_reports_v3_component_accounting_append_only \
  tests/test_public_benchmarks.py::test_public_case_diagnostics_uses_v3_final_context_trace_source_refs \
  tests/test_public_benchmarks.py::test_public_benchmark_reports_locomo_neighbor_diagnostics \
  -q
```

## Full Verification

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Do not report completion if either command fails.

## Milestone Eval

If public benchmark path behavior changed, run both milestone commands and report case-level movement. These can be run in parallel:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30
```

The report must include:

- pass/fail count for each benchmark;
- fail-to-pass and pass-to-fail if comparison inputs are available;
- retrieval miss, context missing evidence, evidence hit answer fail, unsupported answer, and judge questionable counts;
- LoCoMo result separately even if LongMemEval looks better;
- a note that 30-case slices are diagnostic and do not prove broad benchmark improvement.

## Review Gate

Review must check:

- artifacts cite `.hermes-loop/work/phase-5/context_bundle.md`;
- real v3 `MemoryOSService.build_context()` emits metadata;
- public reports expose per-case metadata append-only;
- v1 fallback excludes v3 metadata;
- v3 remains default;
- kernel remains opt-in/default-off;
- no benchmark case-id or expected-answer leaks;
- LoCoMo temporal/session neighbor diagnostics are real and do not rely on recent-message bypass;
- no aggregate-only improvement claim hides case-level regressions.
