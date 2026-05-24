# phase: phase-17

# Phase 17 Result

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle used: `work/phase-17/context_bundle.md`.

## Implemented Real Chain

- `public_eval`: added explicit `--repair-smoke-baseline-report` routing for LoCoMo repair smoke.
- `kernel_loop`: repair smoke requires `MEMORYOS_AGENT_KERNEL=v1` and executes approved `archive_write` through `SimpleAgentStepRunner.run_step()`.
- `store`: repair smoke writes only into the isolated public eval run store.
- `context_composer`: verified archive artifacts become visible only through session-attached, eligible archive passages.
- `answer_projection`: unchanged except full-chain provider failures are surfaced in repair-smoke summary metadata instead of being silently treated as a satisfied gate.
- Default v3 path, explicit v1 fallback, and kernel default-off behavior are preserved.

## Review Repair

The review FAIL was repaired in the same phase:

- Judge-pass/source-localization misses are now normalized into `source_miss_judge_pass` instead of being hidden under `retrieval_miss`.
- Repair summaries now include `baseline_coverage` and block with `full_chain_gate_status = "blocked_baseline_mismatch"` when baseline/current fixed-slice rows are missing, extra, or duplicated.
- Real diagnostic classes `evidence_retrieved_not_selected`, `evidence_selected_not_rendered`, and `evidence_rendered_not_answer_evidence` are now reported through `context_missing_evidence`.
- The public runner preserves raw baseline report rows for summary coverage while using a keyed map only for per-case repair hooks.

## Verification

RED evidence before repair:

- `uv run pytest tests/test_public_benchmarks.py -q -k 'repair_smoke_summary_buckets_judge_pass_source_miss_separately or repair_smoke_summary_blocks_missing_extra_and_duplicate_baseline_rows or repair_smoke_summary_maps_context_diagnostic_classes'` -> `5 failed, 71 deselected`.
- `uv run pytest tests/test_public_benchmarks.py -q -k 'public_repair_smoke_summary_preserves_duplicate_baseline_rows'` -> `1 failed, 76 deselected`.

GREEN/final evidence:

- `uv run pytest tests/test_public_benchmarks.py -q -k 'repair_smoke_summary_buckets_judge_pass_source_miss_separately or repair_smoke_summary_blocks_missing_extra_and_duplicate_baseline_rows or public_repair_smoke_summary_preserves_duplicate_baseline_rows or repair_smoke_summary_maps_context_diagnostic_classes'` -> `6 passed, 71 deselected`.
- `uv run pytest tests/test_public_benchmarks.py -q` -> `77 passed in 66.59s`.
- `uv run pytest tests/test_agent_kernel.py -q` -> `48 passed in 56.75s`.
- `uv run pytest tests/test_context_composer.py tests/test_memory_lifecycle.py -q` -> `22 passed in 12.23s`.
- `uv run pytest -q` -> `536 passed, 1 warning in 682.50s`.
- `uv run ruff check .` -> `All checks passed!`.
- `uv run mypy src/memoryos_lite/public_repair_smoke.py` -> `Success: no issues found in 1 source file`.
- `uv run mypy src` was attempted and remains blocked by unrelated pre-existing project type errors outside the phase scope.

## Case-Level Eval Evidence

Baseline r3:

- Command: `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --run-id phase17_locomo10_baseline_r3 --llm-answer --llm-judge`
- Report: `.memoryos/evals/phase17_locomo10_baseline_r3_locomo.json`
- Heartbeat: `work/phase-17/eval_heartbeat_phase17_locomo10_baseline_r3.json`
- Result: `8 pass / 2 fail`, `answer_mode=llm`, `judge_done=10/10`.

Repair smoke r3:

- Command: `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 10 --run-id phase17_locomo10_kernel_repair_smoke_r3 --repair-smoke-baseline-report .memoryos/evals/phase17_locomo10_baseline_r3_locomo.json --llm-answer --llm-judge`
- Report: `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo.json`
- Summary: `.memoryos/evals/phase17_locomo10_kernel_repair_smoke_r3_locomo_repair_smoke_summary.json`
- Heartbeat: `work/phase-17/eval_heartbeat_phase17_locomo10_kernel_repair_smoke_r3.json`
- Result: `8 pass / 2 fail`, `answer_mode=llm`, `judge_done=10/10`.

Movement:

- `fail_to_pass`: `[]`
- `pass_to_fail`: `[]`
- `unchanged_fail`: `["conv-26_qa_006", "conv-26_qa_008"]`
- `unchanged_pass`: `["conv-26_qa_001", "conv-26_qa_002", "conv-26_qa_003", "conv-26_qa_004", "conv-26_qa_005", "conv-26_qa_007", "conv-26_qa_009", "conv-26_qa_010"]`

Failure classes:

- `retrieval_miss`: `["conv-26_qa_008"]`
- `evidence_hit_answer_fail`: `["conv-26_qa_006"]`
- `context_missing_evidence`: `[]`
- `unsupported_answer`: `[]`
- `judge_questionable`: `[]`
- `source_miss_judge_pass`: `["conv-26_qa_002", "conv-26_qa_003", "conv-26_qa_004", "conv-26_qa_005"]`

Source metric movement:

- `source_hit`: improved `[]`, regressed `[]`
- `planned_evidence_source_hit_at_5`: improved `[]`, regressed `[]`
- `episode_source_hit_at_10`: improved `[]`, regressed `[]`

Baseline coverage:

- `valid=true`
- missing baseline rows: `[]`
- extra baseline rows: `[]`
- duplicate baseline rows: `[]`
- duplicate repair rows: `[]`

Repair execution:

- Executed `archive_write`: `["conv-26_qa_003", "conv-26_qa_004", "conv-26_qa_005", "conv-26_qa_006"]`
- Verified session-attached archive artifacts: 4/4 executed rows.
- Denied rows: `["conv-26_qa_001", "conv-26_qa_002", "conv-26_qa_007", "conv-26_qa_008", "conv-26_qa_009", "conv-26_qa_010"]`
- Denial reasons: 5 `forbidden gold or benchmark value in executable payload`, 1 `unknown or unopened kernel tool`.

Gate interpretation:

- `full_chain_gate_status = "not_satisfied"`.
- Same-slice repair smoke is diagnostic only and is not promotion evidence.
- No LoCoMo pass-to-fail or source metric regression was hidden.
- LongMemEval was not rerun because default v3 retrieval/context/answer behavior is unchanged outside explicit LoCoMo repair-smoke mode.
