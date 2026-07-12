import json

import pytest
from sqlalchemy import text

from memoryos_lite.agent_kernel import (
    ApprovalGateV1,
    SimpleAgentStepRunner,
    SimpleToolExecutionManager,
    SimpleToolPolicyEngine,
)
from memoryos_lite.agent_tool_selection import ToolSelectionBoundary
from memoryos_lite.config import Settings
from memoryos_lite.context_composer import V3ContextComposer
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import Role, new_id
from memoryos_lite.store import create_store
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    ArchivalMemory,
    ContextComposerRequest,
    ContextPackageV3,
    SourceRef,
    SourceType,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicyRule,
    ToolSelectionChoice,
)


def _request(session_id: str = "ses_1") -> AgentStepRequest:
    return AgentStepRequest(
        session_id=session_id,
        input_messages=[],
        context=ContextPackageV3(session_id=session_id, task="demo"),
    )


def _source_ref(session_id: str = "ses_1") -> SourceRef:
    return SourceRef(
        source_type=SourceType.MESSAGE,
        source_id="msg_1",
        session_id=session_id,
    )


def _archive_request(
    *,
    content: str = "approved archival fact",
    approval_id: str | None = None,
    session_id: str = "ses_1",
    tool_name: str = "archive_write",
    tool_call_id: str | None = None,
) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        session_id=session_id,
        tool_name=tool_name,
        arguments={"content": content, "memory_type": "fact"},
        source_refs=[_source_ref(session_id)],
        approval_id=approval_id,
        tool_call_id=tool_call_id,
    )


def _approval_runner(store, *, tool_selection_boundary=None):
    return SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="rule_1",
                    tool_name="archive_write",
                    effect="require_approval",
                    reason="approval required",
                )
            ]
        ),
        approval_gate=ApprovalGateV1(),
        tool_execution_manager=SimpleToolExecutionManager(store=store),
        tool_selection_boundary=tool_selection_boundary,
    )


def _archival_memory_count(store) -> int:
    with store.db() as db:
        return int(db.scalar(text("select count(*) from archival_memories")))


def _core_promotion_request(
    *,
    content: str = "Alice prefers concise status updates.",
    label: str = "human",
    source_refs: list[SourceRef] | None = None,
    approval_id: str | None = None,
    tool_call_id: str | None = None,
    session_id: str = "ses_1",
) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        session_id=session_id,
        tool_name="core_promotion_request",
        arguments={
            "content": content,
            "label": label,
            "reason": "source-backed preference candidate",
            "limit_tokens": 120,
        },
        source_refs=[_source_ref(session_id)] if source_refs is None else source_refs,
        approval_id=approval_id,
        tool_call_id=tool_call_id,
    )


def _core_promotion_runner(store):
    return SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="core_promotion_request_requires_approval",
                    tool_name="core_promotion_request",
                    effect="require_approval",
                    reason="core promotion requests require approval",
                )
            ]
        ),
        approval_gate=ApprovalGateV1(),
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )


def _core_candidate_apply_request(
    *,
    candidate_id: str,
    approval_id: str | None = None,
    tool_call_id: str | None = None,
    session_id: str = "ses_1",
    source_refs: list[SourceRef] | None = None,
) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        session_id=session_id,
        tool_name="core_candidate_apply",
        arguments={"candidate_id": candidate_id, "actor": "agent"},
        source_refs=[_source_ref(session_id)] if source_refs is None else source_refs,
        approval_id=approval_id,
        tool_call_id=tool_call_id,
    )


def _core_candidate_apply_runner(store):
    return SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="core_candidate_apply_requires_approval",
                    tool_name="core_candidate_apply",
                    effect="require_approval",
                    reason="core candidate apply requires approval",
                )
            ]
        ),
        approval_gate=ApprovalGateV1(),
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )


def _promotion_candidate_count(store) -> int:
    return len(store.list_promotion_candidates())


def _seed_archival_memory(
    store,
    *,
    archive_id: str,
    content: str,
    session_id: str = "ses_1",
) -> str:
    memory = store.add_archival_memory(
        ArchivalMemory(
            id=new_id("amem"),
            archive_id=archive_id,
            memory_type="fact",
            content=content,
            source_refs=[_source_ref(session_id)],
            metadata={"test": "phase16_archive_attach"},
        ),
        actor="agent",
        reason="test seed archival memory",
    )
    return memory.id


def _trace_payloads(store, session_id: str, event_type: str) -> list[dict]:
    return [
        trace.payload for trace in store.list_traces(session_id) if trace.event_type == event_type
    ]


def _pending_tool_call_id(trace) -> str:
    pending = next(event for event in trace if event.event_type == "approval_pending")
    tool_call_id = pending.payload["metadata"]["tool_call_id"]
    assert tool_call_id.startswith("toolcall_")
    return tool_call_id


def _candidate_ids(candidate_payload: dict) -> set[str]:
    candidates = candidate_payload["candidates"]
    return {candidate["tool_call_id"] for candidate in candidates}


class _NonCandidateSelector:
    def select(self, request, candidates):
        return ToolSelectionChoice(
            tool_call_id="toolcall_not_declared",
            selection_origin="llm",
            reason="attempted invented tool selection",
        )


class _TimeoutSelector:
    def select(self, request, candidates):
        raise TimeoutError("selector timeout")


class _UnavailableSelector:
    def select(self, request, candidates):
        raise RuntimeError("selector provider unavailable")


class _MalformedSelector:
    def select(self, request, candidates):
        return "toolcall_not_a_choice_object"


class _MissingProvenanceSelector:
    def select(self, request, candidates):
        return {"tool_call_id": candidates[0].tool_call_id, "selection_origin": "llm"}


class _NoopSelector:
    def select(self, request, candidates):
        return ToolSelectionChoice(
            tool_call_id=None,
            selection_origin="llm",
            reason="selector declined all candidates",
        )


def test_kernel_tool_registry_exposes_only_governed_memory_maintenance_tools():
    from memoryos_lite.agent_tool_registry import (
        executable_kernel_tool_names,
        get_kernel_tool_spec,
    )

    assert executable_kernel_tool_names() == {
        "archive_write",
        "archive_attach",
        "core_promotion_request",
        "core_candidate_apply",
    }
    assert get_kernel_tool_spec("archive_attach").mutating is True
    assert get_kernel_tool_spec("core_promotion_request").verification_required is True
    assert get_kernel_tool_spec("core_memory_append") is None


