from pathlib import Path

from sqlalchemy import text

from memoryos_lite.agent_kernel import (
    ApprovalGateV1,
    SimpleAgentStepRunner,
    SimpleToolExecutionManager,
    SimpleToolPolicyEngine,
)
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.kernel_maintenance import (
    KernelMaintenanceAnalyzer,
    KernelMaintenanceProposalExecutor,
    MaintenanceSignal,
)
from memoryos_lite.memory_lifecycle import MemoryLifecycleService
from memoryos_lite.schemas import Message, Role
from memoryos_lite.store import create_store
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    ArchivalMemory,
    ContextLayerItem,
    ContextPackageV3,
    DiagnosticEvent,
    LayerBudgetDecision,
    SourceRef,
    SourceType,
    ToolPolicyRule,
)


def test_kernel_maintenance_facade_stays_small_and_reexports_public_contracts():
    facade = Path(__file__).parents[1] / "src" / "memoryos_lite" / "kernel_maintenance.py"

    assert len(facade.read_text().splitlines()) <= 120
    assert KernelMaintenanceAnalyzer.__module__ == "memoryos_lite.kernel_analyzer"
    assert KernelMaintenanceProposalExecutor.__module__ == "memoryos_lite.kernel_executor"
    assert MaintenanceSignal.__module__ == "memoryos_lite.kernel_contracts"


def _request_with_context(context: ContextPackageV3) -> AgentStepRequest:
    return AgentStepRequest(
        session_id=context.session_id,
        input_messages=[],
        context=context,
    )


def _source_ref(session_id: str = "ses_1") -> SourceRef:
    return SourceRef(
        source_type=SourceType.MESSAGE,
        source_id="msg_1",
        session_id=session_id,
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


def test_kernel_maintenance_analyzer_proposes_archive_write_from_source_backed_recall(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="Where did Alice move?",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="msg_1",
                text="Alice moved to Shanghai.",
                estimated_tokens=4,
                source_refs=[_source_ref()],
                metadata={"reason": "test recall"},
            )
        ],
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert [signal.signal_type for signal in result.signals] == ["recall_to_archive_candidate"]
    assert [decision.action for decision in result.decisions] == ["propose"]
    proposal = result.memory_proposals[0]
    assert proposal.proposal_type == "archive_write"
    assert proposal.tool_request.tool_name == "archive_write"
    assert proposal.tool_request.arguments["content"] == "Alice moved to Shanghai."
    assert proposal.tool_request.source_refs[0].source_id == "msg_1"
    assert _archival_memory_count(store) == 0
    assert any(
        event.event_type == "maintenance_decision"
        and event.payload["decision"]["action"] == "propose"
        and event.payload["source_ids"] == ["msg_1"]
        for event in result.trace
    )


def test_kernel_maintenance_analyzer_rejects_mutating_proposal_without_source_refs(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What changed?",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="msg_missing_source",
                text="Alice moved to Shanghai.",
                estimated_tokens=4,
                source_refs=[],
            )
        ],
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert result.memory_proposals == []
    assert [decision.action for decision in result.decisions] == ["reject"]
    assert "source_refs" in result.decisions[0].reason
    assert _archival_memory_count(store) == 0
    assert any(
        event.event_type == "maintenance_decision"
        and event.payload["decision"]["action"] == "reject"
        for event in result.trace
    )


