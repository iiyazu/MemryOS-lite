# phase: phase-7

Context source: `work/phase-7/context_bundle.md` is the controlling bundle for this plan. This plan follows Option B from `work/phase-7/brainstorm.md`: durable control-plane slice, narrow scope, kernel opt-in only.

## Goal

Make the opt-in v3 kernel auditable in the real public benchmark path by adding denial results, persisted approval replay validation across a recreated runner/gate/store boundary, idempotent tool execution, tool-result traces, and later-context-visible tool-result messages without enabling the kernel by default.

## File Map

- Modify: `tests/test_agent_kernel.py`
  - Add RED coverage for denial non-execution, unknown-tool denial, persisted approval replay across a cold runner/gate/store boundary, unknown/mismatched approval rejection, approval idempotence, and tool-result message visibility.
- Modify: `tests/test_public_benchmarks.py`
  - Keep default-off public benchmark assertion and update opt-in assertion to require payload-bearing kernel trace events.
- Modify: `src/memoryos_lite/agent_kernel.py`
  - Emit denial result traces, persist tool-result messages, attach approval ids to tool execution traces, validate approval replay from persisted pending evidence, and guard repeated approval execution.
- Modify: `src/memoryos_lite/evals.py`
  - Preserve full kernel trace event payloads from the opt-in public benchmark probe instead of event-name-only rows.
- Modify: `src/memoryos_lite/public_benchmarks.py`
  - Carry payload-bearing `kernel_trace_events` into reports.
- Modify: `src/memoryos_lite/public_case_diagnostics.py`
  - Treat payload-bearing `kernel_trace_events` as presence evidence without changing failure classification semantics.
- Verify only if needed: `src/memoryos_lite/context_composer.py`
  - Existing recent-message layer should make role `tool` messages visible; change only if the RED visibility test proves otherwise.
- Verify only if needed: `src/memoryos_lite/v3_contracts.py`
  - Existing `KernelTraceEvent.approval_id`, `AgentStepResult.messages`, and `ToolExecutionResult` should be enough; change only if schema validation blocks payload detail.

## RED

1. Add `tests/test_agent_kernel.py::test_kernel_denies_archive_write_without_execution_or_memory_write`

   Test setup:

   - Create `Settings(data_dir=tmp_path / ".memoryos")`, `store = create_store(settings)`, and `store.reset()`.
   - Build `SimpleAgentStepRunner` with one `ToolPolicyRule(id="deny_archive_write", tool_name="archive_write", effect="deny", reason="not allowed in this test")` and `SimpleToolExecutionManager(store=store)`.
   - Send `ToolExecutionRequest(session_id="ses_1", tool_name="archive_write", arguments={"content": "must not be written"}, source_refs=[SourceRef(source_type=SourceType.MESSAGE, source_id="msg_1", session_id="ses_1")])`.

   Required assertions:

   - `result.continuation == "stop"`.
   - Result trace event types include `tool_policy_decision`, `tool_denied`, and `kernel_step_completed`.
   - Result trace event types do not include `tool_executed`.
   - The `tool_denied` payload contains `tool_name == "archive_write"`, `ok is False`, and the denial reason.
   - `store.list_messages("ses_1") == []`.
   - A direct SQLite count of `archival_memories` is `0`.

   Expected failure command:

   ```bash
   uv run pytest tests/test_agent_kernel.py::test_kernel_denies_archive_write_without_execution_or_memory_write -q
   ```

   Expected RED failure: assertion fails because current denial records only `tool_policy_decision` and does not emit `tool_denied`.

2. Add `tests/test_agent_kernel.py::test_kernel_denies_unknown_tool_as_result_without_executor_call`

   Test setup:

   - Build `SimpleAgentStepRunner(store=store, tool_execution_manager=SimpleToolExecutionManager(store=store))` with no policy rules.
   - Send `ToolExecutionRequest(session_id="ses_1", tool_name="unknown_tool", arguments={"content": "ignored"})`.

   Required assertions:

   - Result trace event types include `tool_denied`.
   - Result trace event types do not include `tool_executed`.
   - `tool_denied.payload["error"]` contains `no matching tool policy rule`.
   - `store.list_messages("ses_1") == []`.

   Expected failure command:

   ```bash
   uv run pytest tests/test_agent_kernel.py::test_kernel_denies_unknown_tool_as_result_without_executor_call -q
   ```

   Expected RED failure: assertion fails because unknown tools currently stop after `tool_policy_decision`.