def test_tool_selection_boundary_reports_unsupported_input_without_runner():
    boundary = ToolSelectionBoundary()

    resolution = boundary.resolve(
        _request(),
        [
            ToolExecutionRequest(
                session_id="ses_1",
                tool_name="unknown_tool",
                arguments={"content": "ignored"},
            )
        ],
    )

    assert resolution.candidates == []
    assert resolution.selected_request is None
    assert resolution.denied is True
    assert resolution.rejected_inputs == [
        {
            "tool_name": "unknown_tool",
            "reason": "unsupported tool for K2 selection",
        }
    ]
    assert resolution.selection_payload["selection_origin"] == "fallback"
    assert "unsupported" in resolution.selection_payload["reason"]


def test_tool_selection_boundary_generates_archive_attach_candidate_without_broad_scope():
    boundary = ToolSelectionBoundary()
    request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_attach",
        arguments={"archive_id": "archive_existing", "scope_type": "session"},
        source_refs=[_source_ref()],
        tool_call_id="toolcall_attach",
    )

    resolution = boundary.resolve(_request(), [request])

    assert resolution.denied is False
    assert resolution.selected_request is not None
    candidate = resolution.candidates[0]
    assert candidate.tool_name == "archive_attach"
    assert candidate.arguments["scope_id"] == "ses_1"
    assert candidate.constraints["requires_session_scope"] is True
    assert candidate.constraints["requires_source_refs_or_approval"] is True


def test_tool_selection_boundary_rejects_archive_attach_non_session_scope():
    boundary = ToolSelectionBoundary()
    request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_attach",
        arguments={
            "archive_id": "archive_existing",
            "scope_type": "agent",
            "scope_id": "agent_1",
        },
        source_refs=[_source_ref()],
    )

    resolution = boundary.resolve(_request(), [request])

    assert resolution.selected_request is None
    assert resolution.denied is True
    assert "session scope" in resolution.selection_payload["reason"]


def test_tool_selection_boundary_generates_core_promotion_request_candidate():
    boundary = ToolSelectionBoundary()
    request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="core_promotion_request",
        arguments={
            "content": "Alice prefers concise status updates.",
            "reason": "source-backed preference candidate",
            "label": "human",
        },
        source_refs=[_source_ref()],
        tool_call_id="toolcall_promote",
    )

    resolution = boundary.resolve(_request(), [request])

    assert resolution.denied is False
    assert resolution.selected_request is not None
    assert resolution.selected_request.tool_name == "core_promotion_request"
    assert resolution.candidates[0].constraints["applies_core_memory"] is False


def test_tool_selection_boundary_preserves_approval_bound_candidate_without_source_refs():
    boundary = ToolSelectionBoundary()
    tool_request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_write",
        arguments={"content": "approved by replay", "memory_type": "fact"},
        approval_id="approval_1",
        tool_call_id="toolcall_1",
    )

    resolution = boundary.resolve(_request(), [tool_request])

    assert resolution.denied is False
    assert resolution.selected_request is not None
    assert resolution.selected_request.approval_id == "approval_1"
    assert resolution.selected_request.tool_call_id == "toolcall_1"
    assert resolution.selected_request.source_refs == []
    assert resolution.selection_payload["tool_call_id"] == "toolcall_1"
    assert resolution.candidates[0].constraints["requires_source_refs_or_approval"] is True


@pytest.mark.parametrize(
    ("selector", "reason_fragment"),
    [
        (_NonCandidateSelector(), "candidate"),
        (_TimeoutSelector(), "timeout"),
        (_MalformedSelector(), "malformed"),
        (_MissingProvenanceSelector(), "provenance"),
        (_NoopSelector(), "declined"),
    ],
)
def test_tool_selection_boundary_fail_closed_selector_outputs_without_runner(
    selector,
    reason_fragment,
):
    boundary = ToolSelectionBoundary(selector=selector)

    resolution = boundary.resolve(_request(), [_archive_request()])

    assert resolution.selected_request is None
    assert resolution.denied is True
    assert resolution.selection_payload["tool_call_id"] in {
        None,
        "toolcall_not_declared",
    }
    assert reason_fragment in resolution.selection_payload["reason"]


def test_tool_selection_boundary_denies_duplicate_candidate_ids_without_runner():
    boundary = ToolSelectionBoundary()

    resolution = boundary.resolve(
        _request(),
        [
            _archive_request(tool_call_id="toolcall_duplicate"),
            _archive_request(content="second fact", tool_call_id="toolcall_duplicate"),
        ],
    )

    assert resolution.selected_request is None
    assert resolution.denied is True
    assert resolution.selection_payload["tool_call_id"] == "toolcall_duplicate"
    assert "duplicate" in resolution.selection_payload["reason"]


