# phase: phase-7

Verdict: PASS

Context source: reviewed against `work/phase-7/context_bundle.md`, then `work/phase-7/god_dispatch.json`, `work/phase-7/brainstorm.md`, `work/phase-7/spec.md`, and `work/phase-7/plan.md`. The active goal is to improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## PASS Rationale

The revised spec and plan satisfy the Phase 7 planning gate.

- The prior durable approval replay blocker is addressed. The plan now requires a RED test that emits `approval_pending`, recreates runner/gate/store from the same durable store, resumes with the persisted approval id, validates the same id through `approval_granted` and `tool_executed`, persists exactly one archival memory and one role `tool` message, and proves a second replay is skipped.
- Invalid replay is now covered. The plan requires unknown approval ids and mismatched session/tool/action replays to emit denial/error traces without tool execution, tool-result messages, or archival writes.
- GREEN implementation now requires approval resume to consult persisted pending approval evidence, validating at least `session_id`, `approval_id`, `tool_name`, and requested action before execution. The idempotence guard remains required but is no longer treated as sufficient by itself.
- Kernel behavior remains opt-in through `MEMORYOS_AGENT_KERNEL=v1`; the plan does not enable the v3 kernel by default.
- The default v3 benchmark path remains kernel-off, and public benchmark default-off behavior has an explicit test.
- `MEMORYOS_MEMORY_ARCH=v1` fallback is identified as a preserved guardrail and is not targeted for behavior changes.
- The plan uses the real v3 public benchmark path, requiring payload-bearing `kernel_trace_events` only when `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1` are explicitly set.
- Denied tools, approval-pending, approval-resumed, tool-executed, and replay-skipped control decisions are traceable and payload-bearing.
- Tool result visibility is part of the RED/GREEN path through a role `tool` message visible to later v3 context via the recent-message layer.
- LongMemEval and LoCoMo smoke evidence is required separately; the plan does not promote aggregate-only success or claim answer-quality gains from kernel trace instrumentation.
- The plan avoids Letta runtime dependency, broad autonomous loop work, broad tool expansion, answer prompt tuning, expected-answer leakage, and Hermes infrastructure rewrites.

## Execution Gate

Execution may proceed from `work/phase-7/plan.md` with the following non-negotiable evidence requirements preserved:

- Add/update the RED tests before production changes.
- Prove cold-boundary approval replay from persisted pending evidence, not from runner-local state or arbitrary supplied approval ids.
- Prove unknown/mismatched approval ids do not execute tools or persist success-equivalent side effects.
- Verify default kernel-off public benchmark output and opt-in v3 kernel public benchmark trace output.
- Run focused kernel/public benchmark tests, full `uv run pytest -q`, `uv run ruff check .`, and separate LongMemEval/LoCoMo limit-5 kernel smokes unless scoped down with explicit evidence.
