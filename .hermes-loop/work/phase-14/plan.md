# phase: phase-14

# Phase 14 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit post-action verification step to the opt-in kernel memory-action loop so approved `archive_write` steps prove durable store/context visibility without changing defaults.

**Architecture:** Keep the kernel surface narrow. `SimpleToolExecutionManager` remains the executor for the existing supported tool, but it now returns a structured verification payload after a successful write. `SimpleAgentStepRunner` emits a separate `tool_verified` trace event only after `tool_executed`. The tests prove the real store, archive attachment, and v3 composer visibility, while unsupported tools and replay tampering remain explicit denials.

**Tech Stack:** Python 3.11, pytest, pydantic, sqlite, existing MemoryOS Lite v3 composer/store/kernel code.

---

### Task 1: Lock the RED tests for kernel verification

**Files:**
- Modify: `tests/test_agent_kernel.py`
- Modify: `tests/test_public_benchmarks.py`

- [ ] **Step 1: Write the failing test**

Add a new kernel test that asserts the approved `archive_write` step emits a
`tool_verified` trace event after `tool_executed`, and that the verification
payload proves store and context visibility.

```python
def test_kernel_archive_write_emits_verification_trace_and_store_visibility(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )

    reopened = create_store(settings)
    resumed = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id)],
    )

    assert [event.event_type for event in resumed.trace] == [
        "kernel_step_started",
        "tool_policy_decision",
        "approval_granted",
        "tool_executed",
        "tool_verified",
        "kernel_step_completed",
    ]
    verified = next(event for event in resumed.trace if event.event_type == "tool_verified")
    assert verified.payload["verification"]["status"] == "verified"
    assert verified.payload["verification"]["session_attachment_found"] is True
    assert verified.payload["verification"]["eligible_for_session"] is True

    v3_package = V3ContextComposer(store=reopened, settings=settings).build(
        ContextComposerRequest(session_id="ses_1", task="approved archival fact", budget=120)
    )
    assert any(item.layer == "archival" for item in v3_package.items)
```

Add a second test that proves replay tampering still has no side effects and no
verification trace.

```python
def test_kernel_replay_tampering_emits_no_verification_trace(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )

    reopened = create_store(settings)
    result = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id, content="tampered archival fact")],
    )
    event_types = [event.event_type for event in result.trace]
    assert "approval_replay_denied" in event_types or "approval_replay_error" in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    assert reopened.list_messages("ses_1") == []
```

Update the public kernel probe test so the enabled-kernel trace sequence
expects `tool_verified`.

```python
assert [event["event_type"] for event in kernel_trace_events] == [
    "kernel_step_started",
    "tool_policy_decision",
    "approval_pending",
    "kernel_step_completed",
    "kernel_step_started",
    "tool_policy_decision",
    "approval_granted",
    "tool_executed",
    "tool_verified",
    "kernel_step_completed",
]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Expected: fail because `tool_verified` does not exist yet.

### Task 2: Implement verification payload and trace emission

**Files:**
- Modify: `src/memoryos_lite/v3_contracts.py`
- Modify: `src/memoryos_lite/agent_kernel.py`
- Modify: `src/memoryos_lite/store.py` only if a tiny read helper is needed

- [ ] **Step 1: Write the minimal implementation**

Add a structured verification payload to `ToolExecutionResult` and compute it
inside `SimpleToolExecutionManager._archive_write()`. The verification should
inspect the real store state after the write:

```python
verification = {
    "status": "verified",
    "memory_id": memory.id,
    "archive_id": memory.archive_id,
    "passage_id": f"apsg_{memory.id}",
    "history_events": len(self.store.list_archival_memory_history(memory.id)),
    "session_attachment_found": any(
        attachment.archive_id == memory.archive_id
        for attachment in self.store.list_archive_attachments(
            scope_type="session",
            scope_id=request.session_id,
        )
    ),
    "eligible_for_session": any(
        passage.id == f"apsg_{memory.id}"
        for passage in self.store.list_archival_passages_for_scope(
            ArchiveEligibilityScope(session_id=request.session_id)
        ).eligible_passages
    ),
    "source_ref_ids": [ref.source_id for ref in source_refs if ref.source_id],
}
```

Return that payload from the tool result, then have `SimpleAgentStepRunner`
append a new `tool_verified` trace event after `tool_executed` when the tool
result is successful. The trace payload should mirror the verification payload
and keep the approval id and tool name attached.

Keep unsupported tool handling unchanged: unknown tool names still produce
explicit denials. Keep replay guard behavior unchanged: tampered approvals still
stop before execution.

- [ ] **Step 2: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
```

Expected: pass.

### Task 3: Re-check the public kernel trace smoke and baseline

**Files:**
- Modify: `tests/test_public_benchmarks.py`
- Modify: `tests/test_agent_kernel.py` if trace ordering needs small cleanup

- [ ] **Step 1: Confirm the public kernel trace still stays default-off**

Keep the default-off test asserting `kernel_trace_events == []` and
`kernel_trace_present is False`.

- [ ] **Step 2: Run the focused public trace tests**

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Expected: pass with the new `tool_verified` trace event in the opt-in path.

- [ ] **Step 3: Run the baseline checks**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: both pass.

### Task 4: Review and handoff

**Files:**
- Create or modify: `.hermes-loop/work/phase-14/result.md`
- Create or modify: `.hermes-loop/work/phase-14/execute_review.md`
- Create or modify: `.hermes-loop/work/phase-14/ack.json` only if the review and evidence justify it

- [ ] **Step 1: Summarize the real chain change**

Record that the kernel now emits an auditable verification trace for the
existing supported tool and that the default kernel-off path did not change.

- [ ] **Step 2: Summarize benchmark impact conservatively**

State that this phase is structural and does not claim LongMemEval or LoCoMo
improvement.

- [ ] **Step 3: Review the phase against the spec**

Confirm no demo-only behavior remains, unsupported tools still deny cleanly, and
kernel opt-in / v3 default / v1 fallback remain intact.