def test_kernel_generates_candidate_trace_before_selection(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()

    result = _approval_runner(store).run_step(
        _request(),
        tool_requests=[_archive_request()],
    )

    event_types = [event.event_type for event in result.trace]
    assert event_types[:4] == [
        "kernel_step_started",
        "tool_candidates_generated",
        "tool_selected",
        "tool_policy_decision",
    ]
    generated = next(
        event for event in result.trace if event.event_type == "tool_candidates_generated"
    )
    candidates = generated.payload["candidates"]
    assert [candidate["tool_name"] for candidate in candidates] == ["archive_write"]
    candidate = candidates[0]
    assert candidate["tool_call_id"].startswith("toolcall_")
    assert candidate["candidate_reason"]
    assert candidate["constraints"]
    selected = next(event for event in result.trace if event.event_type == "tool_selected")
    assert selected.payload["selection_origin"] == "deterministic"
    assert selected.payload["candidate_reason"]
    assert selected.payload["tool_call_id"] in _candidate_ids(generated.payload)
    durable_generated = _trace_payloads(store, "ses_1", "tool_candidates_generated")
    durable_selected = _trace_payloads(store, "ses_1", "tool_selected")
    assert len(durable_generated) == 1
    assert len(durable_selected) == 1
    assert durable_generated[0]["payload"]["candidates"] == candidates
    assert durable_selected[0]["payload"]["tool_call_id"] == selected.payload["tool_call_id"]
    assert durable_selected[0]["payload"]["selection_origin"] == "deterministic"
    assert (
        durable_selected[0]["payload"]["candidate_reason"] == selected.payload["candidate_reason"]
    )


def test_kernel_denies_selector_non_candidate_without_policy_or_execution(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    runner = _approval_runner(
        store,
        tool_selection_boundary=ToolSelectionBoundary(selector=_NonCandidateSelector()),
    )

    result = runner.run_step(_request(), tool_requests=[_archive_request()])

    event_types = [event.event_type for event in result.trace]
    assert "tool_candidates_generated" in event_types
    assert "tool_selection_denied" in event_types
    generated = next(
        event for event in result.trace if event.event_type == "tool_candidates_generated"
    )
    denial = next(event for event in result.trace if event.event_type == "tool_selection_denied")
    assert "toolcall_not_declared" not in _candidate_ids(generated.payload)
    assert denial.payload["tool_call_id"] == "toolcall_not_declared"
    assert "candidate" in denial.payload["reason"]
    assert "tool_policy_decision" not in event_types
    assert "tool_denied" not in event_types
    assert "tool_executed" not in event_types
    durable_generated = _trace_payloads(store, "ses_1", "tool_candidates_generated")
    durable_denied = _trace_payloads(store, "ses_1", "tool_selection_denied")
    assert len(durable_generated) == 1
    assert durable_generated[0]["payload"]["candidates"] == generated.payload["candidates"]
    assert len(durable_denied) == 1
    assert durable_denied[0]["payload"]["tool_call_id"] == "toolcall_not_declared"
    assert "candidate" in durable_denied[0]["payload"]["reason"]
    assert _archival_memory_count(store) == 0


def test_kernel_selector_timeout_falls_back_to_noop_without_mutation(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    runner = _approval_runner(
        store,
        tool_selection_boundary=ToolSelectionBoundary(selector=_TimeoutSelector()),
    )

    result = runner.run_step(_request(), tool_requests=[_archive_request()])

    denial = next(event for event in result.trace if event.event_type == "tool_selection_denied")
    assert denial.payload["selection_origin"] == "fallback"
    assert "timeout" in denial.payload["reason"]
    assert "tool_policy_decision" not in [event.event_type for event in result.trace]
    assert "tool_denied" not in [event.event_type for event in result.trace]
    assert _archival_memory_count(store) == 0


def test_kernel_selector_unavailable_fails_closed_without_policy_or_mutation(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    runner = _approval_runner(
        store,
        tool_selection_boundary=ToolSelectionBoundary(selector=_UnavailableSelector()),
    )

    result = runner.run_step(_request(), tool_requests=[_archive_request()])

    event_types = [event.event_type for event in result.trace]
    assert "tool_candidates_generated" in event_types
    assert "tool_selection_denied" in event_types
    denial = next(event for event in result.trace if event.event_type == "tool_selection_denied")
    assert denial.payload["selection_origin"] == "fallback"
    assert "unavailable" in denial.payload["reason"]
    assert "tool_policy_decision" not in event_types
    assert "approval_pending" not in event_types
    assert "tool_executed" not in event_types
    durable_denied = _trace_payloads(store, "ses_1", "tool_selection_denied")
    assert len(durable_denied) == 1
    assert "unavailable" in durable_denied[0]["payload"]["reason"]
    assert _archival_memory_count(store) == 0
    assert [msg for msg in store.list_messages("ses_1") if msg.role == Role.TOOL] == []


def test_kernel_denies_malformed_selector_output_before_policy_or_mutation(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    runner = _approval_runner(
        store,
        tool_selection_boundary=ToolSelectionBoundary(selector=_MalformedSelector()),
    )

    result = runner.run_step(_request(), tool_requests=[_archive_request()])

    event_types = [event.event_type for event in result.trace]
    assert "tool_candidates_generated" in event_types
    assert "tool_selection_denied" in event_types
    denial = next(event for event in result.trace if event.event_type == "tool_selection_denied")
    assert "malformed" in denial.payload["reason"] or "invalid" in denial.payload["reason"]
    assert "tool_policy_decision" not in event_types
    assert "tool_denied" not in event_types
    assert "tool_executed" not in event_types
    assert _trace_payloads(store, "ses_1", "tool_selection_denied")
    assert _archival_memory_count(store) == 0
    assert [msg for msg in store.list_messages("ses_1") if msg.role == Role.TOOL] == []


def test_kernel_denies_selector_choice_missing_provenance_before_policy_or_mutation(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    runner = _approval_runner(
        store,
        tool_selection_boundary=ToolSelectionBoundary(selector=_MissingProvenanceSelector()),
    )

    result = runner.run_step(_request(), tool_requests=[_archive_request()])

    event_types = [event.event_type for event in result.trace]
    assert "tool_candidates_generated" in event_types
    assert "tool_selection_denied" in event_types
    denial = next(event for event in result.trace if event.event_type == "tool_selection_denied")
    assert "provenance" in denial.payload["reason"]
    assert "tool_policy_decision" not in event_types
    assert "tool_denied" not in event_types
    assert "tool_executed" not in event_types
    assert _trace_payloads(store, "ses_1", "tool_selection_denied")
    assert _archival_memory_count(store) == 0
    assert [msg for msg in store.list_messages("ses_1") if msg.role == Role.TOOL] == []


def test_kernel_selected_request_carries_selection_origin_and_candidate_reason(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    pending = next(event for event in first.trace if event.event_type == "approval_pending")
    tool_call_id = _pending_tool_call_id(first.trace)

    resumed = _approval_runner(create_store(settings)).run_step(
        _request(),
        tool_requests=[
            _archive_request(
                approval_id=pending.approval_id,
                tool_call_id=tool_call_id,
            )
        ],
    )

    selected = next(event for event in resumed.trace if event.event_type == "tool_selected")
    assert selected.payload["tool_call_id"] == tool_call_id
    assert selected.payload["selection_origin"] == "deterministic"
    assert selected.payload["candidate_reason"]
    assert selected.payload["tool_call_id"] in _candidate_ids(
        next(
            event.payload
            for event in resumed.trace
            if event.event_type == "tool_candidates_generated"
        )
    )
    assert "approval_granted" in [event.event_type for event in resumed.trace]


def test_kernel_rejects_approval_replay_with_tampered_tool_call_id(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    pending = next(event for event in first.trace if event.event_type == "approval_pending")
    approval_id = pending.approval_id
    assert approval_id is not None
    assert _pending_tool_call_id(first.trace).startswith("toolcall_")

    reopened = create_store(settings)
    result = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[
            _archive_request(
                approval_id=approval_id,
                tool_call_id="toolcall_tampered",
            )
        ],
    )

    event_types = [event.event_type for event in result.trace]
    assert "approval_replay_denied" in event_types
    denial = next(event for event in result.trace if event.event_type == "approval_replay_denied")
    assert denial.payload["approval_id"] == approval_id
    assert "tool_call" in denial.payload["reason"]
    assert "approval_granted" not in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    assert _archival_memory_count(reopened) == 0
    assert [msg for msg in reopened.list_messages("ses_1") if msg.role == Role.TOOL] == []


def test_kernel_rejects_approval_replay_missing_tool_call_id(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    pending = next(event for event in first.trace if event.event_type == "approval_pending")
    approval_id = pending.approval_id
    assert approval_id is not None
    assert _pending_tool_call_id(first.trace).startswith("toolcall_")

    reopened = create_store(settings)
    result = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id)],
    )

    event_types = [event.event_type for event in result.trace]
    assert "approval_replay_denied" in event_types
    denial = next(event for event in result.trace if event.event_type == "approval_replay_denied")
    assert denial.payload["approval_id"] == approval_id
    assert "tool_call" in denial.payload["reason"]
    assert "approval_granted" not in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    assert _archival_memory_count(reopened) == 0
    assert [msg for msg in reopened.list_messages("ses_1") if msg.role == Role.TOOL] == []


def test_kernel_persists_trace_and_stops_without_tool_requests(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(store=store)
    request = AgentStepRequest(
        session_id="ses_1",
        input_messages=[],
        context=ContextPackageV3(session_id="ses_1", task="demo"),
    )

    result = runner.run_step(request)

    assert result.continuation == "stop"
    assert [event.event_type for event in store.list_traces("ses_1")] == [
        "kernel_step_started",
        "kernel_step_completed",
    ]
    assert result.trace[0].event_type == "kernel_step_started"


def test_kernel_denies_archive_write_without_execution_or_memory_write(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="deny_archive_write",
                    tool_name="archive_write",
                    effect="deny",
                    reason="not allowed in this test",
                )
            ]
        ),
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )

    result = runner.run_step(
        _request(),
        tool_requests=[_archive_request(content="must not be written")],
    )

    event_types = [event.event_type for event in result.trace]
    assert result.continuation == "stop"
    assert "tool_policy_decision" in event_types
    assert "tool_denied" in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    denied = next(event for event in result.trace if event.event_type == "tool_denied")
    assert denied.payload["tool_name"] == "archive_write"
    assert denied.payload["ok"] is False
    assert denied.payload["error"] == "not allowed in this test"
    assert store.list_messages("ses_1") == []
    assert _archival_memory_count(store) == 0


def test_kernel_denies_unknown_tool_as_result_without_executor_call(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(
        store=store,
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )

    result = runner.run_step(
        _request(),
        tool_requests=[
            ToolExecutionRequest(
                session_id="ses_1",
                tool_name="unknown_tool",
                arguments={"content": "ignored"},
            )
        ],
    )

    event_types = [event.event_type for event in result.trace]
    assert "tool_candidates_generated" in event_types
    assert "tool_selection_denied" in event_types
    assert "tool_policy_decision" not in event_types
    assert "tool_denied" not in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    denied = next(event for event in result.trace if event.event_type == "tool_selection_denied")
    assert "unsupported tool for K2 selection" in denied.payload["reason"]
    assert store.list_messages("ses_1") == []
    assert _archival_memory_count(store) == 0


@pytest.mark.parametrize(
    "tool_name",
    [
        "core_memory_append",
        "core_memory_replace",
        "archive_detach",
        "archive_delete",
        "archive_deprecate",
        "recall_search",
        "archive_search",
        "unknown_tool",
    ],
)
def test_kernel_denies_unopened_phase16_tools_before_policy_or_execution(
    tmp_path,
    tool_name,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(
        store=store,
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )

    result = runner.run_step(
        _request(),
        tool_requests=[
            ToolExecutionRequest(
                session_id="ses_1",
                tool_name=tool_name,
                arguments={"content": "must not be written"},
                source_refs=[_source_ref()],
            )
        ],
    )

    event_types = [event.event_type for event in result.trace]
    assert "tool_selection_denied" in event_types
    assert "tool_policy_decision" not in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    assert _archival_memory_count(store) == 0
    assert store.list_messages("ses_1") == []


def test_kernel_denies_unsupported_memory_tools_without_verification_or_write(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(
        store=store,
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )

    for tool_name in ["core_memory_append", "core_memory_replace"]:
        result = runner.run_step(
            _request(),
            tool_requests=[
                ToolExecutionRequest(
                    session_id="ses_1",
                    tool_name=tool_name,
                    arguments={"label": "human", "content": "must not be written"},
                    source_refs=[_source_ref()],
                )
            ],
        )

        event_types = [event.event_type for event in result.trace]
        assert "tool_selection_denied" in event_types
        assert "tool_policy_decision" not in event_types
        assert "tool_denied" not in event_types
        assert "tool_executed" not in event_types
        assert "tool_verified" not in event_types
        assert store.list_messages("ses_1") == []
        assert _archival_memory_count(store) == 0


def test_kernel_pauses_when_tool_requires_approval(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="rule_1",
                    tool_name="archive_write",
                    effect="require_approval",
                    reason="approval required",
                )
            ]
        ),
        approval_gate=ApprovalGateV1(),
    )
    request = AgentStepRequest(
        session_id="ses_1",
        input_messages=[],
        context=ContextPackageV3(session_id="ses_1", task="demo"),
    )
    tool_request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_write",
        arguments={"content": "note"},
    )

    result = runner.run_step(request, tool_requests=[tool_request])

    assert result.continuation == "pause"
    assert any(event.event_type == "approval_pending" for event in result.trace)
    assert [trace.event_type for trace in store.list_traces("ses_1")] == [
        "kernel_step_started",
        "tool_candidates_generated",
        "tool_selected",
        "tool_policy_decision",
        "approval_pending",
        "kernel_step_completed",
    ]


def test_kernel_replays_persisted_approval_after_cold_boundary_once(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None
    tool_call_id = _pending_tool_call_id(first.trace)

    reopened = create_store(settings)
    pending_payloads = _trace_payloads(reopened, "ses_1", "approval_pending")
    assert len(pending_payloads) == 1
    pending = pending_payloads[0]
    assert pending["approval_id"] == approval_id
    assert pending["payload"]["status"] == "pending"
    assert pending["payload"]["session_id"] == "ses_1"
    assert pending["payload"]["tool_name"] == "archive_write"
    assert pending["payload"]["requested_action"]["content"] == "approved archival fact"
    assert pending["payload"]["source_refs"][0]["source_id"] == "msg_1"
    assert pending["payload"]["metadata"]["policy_reason"] == "approval required"
    assert pending["payload"]["metadata"]["tool_call_id"] == tool_call_id
    assert _archival_memory_count(reopened) == 0
    assert reopened.list_messages("ses_1") == []

    resumed = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id, tool_call_id=tool_call_id)],
    )

    assert resumed.continuation == "stop"
    assert [event.event_type for event in resumed.trace] == [
        "kernel_step_started",
        "tool_candidates_generated",
        "tool_selected",
        "tool_policy_decision",
        "approval_granted",
        "tool_executed",
        "tool_verified",
        "kernel_step_completed",
    ]
    granted = next(event for event in resumed.trace if event.event_type == "approval_granted")
    assert granted.approval_id == approval_id
    assert granted.payload["approval_id"] == approval_id
    assert granted.payload["session_id"] == "ses_1"
    assert granted.payload["tool_name"] == "archive_write"
    assert granted.payload["approved_action"]["content"] == "approved archival fact"
    executed = next(event for event in resumed.trace if event.event_type == "tool_executed")
    assert executed.approval_id == approval_id
    assert executed.payload["approval_id"] == approval_id
    assert executed.payload["ok"] is True
    memory_id = executed.payload["result"]["memory_id"]
    verified = next(event for event in resumed.trace if event.event_type == "tool_verified")
    assert verified.approval_id == approval_id
    assert verified.payload["tool_name"] == "archive_write"
    assert verified.payload["ok"] is True
    assert verified.payload["verification"]["status"] == "verified"
    assert verified.payload["verification"]["session_attachment_found"] is True
    assert verified.payload["verification"]["eligible_for_session"] is True
    assert len(resumed.messages) == 1
    assert resumed.messages[0].role == Role.TOOL
    assert resumed.messages[0].metadata["tool_name"] == "archive_write"
    assert resumed.messages[0].metadata["approval_id"] == approval_id
    tool_messages = [msg for msg in reopened.list_messages("ses_1") if msg.role == Role.TOOL]
    assert len(tool_messages) == 1
    assert _archival_memory_count(reopened) == 1
    history = reopened.list_archival_memory_history(memory_id)
    assert history[0].after["content"] == "approved archival fact"
    assert history[0].source_refs[0].approval_id == approval_id

    second_store = create_store(settings)
    replayed = _approval_runner(second_store).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id, tool_call_id=tool_call_id)],
    )
    event_types = [event.event_type for event in replayed.trace]
    assert "tool_replay_skipped" in event_types
    skipped = next(event for event in replayed.trace if event.event_type == "tool_replay_skipped")
    assert skipped.payload["approval_id"] == approval_id
    assert skipped.payload["reason"] == "approval already executed"
    assert len([event for event in replayed.trace if event.event_type == "tool_executed"]) == 0
    assert len([event for event in replayed.trace if event.event_type == "tool_verified"]) == 0
    assert _archival_memory_count(second_store) == 1
    assert len([msg for msg in second_store.list_messages("ses_1") if msg.role == Role.TOOL]) == 1


