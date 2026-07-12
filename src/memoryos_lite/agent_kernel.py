from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from memoryos_lite.agent_kernel_tools import (
    ArchiveMaintenanceService,
    PromotionMaintenanceService,
)
from memoryos_lite.agent_tool_selection import ToolSelectionBoundary
from memoryos_lite.schemas import Message, Role, TraceEvent, new_id, utc_now
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    AgentStepResult,
    ApprovalState,
    KernelTraceEvent,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicyDecision,
    ToolPolicyRule,
    message_to_log_entry,
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
class SimpleToolExecutionManager:
    store: MemoryStore
    archive_service: ArchiveMaintenanceService | None = None
    promotion_service: PromotionMaintenanceService | None = None

    def __post_init__(self) -> None:
        if self.archive_service is None:
            self.archive_service = ArchiveMaintenanceService(self.store)
        if self.promotion_service is None:
            self.promotion_service = PromotionMaintenanceService(self.store)

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        try:
            archive_service = self._archive_maintenance_service()
            if request.tool_name == "archive_write":
                return archive_service.write(request)
            if request.tool_name == "archive_attach":
                return archive_service.attach(request)
            if request.tool_name == "core_promotion_request":
                return self._promotion_maintenance_service().request_core_promotion(request)
            if request.tool_name == "core_candidate_apply":
                return self._promotion_maintenance_service().apply_core_candidate(request)
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error=(f"{request.tool_name} execution failed: {type(exc).__name__}: {exc}"),
            )
        return ToolExecutionResult(
            tool_name=request.tool_name,
            ok=False,
            error=f"unsupported tool: {request.tool_name}",
        )

    def verify(
        self,
        request: ToolExecutionRequest,
        *,
        memory_id: str | None = None,
        archive_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        archive_service = self._archive_maintenance_service()
        if request.tool_name == "archive_write":
            return archive_service.verify_archive_write(
                request,
                memory_id=memory_id,
                archive_id=archive_id,
            )
        if request.tool_name == "archive_attach":
            return archive_service.verify_archive_attach(
                request,
                archive_id=archive_id,
            )
        if request.tool_name == "core_promotion_request":
            return self._promotion_maintenance_service().verify_core_promotion_request(
                request,
                candidate_id=kwargs.get("candidate_id"),
            )
        if request.tool_name == "core_candidate_apply":
            return self._promotion_maintenance_service().verify_core_candidate_apply(
                request,
                candidate_id=kwargs.get("candidate_id"),
            )
        return {}

    def _archive_maintenance_service(self) -> ArchiveMaintenanceService:
        if self.archive_service is None:
            self.archive_service = ArchiveMaintenanceService(self.store)
        return self.archive_service

    def _promotion_maintenance_service(self) -> PromotionMaintenanceService:
        if self.promotion_service is None:
            self.promotion_service = PromotionMaintenanceService(self.store)
        return self.promotion_service


@dataclass
class SimpleAgentStepRunner:
    store: MemoryStore
    tool_policy_engine: SimpleToolPolicyEngine = field(default_factory=SimpleToolPolicyEngine)
    approval_gate: ApprovalGateV1 = field(default_factory=ApprovalGateV1)
    tool_execution_manager: SimpleToolExecutionManager | None = None
    tool_selection_boundary: ToolSelectionBoundary = field(default_factory=ToolSelectionBoundary)

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
        messages = []
        selected_requests: list[ToolExecutionRequest] = []
        if tool_requests:
            tool_selection_boundary = self.tool_selection_boundary or ToolSelectionBoundary()
            resolution = tool_selection_boundary.resolve(request, tool_requests)
            trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="tool_candidates_generated",
                    payload={
                        "candidates": [
                            candidate.model_dump(mode="json") for candidate in resolution.candidates
                        ],
                        "rejected_inputs": resolution.rejected_inputs,
                    },
                )
            )
            sequence += 1
            if resolution.selected_request is None:
                trace.append(
                    self._trace(
                        step_id=step_id,
                        session_id=request.session_id,
                        sequence=sequence,
                        event_type="tool_selection_denied",
                        payload=resolution.selection_payload,
                    )
                )
                sequence += 1
            else:
                trace.append(
                    self._trace(
                        step_id=step_id,
                        session_id=request.session_id,
                        sequence=sequence,
                        event_type="tool_selected",
                        payload=resolution.selection_payload,
                    )
                )
                sequence += 1
                selected_requests = [resolution.selected_request]
        for tool_request in selected_requests:
            replay_pending: dict | None = None
            if tool_request.approval_id:
                replay_pending, replay_error = self._pending_approval_for_replay(tool_request)
                if replay_error is not None:
                    trace.append(
                        self._trace(
                            step_id=step_id,
                            session_id=request.session_id,
                            sequence=sequence,
                            event_type="approval_replay_denied",
                            payload=replay_error,
                            approval_id=tool_request.approval_id,
                        )
                    )
                    sequence += 1
                    continue
            decision = self.tool_policy_engine.decide(tool_request)
            trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="tool_policy_decision",
                    payload={
                        **decision.model_dump(mode="json"),
                        **self._selected_call_metadata(tool_request),
                    },
                )
            )
            sequence += 1
            if decision.effect == "deny":
                tool_result = ToolExecutionResult(
                    tool_name=tool_request.tool_name,
                    ok=False,
                    error=decision.reason,
                )
                trace.append(
                    self._trace(
                        step_id=step_id,
                        session_id=request.session_id,
                        sequence=sequence,
                        event_type="tool_denied",
                        payload={
                            "tool_name": tool_request.tool_name,
                            "ok": False,
                            "error": decision.reason,
                            **self._selected_call_metadata(tool_request),
                            "decision": decision.model_dump(mode="json"),
                            "result": tool_result.model_dump(mode="json"),
                        },
                    )
                )
                sequence += 1
                continuation = "stop"
                continue
            should_execute = decision.effect == "allow"
            if decision.requires_approval:
                if replay_pending is not None:
                    if not tool_request.approval_id:
                        raise ValueError("approval replay requires approval_id")
                    if self._approval_already_executed(tool_request.approval_id):
                        trace.append(
                            self._trace(
                                step_id=step_id,
                                session_id=request.session_id,
                                sequence=sequence,
                                event_type="tool_replay_skipped",
                                payload={
                                    "approval_id": tool_request.approval_id,
                                    "session_id": tool_request.session_id,
                                    "tool_name": tool_request.tool_name,
                                    **self._selected_call_metadata(tool_request),
                                    "reason": "approval already executed",
                                },
                                approval_id=tool_request.approval_id,
                            )
                        )
                        sequence += 1
                        continue
                    approval = ApprovalState(
                        id=tool_request.approval_id,
                        session_id=tool_request.session_id,
                        tool_name=tool_request.tool_name,
                        requested_action=tool_request.arguments,
                        status="approved",
                        requested_by=str(replay_pending.get("requested_by") or "agent"),
                        approved_by="agent",
                        source_refs=list(tool_request.source_refs),
                        resolved_at=utc_now(),
                        metadata={
                            "reason": "approval resumed",
                            "policy_reason": replay_pending.get("metadata", {}).get(
                                "policy_reason"
                            ),
                            **self._selected_call_metadata(tool_request),
                            "request_fingerprint": self._request_fingerprint(tool_request),
                        },
                    )
                else:
                    approval = self.approval_gate.request_or_resume(tool_request)
                    approval = approval.model_copy(
                        update={
                            "metadata": {
                                **approval.metadata,
                                "policy_reason": decision.reason,
                                "matched_rule_ids": list(decision.matched_rule_ids),
                                **self._selected_call_metadata(tool_request),
                                "request_fingerprint": self._request_fingerprint(tool_request),
                            }
                        }
                    )
                event_type = (
                    "approval_granted" if approval.status == "approved" else "approval_pending"
                )
                trace.append(
                    self._trace(
                        step_id=step_id,
                        session_id=request.session_id,
                        sequence=sequence,
                        event_type=event_type,
                        payload={
                            **approval.model_dump(mode="json"),
                            "approval_id": approval.id,
                            "approved_action": approval.requested_action,
                        },
                        approval_id=approval.id,
                    )
                )
                sequence += 1
                if approval.status == "pending":
                    continuation = "pause"
                    break
                should_execute = True
                tool_request = tool_request.model_copy(update={"approval_id": approval.id})
            if should_execute and self.tool_execution_manager is not None:
                tool_result = self.tool_execution_manager.execute(tool_request)
                payload = {
                    **tool_result.model_dump(mode="json"),
                    "approval_id": tool_request.approval_id,
                    **self._selected_call_metadata(tool_request),
                }
                trace.append(
                    self._trace(
                        step_id=step_id,
                        session_id=request.session_id,
                        sequence=sequence,
                        event_type="tool_executed",
                        payload=payload,
                        approval_id=tool_request.approval_id,
                    )
                )
                sequence += 1
                if tool_result.ok:
                    verification = tool_result.verification
                    if not verification and hasattr(self.tool_execution_manager, "verify"):
                        verification = self.tool_execution_manager.verify(
                            tool_request,
                            memory_id=tool_result.result.get("memory_id"),
                            archive_id=tool_result.result.get("archive_id"),
                            attachment_id=tool_result.result.get("attachment_id"),
                            candidate_id=tool_result.result.get("candidate_id"),
                        )
                        tool_result = tool_result.model_copy(update={"verification": verification})
                    if verification:
                        trace.append(
                            self._trace(
                                step_id=step_id,
                                session_id=request.session_id,
                                sequence=sequence,
                                event_type="tool_verified",
                                payload={
                                    "tool_name": tool_request.tool_name,
                                    "ok": verification.get("status") == "verified",
                                    "approval_id": tool_request.approval_id,
                                    **self._selected_call_metadata(tool_request),
                                    "verification": verification,
                                },
                                approval_id=tool_request.approval_id,
                            )
                        )
                        sequence += 1
                    if verification and verification.get("status") != "verified":
                        continue
                    message = self._tool_result_message(
                        session_id=request.session_id,
                        request=tool_request,
                        result=tool_result,
                    )
                    self.store.add_message(message)
                    messages.append(message_to_log_entry(message))
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
            messages=messages,
            trace=trace,
            continuation=continuation,
        )

    def _pending_approval_for_replay(
        self,
        request: ToolExecutionRequest,
    ) -> tuple[dict | None, dict | None]:
        pending = self._find_pending_approval(request.approval_id)
        if pending is None:
            return None, self._replay_error(request, "approval not found")
        if pending.get("session_id") != request.session_id:
            return None, self._replay_error(
                request,
                f"session_id mismatch: expected {pending.get('session_id')}",
            )
        if pending.get("tool_name") != request.tool_name:
            return None, self._replay_error(
                request,
                f"tool_name mismatch: expected {pending.get('tool_name')}",
            )
        if pending.get("requested_action") != request.arguments:
            return None, self._replay_error(request, "requested action mismatch")
        metadata = pending.get("metadata", {})
        expected_tool_call_id = metadata.get("tool_call_id")
        if not request.tool_call_id:
            return None, self._replay_error(request, "tool_call_id missing")
        if expected_tool_call_id != request.tool_call_id:
            return None, self._replay_error(request, "tool_call_id mismatch")
        expected_fingerprint = metadata.get("request_fingerprint")
        if expected_fingerprint is not None and expected_fingerprint != self._request_fingerprint(
            request
        ):
            return None, self._replay_error(request, "request fingerprint mismatch")
        return pending, None

    def _find_pending_approval(self, approval_id: str | None) -> dict | None:
        if not approval_id:
            return None
        with self.store.db() as db:
            rows = db.execute(
                text(
                    """
                select payload_json from trace_events
                where event_type = 'approval_pending'
                order by created_at asc
                """
                )
            ).all()
        for (payload_json,) in rows:
            event_payload = json.loads(payload_json)
            if event_payload.get("approval_id") != approval_id:
                continue
            payload = event_payload.get("payload")
            if isinstance(payload, dict):
                return payload
        return None

    def _approval_already_executed(self, approval_id: str | None) -> bool:
        if not approval_id:
            return False
        with self.store.db() as db:
            rows = db.execute(
                text(
                    """
                select payload_json from trace_events
                where event_type = 'tool_executed'
                order by created_at asc
                """
                )
            ).all()
        for (payload_json,) in rows:
            event_payload = json.loads(payload_json)
            if event_payload.get("approval_id") == approval_id:
                return True
            payload = event_payload.get("payload")
            if isinstance(payload, dict) and payload.get("approval_id") == approval_id:
                return True
        return False

    @staticmethod
    def _replay_error(
        request: ToolExecutionRequest,
        reason: str,
    ) -> dict:
        return {
            "approval_id": request.approval_id,
            "session_id": request.session_id,
            "tool_name": request.tool_name,
            **SimpleAgentStepRunner._selected_call_metadata(request),
            "reason": reason,
            "requested_action": request.arguments,
        }

    @staticmethod
    def _selected_call_metadata(request: ToolExecutionRequest) -> dict[str, Any]:
        return {
            "tool_call_id": request.tool_call_id,
            "selection_origin": request.selection_origin,
            "candidate_reason": request.candidate_reason,
        }

    @staticmethod
    def _request_fingerprint(request: ToolExecutionRequest) -> str:
        payload = {
            "session_id": request.session_id,
            "tool_name": request.tool_name,
            "arguments": request.arguments,
            "tool_call_id": request.tool_call_id,
            "selection_origin": request.selection_origin,
            "candidate_reason": request.candidate_reason,
            "source_refs": [
                source_ref.model_dump(mode="json", exclude={"approval_id"})
                for source_ref in request.source_refs
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _tool_result_message(
        *,
        session_id: str,
        request: ToolExecutionRequest,
        result: ToolExecutionResult,
    ) -> Message:
        memory_id = result.result.get("memory_id")
        attachment_id = result.result.get("attachment_id")
        candidate_id = result.result.get("candidate_id")
        return Message(
            session_id=session_id,
            role=Role.TOOL,
            content=f"tool {request.tool_name} executed",
            metadata={
                "tool_name": request.tool_name,
                "approval_id": request.approval_id,
                **SimpleAgentStepRunner._selected_call_metadata(request),
                "ok": result.ok,
                "result": result.result,
                "verification": result.verification,
                "memory_id": memory_id,
                "attachment_id": attachment_id,
                "candidate_id": candidate_id,
            },
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
