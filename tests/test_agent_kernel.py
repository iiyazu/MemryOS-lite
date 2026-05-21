from memoryos_lite.agent_kernel import (
    ApprovalGateV1,
    SimpleAgentStepRunner,
    SimpleToolPolicyEngine,
)
from memoryos_lite.config import Settings
from memoryos_lite.store import create_store
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    ContextPackageV3,
    ToolExecutionRequest,
    ToolPolicyRule,
)


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