def test_kernel_rejects_unknown_or_mismatched_approval_replay_without_side_effects(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None
    tool_call_id = _pending_tool_call_id(first.trace)

    invalid_requests = [
        _archive_request(approval_id="approval_missing", tool_call_id=tool_call_id),
        _archive_request(
            approval_id=approval_id,
            session_id="ses_2",
            tool_call_id=tool_call_id,
        ),
        _archive_request(
            approval_id=approval_id,
            tool_name="unknown_tool",
            tool_call_id=tool_call_id,
        ),
        _archive_request(
            approval_id=approval_id,
            content="tampered archival fact",
            tool_call_id=tool_call_id,
        ),
    ]

    for tool_request in invalid_requests:
        reopened = create_store(settings)
        result = _approval_runner(reopened).run_step(
            _request().model_copy(update={"session_id": tool_request.session_id}),
            tool_requests=[tool_request],
        )
        event_types = [event.event_type for event in result.trace]
        if tool_request.tool_name != "archive_write":
            assert "tool_selection_denied" in event_types
            assert "approval_replay_denied" not in event_types
            assert "tool_policy_decision" not in event_types
            denial = next(
                event for event in result.trace if event.event_type == "tool_selection_denied"
            )
            assert "unsupported tool for K2 selection" in denial.payload["reason"]
        else:
            assert "approval_replay_denied" in event_types or "approval_replay_error" in event_types
            denial = next(
                event
                for event in result.trace
                if event.event_type in {"approval_replay_denied", "approval_replay_error"}
            )
            assert denial.payload["approval_id"] == tool_request.approval_id
        assert denial.payload["reason"]
        assert "approval_granted" not in event_types
        assert "tool_executed" not in event_types
        assert "tool_verified" not in event_types
        assert _archival_memory_count(reopened) == 0
        assert [msg for msg in reopened.list_messages("ses_1") if msg.role == Role.TOOL] == []
        assert [msg for msg in reopened.list_messages("ses_2") if msg.role == Role.TOOL] == []


def test_kernel_rejects_replay_without_original_request_binding(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None
    tool_call_id = _pending_tool_call_id(first.trace)

    with store.db() as db:
        row = db.execute(
            text(
                """
                select id, payload_json from trace_events
                where event_type = 'approval_pending'
                """
            )
        ).one()
        trace_id, payload_json = row
        payload = json.loads(payload_json)
        payload["payload"]["metadata"]["request_fingerprint"] = "original-fingerprint"
        payload["payload"]["metadata"]["tool_call_id"] = tool_call_id
        db.execute(
            text(
                """
                update trace_events
                set payload_json = :payload_json
                where id = :trace_id
                """
            ),
            {"payload_json": json.dumps(payload), "trace_id": trace_id},
        )

    reopened = create_store(settings)
    result = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id, tool_call_id=tool_call_id)],
    )

    event_types = [event.event_type for event in result.trace]
    assert "approval_replay_denied" in event_types
    denial = next(event for event in result.trace if event.event_type == "approval_replay_denied")
    assert denial.payload["approval_id"] == approval_id
    assert "fingerprint" in denial.payload["reason"]
    assert "approval_granted" not in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    assert _archival_memory_count(reopened) == 0
    assert [msg for msg in reopened.list_messages("ses_1") if msg.role == Role.TOOL] == []