def test_kernel_maintenance_analyzer_reports_dropped_high_value_context_feedback(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    dropped_ref = SourceRef(
        source_type=SourceType.MESSAGE,
        source_id="msg_dropped",
        session_id="ses_1",
    )
    context = ContextPackageV3(
        session_id="ses_1",
        task="What appointment is important?",
        diagnostics=[
            DiagnosticEvent(
                layer="recall",
                event_type="select",
                item_id="msg_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=240,
                source_refs=[dropped_ref],
                metadata={"reason": "high_value_recall_evidence"},
            )
        ],
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert result.memory_proposals == []
    assert [feedback.feedback_type for feedback in result.context_feedback] == [
        "dropped_high_value_evidence"
    ]
    assert result.context_feedback[0].source_refs[0].source_id == "msg_dropped"
    assert result.context_feedback[0].suggested_action == "review_layer_budget_or_persist"
    assert any(
        event.event_type == "maintenance_context_feedback"
        and event.payload["feedback_type"] == "dropped_high_value_evidence"
        and event.payload["source_ids"] == ["msg_dropped"]
        for event in result.trace
    )


def test_kernel_maintenance_analyzer_proposes_archive_write_for_dropped_high_value_message(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    store.add_message(
        Message(
            id="msg_dropped",
            session_id="ses_1",
            role=Role.USER,
            content="Alice has an important cardiology appointment next Tuesday.",
            token_count=8,
        )
    )
    dropped_ref = SourceRef(
        source_type=SourceType.MESSAGE,
        source_id="msg_dropped",
        session_id="ses_1",
    )
    context = ContextPackageV3(
        session_id="ses_1",
        task="What appointment is important?",
        diagnostics=[
            DiagnosticEvent(
                layer="message_log",
                event_type="select",
                item_id="msg_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=240,
                source_refs=[dropped_ref],
                metadata={"reason": "recent_message"},
            )
        ],
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert [feedback.feedback_type for feedback in result.context_feedback] == [
        "dropped_high_value_evidence"
    ]
    proposals = [
        proposal
        for proposal in result.memory_proposals
        if proposal.signal_id == "msig_dropped_high_value_evidence_msg_dropped"
    ]
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.proposal_type == "archive_write"
    assert proposal.tool_request.tool_name == "archive_write"
    assert proposal.tool_request.arguments["content"] == (
        "Alice has an important cardiology appointment next Tuesday."
    )
    assert proposal.tool_request.arguments["source_layer"] == "message_log"
    assert proposal.tool_request.source_refs[0].source_id == "msg_dropped"
    assert _archival_memory_count(store) == 0
    assert any(
        decision.action == "propose"
        and decision.signal_id == "msig_dropped_high_value_evidence_msg_dropped"
        for decision in result.decisions
    )
    assert any(
        event.event_type == "maintenance_memory_proposal"
        and event.payload["proposal"]["proposal_type"] == "archive_write"
        and event.payload["source_ids"] == ["msg_dropped"]
        for event in result.trace
    )


def test_kernel_maintenance_analyzer_rejects_dropped_archive_proposal_when_message_missing(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What appointment is important?",
        diagnostics=[
            DiagnosticEvent(
                layer="message_log",
                event_type="select",
                item_id="msg_missing",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=240,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.MESSAGE,
                        source_id="msg_missing",
                        session_id="ses_1",
                    )
                ],
                metadata={"reason": "recent_message"},
            )
        ],
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert result.memory_proposals == []
    assert [feedback.feedback_type for feedback in result.context_feedback] == [
        "dropped_high_value_evidence"
    ]
    assert any(
        decision.action == "reject"
        and decision.signal_id == "msig_dropped_high_value_evidence_msg_missing"
        and "source message not found" in decision.reason
        for decision in result.decisions
    )


def test_kernel_maintenance_analyzer_defers_duplicate_dropped_archive_proposal(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    store.add_message(
        Message(
            id="msg_dropped",
            session_id="ses_1",
            role=Role.USER,
            content="Alice has an important cardiology appointment next Tuesday.",
            token_count=8,
        )
    )
    store.add_archival_memory(
        ArchivalMemory(
            id="amem_existing",
            archive_id="ses_1",
            memory_type="fact",
            content="Alice has an important cardiology appointment next Tuesday.",
            source_refs=[_source_ref()],
        ),
        actor="agent",
        reason="existing archive",
    )
    context = ContextPackageV3(
        session_id="ses_1",
        task="What appointment is important?",
        diagnostics=[
            DiagnosticEvent(
                layer="message_log",
                event_type="select",
                item_id="msg_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=240,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.MESSAGE,
                        source_id="msg_dropped",
                        session_id="ses_1",
                    )
                ],
                metadata={"reason": "recent_message"},
            )
        ],
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert result.memory_proposals == []
    assert any(
        decision.action == "defer"
        and decision.signal_id == "msig_dropped_high_value_evidence_msg_dropped"
        and "duplicate archival memory already exists" in decision.reason
        for decision in result.decisions
    )


def test_kernel_maintenance_analyzer_reports_recall_budget_pressure_feedback(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    dropped_ref = SourceRef(
        source_type=SourceType.MESSAGE,
        source_id="msg_budget_dropped",
        session_id="ses_1",
    )
    context = ContextPackageV3(
        session_id="ses_1",
        task="What source was dropped?",
        diagnostics=[
            DiagnosticEvent(
                layer="recall",
                event_type="select",
                item_id="msg_budget_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=96,
                source_refs=[dropped_ref],
                metadata={
                    "reason": "recall_memory=9.1 overlap=2",
                    "evidence_packet_id": "packet_1",
                },
            )
        ],
        budget_decisions=[
            LayerBudgetDecision(
                layer="task",
                requested_tokens=8,
                allocated_tokens=8,
                used_tokens=8,
                dropped_item_ids=[],
                reason_code="fit",
            ),
            LayerBudgetDecision(
                layer="recall",
                requested_tokens=5200,
                allocated_tokens=4792,
                used_tokens=4704,
                dropped_item_ids=["msg_budget_dropped"],
                reason_code="budget_drop",
            ),
        ],
        metadata={
            "component_accounting": [
                {
                    "component": "recall",
                    "layer": "recall",
                    "event_type": "select",
                    "item_id": "msg_budget_dropped",
                    "source_ids": ["msg_budget_dropped"],
                    "estimated_tokens": 96,
                    "included": False,
                    "dropped": True,
                    "reason_code": "budget_drop",
                    "metadata": {"evidence_packet_id": "packet_1"},
                }
            ],
            "component_token_totals": {"task": 8, "recall": 4704},
            "component_drop_counts": {"recall": 1},
        },
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert result.memory_proposals == []
    budget_feedback = [
        feedback
        for feedback in result.context_feedback
        if feedback.feedback_type == "recall_budget_pressure"
    ]
    assert len(budget_feedback) == 1
    feedback = budget_feedback[0]
    assert feedback.suggested_action == "record_budget_pressure_for_future_context"
    assert feedback.source_refs[0].source_id == "msg_budget_dropped"
    assert feedback.metadata["layer"] == "recall"
    assert feedback.metadata["dropped_item_ids"] == ["msg_budget_dropped"]
    assert feedback.metadata["requested_tokens"] == 5200
    assert feedback.metadata["allocated_tokens"] == 4792
    assert feedback.metadata["used_tokens"] == 4704
    assert feedback.metadata["dropped_source_ids"] == ["msg_budget_dropped"]
    assert feedback.metadata["component_drop_count"] == 1
    assert any(
        event.event_type == "maintenance_context_feedback"
        and event.payload["feedback_type"] == "recall_budget_pressure"
        and event.payload["source_ids"] == ["msg_budget_dropped"]
        for event in result.trace
    )
    assert context.budget_decisions[1].dropped_item_ids == ["msg_budget_dropped"]
    assert context.items == []


def test_kernel_maintenance_analyzer_reports_recent_layer_budget_pressure_feedback(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    dropped_ref = SourceRef(
        source_type=SourceType.MESSAGE,
        source_id="msg_recent_dropped",
        session_id="ses_1",
    )
    context = ContextPackageV3(
        session_id="ses_1",
        task="What recent source was dropped?",
        diagnostics=[
            DiagnosticEvent(
                layer="message_log",
                event_type="select",
                item_id="msg_recent_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=96,
                source_refs=[dropped_ref],
                metadata={"reason": "recent_message", "role": "user"},
            )
        ],
        budget_decisions=[
            LayerBudgetDecision(
                layer="recent",
                requested_tokens=1200,
                allocated_tokens=480,
                used_tokens=480,
                dropped_item_ids=["msg_recent_dropped"],
                reason_code="budget_drop",
            ),
        ],
        metadata={
            "component_accounting": [
                {
                    "component": "recent",
                    "layer": "message_log",
                    "event_type": "select",
                    "item_id": "msg_recent_dropped",
                    "source_ids": ["msg_recent_dropped"],
                    "estimated_tokens": 96,
                    "included": False,
                    "dropped": True,
                    "reason_code": "budget_drop",
                    "metadata": {"reason": "recent_message"},
                }
            ],
            "component_drop_counts": {"recent": 1},
        },
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    budget_feedback = [
        feedback
        for feedback in result.context_feedback
        if feedback.feedback_type == "layer_budget_pressure"
    ]
    assert len(budget_feedback) == 1
    feedback = budget_feedback[0]
    assert feedback.suggested_action == "record_budget_pressure_for_future_context"
    assert feedback.source_refs[0].source_id == "msg_recent_dropped"
    assert feedback.metadata["layer"] == "recent"
    assert feedback.metadata["component"] == "recent"
    assert feedback.metadata["dropped_item_ids"] == ["msg_recent_dropped"]
    assert feedback.metadata["dropped_source_ids"] == ["msg_recent_dropped"]
    assert feedback.metadata["component_drop_count"] == 1
    assert any(
        event.event_type == "maintenance_context_feedback"
        and event.payload["feedback_type"] == "layer_budget_pressure"
        and event.payload["source_ids"] == ["msg_recent_dropped"]
        for event in result.trace
    )


def test_kernel_maintenance_analyzer_ignores_recall_budget_fit_without_drops(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What fit?",
        budget_decisions=[
            LayerBudgetDecision(
                layer="recall",
                requested_tokens=200,
                allocated_tokens=200,
                used_tokens=200,
                dropped_item_ids=[],
                reason_code="fit",
            )
        ],
        metadata={
            "component_accounting": [
                {
                    "component": "recall",
                    "layer": "recall",
                    "item_id": "msg_fit",
                    "source_ids": ["msg_fit"],
                    "included": True,
                    "dropped": False,
                    "reason_code": "recall",
                }
            ],
            "component_drop_counts": {"recall": 0},
        },
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert result.context_feedback == []
    assert result.memory_proposals == []
    assert [decision.action for decision in result.decisions] == ["noop"]


def test_kernel_maintenance_analyzer_core_promotion_request_does_not_mutate_core(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What does Alice prefer?",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="msg_1",
                text="Alice prefers concise status updates.",
                estimated_tokens=5,
                source_refs=[_source_ref()],
                metadata={"reason": "test recall"},
            )
        ],
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    proposal = result.memory_proposals[0]
    assert proposal.proposal_type == "core_promotion_request"
    assert proposal.tool_request.tool_name == "core_promotion_request"
    assert proposal.tool_request.arguments["content"] == ("Alice prefers concise status updates.")
    assert proposal.tool_request.arguments["label"] == "human"
    assert store.list_core_memory_blocks() == []
    assert store.list_promotion_candidates() == []


def test_kernel_maintenance_analyzer_suppresses_duplicate_pending_core_proposal(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    lifecycle = MemoryLifecycleService(store)
    lifecycle.create_candidate(
        source_layer="recall",
        target_layer="core",
        operation="promote",
        content="Alice prefers concise status updates.",
        source_refs=[_source_ref()],
        identity_scope=None,
        reason="existing pending candidate",
        confidence=0.9,
        write_source="message_extraction",
        metadata={"label": "human"},
    )
    context = ContextPackageV3(
        session_id="ses_1",
        task="What does Alice prefer?",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="msg_1",
                text="Alice prefers concise status updates.",
                estimated_tokens=5,
                source_refs=[_source_ref()],
            )
        ],
    )

    result = KernelMaintenanceAnalyzer(store).analyze(_request_with_context(context))

    assert result.memory_proposals == []
    assert [decision.action for decision in result.decisions] == ["defer"]
    assert "duplicate" in result.decisions[0].reason


def test_kernel_maintenance_executor_routes_proposal_to_approval_boundary(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="Where did Alice move?",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="msg_1",
                text="Alice moved to Shanghai.",
                estimated_tokens=4,
                source_refs=[_source_ref()],
            )
        ],
    )
    request = _request_with_context(context)
    analysis = KernelMaintenanceAnalyzer(store).analyze(request)

    result = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    ).execute(request, analysis)

    assert result.agent_step is not None
    assert result.agent_step.continuation == "pause"
    assert [event.event_type for event in result.agent_step.trace] == [
        "kernel_step_started",
        "tool_candidates_generated",
        "tool_selected",
        "tool_policy_decision",
        "approval_pending",
        "kernel_step_completed",
    ]
    pending = next(
        event for event in result.agent_step.trace if event.event_type == "approval_pending"
    )
    assert pending.payload["tool_name"] == "archive_write"
    assert pending.payload["source_refs"][0]["source_id"] == "msg_1"
    assert pending.payload["metadata"]["request_fingerprint"]
    assert _archival_memory_count(store) == 0
    durable_event_types = [trace.event_type for trace in store.list_traces("ses_1")]
    assert "maintenance_signal" in durable_event_types
    assert "maintenance_decision" in durable_event_types
    assert "maintenance_memory_proposal" in durable_event_types
    assert "approval_pending" in durable_event_types


def test_kernel_maintenance_executor_replays_approval_through_runner_once(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="Where did Alice move?",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="msg_1",
                text="Alice moved to Shanghai.",
                estimated_tokens=4,
                source_refs=[_source_ref()],
            )
        ],
    )
    request = _request_with_context(context)
    first_analysis = KernelMaintenanceAnalyzer(store).analyze(request)
    first = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    ).execute(request, first_analysis)
    assert first.agent_step is not None
    approval_id = next(
        event.approval_id
        for event in first.agent_step.trace
        if event.event_type == "approval_pending"
    )
    assert approval_id is not None

    reopened = create_store(settings)
    resumed_analysis = KernelMaintenanceAnalyzer(reopened).analyze(request)
    proposal = resumed_analysis.memory_proposals[0]
    resumed_analysis.memory_proposals[0] = proposal.model_copy(
        update={
            "tool_request": proposal.tool_request.model_copy(update={"approval_id": approval_id})
        }
    )
    resumed = KernelMaintenanceProposalExecutor(
        reopened,
        runner=_approval_runner(reopened),
    ).execute(request, resumed_analysis)

    assert resumed.agent_step is not None
    event_types = [event.event_type for event in resumed.agent_step.trace]
    assert "approval_granted" in event_types
    assert "tool_executed" in event_types
    assert "tool_verified" in event_types
    assert _archival_memory_count(reopened) == 1

    replayed = KernelMaintenanceProposalExecutor(
        create_store(settings),
        runner=_approval_runner(create_store(settings)),
    ).execute(request, resumed_analysis)
    assert replayed.agent_step is not None
    assert "tool_replay_skipped" in [event.event_type for event in replayed.agent_step.trace]


