from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from memoryos_lite.kernel_analyzer import KernelMaintenanceAnalyzer
from memoryos_lite.kernel_contracts import (
    KernelMaintenanceAnalysisResult,
    KernelMaintenanceExecutionResult,
    MaintenanceContextFeedback,
)
from memoryos_lite.schemas import TraceEvent
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    AgentStepResult,
    ContextPolicyCandidate,
    KernelTraceEvent,
    SourceRef,
    ToolExecutionRequest,
)


@dataclass
class KernelMaintenanceProposalExecutor:
    store: MemoryStore
    runner: object | None = None

    def execute(
        self,
        request: AgentStepRequest,
        analysis: KernelMaintenanceAnalysisResult,
    ) -> KernelMaintenanceExecutionResult:
        step_id = f"maintenance_exec_{request.session_id}"
        trace: list[KernelTraceEvent] = []
        sequence = 1
        trace.append(
            KernelMaintenanceAnalyzer._trace(
                step_id=step_id,
                session_id=request.session_id,
                sequence=sequence,
                event_type="maintenance_executor_started",
                payload={
                    "memory_proposal_count": len(analysis.memory_proposals),
                    "context_feedback_count": len(analysis.context_feedback),
                },
            )
        )
        sequence += 1

        persisted_feedback = 0
        for event in analysis.trace:
            self._persist_trace_event(event)
            if event.event_type == "maintenance_context_feedback":
                persisted_feedback += 1

        created_policy_candidates = 0
        skipped_policy_candidates = 0
        for feedback in analysis.context_feedback:
            candidate_event = self._create_context_policy_candidate_event(
                request,
                feedback,
                step_id=step_id,
                sequence=sequence,
            )
            if candidate_event is None:
                continue
            trace.append(candidate_event)
            self._persist_trace_event(candidate_event)
            sequence += 1
            if candidate_event.event_type == "maintenance_context_policy_candidate_created":
                created_policy_candidates += 1
            elif candidate_event.event_type == "maintenance_duplicate_policy_candidate_skipped":
                skipped_policy_candidates += 1

        unique_requests: list[ToolExecutionRequest] = []
        seen_fingerprints: set[str] = set()
        seen_tool_call_ids: set[str] = set()
        skipped_duplicates = 0
        for proposal in analysis.memory_proposals:
            fingerprint = self._proposal_fingerprint(proposal.tool_request)
            tool_call_id = proposal.tool_request.tool_call_id
            if proposal.tool_request.approval_id is None and self._has_matching_pending_approval(
                proposal.tool_request
            ):
                skipped_duplicates += 1
                skip_event = KernelMaintenanceAnalyzer._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="maintenance_duplicate_proposal_skipped",
                    payload={
                        "signal_id": proposal.signal_id,
                        "proposal_type": proposal.proposal_type,
                        "tool_name": proposal.tool_request.tool_name,
                        "tool_call_id": proposal.tool_request.tool_call_id,
                        "reason": "matching approval is already pending",
                    },
                    source_refs=proposal.tool_request.source_refs,
                )
                trace.append(skip_event)
                self._persist_trace_event(skip_event)
                sequence += 1
                continue
            if fingerprint in seen_fingerprints or (
                tool_call_id is not None and tool_call_id in seen_tool_call_ids
            ):
                skipped_duplicates += 1
                skip_event = KernelMaintenanceAnalyzer._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="maintenance_duplicate_proposal_skipped",
                    payload={
                        "signal_id": proposal.signal_id,
                        "proposal_type": proposal.proposal_type,
                        "tool_name": proposal.tool_request.tool_name,
                        "tool_call_id": proposal.tool_request.tool_call_id,
                        "reason": "duplicate maintenance proposal fingerprint",
                    },
                    source_refs=proposal.tool_request.source_refs,
                )
                trace.append(skip_event)
                self._persist_trace_event(skip_event)
                sequence += 1
                continue
            seen_fingerprints.add(fingerprint)
            if tool_call_id is not None:
                seen_tool_call_ids.add(tool_call_id)
            unique_requests.append(proposal.tool_request)

        agent_step: AgentStepResult | None = None
        if unique_requests:
            agent_step = self._runner().run_step(
                request,
                tool_requests=unique_requests,
            )

        trace.append(
            KernelMaintenanceAnalyzer._trace(
                step_id=step_id,
                session_id=request.session_id,
                sequence=sequence,
                event_type="maintenance_executor_completed",
                payload={
                    "submitted_tool_request_count": len(unique_requests),
                    "skipped_duplicate_proposal_count": skipped_duplicates,
                    "created_policy_candidate_count": created_policy_candidates,
                    "skipped_duplicate_policy_candidate_count": skipped_policy_candidates,
                    "agent_continuation": (
                        agent_step.continuation if agent_step is not None else None
                    ),
                },
            )
        )
        sequence += 1
        self._persist_trace_event(trace[-1])

        return KernelMaintenanceExecutionResult(
            analysis=analysis,
            agent_step=agent_step,
            persisted_feedback_trace_count=persisted_feedback,
            skipped_duplicate_proposal_count=skipped_duplicates,
            skipped_duplicate_policy_candidate_count=skipped_policy_candidates,
            trace=trace,
        )

    def _runner(self):  # type: ignore[no-untyped-def]
        if self.runner is not None:
            return self.runner
        from memoryos_lite.agent_kernel import SimpleAgentStepRunner

        self.runner = SimpleAgentStepRunner(store=self.store)
        return self.runner

    def _persist_trace_event(self, event: KernelTraceEvent) -> None:
        self.store.add_trace(
            TraceEvent(
                session_id=event.session_id,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
        )

    def _create_context_policy_candidate_event(
        self,
        request: AgentStepRequest,
        feedback: MaintenanceContextFeedback,
        *,
        step_id: str,
        sequence: int,
    ) -> KernelTraceEvent | None:
        if not feedback.source_refs:
            return KernelMaintenanceAnalyzer._trace(
                step_id=step_id,
                session_id=request.session_id,
                sequence=sequence,
                event_type="maintenance_context_policy_candidate_rejected",
                payload={
                    "feedback_type": feedback.feedback_type,
                    "suggested_action": feedback.suggested_action,
                    "reason": "context policy candidate requires source_refs",
                    "metadata": feedback.metadata,
                },
            )
        fingerprint = self._feedback_fingerprint(request, feedback)
        existing = self.store.get_context_policy_candidate_by_fingerprint(fingerprint)
        if existing is not None:
            return KernelMaintenanceAnalyzer._trace(
                step_id=step_id,
                session_id=request.session_id,
                sequence=sequence,
                event_type="maintenance_duplicate_policy_candidate_skipped",
                payload={
                    "candidate_id": existing.id,
                    "feedback_type": feedback.feedback_type,
                    "suggested_action": feedback.suggested_action,
                    "fingerprint": fingerprint,
                    "reason": "duplicate context policy candidate fingerprint",
                },
                source_refs=feedback.source_refs,
            )
        metadata = {
            **feedback.metadata,
            "suggested_action": feedback.suggested_action,
            "producer": "kernel_maintenance",
        }
        candidate = self.store.create_context_policy_candidate(
            ContextPolicyCandidate(
                session_id=request.session_id,
                feedback_type=feedback.feedback_type,
                suggested_action=feedback.suggested_action,
                source_refs=list(feedback.source_refs),
                fingerprint=fingerprint,
                metadata=metadata,
            )
        )
        return KernelMaintenanceAnalyzer._trace(
            step_id=step_id,
            session_id=request.session_id,
            sequence=sequence,
            event_type="maintenance_context_policy_candidate_created",
            payload={
                "candidate_id": candidate.id,
                "feedback_type": candidate.feedback_type,
                "policy_type": candidate.policy_type,
                "status": candidate.status,
                "suggested_action": candidate.suggested_action,
                "fingerprint": candidate.fingerprint,
                "source_ids": KernelMaintenanceAnalyzer._source_ids(candidate.source_refs),
            },
            source_refs=candidate.source_refs,
        )

    def _has_matching_pending_approval(self, request: ToolExecutionRequest) -> bool:
        expected_refs = self._source_ref_fingerprint_payload(request.source_refs)
        for trace in self.store.list_traces(request.session_id):
            if trace.event_type != "approval_pending":
                continue
            payload = trace.payload.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("status") != "pending":
                continue
            if payload.get("tool_name") != request.tool_name:
                continue
            if payload.get("requested_action") != request.arguments:
                continue
            metadata = payload.get("metadata")
            if isinstance(metadata, dict):
                pending_tool_call_id = metadata.get("tool_call_id")
                if pending_tool_call_id and pending_tool_call_id != request.tool_call_id:
                    continue
            pending_refs = payload.get("source_refs")
            if not isinstance(pending_refs, list):
                continue
            if self._source_ref_fingerprint_payload_from_json(pending_refs) != expected_refs:
                continue
            return True
        return False

    @staticmethod
    def _proposal_fingerprint(request: ToolExecutionRequest) -> str:
        payload = {
            "session_id": request.session_id,
            "tool_name": request.tool_name,
            "arguments": request.arguments,
            "source_refs": KernelMaintenanceProposalExecutor._source_ref_fingerprint_payload(
                request.source_refs
            ),
            "approval_id": request.approval_id,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _feedback_fingerprint(
        request: AgentStepRequest,
        feedback: MaintenanceContextFeedback,
    ) -> str:
        payload = {
            "session_id": request.session_id,
            "feedback_type": feedback.feedback_type,
            "suggested_action": feedback.suggested_action,
            "source_refs": KernelMaintenanceProposalExecutor._source_ref_fingerprint_payload(
                feedback.source_refs
            ),
            "metadata": feedback.metadata,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _source_ref_fingerprint_payload(
        source_refs: list[SourceRef],
    ) -> list[dict[str, object]]:
        return [
            source_ref.model_dump(mode="json", exclude={"approval_id"})
            for source_ref in source_refs
        ]

    @staticmethod
    def _source_ref_fingerprint_payload_from_json(
        source_refs: list[object],
    ) -> list[dict[str, object]]:
        payloads: list[dict[str, object]] = []
        for source_ref in source_refs:
            if not isinstance(source_ref, dict):
                continue
            payload = dict(source_ref)
            payload.pop("approval_id", None)
            payloads.append(payload)
        return payloads


__all__ = ["KernelMaintenanceProposalExecutor"]