class _UnverifiableArchiveWriteExecutionManager(SimpleToolExecutionManager):
    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        if request.tool_name == "archive_write":
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=True,
                result={"memory_id": "amem_missing", "archive_id": request.session_id},
                source_refs=list(request.source_refs),
            )
        return super().execute(request)


def test_kernel_emits_negative_verification_when_execution_is_not_store_visible(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="allow_archive_write",
                    tool_name="archive_write",
                    effect="allow",
                    reason="allowed for verification failure test",
                )
            ]
        ),
        tool_execution_manager=_UnverifiableArchiveWriteExecutionManager(store=store),
    )

    result = runner.run_step(
        _request(),
        tool_requests=[_archive_request(content="execution-only fact")],
    )

    event_types = [event.event_type for event in result.trace]
    assert "tool_executed" in event_types
    assert "tool_verified" in event_types
    verified = next(event for event in result.trace if event.event_type == "tool_verified")
    assert verified.payload["tool_name"] == "archive_write"
    assert verified.payload["ok"] is False
    assert verified.payload["verification"]["status"] == "failed"
    assert verified.payload["verification"]["history_found"] is False
    assert verified.payload["verification"]["passage_found"] is False
    assert verified.payload["verification"]["session_attachment_found"] is False
    assert verified.payload["verification"]["eligible_for_session"] is False
    assert not any(
        event.event_type == "tool_verified" and event.payload.get("ok") is True
        for event in result.trace
    )
    assert _archival_memory_count(store) == 0
    assert [msg for msg in store.list_messages("ses_1") if msg.role == Role.TOOL] == []


