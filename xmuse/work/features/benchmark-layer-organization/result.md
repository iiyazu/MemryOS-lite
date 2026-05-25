# Result: benchmark-layer-organization

feature_id: benchmark-layer-organization
status: bounded_rework_complete_full_blueprint_blocked
updated_at: 2026-05-25T06:43:25Z
worktree: /home/iiyatu/projects/python/memoryOS-benchmark-layer-organization
branch: feat/benchmark-layer-organization
pre_artifact_head: 6ab377073d758e8244bb0e9d3ac58701905a826b

## Implemented Repair Slice

Regular public benchmark comparison summaries now include
`source_metric_movement` for `source_hit`,
`planned_evidence_source_hit_at_5`, and `episode_source_hit_at_10`.
The summary records `improved`, `regressed`, `unchanged_hit`, and
`unchanged_miss` case lists and counts for each metric.

Baseline source metrics from comparison reports are preserved in per-case
diagnostics under `case_diagnostics.baseline_source_metrics`. Verdict movement
remains separate from source-metric movement, and public `source_hit` remains
documented as final projected source overlap rather than pure retrieval
localization. Post-review hardening also documents that source-metric movement
omits cases with missing baseline or current metric values, so metric-movement
counts are not expected to sum to total cases when reports contain `null`
metrics.

## RED Evidence

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_writes_case_movement_summary_for_comparison_report -q
```

Initial result before implementation:

```text
FAILED ... KeyError: 'source_metric_movement'
1 failed in 2.04s
```

Expected failure reason: regular comparison summaries did not expose independent
source-metric movement.

## GREEN Evidence

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_writes_case_movement_summary_for_comparison_report -q
```

Result:

```text
1 passed in 7.68s
```

Focused movement checks:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_case_movement_from_comparison_report_pairs tests/test_public_benchmarks.py::test_public_benchmark_writes_case_movement_summary_for_comparison_report -q
```

Result:

```text
2 passed in 3.93s
```

Post-review missing-metric note and movement-bucket check:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_case_movement_summary_reports_source_metric_movement_and_omits_missing_values tests/test_public_benchmarks.py::test_public_benchmark_writes_case_movement_summary_for_comparison_report -q
```

RED before note hardening:

```text
FAILED ... AssertionError: assert 'missing baseline or current metric values are omitted' in diagnostic_note
1 failed in 0.56s
```

GREEN after note hardening:

```text
2 passed in 7.62s
```

## Focused Verification

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q
```

Result:

```text
19 passed in 8.91s
```

```bash
uv run pytest tests/test_context_composer.py -q
```

Result:

```text
14 passed in 17.89s
```

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_diagnostic_report.py -q
```

Result:

```text
93 passed in 117.98s (0:01:57)
```

```bash
uv run mypy src/memoryos_lite/public_case_movement.py src/memoryos_lite/public_case_diagnostics.py src/memoryos_lite/public_benchmarks.py
```

Result:

```text
Success: no issues found in 3 source files
```

Post-review targeted checks:

```bash
uv run ruff check src/memoryos_lite/public_case_movement.py tests/test_public_benchmarks.py
```

Result:

```text
All checks passed!
```

```bash
uv run mypy src/memoryos_lite/public_case_movement.py
```

Result:

```text
Success: no issues found in 1 source file
```

## Regression Gates

```bash
uv run pytest -q
```

Result:

```text
601 passed, 1 warning in 944.11s (0:15:44)
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

These are the same project-wide blocker class recorded by the previous partial
ACK. Targeted mypy for the touched modules passed.

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Result:

```text
memoryos_lite: cases=16, accuracy=0.56, source=0.56
Report: .memoryos/evals/run_20260525_062949.json
```

This remains the documented hard-eval baseline mismatch for this branch; no
hard-eval improvement or regression claim is made.

## Public Diagnostics

Full public LLM answer/judge gates were not run because no `OPENAI_API_KEY` or
`DEEPSEEK_API_KEY` is configured. The raw public JSON paths named by the
blueprint are also absent in this feature worktree, so no-LLM diagnostics used
absolute data paths from `/home/iiyatu/projects/python/memoryOS/benchmarks`.

No-LLM LongMemEval diagnostic:

```bash
MEMORYOS_EMBEDDING_PROVIDER=none uv run memoryos eval public --benchmark longmemeval --data-path /home/iiyatu/projects/python/memoryOS/benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge --run-id routeb_lme10_after_benchmark_layer_organization_source_metric_no_llm --comparison-report /home/iiyatu/projects/python/memoryOS/.memoryos/evals/routeb_lme50_llm_20260524_longmemeval.json
```

Report:

```text
.memoryos/evals/routeb_lme10_after_benchmark_layer_organization_source_metric_no_llm_longmemeval.json
.memoryos/evals/routeb_lme10_after_benchmark_layer_organization_source_metric_no_llm_longmemeval_movement_summary.json
```

Summary:

```text
rows=10
verdicts={'fail': 7, 'pass': 3}
movement={'fail_to_pass': 0, 'pass_to_fail': 7, 'unchanged_pass': 3, 'unchanged_fail': 0, 'new_case_no_baseline': 0}
source_metric_movement.source_hit={'improved': 0, 'regressed': 0, 'unchanged_hit': 10, 'unchanged_miss': 0}
planned_evidence_source_hit_at_5={'improved': 0, 'regressed': 0, 'unchanged_hit': 8, 'unchanged_miss': 2}
episode_source_hit_at_10={'improved': 0, 'regressed': 0, 'unchanged_hit': 8, 'unchanged_miss': 2}
```

No-LLM LoCoMo diagnostic:

```bash
MEMORYOS_EMBEDDING_PROVIDER=none uv run memoryos eval public --benchmark locomo --data-path /home/iiyatu/projects/python/memoryOS/benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge --run-id routeb_locomo10_after_benchmark_layer_organization_source_metric_no_llm --comparison-report /home/iiyatu/projects/python/memoryOS/.memoryos/evals/routeb_locomo50_llm_20260524_locomo.json
```

Report:

```text
.memoryos/evals/routeb_locomo10_after_benchmark_layer_organization_source_metric_no_llm_locomo.json
.memoryos/evals/routeb_locomo10_after_benchmark_layer_organization_source_metric_no_llm_locomo_movement_summary.json
```

Summary:

```text
rows=10
verdicts={'fail': 10}
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
- Public data files are absent from the assigned feature worktree.
- Full-project `uv run mypy src` still fails with 90 pre-existing errors.
- Hard eval still reports `0.56/0.56`, inconsistent with the AGENTS.md stated
  `1.00/1.00` baseline.

## Decision

The bounded repair slice is implemented and verified. Full blueprint readiness
remains blocked. No aggregate LongMemEval, LoCoMo, or hard-eval improvement is
claimed.