3. Update `tests/test_agent_kernel.py::test_kernel_resumes_approval_and_executes_archive_write`

   Rename it to `test_kernel_replays_persisted_approval_after_cold_boundary_executes_once_and_persists_tool_result_message`.

   Test setup:

   - Create `Settings(data_dir=tmp_path / ".memoryos")`, `store = create_store(settings)`, and `store.reset()`.
   - Build an initial `SimpleAgentStepRunner` with `ApprovalGateV1(store=store)` or the equivalent current constructor that allows the gate to consult persisted traces, one `ToolPolicyRule(id="approve_archive_write", tool_name="archive_write", effect="require_approval", reason="needs approval")`, and `SimpleToolExecutionManager(store=store)`.
   - Send `ToolExecutionRequest(session_id="ses_1", tool_name="archive_write", arguments={"content": "approved archival fact"}, source_refs=[SourceRef(source_type=SourceType.MESSAGE, source_id="msg_1", session_id="ses_1")])` without `approval_id`.
   - Assert the initial result emits `approval_pending` and persists that pending trace before any resume.
   - Save `approval_id = approval_pending.approval_id`.
   - Recreate the durable boundary: close or discard the initial runner, approval gate, and store handle; create a new store with the same `settings.data_dir`; then create a new `ApprovalGateV1`, `SimpleToolExecutionManager`, and `SimpleAgentStepRunner` from that reopened store.
   - Resume by sending the same request with `approval_id=approval_id`.

   Required assertions after initial pending:

   - Persisted traces from the reopened store contain exactly one `approval_pending`.
   - The pending trace has the same `approval_id`.
   - The pending trace payload includes `status == "pending"`, `session_id == "ses_1"`, `tool_name == "archive_write"`, requested action/content for `approved archival fact`, source refs, and policy reason metadata.
   - Direct SQLite count of `archival_memories` is `0`.
   - `store.list_messages("ses_1") == []`.

   Required assertions after first resume:

   - `approval_granted.approval_id == approval_id`.
   - `approval_granted.payload["approval_id"] == approval_id`.
   - `approval_granted.payload["session_id"] == "ses_1"`.
   - `approval_granted.payload["tool_name"] == "archive_write"`.
   - `approval_granted.payload["approved_action"]` or equivalent payload field matches the persisted pending requested action/content.
   - `tool_executed.approval_id == approval_id`.
   - `tool_executed.payload["approval_id"] == approval_id`.
   - `tool_executed.payload["ok"] is True`.
   - `len(resumed.messages) == 1`.
   - `resumed.messages[0].role == Role.TOOL`.
   - `resumed.messages[0].metadata["tool_name"] == "archive_write"`.
   - `resumed.messages[0].metadata["approval_id"] == approval_id`.
   - `store.list_messages("ses_1")` contains exactly one role `tool` message.
   - Direct SQLite count of `archival_memories` is `1`.

   Add a second replay through a freshly recreated runner/gate/store using the same durable store and the same approval id/request. Required assertions:

   - Trace contains `tool_replay_skipped`.
   - `tool_replay_skipped.payload["approval_id"] == approval_id`.
   - `tool_replay_skipped.payload["reason"] == "approval already executed"`.
   - Trace does not contain a second successful `tool_executed`.
   - Direct SQLite count of `archival_memories` remains `1`.
   - Role `tool` message count remains `1`.

   Expected failure command:

   ```bash
   uv run pytest tests/test_agent_kernel.py::test_kernel_replays_persisted_approval_after_cold_boundary_executes_once_and_persists_tool_result_message -q
   ```

   Expected RED failure: current approval handling can approve based on the supplied `approval_id` without proving persisted pending evidence across a recreated runner/gate/store boundary, returns no result messages, and repeats the archival write on repeated replay.

