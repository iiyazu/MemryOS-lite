# Result: benchmark-layer-organization

feature_id: benchmark-layer-organization
status: hard_gate_repair_complete_full_blueprint_blocked
updated_at: 2026-05-25T07:52:36Z
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization
pre_repair_head: 8a6bc56

## Implemented Repair Slice

The default v3 hard-eval mismatch is repaired. Before this pass, the documented
gate:

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

reported `accuracy=0.56` and `source=0.56` under default settings, while the
v1 fallback path reported `1.00/1.00`.

Root cause: v3 default eval answer selection allowed generic assistant
acknowledgements to win over substantive update evidence and only boosted
update-marked evidence when the question itself contained explicit temporal
markers. That made several current-slot hard cases select stale evidence or an
empty generic acknowledgement projection.

Changes:

- `src/memoryos_lite/evals.py` skips generic acknowledgement evidence during
  answer selection.
- Update-marked evidence is preferred for slot-value questions such as
  "what/which/how much/who" questions, not only explicit "current/final"
  questions.
- Habit/preference questions can include the top two retrieved-message
  restatements only on the v3 retrieved-message path, preserving v1 page-first
  behavior.
- `tests/test_evals.py` now covers the direct selector failures and the default
  v3 hard case set.

Ignored local symlinks were added so the worktree can resolve blueprint-relative
public data and comparison-report paths:

- `benchmarks/longmemeval/longmemeval.json`
- `benchmarks/locomo/locomo10.json`
- `.memoryos/evals/routeb_lme50_llm_20260524_longmemeval.json`
- `.memoryos/evals/routeb_locomo50_llm_20260524_locomo.json`

## RED Evidence

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Before repair:

```text
memoryos_lite: cases=16, accuracy=0.56, source=0.56
Report: .memoryos/evals/run_20260525_070026.json
```

Control check:

```bash
MEMORYOS_MEMORY_ARCH=v1 uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Result:

```text
memoryos_lite: cases=16, accuracy=1.00, source=1.00
Report: .memoryos/evals/run_20260525_070236.json
```

New RED tests:

```bash
uv run pytest tests/test_evals.py::test_memoryos_v3_default_preserves_hard_eval_source_accuracy -q
```

Initial result:

```text
FAILED ... assert False
1 failed in 34.55s
```

```bash
uv run pytest tests/test_evals.py::test_eval_evidence_selection_skips_generic_acknowledgements tests/test_evals.py::test_eval_evidence_selection_prefers_update_evidence_for_slot_questions -q
```

Initial result:

```text
2 failed in 0.25s
```

Expected failure reason: default v3 eval selection chose generic or stale
evidence instead of substantive update evidence.

## GREEN Evidence

```bash
uv run pytest tests/test_evals.py::test_eval_evidence_selection_skips_generic_acknowledgements tests/test_evals.py::test_eval_evidence_selection_prefers_update_evidence_for_slot_questions tests/test_evals.py::test_memoryos_v3_default_preserves_hard_eval_source_accuracy -q
```

Result:

```text
3 passed in 34.10s
```

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Result:

```text
memoryos_lite: cases=16, accuracy=1.00, source=1.00
Report: .memoryos/evals/run_20260525_071141.json
```

## Focused Verification

```bash
uv run pytest tests/test_evals.py -q
```

Result:

```text
45 passed in 770.57s (0:12:50)
```

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
```

Result:

```text
19 passed in 17.23s
```

```bash
uv run pytest tests/test_context_composer.py -q
```

Result:

