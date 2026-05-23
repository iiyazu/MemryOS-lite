import json

from sqlalchemy import text

from memoryos_lite.agent_kernel import (
    ApprovalGateV1,
    SimpleAgentStepRunner,
    SimpleToolExecutionManager,
    SimpleToolPolicyEngine,
)
from memoryos_lite.config import Settings
from memoryos_lite.context_composer import V3ContextComposer
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import Role
from memoryos_lite.store import create_store
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    ContextComposerRequest,
    ContextPackageV3,
    SourceRef,
    SourceType,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicyRule,
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
) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        session_id=session_id,
        tool_name=tool_name,
        arguments={"content": content, "memory_type": "fact"},
        source_refs=[_source_ref(session_id)],
        approval_id=approval_id,
    )


def _approval_runner(store):
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
    )


def _archival_memory_count(store) -> int:
    with store.db() as db:
        return int(db.scalar(text("select count(*) from archival_memories")))


def _trace_payloads(store, session_id: str, event_type: str) -> list[dict]:
    return [
        trace.payload
        for trace in store.list_traces(session_id)
        if trace.event_type == event_type
    ]


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
    assert "tool_denied" in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    denied = next(event for event in result.trace if event.event_type == "tool_denied")
    assert "no matching tool policy rule" in denied.payload["error"]
    assert store.list_messages("ses_1") == []
    assert _archival_memory_count(store) == 0


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
        assert "tool_denied" in event_types
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
    assert _archival_memory_count(reopened) == 0
    assert reopened.list_messages("ses_1") == []

    resumed = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id)],
    )

    assert resumed.continuation == "stop"
    assert [event.event_type for event in resumed.trace] == [
        "kernel_step_started",
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
        tool_requests=[_archive_request(approval_id=approval_id)],
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

    invalid_requests = [
        _archive_request(approval_id="approval_missing"),
        _archive_request(approval_id=approval_id, session_id="ses_2"),
        _archive_request(approval_id=approval_id, tool_name="unknown_tool"),
        _archive_request(approval_id=approval_id, content="tampered archival fact"),
    ]

    for tool_request in invalid_requests:
        reopened = create_store(settings)
        result = _approval_runner(reopened).run_step(
            _request().model_copy(update={"session_id": tool_request.session_id}),
            tool_requests=[tool_request],
        )
        event_types = [event.event_type for event in result.trace]
        assert "approval_replay_denied" in event_types or "approval_replay_error" in event_types
        denial = next(
            event
            for event in result.trace
            if event.event_type in {"approval_replay_denied", "approval_replay_error"}
        )
        assert denial.payload["approval_id"] == tool_request.approval_id
        assert denial.payload["session_id"] == tool_request.session_id
        assert denial.payload["tool_name"] == tool_request.tool_name
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
        payload["payload"]["metadata"]["tool_call_id"] = "tool_call_original"
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
        tool_requests=[_archive_request(approval_id=approval_id)],
    )

    event_types = [event.event_type for event in result.trace]
    assert "approval_replay_denied" in event_types
    denial = next(event for event in result.trace if event.event_type == "approval_replay_denied")
    assert denial.payload["approval_id"] == approval_id
    assert "fingerprint" in denial.payload["reason"] or "tool_call" in denial.payload["reason"]
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


def test_kernel_tool_result_message_is_visible_to_later_v3_context(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None

    reopened = create_store(settings)
    resumed = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id)],
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
    assert "archive_write" in recent_tool_items[0].text
    assert (
        memory_id in recent_tool_items[0].text
        or recent_tool_items[0].metadata.get("memory_id") == memory_id
    )
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

    reopened = create_store(settings)
    resumed = _approval_runner(reopened).run_step(
        _request(session.id),
        tool_requests=[_archive_request(approval_id=approval_id, session_id=session.id)],
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