def test_kernel_maintenance_executor_suppresses_duplicate_proposals_before_selection(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="Where did Alice move?",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="msg_1",
                text="Alice moved to Shanghai.",
                estimated_tokens=4,
                source_refs=[_source_ref()],
            ),
            ContextLayerItem(
                layer="recall",
                item_id="msg_1_duplicate",
                text="Alice moved to Shanghai.",
                estimated_tokens=4,
                source_refs=[_source_ref()],
            ),
        ],
    )
    request = _request_with_context(context)
    analysis = KernelMaintenanceAnalyzer(store).analyze(request)
    assert len(analysis.memory_proposals) == 2

    result = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    ).execute(request, analysis)

    assert result.skipped_duplicate_proposal_count == 1
    assert result.agent_step is not None
    generated = next(
        event
        for event in result.agent_step.trace
        if event.event_type == "tool_candidates_generated"
    )
    assert len(generated.payload["candidates"]) == 1
    assert any(
        trace.event_type == "maintenance_duplicate_proposal_skipped"
        for trace in store.list_traces("ses_1")
    )


def test_kernel_maintenance_executor_persists_context_feedback_without_execution(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What appointment is important?",
        diagnostics=[
            DiagnosticEvent(
                layer="recall",
                event_type="select",
                item_id="msg_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=240,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.MESSAGE,
                        source_id="msg_dropped",
                        session_id="ses_1",
                    )
                ],
                metadata={"reason": "high_value_recall_evidence"},
            )
        ],
    )
    request = _request_with_context(context)
    analysis = KernelMaintenanceAnalyzer(store).analyze(request)

    result = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    ).execute(request, analysis)

    assert result.agent_step is None
    assert result.persisted_feedback_trace_count == 1
    assert _archival_memory_count(store) == 0
    durable_feedback = [
        trace
        for trace in store.list_traces("ses_1")
        if trace.event_type == "maintenance_context_feedback"
    ]
    assert len(durable_feedback) == 1
    assert durable_feedback[0].payload["source_ids"] == ["msg_dropped"]