```text
14 passed in 34.65s
```

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q
```

Result:

```text
94 passed in 115.87s (0:01:55)
```

```bash
uv run mypy src/memoryos_lite/evals.py src/memoryos_lite/public_case_movement.py src/memoryos_lite/public_case_diagnostics.py src/memoryos_lite/public_benchmarks.py
```

Result:

```text
Success: no issues found in 4 source files
```

## Regression Gates

```bash
uv run pytest -q
```

Result:

```text
605 passed, 1 warning in 968.49s (0:16:08)
```

```bash
uv run ruff check .
```

Result:

```text
All checks passed!
```

```bash
uv run mypy src
```

Result:

```text
Found 90 errors in 12 files (checked 56 source files)
```

This remains the documented project-wide mypy blocker. The touched source file
and prior touched public benchmark modules pass targeted mypy.

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Result:

```text
memoryos_lite: cases=16, accuracy=1.00, source=1.00
Report: .memoryos/evals/run_20260525_071141.json
```

## Public Diagnostics

Full public LongMemEval 50 and LoCoMo 50 LLM answer/judge gates were not run
because no `OPENAI_API_KEY` or `DEEPSEEK_API_KEY` is configured. The local
worktree now has ignored symlinks for the raw public JSON files and baseline
comparison reports, so the remaining public full-chain blocker is provider
credentials.

Relative-path no-LLM LongMemEval diagnostic:

```bash
MEMORYOS_RECALL_PIPELINE=v2 MEMORYOS_EMBEDDING_PROVIDER=none uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge --run-id routeb_lme10_after_benchmark_layer_organization_hardgate_repair_no_llm --comparison-report .memoryos/evals/routeb_lme50_llm_20260524_longmemeval.json
```

Report:

```text
.memoryos/evals/routeb_lme10_after_benchmark_layer_organization_hardgate_repair_no_llm_longmemeval.json
.memoryos/evals/routeb_lme10_after_benchmark_layer_organization_hardgate_repair_no_llm_longmemeval_movement_summary.json
```

Summary:

```text
rows=10
movement={'fail_to_pass': 0, 'pass_to_fail': 7, 'unchanged_pass': 3, 'unchanged_fail': 0, 'new_case_no_baseline': 0}
source_metric_movement.source_hit={'improved': 0, 'regressed': 0, 'unchanged_hit': 10, 'unchanged_miss': 0}
planned_evidence_source_hit_at_5={'improved': 0, 'regressed': 0, 'unchanged_hit': 8, 'unchanged_miss': 2}
episode_source_hit_at_10={'improved': 0, 'regressed': 0, 'unchanged_hit': 8, 'unchanged_miss': 2}
```

Relative-path no-LLM LoCoMo diagnostic:

```bash
MEMORYOS_RECALL_PIPELINE=v2 MEMORYOS_EMBEDDING_PROVIDER=none uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge --run-id routeb_locomo10_after_benchmark_layer_organization_hardgate_repair_no_llm --comparison-report .memoryos/evals/routeb_locomo50_llm_20260524_locomo.json
```

Report:

```text
.memoryos/evals/routeb_locomo10_after_benchmark_layer_organization_hardgate_repair_no_llm_locomo.json
.memoryos/evals/routeb_locomo10_after_benchmark_layer_organization_hardgate_repair_no_llm_locomo_movement_summary.json
```

Summary:

```text
rows=10
movement={'fail_to_pass': 0, 'pass_to_fail': 7, 'unchanged_pass': 0, 'unchanged_fail': 3, 'new_case_no_baseline': 0}
source_metric_movement.source_hit={'improved': 0, 'regressed': 0, 'unchanged_hit': 6, 'unchanged_miss': 4}
planned_evidence_source_hit_at_5={'improved': 0, 'regressed': 0, 'unchanged_hit': 5, 'unchanged_miss': 5}
episode_source_hit_at_10={'improved': 0, 'regressed': 0, 'unchanged_hit': 5, 'unchanged_miss': 5}
```

These no-LLM runs are diagnostic only. They do not support promotion or
aggregate benchmark-improvement claims.

## Residual Blockers

- Full public LongMemEval 50 and LoCoMo 50 LLM answer/judge comparison gates
  require provider credentials that are not configured.
- Full-project `uv run mypy src` still fails with 90 pre-existing errors in 12
  files.

## Decision

The bounded hard-gate repair is implemented and verified. Full blueprint
readiness remains blocked by external credentials and the project-wide mypy
cleanup lane. No aggregate LongMemEval, LoCoMo, or public hard-eval improvement
claim is made.
