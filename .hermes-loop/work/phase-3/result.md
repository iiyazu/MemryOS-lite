# phase: phase-3

# Execute Result

Context bundle: `.hermes-loop/work/phase-3/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Changed Files

- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/store.py`
- `alembic/versions/0007_add_core_block_read_only_tags.py`
- `src/memoryos_lite/core_memory.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/engine.py`
- `tests/test_v3_contracts.py`
- `tests/test_core_memory_store.py`
- `tests/test_core_memory_service.py`
- `tests/test_context_composer.py`
- `tests/test_engine.py`
- `tests/test_public_benchmarks.py`

Unrelated existing controller/Hermes worktree changes were preserved and not edited by this execute pass.

## Implementation Summary

- Added `CoreMemoryBlock.read_only` and `CoreMemoryBlock.tags`.
- Added SQLite persistence for `read_only` and `tags_json`, plus Alembic head `0007_add_core_block_read_only_tags`.
- Added `init_db()` schema compatibility for existing 0006 SQLite DBs so missing core-memory columns are added before stamping 0007.
- Added `CoreMemoryService.create_block()` fields for `read_only`, `tags`, and `metadata`.
- Enforced read-only rejection for append, replace, update, and delete.
- Replaced plain core rendering with structured `CoreMemoryRender` containing text plus per-block metadata.
- Wired structured core render into the real `V3ContextComposer` path with core diagnostics, source refs, and token budget cost.
- Updated engine metadata source-id extraction so core source refs do not inflate retrieval/source-hit candidate metrics.
- Replaced stale engine coverage with explicit v3 inclusion and explicit v1 exclusion tests.
- Added append-only public benchmark diagnostic coverage for v3 core diagnostics.

## RED Observations

- `uv run pytest tests/test_v3_contracts.py::test_core_memory_block_has_letta_style_defaults_and_serialization -q` -> exit 1, intended RED: `CoreMemoryBlock` lacked `read_only`.
- `uv run pytest tests/test_core_memory_store.py::test_core_memory_store_round_trip_history_and_soft_delete -q` -> exit 1, intended RED: persisted block lacked `read_only`.
- `uv run pytest tests/test_core_memory_store.py::test_init_db_stamps_current_migration_head -q` -> exit 1, intended RED: DB stamped `0006_add_archival_memory`.
- `uv run pytest tests/test_core_memory_service.py::test_core_memory_service_rejects_read_only_mutations -q` -> exit 1, intended RED: `create_block()` lacked `read_only`.
- `uv run pytest tests/test_core_memory_service.py::test_core_memory_service_append_replace_update_and_render -q` -> exit 1, intended RED: `create_block()` lacked `tags` and renderer returned a plain string.
- `uv run pytest tests/test_context_composer.py::test_v3_composer_core_items_use_structured_render_and_diagnostics -q` -> exit 1, intended RED: `create_block()` lacked `tags`; composer path could not expose structured metadata.
- `uv run pytest tests/test_engine.py::test_v3_build_context_includes_core_memory_diagnostics tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_core_memory_blocks -q` -> first run exit 1 due stale v1 fixture use in the new v3 test. After correcting the test setup, rerun exit 1 for intended RED: v3 pinned core did not contain `<memory_blocks>`; explicit v1 stayed green.
- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_v3_core_diagnostics_are_append_only -q` -> exit 1, intended RED: public v3 core diagnostics omitted `tags`.
- `uv run pytest tests/test_core_memory_store.py::test_init_db_upgrades_existing_core_memory_schema_before_stamping_head -q` -> exit 1, intended RED: existing 0006-style `core_memory_blocks` table was stamped to 0007 without `read_only` or `tags_json`.

## Verification

- `uv run pytest tests/test_v3_contracts.py::test_core_memory_block_has_letta_style_defaults_and_serialization tests/test_core_memory_store.py::test_core_memory_store_round_trip_history_and_soft_delete tests/test_core_memory_store.py::test_init_db_stamps_current_migration_head tests/test_core_memory_service.py::test_core_memory_service_rejects_read_only_mutations tests/test_core_memory_service.py::test_core_memory_service_append_replace_update_and_render tests/test_context_composer.py::test_v3_composer_core_items_use_structured_render_and_diagnostics tests/test_engine.py::test_v3_build_context_includes_core_memory_diagnostics tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_core_memory_blocks tests/test_public_benchmarks.py::test_public_benchmark_v3_core_diagnostics_are_append_only -q` -> exit 0, `9 passed in 8.68s`.
- `uv run pytest tests/test_core_memory_store.py::test_init_db_upgrades_existing_core_memory_schema_before_stamping_head -q` -> exit 0, `1 passed in 0.73s`.
- `uv run pytest tests/test_v3_contracts.py tests/test_core_memory_store.py tests/test_core_memory_service.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q` -> exit 0, `89 passed in 63.47s`.
- `uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off -q` -> exit 0, `3 passed in 2.80s`.
- `uv run pytest -q` -> exit 0, `372 passed, 1 warning in 557.50s`.
- `uv run ruff check .` -> exit 0, `All checks passed!`.

## Smoke Reports

LongMemEval:

- Command: `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge`
- Exit: 0.
- Report: `.memoryos/evals/public_20260521_234559_longmemeval.json`.
- Cases: `e47becba`, `118b2229`, `51a45a95`, `58bf7951`, `1e043500`, `c5e8278d`, `6ade9755`, `6f9b354f`, `58ef2f1c`, `f8c5f88b`.
- Pass/fail: `3/10`.
- `memory_arch`: `v3` for all 10.
- Append-only fields present for all 10: `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`.
- `v3_diagnostics` nonempty for all 10.
- Core layer absent for all smoke cases because no automatic benchmark core writes were added.
- Failure classes: `context_missing_evidence=3`, `evidence_hit_answer_fail=2`, `retrieval_miss=2`, `supported_cited_answer=3`.
- Movement: `new_case_no_baseline=10`; no comparison baseline available, so no pass-to-fail or fail-to-pass claim.

LoCoMo:

- Command: `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge`
- Exit: 0.
- Report: `.memoryos/evals/public_20260521_235024_locomo.json`.
- Cases: `conv-26_qa_001`, `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_008`, `conv-26_qa_009`, `conv-26_qa_010`.
- Pass/fail: `0/10`.
- `memory_arch`: `v3` for all 10.
- Append-only fields present for all 10: `v3_layer_counts`, `v3_budget_decisions`, `v3_diagnostics`.
- `v3_diagnostics` nonempty for all 10.
- Core layer absent for all smoke cases because no automatic benchmark core writes were added.
- Failure classes: `evidence_hit_answer_fail=4`, `retrieval_miss=5`, `context_missing_evidence=1`.
- Movement: `new_case_no_baseline=10`; no comparison baseline available, so no pass-to-fail or fail-to-pass claim.

## Real Path Status

The real v3 path is wired: `MemoryOSService.build_context()` routes default v3 through `V3ContextComposer`, and structured core blocks appear in `pinned_core`, `v3_context`, `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics` when blocks exist.

The public benchmark path is wired append-only: seeded core diagnostics are visible through `run_public_benchmark()` reports without changing scoring fields or adding automatic benchmark memory writes.

Explicit v1 fallback remains isolated, and `MEMORYOS_AGENT_KERNEL` remains default-off.

## Remaining Gaps

- Smoke reports show case-level diagnostic failures remain, especially LoCoMo retrieval misses. This phase did not claim benchmark improvement.
- No comparison baseline was available for smoke movement analysis.
- Full-chain LLM judge gates were not run because this phase changed context structure and diagnostics, not answer prompt behavior.