def test_kernel_maintenance_executor_creates_context_policy_candidate_from_feedback(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What source was dropped?",
        diagnostics=[
            DiagnosticEvent(
                layer="recall",
                event_type="select",
                item_id="msg_budget_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=96,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.MESSAGE,
                        source_id="msg_budget_dropped",
                        session_id="ses_1",
                    )
                ],
            )
        ],
        budget_decisions=[
            LayerBudgetDecision(
                layer="recall",
                requested_tokens=5200,
                allocated_tokens=4792,
                used_tokens=4704,
                dropped_item_ids=["msg_budget_dropped"],
                reason_code="budget_drop",
            )
        ],
    )
    request = _request_with_context(context)
    analysis = KernelMaintenanceAnalyzer(store).analyze(request)

    result = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    ).execute(request, analysis)

    assert result.agent_step is None
    candidates = store.list_context_policy_candidates(status="pending")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.feedback_type == "recall_budget_pressure"
    assert candidate.policy_type == "context_quality"
    assert candidate.status == "pending"
    assert candidate.source_refs[0].source_id == "msg_budget_dropped"
    assert candidate.metadata["dropped_item_ids"] == ["msg_budget_dropped"]
    assert candidate.metadata["suggested_action"] == ("record_budget_pressure_for_future_context")
    assert any(
        trace.event_type == "maintenance_context_policy_candidate_created"
        and trace.payload["candidate_id"] == candidate.id
        and trace.payload["feedback_type"] == "recall_budget_pressure"
        for trace in store.list_traces("ses_1")
    )


