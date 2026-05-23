# phase: phase-14

# Phase 14 Final Plan: Opt-In Kernel Memory Action Verification

Context bundle: `.hermes-loop/work/phase-14/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Source artifacts:

- Brainstorm: `.hermes-loop/work/phase-14/brainstorm.md`;
- Spec: `.hermes-loop/work/phase-14/spec.md`;
- Draft plan: `.hermes-loop/work/phase-14/plan.md`;
- Plan review: `.hermes-loop/work/phase-14/plan_review.md` (`PASS`).

## Final Decision

Implement the smallest credible audited kernel loop:

- keep `archive_write` as the only supported kernel tool;
- add a durable `tool_verified` trace event after successful `tool_executed`;
- verify the real store and same-session v3 archival eligibility path;
- keep unsupported tools denied;
- keep `MEMORYOS_AGENT_KERNEL=v1` opt-in.

Do not add core-memory tools in this phase unless execution RED evidence proves
`archive_write` verification alone is demo-only.

## Files

Expected production files:

- `src/memoryos_lite/v3_contracts.py`;
- `src/memoryos_lite/agent_kernel.py`;
- `src/memoryos_lite/store.py` only if a tiny read helper is needed.

Expected tests:

- `tests/test_agent_kernel.py`;
- `tests/test_public_benchmarks.py`;
- `tests/test_context_composer.py` only if a new composer-only assertion is required.

## Task 1: RED Tests

Add failing tests before production changes.

Required failing assertion in `tests/test_agent_kernel.py`:

```python
assert [event.event_type for event in resumed.trace] == [
    "kernel_step_started",
    "tool_policy_decision",
    "approval_granted",
    "tool_executed",
    "tool_verified",
    "kernel_step_completed",
]
```

The `tool_verified` payload must assert:

```python
assert verified.payload["tool_name"] == "archive_write"
assert verified.payload["ok"] is True
assert verified.payload["verification"]["status"] == "verified"
assert verified.payload["verification"]["session_attachment_found"] is True
assert verified.payload["verification"]["eligible_for_session"] is True
```

Also add or extend tests so replay-tampered approvals and unsupported tools
produce no `tool_executed`, no `tool_verified`, no tool message, and no memory
write.

Update `tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled`
so the opt-in trace shape includes `tool_verified` after `tool_executed`. Keep
`test_public_benchmark_kernel_trace_remains_default_off` unchanged.

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Expected before implementation: failure because `tool_verified` is missing.

## Task 2: GREEN Implementation

Add verification support with minimal surface area.

Required shape:

- `ToolExecutionResult` can carry a structured `verification` payload;
- `SimpleToolExecutionManager._archive_write()` computes verification after the
  archival memory and archive attachment are written;
- `SimpleAgentStepRunner.run_step()` emits `tool_verified` after `tool_executed`
  when a successful tool result has verification data.

Verification must inspect real store state:

- archival memory history exists for `memory_id`;
- passage id `apsg_{memory_id}` exists in archival passages for the archive;
- same-session archive attachment exists;
- `MemoryStore.list_archival_passages_for_scope(ArchiveEligibilityScope(session_id=...))`
  includes the passage.

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Expected after implementation: pass.

## Task 3: Public Kernel Trace Smoke

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Expected:

- default-off report still has `kernel_trace_events == []`;
- opt-in report includes `tool_verified`;
- no public scoring, answer projection, or judge behavior changes.

## Task 4: Baseline And Review Evidence

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Write execution artifacts:

- `.hermes-loop/work/phase-14/result.md`;
- `.hermes-loop/work/phase-14/execute_review.md`;
- `.hermes-loop/work/phase-14/review_verdict.json`;
- `.hermes-loop/work/phase-14/ack.json` only after review PASS and usable evidence.

The result and ACK must state that this is structural kernel-loop evidence and
not a LongMemEval/LoCoMo benchmark improvement claim.

## Anti-Demo Gate

The phase is not usable if:

- `tool_verified` only echoes the request/result payload;
- verification does not inspect real store or context eligibility;
- unsupported tools are silently remapped or no-op accepted;
- kernel becomes default-on;
- public benchmark scoring changes without a full-chain same-case gate.

