# phase: phase-3

# Execute Review

Context bundle: `.hermes-loop/work/phase-3/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Verdict

PASS for execute-lane completion against the phase-3 implementation scope.

## Review Checks

- CoreMemoryBlock contract now includes Letta-style `read_only` and `tags`.
- SQLite stores and reloads `read_only` and `tags_json`; new DBs stamp `0007_add_core_block_read_only_tags`.
- Existing 0006-style SQLite DBs get missing core-memory columns added by `init_db()` before 0007 stamping, preventing silent stamp-without-schema drift.
- CoreMemoryService rejects append, replace, update, and delete on read-only blocks.
- Limit behavior remains reject-on-over-limit and is covered by existing service tests.
- Structured renderer includes description, tags, metadata, source refs, current/limit token counts, read-only state, and value.
- V3ContextComposer consumes the structured renderer and emits core layer diagnostics with budget cost.
- MemoryOSService v3 path exposes core diagnostics through `build_context()`; explicit v1 excludes v3 core blocks.
- Public benchmark report schema remains append-only and exposes `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics`.
- Core source refs were kept out of aggregate v3 retrieval/source-id candidate extraction.
- `MEMORYOS_MEMORY_ARCH=v3` remains default, verified by focused preservation test.
- `MEMORYOS_AGENT_KERNEL` remains default `off`, verified by focused public benchmark test.
- No answer prompt tuning, benchmark case-id hacks, expected-answer leaks, automatic benchmark memory writes, or source-less core writes were added.

## Evidence

- RED commands were run before production changes and failed for intended missing-contract reasons, except the first engine RED exposed a stale v1 fixture in the new test; after correcting that test setup, it failed for the intended missing structured render reason while explicit v1 stayed green.
- Store migration compatibility RED/GREEN: `uv run pytest tests/test_core_memory_store.py::test_init_db_upgrades_existing_core_memory_schema_before_stamping_head -q` failed before the fix because `read_only` and `tags_json` were absent, then passed after the fix with `1 passed in 0.73s`.
- Focused phase-3 suite: `uv run pytest tests/test_v3_contracts.py tests/test_core_memory_store.py tests/test_core_memory_service.py tests/test_context_composer.py tests/test_engine.py tests/test_public_benchmarks.py -q` -> exit 0, `89 passed in 63.47s`.
- Preservation suite: `uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_public_benchmarks.py::test_public_benchmark_explicit_v1_fallback_has_no_v3_case_context tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off -q` -> exit 0, `3 passed in 2.80s`.
- Full suite: `uv run pytest -q` -> exit 0, `372 passed, 1 warning in 557.50s`.
- Lint: `uv run ruff check .` -> exit 0, `All checks passed!`.
- LongMemEval v3 no-LLM smoke: exit 0, report `.memoryos/evals/public_20260521_234559_longmemeval.json`.
- LoCoMo v3 no-LLM smoke: exit 0, report `.memoryos/evals/public_20260521_235024_locomo.json`.

## Smoke Review

LongMemEval smoke kept all 10 cases at `memory_arch=v3`, with `v3_layer_counts`, `v3_budget_decisions`, and `v3_diagnostics` present and nonempty. Pass/fail was `3/10`. Case-level classes were `context_missing_evidence=3`, `evidence_hit_answer_fail=2`, `retrieval_miss=2`, `supported_cited_answer=3`.

LoCoMo smoke kept all 10 cases at `memory_arch=v3`, with the same v3 diagnostics fields present and nonempty. Pass/fail was `0/10`. Case-level classes were `evidence_hit_answer_fail=4`, `retrieval_miss=5`, `context_missing_evidence=1`.

Both smokes had `movement_status=new_case_no_baseline` for all cases. No comparison baseline was available, so there is no pass-to-fail or fail-to-pass claim.

## Remaining Risk

- Phase 3 wires structured core memory and diagnostics, but benchmark case failures remain. Phase completion should not be interpreted as answer-quality improvement.
- Smoke core counts are 0 because this execute lane intentionally did not add automatic benchmark core writes. The real path is proven by unit/integration and public benchmark seeded-core diagnostics test.
