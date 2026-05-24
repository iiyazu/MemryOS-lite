# phase: phase-17

Task 7: Case-Level Repair Comparison Summary.

RED:
- Command: `uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_comparison_report_lists_case_level_movement_and_source_metrics -q`
- Result: failed with `FileNotFoundError` for `.memoryos/evals/repair-comparison-summary_locomo_repair_smoke_summary.json`, proving `run_public_benchmark` did not yet write the repair-smoke comparison summary.

GREEN:
- Command: `uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_comparison_report_lists_case_level_movement_and_source_metrics -q`
- Result: `1 passed in 2.96s`.

Files changed:
- `tests/test_public_benchmarks.py`
- `src/memoryos_lite/public_repair_smoke.py`
- `src/memoryos_lite/public_benchmarks.py`
- `.hermes-loop/work/phase-17/subagents/task7_comparison_summary.md`

Self-review:
- Summary is written only when `repair_smoke_baseline_report_path` is provided.
- Movement and source metric outputs are case-id lists, with aggregate counts secondary under `counts`.
- `full_chain_gate_status` remains `not_satisfied` for no-LLM repair smoke.
- No executable tool arguments were changed for Task 7.
- Did not edit `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, ACK/review files, benchmark fixtures, or eval output reports.
