# phase: phase-7

Context source: `work/phase-7/context_bundle.md` is the controlling bundle for this spec. Scope is intentionally narrowed to Option B from `work/phase-7/brainstorm.md`: a durable opt-in control-plane slice.

## Phase 7 Contract

Phase 7 hardens `MEMORYOS_AGENT_KERNEL=v1` from a trace demo into a benchmark-usable, Letta-style control-plane slice for MemoryOS Lite v3. The kernel must remain opt-in, must not alter `MEMORYOS_MEMORY_ARCH=v1`, and must not change the default v3 public benchmark path when `MEMORYOS_AGENT_KERNEL` is unset or `off`.

The contract is:

1. A tool request is always represented as an auditable control-plane decision.
2. Denied tools produce a durable denial result and are not executed.
3. Initial approval-pending state is persisted with enough evidence to survive a recreated runner/gate/store boundary.
4. Approval replay resumes only from persisted pending approval evidence with the same approval id.
5. Approval grant validation checks session id, approval id, tool name, and requested action before execution.
6. Resumed approval executes the approved tool exactly once.
7. Unknown or mismatched approval ids are denied or error-traced and do not execute tools, persist tool messages, or write memory.
8. Executed tools produce durable result traces.
9. Successful tool execution produces a bounded tool-result message/log entry visible to a later v3 context build when relevant.
10. Public benchmark reports expose kernel trace events only when `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1` are explicitly set.
11. LongMemEval and LoCoMo evidence remains case-level; kernel trace presence is not an answer-quality claim.

## Scope

Implementation scope:

- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`
- `src/memoryos_lite/context_composer.py` only if tool-result messages are not already visible through the recent-message layer
- `src/memoryos_lite/store.py` only if existing message/trace persistence cannot support the durable contract
- `src/memoryos_lite/v3_contracts.py` only if result schemas need explicit fields for approval ids or trace payloads

Test scope:

- `tests/test_agent_kernel.py`
- `tests/test_public_benchmarks.py`
- `tests/test_context_composer.py` only if the visibility assertion is clearer there than in `test_agent_kernel.py`

Required behavior is limited to `archive_write` and unknown-tool denial. Do not add broad tool support unless a failing Phase 7 test proves a real chain need.

## Non-Goals

- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change the default `MEMORYOS_MEMORY_ARCH=v3` behavior into a kernel path.
- Do not change `MEMORYOS_MEMORY_ARCH=v1` fallback behavior.
- Do not add Letta as a runtime dependency.
- Do not port Letta internals or implement a broad autonomous loop.
- Do not tune answer prompts, answer projection, citation rules, or benchmark expected-answer handling.
- Do not use benchmark case ids, expected answers, or expected evidence as kernel control inputs.
- Do not hide LoCoMo misses behind aggregate benchmark movement or trace presence.
- Do not edit Hermes controller files outside `work/phase-7/spec.md` and `work/phase-7/plan.md` for this lane.

## Acceptance Criteria

Phase 7 is acceptable only if all criteria below are met:

- `Settings.memoryos_agent_kernel` remains default `off`, and `Settings.resolved_agent_kernel` still accepts only `off` and `v1`.
- `MemoryOSService.agent_kernel` is constructed only when `settings.resolved_agent_kernel == "v1"`.
- Denied `archive_write` and denied unknown-tool requests emit a durable denial trace/result and create no archival memory.
- Initial approval-pending trace payload is persisted before any resume and contains replayable approval state, including approval id, session id, tool name, requested action, status, source refs, and reason metadata.
- A fresh `SimpleAgentStepRunner`, `ApprovalGateV1`, and store handle using the same durable store can resume with the persisted pending approval id.
- Approval replay consults persisted pending approval evidence and validates session id, approval id, tool name, and requested action before execution.
- Resume with the persisted pending approval id emits `approval_granted` and `tool_executed` trace details preserving the same approval id.
- Exactly one archival memory and exactly one role `tool` message are persisted for the approved execution.
- Repeating the same approved request does not duplicate the archival memory write or tool-result message.
- A second replay with the same approval id is idempotently skipped with a durable `tool_replay_skipped` trace.
- Unknown approval ids, or approvals whose id exists but whose session id, tool name, or requested action does not match persisted pending evidence, produce a denial/error trace and do not execute the tool, persist a tool message, or write archival memory.
- Successful `archive_write` emits a tool-result message/log entry with role `tool`, tool name, approval id when present, result payload, and source refs or explicit manual approval source.
- A later v3 context build can include the tool-result message through the normal recent-message path, or a precise diagnostic explains why visibility is intentionally unavailable.
- Public benchmark output keeps `kernel_trace_events` empty when kernel is default-off.
- Public benchmark output includes non-empty, payload-bearing `kernel_trace_events` when `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1` are explicitly set.
- Focused kernel tests, default-off public benchmark test, opt-in public benchmark test, full pytest, ruff, and both 5-case public kernel smokes are run or explicitly scoped down with evidence.
- Any full-chain judge run, if needed, reports LongMemEval and LoCoMo separately with case-level records.

## Anti-Demo Criteria

The phase is not acceptable if any of these are true:

- Kernel usability is proven only by direct unit tests and not by the real v3 public benchmark path.
- `kernel_trace_events` is non-empty but contains only event names with no decision/result payload detail.
- Approval pause/resume works only within a single in-memory call stack and cannot be replayed from persisted pending approval evidence after runner/gate/store recreation.
- Approval replay trusts an arbitrary supplied `approval_id` instead of validating it against persisted pending evidence for the same session id, tool name, and requested action.
- Unknown or mismatched approval ids execute a tool, write archival memory, persist a role `tool` message, or emit success-equivalent traces.
- Denial silently skips execution without a denial result the loop can reason about.
- A denied tool writes archival memory, core memory, trace-equivalent success, or a tool-result message that implies success.
- Tool execution writes archival memory but leaves no durable result trace or later-context-visible result message.
- Replaying the same approval duplicates memory writes.
- Kernel behavior appears when `MEMORYOS_AGENT_KERNEL` is unset or `off`.
- `MEMORYOS_MEMORY_ARCH=v1` behavior changes.
- LoCoMo residual failures are hidden by aggregate scores, trace presence, or LongMemEval-only success.
- Phase completion claims answer-quality improvement from control-plane instrumentation alone.