4. Add `tests/test_agent_kernel.py::test_kernel_rejects_unknown_or_mismatched_approval_replay_without_side_effects`

   Test setup:

   - Use the same initial approval-pending flow from step 3 to persist one pending approval for `session_id="ses_1"`, `tool_name="archive_write"`, and content `approved archival fact`.
   - Recreate the runner/gate/store boundary from the same durable store before each invalid replay.
   - Attempt replay with `approval_id="approval_missing"` and otherwise matching request.
   - Attempt replay with the persisted pending `approval_id` but `session_id="ses_2"`.
   - Attempt replay with the persisted pending `approval_id` but `tool_name="unknown_tool"`.
   - Attempt replay with the persisted pending `approval_id` and `tool_name="archive_write"` but requested content/action changed to `tampered archival fact`.

   Required assertions for each invalid replay:

   - Trace contains `approval_replay_denied` or `approval_replay_error` with payload fields `approval_id`, `session_id`, `tool_name`, and a concrete mismatch reason.
   - Trace does not contain `approval_granted`.
   - Trace does not contain `tool_executed`.
   - Direct SQLite count of `archival_memories` remains `0`.
   - `store.list_messages("ses_1")` has no role `tool` messages.
   - No success-equivalent tool result message is persisted for any session.

   Expected failure command:

   ```bash
   uv run pytest tests/test_agent_kernel.py::test_kernel_rejects_unknown_or_mismatched_approval_replay_without_side_effects -q
   ```

   Expected RED failure: current approval handling can treat an arbitrary supplied `approval_id` as approved and does not validate session id, tool name, or requested action against persisted pending evidence before execution.

5. Add `tests/test_agent_kernel.py::test_kernel_tool_result_message_is_visible_to_later_v3_context`

   Test setup:

   - Use the cold-boundary approval replay flow from step 3 to execute `archive_write` with content `approved archival fact`.
   - Build a later context with `V3ContextComposer(store=store, settings=settings).build(ContextComposerRequest(session_id="ses_1", task="approved archival fact", budget=120))`.

   Required assertions:

   - A context item exists with `layer == "recent"`.
   - That item has `metadata["role"] == "tool"`.
   - Its text contains `archive_write`.
   - Its text or metadata contains the created `memory_id`.
   - `package.metadata["memory_arch"] == "v3"`.

   Expected failure command:

   ```bash
   uv run pytest tests/test_agent_kernel.py::test_kernel_tool_result_message_is_visible_to_later_v3_context -q
   ```

   Expected RED failure: current kernel does not persist a tool result message.

6. Keep and update `tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off`

   Required assertions:

   - `report["memory_arch"] == "v3"`.
   - `report["kernel_trace_events"] == []`.
   - `report["case_diagnostics"]["kernel_trace_present"] is False`.

   Expected failure command:

   ```bash
   uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off -q
   ```

   Expected result before GREEN: PASS. If it fails, stop and fix the default-off regression before adding kernel behavior.

7. Rename `tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled` to `test_public_benchmark_kernel_trace_present_when_opted_in`

   Required assertions:

   - `report["memory_arch"] == "v3"`.
   - `report["kernel_trace_events"]` is non-empty.
   - `[event["event_type"] for event in report["kernel_trace_events"]]` equals:

     ```python
     [
         "kernel_step_started",
         "tool_policy_decision",
         "approval_pending",
         "kernel_step_completed",
         "kernel_step_started",
         "tool_policy_decision",
         "approval_granted",
         "tool_executed",
         "kernel_step_completed",
     ]
     ```

   - The `tool_policy_decision` event payload includes `effect == "require_approval"`.
   - The `approval_pending` event has a non-empty `approval_id`.
   - The `approval_granted` event has the same `approval_id`.
   - The `tool_executed` event has the same `approval_id`, `payload["ok"] is True`, and a non-empty `payload["result"]["memory_id"]`.
   - `report["case_diagnostics"]["kernel_trace_present"] is True`.

   Expected failure command:

   ```bash
   uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_present_when_opted_in -q
   ```

   Expected RED failure: current public benchmark stores event names only, so `event["event_type"]` fails.

## GREEN

1. Update `src/memoryos_lite/agent_kernel.py` denial handling

   Implementation requirements:

   - When `decision.effect == "deny"`, create `ToolExecutionResult(tool_name=tool_request.tool_name, ok=False, error=decision.reason)`.
   - Append a `tool_denied` `KernelTraceEvent` with payload:

     ```python
     {
         "tool_name": tool_request.tool_name,
         "ok": False,
         "error": decision.reason,
         "decision": decision.model_dump(mode="json"),
     }
     ```

   - Do not call `self.tool_execution_manager.execute()`.
   - Do not persist a tool result message for denied tools.
   - Preserve `continuation = "stop"`.

   Pass command:

   ```bash
   uv run pytest tests/test_agent_kernel.py::test_kernel_denies_archive_write_without_execution_or_memory_write tests/test_agent_kernel.py::test_kernel_denies_unknown_tool_as_result_without_executor_call -q
   ```