def test_kernel_maintenance_executor_creates_policy_candidate_for_recent_budget_pressure(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What recent source was dropped?",
        diagnostics=[
            DiagnosticEvent(
                layer="message_log",
                event_type="select",
                item_id="msg_recent_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=96,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.MESSAGE,
                        source_id="msg_recent_dropped",
                        session_id="ses_1",
                    )
                ],
                metadata={"reason": "recent_message"},
            )
        ],
        budget_decisions=[
            LayerBudgetDecision(
                layer="recent",
                requested_tokens=1200,
                allocated_tokens=480,
                used_tokens=480,
                dropped_item_ids=["msg_recent_dropped"],
                reason_code="budget_drop",
            )
        ],
    )
    request = _request_with_context(context)
    analysis = KernelMaintenanceAnalyzer(store).analyze(request)

    result = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    ).execute(request, analysis)

    assert result.agent_step is None
    candidates = store.list_context_policy_candidates(status="pending")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.feedback_type == "layer_budget_pressure"
    assert candidate.source_refs[0].source_id == "msg_recent_dropped"
    assert candidate.metadata["layer"] == "recent"
    assert candidate.metadata["dropped_item_ids"] == ["msg_recent_dropped"]
    assert any(
        trace.event_type == "maintenance_context_policy_candidate_created"
        and trace.payload["candidate_id"] == candidate.id
        and trace.payload["feedback_type"] == "layer_budget_pressure"
        for trace in store.list_traces("ses_1")
    )


