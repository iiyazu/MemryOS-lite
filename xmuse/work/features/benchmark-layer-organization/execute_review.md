# Execute Review: benchmark-layer-organization

feature_id: benchmark-layer-organization
reviewed_at: 2026-05-25T07:52:36Z
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization

## Scope Review

Touched product file:

- `src/memoryos_lite/evals.py`

Touched test file:

- `tests/test_evals.py`

Feature-local artifacts were written under
`xmuse/work/features/benchmark-layer-organization/`.

Ignored local symlinks were added for public benchmark JSON and comparison
report inputs. No Master-owned artifacts, approval artifacts, target branch,
other feature worktrees, archive-rag implementation files, or historical paths
were edited.

## Invariant Review

- v3 default preserved: no settings default changed.
- v1 fallback preserved: `MEMORYOS_MEMORY_ARCH=v1` behavior remains available
  and was used as a control check.
- v2 recall remains opt-in: no `MEMORYOS_RECALL_PIPELINE` default changed.
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

The repair changes generic deterministic eval selection rules: skip generic
acknowledgements, prefer update-marked evidence for slot-value questions, and
preserve competing retrieved-message restatements for habit/preference queries.

## Diagnostic Review

The prior public source-metric movement repair remains intact. This pass
repairs the separate hard-eval default mismatch by making v3 default eval answer
projection treat substantive update evidence consistently with the v1 fallback
control path. Retrieval diagnostics, answer-quality diagnostics, and public
source metrics were not merged or redefined.

Budget-dropped evidence accounting and selected/rendered evidence accounting
were not changed.

## Verification Review

Passing:

- `uv run pytest tests/test_evals.py::test_memoryos_v3_default_preserves_hard_eval_source_accuracy -q`
- `uv run pytest tests/test_evals.py::test_eval_evidence_selection_skips_generic_acknowledgements tests/test_evals.py::test_eval_evidence_selection_prefers_update_evidence_for_slot_questions -q`
- `uv run pytest tests/test_evals.py::test_eval_evidence_selection_skips_generic_acknowledgements tests/test_evals.py::test_eval_evidence_selection_prefers_update_evidence_for_slot_questions tests/test_evals.py::test_memoryos_v3_default_preserves_hard_eval_source_accuracy -q`
- `uv run pytest tests/test_evals.py -q`
- `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q`
- `uv run pytest tests/test_context_composer.py -q`
- `uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q`
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run mypy src/memoryos_lite/evals.py src/memoryos_lite/public_case_movement.py src/memoryos_lite/public_case_diagnostics.py src/memoryos_lite/public_benchmarks.py`
- `uv run memoryos eval run --case-set hard --baseline memoryos_lite`
- relative-path no-LLM LongMemEval limit-10 public diagnostic
- relative-path no-LLM LoCoMo limit-10 public diagnostic

Blocked or failing:

- `uv run mypy src` fails with 90 project-wide errors.
- Full public LLM gates are blocked by missing `OPENAI_API_KEY` and
  `DEEPSEEK_API_KEY`.

## Review Decision

Bounded hard-gate repair review: PASS.

Full blueprint review: FAIL/BLOCKED for external public LLM credentials and
pre-existing project-wide mypy cleanup. No usable full-feature ACK should be
issued from this pass.