def test_kernel_archive_attach_is_approval_bound_verified_and_visible_to_v3(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    archive_id = "archive_phase16"
    memory_id = _seed_archival_memory(
        store,
        archive_id=archive_id,
        content="Alice wants the blue notebook remembered.",
    )
    before = V3ContextComposer(store=store, settings=settings).build(
        ContextComposerRequest(session_id="ses_1", task="blue notebook", budget=120)
    )
    assert [item for item in before.items if item.layer == "archival"] == []

    runner = SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="archive_attach_requires_approval",
                    tool_name="archive_attach",
                    effect="require_approval",
                    reason="archive attachments require approval",
                )
            ]
        ),
        approval_gate=ApprovalGateV1(),
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )
    tool_request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_attach",
        arguments={"archive_id": archive_id, "scope_type": "session"},
        source_refs=[_source_ref()],
    )

    first = runner.run_step(_request(), tool_requests=[tool_request])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    tool_call_id = _pending_tool_call_id(first.trace)
    resumed = runner.run_step(
        _request(),
        tool_requests=[
            tool_request.model_copy(
                update={"approval_id": approval_id, "tool_call_id": tool_call_id}
            )
        ],
    )

    event_types = [event.event_type for event in resumed.trace]
    assert "tool_executed" in event_types
    assert "tool_verified" in event_types
    verified = next(event for event in resumed.trace if event.event_type == "tool_verified")
    assert verified.payload["tool_name"] == "archive_attach"
    assert verified.payload["ok"] is True
    assert verified.payload["verification"]["status"] == "verified"
    assert verified.payload["verification"]["attachment_found"] is True
    assert f"apsg_{memory_id}" in verified.payload["verification"]["eligible_passage_ids"]
    attachments = store.list_archive_attachments(scope_type="session", scope_id="ses_1")
    assert [attachment.archive_id for attachment in attachments] == [archive_id]

    tool_messages = [msg for msg in store.list_messages("ses_1") if msg.role == Role.TOOL]
    assert [msg.content for msg in tool_messages] == ["tool archive_attach executed"]
    assert tool_messages[0].metadata["result"]["attachment_id"]
    after = V3ContextComposer(store=store, settings=settings).build(
        ContextComposerRequest(session_id="ses_1", task="blue notebook", budget=120)
    )
    archival_items = [item for item in after.items if item.layer == "archival"]
    assert [item.text for item in archival_items] == ["Alice wants the blue notebook remembered."]


def test_kernel_archive_attach_replay_tamper_denies_before_execution(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    _seed_archival_memory(store, archive_id="archive_phase16", content="attach me")
    runner = _approval_runner(store)
    runner.tool_policy_engine = SimpleToolPolicyEngine(
        rules=[
            ToolPolicyRule(
                id="archive_attach_requires_approval",
                tool_name="archive_attach",
                effect="require_approval",
                reason="archive attachments require approval",
            )
        ]
    )
    tool_request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_attach",
        arguments={"archive_id": "archive_phase16", "scope_type": "session"},
        source_refs=[_source_ref()],
    )
    first = runner.run_step(_request(), tool_requests=[tool_request])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    tool_call_id = _pending_tool_call_id(first.trace)

    tampered = tool_request.model_copy(
        update={
            "approval_id": approval_id,
            "tool_call_id": tool_call_id,
            "arguments": {"archive_id": "archive_other", "scope_type": "session"},
        }
    )
    result = runner.run_step(_request(), tool_requests=[tampered])

    event_types = [event.event_type for event in result.trace]
    assert "approval_replay_denied" in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    assert store.list_archive_attachments(scope_type="session", scope_id="ses_1") == []


