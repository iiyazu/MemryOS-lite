# phase: phase-15

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Files changed:
- `src/memoryos_lite/public_maintenance_planner.py`
- `src/memoryos_lite/public_benchmarks.py`
- `tests/test_public_benchmarks.py`
- `.hermes-loop/work/phase-15/task7_execute_result.md`

Commands:
- `uv run pytest tests/test_public_benchmarks.py -q`
  - First GREEN attempt: failed, `1 failed, 60 passed`; failure was `test_planner_without_model_visible_evidence_yields_diagnostic_only_denial`, because explicit `citation_contract_status="no_cited_evidence"` still yielded a proposal.
  - Final run after import-order cleanup: `61 passed in 72.07s`.
- `uv run pytest tests/test_agent_kernel.py -q`
  - `27 passed in 27.61s`.
- `uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags -q`
  - `2 passed in 0.02s`.
- `uv run ruff check src/memoryos_lite/public_maintenance_planner.py src/memoryos_lite/public_benchmarks.py tests/test_public_benchmarks.py`
  - First run: failed on import ordering in `tests/test_public_benchmarks.py`.
  - Final run: `All checks passed!`.
- `git diff --check -- src/memoryos_lite/public_maintenance_planner.py src/memoryos_lite/public_benchmarks.py tests/test_public_benchmarks.py .hermes-loop/work/phase-15/task7_execute_result.md`
  - Passed with no output.

Pass/fail summary:
- PASS: Task 7 planner/report GREEN tests pass.
- PASS: focused K2 kernel tests pass.
- PASS: focused v3 default/kernel flag checks pass.
- PASS: scoped Ruff and diff whitespace checks pass.

Implementation summary:
- Added proposal-only public maintenance planner contracts: `ModelVisiblePlannerInput`, `EvalGoldSidecar`, `MaintenanceProposal`, `MaintenanceArtifact`, and `build_maintenance_artifact`.
- Kept proposal construction sourced from model-visible fields only. Eval sidecar values are retained for reporting and non-executable grounding-risk classification only.
- Added diagnostic-only denial for no model-visible evidence and explicit `no_cited_evidence`.
- Added judge-pass/source-miss `grounding_risk` proposal classification with no executable tool arguments or source refs.
- Added valid evidence `archive_write` proposal shape with `execution_mode="proposal_only"`, `gold_fields_used=false`, and `SourceRef(SourceType.MESSAGE, source_id=...)` derived from model-visible source ids only.
- Wired public reports to emit `model_visible_planner_input`, `eval_gold_sidecar`, and `maintenance_proposal` without calling `SimpleAgentStepRunner` or creating `ToolExecutionRequest` from proposals.

Concerns:
- No LongMemEval/LoCoMo quality claim is made from this structural Task 7 slice.
- Existing unrelated phase-15 worktree changes from earlier tasks were left in place.