def test_kernel_maintenance_executor_suppresses_duplicate_context_policy_candidate(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What source was dropped?",
        diagnostics=[
            DiagnosticEvent(
                layer="recall",
                event_type="select",
                item_id="msg_budget_dropped",
                reason_code="budget_drop",
                included=False,
                dropped=True,
                budget_tokens=96,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.MESSAGE,
                        source_id="msg_budget_dropped",
                        session_id="ses_1",
                    )
                ],
            )
        ],
        budget_decisions=[
            LayerBudgetDecision(
                layer="recall",
                requested_tokens=5200,
                allocated_tokens=4792,
                used_tokens=4704,
                dropped_item_ids=["msg_budget_dropped"],
                reason_code="budget_drop",
            )
        ],
    )
    request = _request_with_context(context)
    executor = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    )

    executor.execute(request, KernelMaintenanceAnalyzer(store).analyze(request))
    second = executor.execute(request, KernelMaintenanceAnalyzer(store).analyze(request))

    assert len(store.list_context_policy_candidates(status="pending")) == 1
    assert second.skipped_duplicate_policy_candidate_count == 1
    assert any(
        trace.event_type == "maintenance_duplicate_policy_candidate_skipped"
        for trace in store.list_traces("ses_1")
    )


def test_kernel_maintenance_executor_does_not_create_policy_candidate_without_sources(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="What source was dropped?",
        budget_decisions=[
            LayerBudgetDecision(
                layer="recall",
                requested_tokens=5200,
                allocated_tokens=4792,
                used_tokens=4704,
                dropped_item_ids=["msg_budget_dropped"],
                reason_code="budget_drop",
            )
        ],
        metadata={
            "component_accounting": [
                {
                    "component": "recall",
                    "item_id": "msg_budget_dropped",
                    "source_ids": ["msg_budget_dropped"],
                    "dropped": True,
                    "reason_code": "budget_drop",
                }
            ]
        },
    )
    request = _request_with_context(context)
    analysis = KernelMaintenanceAnalyzer(store).analyze(request)
    assert [feedback.feedback_type for feedback in analysis.context_feedback] == [
        "recall_budget_pressure"
    ]
    assert analysis.context_feedback[0].source_refs == []

    result = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    ).execute(request, analysis)

    assert result.agent_step is None
    assert store.list_context_policy_candidates() == []
    assert any(
        trace.event_type == "maintenance_context_policy_candidate_rejected"
        and trace.payload["reason"] == "context policy candidate requires source_refs"
        for trace in store.list_traces("ses_1")
    )


