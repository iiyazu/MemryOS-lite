# phase: phase-17

Task 8: No-LLM Full-Chain Gate Labeling.

RED:
- Command: `uv run pytest tests/test_public_benchmarks.py::test_no_llm_repair_smoke_report_is_diagnostic_not_full_chain_gate -q`
- Result: failed with `KeyError: 'answer_mode'`, proving the repair-smoke summary did not yet label no-LLM evidence as diagnostic or expose full-chain gate metadata.

GREEN:
- Command: `uv run pytest tests/test_public_benchmarks.py::test_no_llm_repair_smoke_report_is_diagnostic_not_full_chain_gate tests/test_public_benchmarks.py::test_full_chain_repair_smoke_provider_blocker_writes_summary -q`
- Result: `2 passed in 2.28s`.
- Command: `uv run pytest tests/test_public_benchmarks.py::test_repair_smoke_comparison_report_lists_case_level_movement_and_source_metrics -q`
- Result: `1 passed in 2.60s`.

Files changed:
- `tests/test_public_benchmarks.py`
- `src/memoryos_lite/public_repair_smoke.py`
- `src/memoryos_lite/public_benchmarks.py`
- `.hermes-loop/work/phase-17/subagents/task8_gate_labeling.md`

Self-review:
- No-LLM and partial-LLM repair smoke now reports `full_chain_gate_status = "not_satisfied"` with an explicit diagnostic-only reason.
- Provider initialization or invocation failures during requested full-chain repair smoke are recorded in summary metadata as `blocked_provider_unavailable`.
- Same-slice repair smoke still has `promotion_gate_satisfied = false` and `quality_gate_satisfied = false`.
- Provider/gate metadata is report-only and does not alter executable `ToolExecutionRequest.arguments`.
- Kernel default remains unchanged; repair smoke still requires explicit `MEMORYOS_AGENT_KERNEL=v1` and a baseline report.
