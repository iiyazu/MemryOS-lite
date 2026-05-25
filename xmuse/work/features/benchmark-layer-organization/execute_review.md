# Execute Review: benchmark-layer-organization

feature_id: benchmark-layer-organization
reviewed_at: 2026-05-25T06:43:25Z
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization

## Scope Review

Touched product files:

- `src/memoryos_lite/public_case_movement.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/public_benchmarks.py`

Touched test file:

- `tests/test_public_benchmarks.py`

Feature-local artifacts were written under
`xmuse/work/features/benchmark-layer-organization/`.

No Master-owned artifacts, approval artifacts, target branch, other feature
worktrees, archive-rag implementation files, or historical paths were edited.

## Invariant Review

- v3 default preserved: no settings default changed.
- v1 fallback preserved: no `MEMORYOS_MEMORY_ARCH` behavior changed.
- v2 recall remains opt-in: the new test opts in locally; no default changed.
- Agent kernel default unchanged.
- SQLite authority unchanged.
- No production-readiness claim was added.

## Leakage Review

- No case-id rules.
- No hard-coded answers.
- No expected-source shortcuts.
- No dataset-specific conversation ids.
- No benchmark score target.
- No archive-rag dependency.

## Diagnostic Review

Regular public comparison summaries now distinguish verdict movement from
source-metric movement. This directly supports blueprint diagnostics that must
separate retrieval/source-grounding movement from answer-quality and judge
movement.

Post-review hardening documents the intentional behavior for missing metric
values: source-metric movement omits rows where either the baseline or current
metric is missing.

Budget-dropped evidence accounting and selected/rendered evidence accounting
were not changed.

## Verification Review

Passing:

- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_writes_case_movement_summary_for_comparison_report -q`
- `uv run pytest tests/test_public_benchmarks.py::test_public_case_movement_summary_reports_source_metric_movement_and_omits_missing_values tests/test_public_benchmarks.py::test_public_benchmark_writes_case_movement_summary_for_comparison_report -q`
- `uv run pytest tests/test_public_benchmarks.py::test_public_case_movement_from_comparison_report_pairs tests/test_public_benchmarks.py::test_public_benchmark_writes_case_movement_summary_for_comparison_report -q`
- `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q`
- `uv run pytest tests/test_context_composer.py -q`
- `uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run mypy src/memoryos_lite/public_case_movement.py src/memoryos_lite/public_case_diagnostics.py src/memoryos_lite/public_benchmarks.py`

Blocked or failing:

- `uv run mypy src` fails with 90 project-wide errors.
- `uv run memoryos eval run --case-set hard --baseline memoryos_lite` exits 0
  but reports `accuracy=0.56`, `source=0.56`.
- Full public LLM gates are blocked by missing LLM credentials and absent raw
  public data files in this worktree.

## Review Decision

Bounded slice review: PASS.

Full blueprint review: FAIL/BLOCKED for external or pre-existing full-gate
blockers. No usable full-feature ACK should be issued from this pass.