def test_kernel_maintenance_executor_skips_existing_pending_approval_for_same_request(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    context = ContextPackageV3(
        session_id="ses_1",
        task="Where did Alice move?",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="msg_1",
                text="Alice moved to Shanghai.",
                estimated_tokens=4,
                source_refs=[_source_ref()],
            )
        ],
    )
    request = _request_with_context(context)
    analysis = KernelMaintenanceAnalyzer(store).analyze(request)
    executor = KernelMaintenanceProposalExecutor(
        store,
        runner=_approval_runner(store),
    )

    first = executor.execute(request, analysis)
    assert first.agent_step is not None
    assert "approval_pending" in [event.event_type for event in first.agent_step.trace]

    second = executor.execute(request, KernelMaintenanceAnalyzer(store).analyze(request))

    assert second.agent_step is None
    assert second.skipped_duplicate_proposal_count == 1
    pending = [
        trace for trace in store.list_traces("ses_1") if trace.event_type == "approval_pending"
    ]
    assert len(pending) == 1
    assert any(
        trace.event_type == "maintenance_duplicate_proposal_skipped"
        and trace.payload["reason"] == "matching approval is already pending"
        for trace in store.list_traces("ses_1")
    )


def test_memoryos_service_runs_opt_in_kernel_maintenance_after_v3_context_build(
    tmp_path,
):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_agent_kernel="v1",
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(settings=settings, store=store)
    session = service.create_session("kernel maintenance integration")
    store.add_message(
        Message(
            id="msg_1",
            session_id=session.id,
            role=Role.USER,
            content="Alice moved to Shanghai.",
            token_count=4,
        )
    )

    package = service.build_context(session.id, "Where did Alice move?", budget=120)

    assert package.metadata["memory_arch"] == "v3"
    event_types = [trace.event_type for trace in store.list_traces(session.id)]
    assert "maintenance_signal" in event_types
    assert "maintenance_decision" in event_types
    assert "approval_pending" in event_types
    assert _archival_memory_count(store) == 0


def test_memoryos_service_does_not_run_kernel_maintenance_when_kernel_off(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_agent_kernel="off",
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(settings=settings, store=store)
    session = service.create_session("kernel off")
    store.add_message(
        Message(
            id="msg_1",
            session_id=session.id,
            role=Role.USER,
            content="Alice moved to Shanghai.",
            token_count=4,
        )
    )

    package = service.build_context(session.id, "Where did Alice move?", budget=120)

    assert package.metadata["memory_arch"] == "v3"
    assert not any(
        trace.event_type.startswith("maintenance_") for trace in store.list_traces(session.id)
    )
