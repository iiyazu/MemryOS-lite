# phase: phase-14

# Phase 14 Spec: Opt-In Kernel Memory Action Verification

Context bundle: `.hermes-loop/work/phase-14/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Decision

Phase 14 should not expand the kernel into a broad Letta-style tool surface.
The usable target is a narrower audited loop for the existing supported memory
tool, `archive_write`.

The phase will add explicit post-action verification for successful
`archive_write` calls and persist that verification as a kernel trace event.
Unsupported memory tool names stay denied unless a later phase intentionally
implements them through the phase-13 lifecycle contract.

## Contract

When `MEMORYOS_AGENT_KERNEL=v1` is enabled and an approved `archive_write`
executes successfully, the kernel step must emit this ordered trace shape:

```text
kernel_step_started
tool_policy_decision
approval_granted
tool_executed
tool_verified
kernel_step_completed
```

The first approval pass still pauses:

```text
kernel_step_started
tool_policy_decision
approval_pending
kernel_step_completed
```

`tool_verified` must be durable in `trace_events` and visible through
`kernel_trace_events` in public benchmark reports when the kernel is explicitly
enabled.

## Verification Payload

`tool_verified.payload` must include:

- `tool_name = "archive_write"`;
- `approval_id`;
- `ok = true` when verification succeeded;
- `result.memory_id`;
- `result.archive_id`;
- `verification.status = "verified"`;
- `verification.memory_id`;
- `verification.archive_id`;
- `verification.passage_id`;
- `verification.history_events >= 1`;
- `verification.session_attachment_found = true`;
- `verification.eligible_for_session = true`;
- `verification.source_ref_ids`.

The verification must inspect real store state after execution:

- archival memory history exists for the new memory id;
- an archival passage for the memory exists;
- the session has an attached archive for the written archive id;
- `MemoryStore.list_archival_passages_for_scope()` makes the passage eligible
  for the current session.

Focused tests should also build a real `V3ContextComposer` package after the
kernel step and prove the archival item can be selected from the same session.

## Unsupported And Replay Behavior

Unsupported memory tool names such as `core_memory_update` and
`memory_deprecate` must remain explicit denials unless implemented in a future
phase.

Approval replay tampering must produce no write, no tool message, and no
`tool_verified` event. Existing replay checks for `session_id`, `tool_name`, and
`requested_action` remain required.

## Implementation Boundaries

Allowed files:

- `src/memoryos_lite/v3_contracts.py`
- `src/memoryos_lite/agent_kernel.py`
- `tests/test_agent_kernel.py`
- `tests/test_public_benchmarks.py`

Possible but not expected:

- `src/memoryos_lite/store.py` only if a small read helper is needed.
- `tests/test_context_composer.py` only if the verification requires a new
  composer assertion not covered by `tests/test_agent_kernel.py`.

Do not change:

- default settings for `MEMORYOS_MEMORY_ARCH`;
- default settings for `MEMORYOS_AGENT_KERNEL`;
- benchmark scoring, judge logic, or answer projection.

## Acceptance Criteria

- At least one phase-14 RED test fails before implementation.
- Approved `archive_write` emits `tool_verified` only after `tool_executed`.
- Verification checks real store/context eligibility state.
- Denied and replay-rejected tool requests do not emit verification events.
- Public benchmark kernel trace remains empty by default.
- Public benchmark kernel trace includes `tool_verified` only when the kernel is
  explicitly enabled.
- `uv run pytest tests/test_agent_kernel.py -q` passes.
- Focused public kernel trace tests pass.
- `uv run pytest -q` and `uv run ruff check .` pass before review.
- No benchmark improvement claim is made from this structural kernel phase.