2. Update `src/memoryos_lite/agent_kernel.py` durable approval replay validation and idempotence guard

   Implementation requirements:

   - On initial `require_approval`, persist `approval_pending` before returning. Its event-level `approval_id` and payload must include `approval_id`, `status="pending"`, `session_id`, `tool_name`, requested action/arguments, source refs, and policy reason metadata.
   - On replay with `approval_id`, do not approve from the supplied id alone. Load persisted pending approval evidence from the durable store, either by scanning persisted `approval_pending` trace payloads or by reading an explicit durable approval record if execution introduces one.
   - A pending approval match is valid only when all of these match the replay request: `session_id`, `approval_id`, `tool_name`, and requested action/arguments. Source refs should also be preserved in the granted payload when present.
   - If no pending evidence exists, or if any required field mismatches, append `approval_replay_denied` or `approval_replay_error` with payload containing `approval_id`, `session_id`, `tool_name`, requested action/arguments, and `reason`.
   - Invalid replay must not append `approval_granted`, must not call `self.tool_execution_manager.execute()`, must not persist a role `tool` message, and must not write archival memory.
   - Before executing a valid approved request, scan durable traces for a previous persisted successful `tool_executed` kernel event with matching `approval_id`, `session_id`, `tool_name`, requested action/arguments, and `ok is True`.
   - If found, append `tool_replay_skipped` with payload containing `approval_id`, `session_id`, `tool_name`, requested action/arguments, and `reason == "approval already executed"`.
   - Do not execute the tool and do not write another message when replay is skipped.
   - For valid first replay, append `approval_granted` with the same `approval_id` and payload fields proving the persisted pending evidence matched the replay request.
   - Keep continuation `stop` for denied/error, skipped, and executed replay outcomes.

   Pass command:

   ```bash
   uv run pytest tests/test_agent_kernel.py::test_kernel_replays_persisted_approval_after_cold_boundary_executes_once_and_persists_tool_result_message tests/test_agent_kernel.py::test_kernel_rejects_unknown_or_mismatched_approval_replay_without_side_effects -q
   ```

3. Update `src/memoryos_lite/agent_kernel.py` successful tool result message persistence

   Implementation requirements:

   - After successful `tool_result.ok`, create a `Message` with:
     - `session_id=tool_request.session_id`
     - `role=Role.TOOL`
     - content containing `archive_write`, `ok`, and the `memory_id`
     - metadata containing `producer="agent_kernel"`, `tool_name`, `approval_id`, and `tool_result`
   - Persist it through `store.add_message`.
   - Return it in `AgentStepResult.messages` as `message_to_log_entry(message)`.
   - Include `approval_id` on the `tool_executed` trace event.

   Pass command:

   ```bash
   uv run pytest tests/test_agent_kernel.py::test_kernel_replays_persisted_approval_after_cold_boundary_executes_once_and_persists_tool_result_message tests/test_agent_kernel.py::test_kernel_tool_result_message_is_visible_to_later_v3_context -q
   ```

4. Update `src/memoryos_lite/evals.py` kernel trace export

   Implementation requirements:

   - Change `BaselineOutput.kernel_trace_events` to `list[dict[str, object]]`.
   - Replace event-name extraction with full event payloads:

     ```python
     kernel_trace_events = [event.model_dump(mode="json") for event in step.trace]
     ```

   - Extend resumed events with the same full payload shape.
   - Keep the kernel probe gated by `service.agent_kernel is not None`, v3 context, and `settings.resolved_memory_arch == "v3"`.

5. Update `src/memoryos_lite/public_benchmarks.py` and `src/memoryos_lite/public_case_diagnostics.py`

   Implementation requirements:

   - Change `PublicBenchmarkResult.kernel_trace_events` to `list[dict[str, object]]`.
   - Pass the full trace list through `to_report()` unchanged.
   - Update diagnostics type hints so `kernel_trace_present` remains `bool(kernel_trace_events)`.
   - Do not use kernel trace presence to change `failure_class`, `movement_status`, `answer_support_status`, or `judge_status`.

   Pass command:

   ```bash
   uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_present_when_opted_in -q
   ```

