from __future__ import annotations

from dataclasses import dataclass, field

from memoryos_lite.schemas import TraceEvent, new_id, utc_now
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    AgentStepResult,
    ApprovalState,
    KernelTraceEvent,
    ToolExecutionRequest,
    ToolPolicyDecision,
    ToolPolicyRule,
)


@dataclass
class SimpleToolPolicyEngine:
    rules: list[ToolPolicyRule] = field(default_factory=list)

    def decide(self, request: ToolExecutionRequest) -> ToolPolicyDecision:
        matched = [rule for rule in self.rules if rule.tool_name == request.tool_name]
        if not matched:
            return ToolPolicyDecision(
                tool_name=request.tool_name,
                effect="deny",
                matched_rule_ids=[],
                reason="no matching tool policy rule",
            )
        rule = sorted(matched, key=lambda item: item.priority, reverse=True)[0]
        return ToolPolicyDecision(
            tool_name=request.tool_name,
            effect=rule.effect,
            matched_rule_ids=[rule.id],
            requires_approval=rule.effect == "require_approval",
            reason=rule.reason,
        )


class ApprovalGateV1:
    def request_or_resume(self, request: ToolExecutionRequest) -> ApprovalState:
        if request.approval_id:
            return ApprovalState(
                id=request.approval_id,
                session_id=request.session_id,
                tool_name=request.tool_name,
                requested_action=request.arguments,
                status="approved",
                requested_by="agent",
                approved_by="agent",
                source_refs=list(request.source_refs),
                resolved_at=utc_now(),
                metadata={"reason": "approval resumed"},
            )
        return ApprovalState(
            id=new_id("approval"),
            session_id=request.session_id,
            tool_name=request.tool_name,
            requested_action=request.arguments,
            status="pending",
            requested_by="agent",
            source_refs=list(request.source_refs),
            metadata={"reason": f"approval required for {request.tool_name}"},
        )


@dataclass
class SimpleAgentStepRunner:
    store: MemoryStore
    tool_policy_engine: SimpleToolPolicyEngine = field(default_factory=SimpleToolPolicyEngine)
    approval_gate: ApprovalGateV1 = field(default_factory=ApprovalGateV1)

    def run_step(
        self,
        request: AgentStepRequest,
        *,
        tool_requests: list[ToolExecutionRequest] | None = None,
    ) -> AgentStepResult:
        step_id = new_id("step")
        trace: list[KernelTraceEvent] = []
        trace.append(
            self._trace(
                step_id=step_id,
                session_id=request.session_id,
                sequence=1,
                event_type="kernel_step_started",
                payload={
                    "context_items": len(request.context.items),
                    "input_messages": len(request.input_messages),
                },
            )
        )
        continuation = "stop"
        sequence = 2
        for tool_request in tool_requests or []:
            decision = self.tool_policy_engine.decide(tool_request)
            trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="tool_policy_decision",
                    payload=decision.model_dump(mode="json"),
                )
            )
            sequence += 1
            if decision.effect == "deny":
                continuation = "stop"
                continue
            if decision.requires_approval:
                approval = self.approval_gate.request_or_resume(tool_request)
                event_type = (
                    "approval_granted"
                    if approval.status == "approved"
                    else "approval_pending"
                )
                trace.append(
                    self._trace(
                        step_id=step_id,
                        session_id=request.session_id,
                        sequence=sequence,
                        event_type=event_type,
                        payload=approval.model_dump(mode="json"),
                        approval_id=approval.id,
                    )
                )
                sequence += 1
                if approval.status == "pending":
                    continuation = "pause"
                    break
        trace.append(
            self._trace(
                step_id=step_id,
                session_id=request.session_id,
                sequence=sequence,
                event_type="kernel_step_completed",
                payload={"continuation": continuation},
            )
        )
        for event in trace:
            self.store.add_trace(
                TraceEvent(
                    session_id=request.session_id,
                    event_type=event.event_type,
                    payload=event.model_dump(mode="json"),
                    created_at=event.created_at,
                )
            )
        return AgentStepResult(
            session_id=request.session_id,
            step_id=step_id,
            messages=[],
            trace=trace,
            continuation=continuation,
        )

    @staticmethod
    def _trace(
        *,
        step_id: str,
        session_id: str,
        sequence: int,
        event_type: str,
        payload: dict,
        approval_id: str | None = None,
    ) -> KernelTraceEvent:
        return KernelTraceEvent(
            step_id=step_id,
            session_id=session_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
            approval_id=approval_id,
        )
