# phase: phase-15

# Execute Self-Review

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle:
`work/phase-15/context_bundle.md`

## What Real Chain Changed?

- `kernel_loop`: changed in the real `SimpleAgentStepRunner.run_step()` path. Non-empty tool requests now go through K2 candidate generation, constrained selection, fail-closed denial, and durable traces before policy.
- `public_eval`: changed for the real public benchmark path. The opt-in kernel probe now replays approval with the selected `tool_call_id`, and public reports include planner sidecar/proposal artifacts.
- `retrieval`, `context_composer`, and `answer_projection`: not changed. They are used as model-visible public diagnostic inputs.

## Demo-Only Or Partial Work?

No demo-only helper is counted as complete:

- K2 is invoked from `SimpleAgentStepRunner.run_step()`, not only tests.
- Public opt-in kernel traces reach K2 through `evals.py`.
- Planner artifacts are emitted from `run_public_benchmark()` reports.
- Planner proposals are intentionally not executed in Phase 15.

Remaining partial scope by design:

- Maintenance proposal execution belongs to later phases.
- Retrieval-miss repair semantics are not implemented in Phase 15.

## Tests Proving Behavior

- `tests/test_agent_kernel.py`: candidate generation, selection, non-candidate denial, invalid selector denial, duplicate id handling, provenance, replay binding, and mutation absence.
- `tests/test_public_benchmarks.py`: default kernel-off report behavior, opt-in kernel K2 trace/replay behavior, planner gold sidecar separation, diagnostic-only denial, grounding-risk non-execution, and public report artifact presence.
- `tests/test_context_composer.py` focused settings tests: v3 default and kernel-off default preserved.

Fresh verification:

- `uv run pytest tests/test_public_benchmarks.py -q` -> `61 passed in 43.86s`
- `uv run pytest tests/test_agent_kernel.py -q` -> `28 passed in 28.48s`
- `uv run pytest tests/test_context_composer.py::test_settings_default_to_v3_composer_with_kernel_off tests/test_context_composer.py::test_settings_resolve_v3_composer_and_kernel_flags -q` -> `2 passed in 0.02s`
- `uv run pytest -q` -> `499 passed, 1 warning in 627.72s`
- `uv run ruff check .` -> `All checks passed!`

## Benchmark Cases Moved Or Regressed?

No baseline comparison was used for this structural smoke, so movement is `new_case_no_baseline`.

LoCoMo 5-case no-LLM smoke:

- `conv-26_qa_001`: fail, `source_hit=true`, `failure_class=evidence_hit_answer_fail`, proposal `archive_write`, no kernel events.
- `conv-26_qa_002`: fail, `source_hit=true`, `failure_class=evidence_hit_answer_fail`, proposal `archive_write`, no kernel events.
- `conv-26_qa_003`: fail, `source_hit=false`, `failure_class=retrieval_miss`, proposal `archive_write`, no kernel events.
- `conv-26_qa_004`: fail, `source_hit=false`, `failure_class=retrieval_miss`, proposal `archive_write`, no kernel events.
- `conv-26_qa_005`: fail, `source_hit=false`, `failure_class=retrieval_miss`, proposal `archive_write`, no kernel events.

This evidence proves planner/report shape and non-execution only. It does not claim answer or retrieval improvement.

## Default And Fallback Check

- v1 fallback preserved: yes.
- v3 default preserved: yes.
- kernel default unchanged: yes, `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- source grounding regressed: no evidence of regression in this phase. The no-LLM LoCoMo smoke keeps source-hit and failure-class fields visible per case.

## Review Risks To Inspect

- Repair verified: planner proposal shape is invariant across different `EvalGoldSidecar` values for the same model-visible input.
- Repair verified: selector/provider unavailable exceptions emit durable `tool_selection_denied` and do not reach policy, approval, execution, verification, or memory mutation.
- Ensure retrieval-miss rows being proposal-only `archive_write` from model-visible evidence are treated as diagnostics, not repair evidence.
- Ensure public default-off kernel reports remain empty in `kernel_trace_events`.