6. Run focused GREEN set

   ```bash
   uv run pytest tests/test_agent_kernel.py -q
   uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_present_when_opted_in -q
   ```

   Expected result: all focused tests pass.

## REFACTOR

1. Keep refactor scope inside `src/memoryos_lite/agent_kernel.py`

   Allowed cleanup:

   - Extract `_tool_denied_trace_payload(decision, request)`.
   - Extract `_persisted_pending_approval(session_id, approval_id)`.
   - Extract `_approval_request_matches_pending(request, pending_payload)`.
   - Extract `_approval_replay_denied_trace_payload(request, approval_id, reason)`.
   - Extract `_approval_already_executed(session_id, approval_id, tool_name, requested_action)`.
   - Extract `_persist_tool_result_message(request, result, approval_id)`.

   Not allowed:

   - New tool families.
   - New Letta dependencies.
   - Default setting changes.
   - Answer prompt or citation changes.

2. Run refactor verification

   ```bash
   uv run pytest tests/test_agent_kernel.py -q
   uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_present_when_opted_in -q
   uv run ruff check .
   ```

   Expected result: all pass.

## Smoke

1. Full local baseline

   ```bash
   uv run pytest -q
   uv run ruff check .
   ```

   Expected result: pytest passes and ruff reports `All checks passed!`.

2. Opt-in LongMemEval kernel smoke, no LLM answer/judge

   ```bash
   MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
     --benchmark longmemeval \
     --data-path benchmarks/longmemeval/longmemeval.json \
     --baseline memoryos_lite \
     --limit 5 \
     --no-llm-answer \
     --no-llm-judge
   ```

   Expected result: run completes; report rows have non-empty payload-bearing `kernel_trace_events`.

3. Opt-in LoCoMo kernel smoke, no LLM answer/judge

   ```bash
   MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
     --benchmark locomo \
     --data-path benchmarks/locomo/locomo10.json \
     --baseline memoryos_lite \
     --limit 5 \
     --no-llm-answer \
     --no-llm-judge
   ```

   Expected result: run completes; report rows have non-empty payload-bearing `kernel_trace_events`.

4. Conditional full-chain judge

   Run 30-case LongMemEval and LoCoMo full-chain LLM judge only if implementation changes answer/context behavior beyond adding tool-result visibility. If run, use explicit `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1`, report LongMemEval and LoCoMo separately, and include case-level pass/fail, retrieval misses, evidence-hit-answer-fail, and kernel trace presence.

## Review

1. Confirm exact guardrails from `work/phase-7/context_bundle.md`

   - Kernel remains opt-in.
   - v3 default remains kernel-off.
   - v1 fallback remains unchanged.
   - Denied tools do not execute or write memory.
   - Initial `approval_pending` is persisted before resume.
   - Approval resume is replayable after runner/gate/store recreation and is idempotent.
   - Approval resume validates persisted pending evidence for session id, approval id, tool name, and requested action.
   - Unknown or mismatched approval ids are denied or error-traced without tool execution, tool message persistence, or memory writes.
   - Tool result trace and tool result message are durable.
   - Public benchmark trace is present only with explicit opt-in.
   - LoCoMo failures are reported separately and not hidden.

2. Review commands

   ```bash
   git diff -- src/memoryos_lite/agent_kernel.py src/memoryos_lite/evals.py src/memoryos_lite/public_benchmarks.py src/memoryos_lite/public_case_diagnostics.py tests/test_agent_kernel.py tests/test_public_benchmarks.py
   uv run pytest tests/test_agent_kernel.py -q
   uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_present_when_opted_in -q
   uv run pytest -q
   uv run ruff check .
   ```

3. ACK evidence required

   - Focused test output.
   - Full pytest and ruff output.
   - LongMemEval limit-5 opt-in kernel smoke path and result summary.
   - LoCoMo limit-5 opt-in kernel smoke path and result summary.
   - Explicit evidence that cold-boundary approval replay emits `approval_granted` and `tool_executed` with the same approval id, persists exactly one archival memory and one role `tool` message, and skips the second replay.
   - Explicit evidence that unknown and mismatched approval ids emit denial/error traces and leave tool execution, messages, and memory unchanged.
   - Explicit note that `kernel_trace_events` is control-plane evidence, not answer-quality evidence.