def test_kernel_core_promotion_request_persists_pending_candidate_without_core_mutation(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = _core_promotion_runner(store)

    first = runner.run_step(_request(), tool_requests=[_core_promotion_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None
    tool_call_id = _pending_tool_call_id(first.trace)

    resumed = runner.run_step(
        _request(),
        tool_requests=[
            _core_promotion_request(
                approval_id=approval_id,
                tool_call_id=tool_call_id,
            )
        ],
    )

    event_types = [event.event_type for event in resumed.trace]
    assert "tool_executed" in event_types
    assert "tool_verified" in event_types
    executed = next(event for event in resumed.trace if event.event_type == "tool_executed")
    candidate_id = executed.payload["result"]["candidate_id"]
    verified = next(event for event in resumed.trace if event.event_type == "tool_verified")
    assert verified.payload["tool_name"] == "core_promotion_request"
    assert verified.payload["ok"] is True
    assert verified.payload["verification"]["status"] == "verified"
    assert verified.payload["verification"]["candidate_pending"] is True
    assert verified.payload["verification"]["core_block_count_before"] == 0
    assert verified.payload["verification"]["core_block_count_after"] == 0
    assert verified.payload["verification"]["core_history_count_before"] == 0
    assert verified.payload["verification"]["core_history_count_after"] == 0

    candidate = store.get_promotion_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status == "pending"
    assert candidate.target_layer == "core"
    assert candidate.operation == "promote"
    assert candidate.write_source == "explicit_instruction"
    assert candidate.content == "Alice prefers concise status updates."
    assert candidate.source_refs[0].approval_id == approval_id
    assert candidate.metadata["label"] == "human"
    assert candidate.metadata["limit_tokens"] == 120
    assert candidate.metadata["tool_name"] == "core_promotion_request"
    assert candidate.metadata["approval_id"] == approval_id
    assert candidate.metadata["tool_call_id"] == tool_call_id

    tool_messages = [msg for msg in store.list_messages("ses_1") if msg.role == Role.TOOL]
    assert [msg.content for msg in tool_messages] == ["tool core_promotion_request executed"]
    assert tool_messages[0].metadata["candidate_id"] == candidate_id
    assert store.list_core_memory_blocks() == []
    assert store.list_core_memory_history(candidate_id) == []

    package = V3ContextComposer(store=store, settings=settings).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="concise status updates",
            budget=120,
        )
    )
    assert [item for item in package.items if item.layer == "core"] == []


def test_kernel_core_promotion_request_replay_tamper_denies_before_execution_or_candidate(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = _core_promotion_runner(store)
    first = runner.run_step(_request(), tool_requests=[_core_promotion_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None
    tool_call_id = _pending_tool_call_id(first.trace)

    tampered_source_refs = [
        SourceRef(
            source_type=SourceType.MESSAGE,
            source_id="msg_tampered",
            session_id="ses_1",
        )
    ]
    tampered_requests = [
        _core_promotion_request(
            content="Alice prefers verbose reports.",
            approval_id=approval_id,
            tool_call_id=tool_call_id,
        ),
        _core_promotion_request(
            label="persona",
            approval_id=approval_id,
            tool_call_id=tool_call_id,
        ),
        _core_promotion_request(
            source_refs=tampered_source_refs,
            approval_id=approval_id,
            tool_call_id=tool_call_id,
        ),
        _core_promotion_request(
            approval_id=approval_id,
            tool_call_id="toolcall_tampered",
        ),
        _core_promotion_request(
            approval_id=approval_id,
            tool_call_id=tool_call_id,
        ).model_copy(
            update={
                "arguments": {
                    "content": "Alice prefers concise status updates.",
                    "label": "human",
                    "reason": "source-backed preference candidate",
                    "limit_tokens": 120,
                    "operation": "update",
                }
            }
        ),
    ]

    for tool_request in tampered_requests:
        reopened = create_store(settings)
        result = _core_promotion_runner(reopened).run_step(
            _request(),
            tool_requests=[tool_request],
        )
        event_types = [event.event_type for event in result.trace]
        assert "approval_replay_denied" in event_types
        assert "approval_granted" not in event_types
        assert "tool_executed" not in event_types
        assert "tool_verified" not in event_types
        assert _promotion_candidate_count(reopened) == 0
        assert reopened.list_core_memory_blocks() == []
        assert [msg for msg in reopened.list_messages("ses_1") if msg.role == Role.TOOL] == []


def test_kernel_core_candidate_apply_requires_approved_replay_and_applies_via_lifecycle(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    request_runner = _core_promotion_runner(store)

    first_request = request_runner.run_step(
        _request(),
        tool_requests=[_core_promotion_request(tool_call_id="toolcall_core_request")],
    )
    request_approval_id = next(
        event.approval_id for event in first_request.trace if event.event_type == "approval_pending"
    )
    requested = request_runner.run_step(
        _request(),
        tool_requests=[
            _core_promotion_request(
                approval_id=request_approval_id,
                tool_call_id="toolcall_core_request",
            )
        ],
    )
    candidate_id = next(
        event.payload["result"]["candidate_id"]
        for event in requested.trace
        if event.event_type == "tool_executed"
    )
    assert store.get_promotion_candidate(candidate_id).status == "pending"
    assert store.list_core_memory_blocks() == []

    apply_runner = _core_candidate_apply_runner(store)
    apply_request = _core_candidate_apply_request(
        candidate_id=candidate_id,
        tool_call_id="toolcall_core_apply",
    )
    pending = apply_runner.run_step(_request(), tool_requests=[apply_request])
    apply_approval_id = next(
        event.approval_id for event in pending.trace if event.event_type == "approval_pending"
    )
    assert store.get_promotion_candidate(candidate_id).status == "pending"
    assert store.list_core_memory_blocks() == []

    resumed = apply_runner.run_step(
        _request(),
        tool_requests=[
            _core_candidate_apply_request(
                candidate_id=candidate_id,
                approval_id=apply_approval_id,
                tool_call_id="toolcall_core_apply",
            )
        ],
    )

    event_types = [event.event_type for event in resumed.trace]
    assert "approval_granted" in event_types
    assert "tool_executed" in event_types
    assert "tool_verified" in event_types
    executed = next(event for event in resumed.trace if event.event_type == "tool_executed")
    verified = next(event for event in resumed.trace if event.event_type == "tool_verified")
    assert executed.payload["tool_name"] == "core_candidate_apply"
    assert executed.payload["result"]["candidate_id"] == candidate_id
    assert verified.payload["verification"]["status"] == "verified"
    assert verified.payload["verification"]["candidate_applied"] is True
    assert verified.payload["verification"]["core_mutated"] is True

    candidate = store.get_promotion_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status == "applied"
    assert candidate.metadata["applied_by"] == "agent"
    assert candidate.metadata["apply_approval_id"] == apply_approval_id
    blocks = store.list_core_memory_blocks()
    assert [block.value for block in blocks] == ["Alice prefers concise status updates."]
    assert blocks[0].metadata["promotion_candidate_id"] == candidate_id
    assert blocks[0].metadata["approval_id"] == apply_approval_id

    tool_messages = [msg for msg in store.list_messages("ses_1") if msg.role == Role.TOOL]
    assert [msg.content for msg in tool_messages] == [
        "tool core_promotion_request executed",
        "tool core_candidate_apply executed",
    ]


def test_kernel_core_candidate_apply_replay_is_idempotent_after_execution(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    request_runner = _core_promotion_runner(store)
    first_request = request_runner.run_step(
        _request(),
        tool_requests=[_core_promotion_request(tool_call_id="toolcall_core_request")],
    )
    request_approval_id = next(
        event.approval_id for event in first_request.trace if event.event_type == "approval_pending"
    )
    requested = request_runner.run_step(
        _request(),
        tool_requests=[
            _core_promotion_request(
                approval_id=request_approval_id,
                tool_call_id="toolcall_core_request",
            )
        ],
    )
    candidate_id = next(
        event.payload["result"]["candidate_id"]
        for event in requested.trace
        if event.event_type == "tool_executed"
    )
    apply_runner = _core_candidate_apply_runner(store)
    pending = apply_runner.run_step(
        _request(),
        tool_requests=[
            _core_candidate_apply_request(
                candidate_id=candidate_id,
                tool_call_id="toolcall_core_apply",
            )
        ],
    )
    apply_approval_id = next(
        event.approval_id for event in pending.trace if event.event_type == "approval_pending"
    )
    apply_request = _core_candidate_apply_request(
        candidate_id=candidate_id,
        approval_id=apply_approval_id,
        tool_call_id="toolcall_core_apply",
    )
    apply_runner.run_step(_request(), tool_requests=[apply_request])

    replay = _core_candidate_apply_runner(create_store(settings)).run_step(
        _request(),
        tool_requests=[apply_request],
    )

    event_types = [event.event_type for event in replay.trace]
    assert "tool_replay_skipped" in event_types
    assert "tool_executed" not in event_types
    assert store.get_promotion_candidate(candidate_id).status == "applied"
    blocks = store.list_core_memory_blocks()
    assert len(blocks) == 1
    assert [event.operation for event in store.list_core_memory_history(blocks[0].id)] == ["add"]


def test_memoryos_service_opt_in_kernel_requires_approval_for_all_phase16_mutating_tools(
    tmp_path,
):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_agent_kernel="v1",
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(settings=settings, store=store)
    assert service.agent_kernel is not None

    tool_requests = [
        _archive_request(tool_call_id="toolcall_archive_write"),
        ToolExecutionRequest(
            session_id="ses_1",
            tool_name="archive_attach",
            arguments={"archive_id": "archive_phase16", "scope_type": "session"},
            source_refs=[_source_ref()],
            tool_call_id="toolcall_archive_attach",
        ),
        _core_promotion_request(tool_call_id="toolcall_core_promotion"),
        _core_candidate_apply_request(
            candidate_id="pcand_pending",
            tool_call_id="toolcall_core_candidate_apply",
        ),
    ]

    for tool_request in tool_requests:
        result = service.agent_kernel.run_step(
            _request(),
            tool_requests=[tool_request],
        )
        event_types = [event.event_type for event in result.trace]
        assert event_types == [
            "kernel_step_started",
            "tool_candidates_generated",
            "tool_selected",
            "tool_policy_decision",
            "approval_pending",
            "kernel_step_completed",
        ]
        pending = next(event for event in result.trace if event.event_type == "approval_pending")
        assert pending.payload["tool_name"] == tool_request.tool_name
        assert pending.payload["metadata"]["tool_call_id"] == tool_request.tool_call_id
        assert result.continuation == "pause"


@pytest.mark.parametrize(
    ("tool_request", "error_fragment"),
    [
        (
            _archive_request(
                tool_call_id="toolcall_bad_archive_write",
            ).model_copy(
                update={
                    "arguments": {
                        "content": "bad archival fact",
                        "memory_type": "not-a-memory-type",
                    }
                }
            ),
            "archive_write",
        ),
        (
            ToolExecutionRequest(
                session_id="ses_1",
                tool_name="archive_attach",
                arguments={"archive_id": "archive_missing", "scope_type": "session"},
                source_refs=[_source_ref()],
                tool_call_id="toolcall_bad_archive_attach",
            ),
            "archive_attach",
        ),
        (
            _core_promotion_request(
                tool_call_id="toolcall_bad_core_promotion",
            ).model_copy(
                update={
                    "arguments": {
                        "content": "Alice prefers concise status updates.",
                        "label": "human",
                        "reason": "source-backed preference candidate",
                        "limit_tokens": "not-an-int",
                    }
                }
            ),
            "core_promotion_request",
        ),
        (
            _core_candidate_apply_request(
                candidate_id="pcand_missing",
                tool_call_id="toolcall_bad_core_candidate_apply",
            ),
            "core_candidate_apply",
        ),
    ],
)
def test_memoryos_service_registered_tool_malformed_replay_fails_closed(
    tmp_path,
    tool_request,
    error_fragment,
):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_agent_kernel="v1",
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(settings=settings, store=store)
    assert service.agent_kernel is not None

    first = service.agent_kernel.run_step(
        _request(),
        tool_requests=[tool_request],
    )
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    tool_call_id = _pending_tool_call_id(first.trace)

    resumed = service.agent_kernel.run_step(
        _request(),
        tool_requests=[
            tool_request.model_copy(
                update={"approval_id": approval_id, "tool_call_id": tool_call_id}
            )
        ],
    )

    event_types = [event.event_type for event in resumed.trace]
    assert "approval_granted" in event_types
    assert "tool_executed" in event_types
    assert "tool_verified" not in event_types
    executed = next(event for event in resumed.trace if event.event_type == "tool_executed")
    assert executed.payload["tool_name"] == tool_request.tool_name
    assert executed.payload["ok"] is False
    assert error_fragment in executed.payload["error"]
    assert _archival_memory_count(store) == 0
    assert store.list_archive_attachments(scope_type="session", scope_id="ses_1") == []
    assert _promotion_candidate_count(store) == 0
    assert [msg for msg in store.list_messages("ses_1") if msg.role == Role.TOOL] == []


def test_kernel_tool_result_message_is_visible_to_later_v3_context(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None
    tool_call_id = _pending_tool_call_id(first.trace)

    reopened = create_store(settings)
    resumed = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id, tool_call_id=tool_call_id)],
    )
    memory_id = next(
        event.payload["result"]["memory_id"]
        for event in resumed.trace
        if event.event_type == "tool_executed"
    )
    package = V3ContextComposer(store=reopened, settings=settings).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="approved archival fact",
            budget=120,
        )
    )

    recent_tool_items = [
        item
        for item in package.items
        if item.layer == "recent" and item.metadata.get("role") == "tool"
    ]
    assert recent_tool_items
    assert recent_tool_items[0].text == "tool archive_write executed"
    tool_messages = [msg for msg in reopened.list_messages("ses_1") if msg.role == Role.TOOL]
    assert tool_messages[0].metadata.get("memory_id") == memory_id
    assert package.metadata["memory_arch"] == "v3"


def test_kernel_archive_write_becomes_same_session_archival_context_item(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    session = store.create_session("phase 12 archival test")
    first = _approval_runner(store).run_step(
        _request(session.id),
        tool_requests=[_archive_request(session_id=session.id)],
    )
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None
    tool_call_id = _pending_tool_call_id(first.trace)

    reopened = create_store(settings)
    resumed = _approval_runner(reopened).run_step(
        _request(session.id),
        tool_requests=[
            _archive_request(
                approval_id=approval_id,
                session_id=session.id,
                tool_call_id=tool_call_id,
            )
        ],
    )
    memory_id = next(
        event.payload["result"]["memory_id"]
        for event in resumed.trace
        if event.event_type == "tool_executed"
    )

    v3_package = V3ContextComposer(store=reopened, settings=settings).build(
        ContextComposerRequest(
            session_id=session.id,
            task="approved archival fact",
            budget=120,
        )
    )
    archival_items = [item for item in v3_package.items if item.layer == "archival"]

    assert [item.text for item in archival_items] == ["approved archival fact"]
    assert archival_items[0].source_refs[0].source_id == "msg_1"
    assert archival_items[0].metadata["archival_memory_id"] == memory_id
    assert archival_items[0].metadata["archive_id"] == session.id
    assert v3_package.metadata["archival_eligibility"]["selected_passage_ids"] == [
        f"apsg_{memory_id}"
    ]
    assert v3_package.metadata["archival_eligibility"]["selected_source_refs"] == [
        {"source_type": "message", "source_id": "msg_1", "session_id": session.id}
    ]

    service = MemoryOSService(settings=settings, store=reopened)
    legacy_package = service.build_context(
        session_id=session.id,
        task="approved archival fact",
        budget=120,
    )
    archival_evidence = [
        evidence
        for evidence in legacy_package.retrieved_evidence
        if evidence.metadata.get("origin") == "archival"
    ]
    assert [evidence.text for evidence in archival_evidence] == ["approved archival fact"]
    assert archival_evidence[0].message_id == "msg_1"
    assert archival_evidence[0].metadata["v3_item_id"] == f"apsg_{memory_id}"
