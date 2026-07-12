from __future__ import annotations

from dataclasses import dataclass

from memoryos_lite.kernel_contracts import (
    ContextFeedbackType,
    KernelMaintenanceAnalysisResult,
    MaintenanceContextFeedback,
    MaintenanceDecision,
    MaintenanceMemoryProposal,
    MaintenanceSignal,
    MaintenanceSignalType,
)
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    ContextLayerItem,
    DiagnosticEvent,
    KernelTraceEvent,
    SourceRef,
    ToolExecutionRequest,
)


@dataclass
class KernelMaintenanceAnalyzer:
    store: MemoryStore
    dropped_high_value_token_threshold: int = 128

    def analyze(self, request: AgentStepRequest) -> KernelMaintenanceAnalysisResult:
        result = KernelMaintenanceAnalysisResult()
        sequence = 1
        step_id = f"maintenance_{request.session_id}"

        for item in request.context.items:
            if item.layer not in {"recall", "archival", "recent"}:
                continue
            signal = self._signal_from_item(item)
            if signal is None:
                continue
            result.signals.append(signal)
            result.trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="maintenance_signal",
                    payload=signal.model_dump(mode="json"),
                    source_refs=signal.source_refs,
                )
            )
            sequence += 1

            decision, proposal = self._decision_and_proposal(request, item, signal)
            result.decisions.append(decision)
            result.trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="maintenance_decision",
                    payload={
                        "signal_id": signal.signal_id,
                        "decision": decision.model_dump(mode="json"),
                        "source_ids": self._source_ids(signal.source_refs),
                    },
                    source_refs=signal.source_refs,
                )
            )
            sequence += 1
            if proposal is not None:
                result.memory_proposals.append(proposal)
                result.trace.append(
                    self._trace(
                        step_id=step_id,
                        session_id=request.session_id,
                        sequence=sequence,
                        event_type="maintenance_memory_proposal",
                        payload={
                            "signal_id": signal.signal_id,
                            "proposal": proposal.model_dump(mode="json"),
                            "source_ids": self._source_ids(proposal.tool_request.source_refs),
                        },
                        source_refs=proposal.tool_request.source_refs,
                    )
                )
                sequence += 1

        for diagnostic in request.context.diagnostics:
            feedback_signal = self._signal_from_dropped_diagnostic(diagnostic)
            if feedback_signal is None:
                continue
            result.signals.append(feedback_signal)
            feedback = MaintenanceContextFeedback(
                feedback_type="dropped_high_value_evidence",
                suggested_action="review_layer_budget_or_persist",
                source_refs=list(feedback_signal.source_refs),
                metadata={
                    "signal_id": feedback_signal.signal_id,
                    **feedback_signal.metadata,
                },
            )
            result.context_feedback.append(feedback)
            result.trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="maintenance_context_feedback",
                    payload={
                        **feedback.model_dump(mode="json"),
                        "source_ids": self._source_ids(feedback.source_refs),
                    },
                    source_refs=feedback.source_refs,
                )
            )
            sequence += 1
            decision, proposal = self._dropped_signal_archive_decision_and_proposal(
                request,
                feedback_signal,
            )
            result.decisions.append(decision)
            result.trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="maintenance_decision",
                    payload={
                        "signal_id": feedback_signal.signal_id,
                        "decision": decision.model_dump(mode="json"),
                        "source_ids": self._source_ids(feedback_signal.source_refs),
                    },
                    source_refs=feedback_signal.source_refs,
                )
            )
            sequence += 1
            if proposal is not None:
                result.memory_proposals.append(proposal)
                result.trace.append(
                    self._trace(
                        step_id=step_id,
                        session_id=request.session_id,
                        sequence=sequence,
                        event_type="maintenance_memory_proposal",
                        payload={
                            "signal_id": feedback_signal.signal_id,
                            "proposal": proposal.model_dump(mode="json"),
                            "source_ids": self._source_ids(proposal.tool_request.source_refs),
                        },
                        source_refs=proposal.tool_request.source_refs,
                    )
                )
                sequence += 1

        for feedback in self._budget_pressure_feedback(request):
            result.context_feedback.append(feedback)
            result.trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="maintenance_context_feedback",
                    payload={
                        **feedback.model_dump(mode="json"),
                        "source_ids": self._source_ids(feedback.source_refs),
                    },
                    source_refs=feedback.source_refs,
                )
            )
            sequence += 1

        if not result.decisions and not result.context_feedback:
            result.decisions.append(
                MaintenanceDecision(
                    action="noop",
                    reason="no maintenance signals found",
                )
            )
            result.trace.append(
                self._trace(
                    step_id=step_id,
                    session_id=request.session_id,
                    sequence=sequence,
                    event_type="maintenance_decision",
                    payload={
                        "decision": result.decisions[-1].model_dump(mode="json"),
                        "source_ids": [],
                    },
                )
            )
        return result

    def _signal_from_item(self, item: ContextLayerItem) -> MaintenanceSignal | None:
        content = item.text.strip()
        if not content:
            return None
        signal_type: MaintenanceSignalType = (
            "core_promotion_candidate"
            if self._looks_core_worthy(content)
            else "recall_to_archive_candidate"
        )
        if not item.source_refs:
            signal_type = "unsupported_memory_candidate"
        return MaintenanceSignal(
            signal_id=self._signal_id(signal_type, item.item_id),
            signal_type=signal_type,
            source_refs=list(item.source_refs),
            metadata={
                "layer": item.layer,
                "item_id": item.item_id,
                "content": content,
                "estimated_tokens": item.estimated_tokens,
                "reason": str(item.metadata.get("reason", item.layer)),
            },
        )

    def _decision_and_proposal(
        self,
        request: AgentStepRequest,
        item: ContextLayerItem,
        signal: MaintenanceSignal,
    ) -> tuple[MaintenanceDecision, MaintenanceMemoryProposal | None]:
        content = str(signal.metadata.get("content") or "").strip()
        if not signal.source_refs:
            return (
                MaintenanceDecision(
                    action="reject",
                    reason="mutating maintenance proposal requires source_refs",
                    signal_id=signal.signal_id,
                ),
                None,
            )
        if signal.signal_type == "core_promotion_candidate":
            if self._duplicate_pending_core_candidate(content):
                return (
                    MaintenanceDecision(
                        action="defer",
                        reason="duplicate pending core promotion candidate",
                        signal_id=signal.signal_id,
                    ),
                    None,
                )
            if self._duplicate_core_block(content):
                return (
                    MaintenanceDecision(
                        action="defer",
                        reason="duplicate live core memory content",
                        signal_id=signal.signal_id,
                    ),
                    None,
                )
            return (
                MaintenanceDecision(
                    action="propose",
                    reason="source-backed stable preference should become a core candidate",
                    signal_id=signal.signal_id,
                ),
                MaintenanceMemoryProposal(
                    proposal_type="core_promotion_request",
                    signal_id=signal.signal_id,
                    tool_request=ToolExecutionRequest(
                        session_id=request.session_id,
                        tool_name="core_promotion_request",
                        arguments={
                            "content": content,
                            "label": "human",
                            "reason": "kernel maintenance source-backed core proposal",
                            "limit_tokens": 200,
                            "source_layer": item.layer,
                            "confidence": 0.75,
                        },
                        source_refs=list(signal.source_refs),
                        tool_call_id=self._tool_call_id(signal.signal_id),
                        candidate_reason="kernel maintenance core promotion proposal",
                    ),
                ),
            )

        if self._duplicate_archival_passage(content):
            return (
                MaintenanceDecision(
                    action="defer",
                    reason="duplicate archival memory already exists",
                    signal_id=signal.signal_id,
                ),
                None,
            )
        return (
            MaintenanceDecision(
                action="propose",
                reason="source-backed recall evidence should become archival memory",
                signal_id=signal.signal_id,
            ),
            MaintenanceMemoryProposal(
                proposal_type="archive_write",
                signal_id=signal.signal_id,
                tool_request=ToolExecutionRequest(
                    session_id=request.session_id,
                    tool_name="archive_write",
                    arguments={
                        "content": content,
                        "memory_type": "fact",
                        "reason": "kernel maintenance source-backed archive proposal",
                        "source_layer": item.layer,
                    },
                    source_refs=list(signal.source_refs),
                    tool_call_id=self._tool_call_id(signal.signal_id),
                    candidate_reason="kernel maintenance archive write proposal",
                ),
            ),
        )

    def _dropped_signal_archive_decision_and_proposal(
        self,
        request: AgentStepRequest,
        signal: MaintenanceSignal,
    ) -> tuple[MaintenanceDecision, MaintenanceMemoryProposal | None]:
        message = self._message_for_signal_source(request.session_id, signal.source_refs)
        if message is None:
            return (
                MaintenanceDecision(
                    action="reject",
                    reason="source message not found for dropped evidence archive proposal",
                    signal_id=signal.signal_id,
                ),
                None,
            )
        content = message.content.strip()
        if not content:
            return (
                MaintenanceDecision(
                    action="reject",
                    reason="source message content is empty",
                    signal_id=signal.signal_id,
                ),
                None,
            )
        if self._duplicate_archival_passage(content):
            return (
                MaintenanceDecision(
                    action="defer",
                    reason="duplicate archival memory already exists",
                    signal_id=signal.signal_id,
                ),
                None,
            )
        source_layer = str(signal.metadata.get("layer") or "message_log")
        return (
            MaintenanceDecision(
                action="propose",
                reason="source-backed dropped high-value evidence should become archival memory",
                signal_id=signal.signal_id,
            ),
            MaintenanceMemoryProposal(
                proposal_type="archive_write",
                signal_id=signal.signal_id,
                tool_request=ToolExecutionRequest(
                    session_id=request.session_id,
                    tool_name="archive_write",
                    arguments={
                        "content": content,
                        "memory_type": "fact",
                        "reason": (
                            "kernel maintenance source-backed dropped evidence archive proposal"
                        ),
                        "source_layer": source_layer,
                    },
                    source_refs=list(signal.source_refs),
                    tool_call_id=self._tool_call_id(signal.signal_id),
                    candidate_reason=("kernel maintenance dropped evidence archive proposal"),
                ),
            ),
        )

    def _message_for_signal_source(
        self,
        session_id: str,
        source_refs: list[SourceRef],
    ):
        message_source_ids = [
            source_ref.source_id
            for source_ref in source_refs
            if getattr(source_ref.source_type, "value", source_ref.source_type) == "message"
            and (source_ref.session_id is None or source_ref.session_id == session_id)
        ]
        if not message_source_ids:
            return None
        wanted = set(message_source_ids)
        for message in self.store.list_messages(session_id):
            if message.id in wanted:
                return message
        return None

    def _signal_from_dropped_diagnostic(
        self,
        diagnostic: DiagnosticEvent,
    ) -> MaintenanceSignal | None:
        if not diagnostic.dropped or diagnostic.reason_code != "budget_drop":
            return None
        if not diagnostic.source_refs:
            return None
        tokens = diagnostic.budget_tokens or 0
        high_value = tokens >= self.dropped_high_value_token_threshold or "high_value" in str(
            diagnostic.metadata.get("reason", "")
        )
        if not high_value:
            return None
        item_id = diagnostic.item_id or "unknown"
        return MaintenanceSignal(
            signal_id=self._signal_id("dropped_high_value_evidence", item_id),
            signal_type="dropped_high_value_evidence",
            source_refs=list(diagnostic.source_refs),
            metadata={
                "layer": diagnostic.layer,
                "item_id": item_id,
                "budget_tokens": tokens,
                "reason_code": diagnostic.reason_code,
                "event_type": diagnostic.event_type,
                "diagnostic_metadata": dict(diagnostic.metadata),
            },
        )

    def _budget_pressure_feedback(
        self,
        request: AgentStepRequest,
    ) -> list[MaintenanceContextFeedback]:
        feedback: list[MaintenanceContextFeedback] = []
        accounting = self._component_accounting_rows(request.context.metadata)
        component_drop_counts = self._dict_metadata(
            request.context.metadata.get("component_drop_counts")
        )
        for decision in request.context.budget_decisions:
            if decision.layer not in {"recall", "archival", "recent"}:
                continue
            if decision.reason_code != "budget_drop" and not decision.dropped_item_ids:
                continue
            component = decision.layer
            dropped_rows = self._dropped_accounting_rows(
                accounting,
                component=component,
                dropped_item_ids=decision.dropped_item_ids,
            )
            source_refs = self._source_refs_for_dropped_items(
                request,
                dropped_item_ids=decision.dropped_item_ids,
            )
            dropped_source_ids = self._source_ids(source_refs)
            if not dropped_source_ids:
                dropped_source_ids = self._source_ids_from_accounting(dropped_rows)
            feedback_type: ContextFeedbackType = (
                "recall_budget_pressure" if decision.layer == "recall" else "layer_budget_pressure"
            )
            metadata = {
                "layer": decision.layer,
                "component": component,
                "reason_code": decision.reason_code,
                "dropped_item_ids": list(decision.dropped_item_ids),
                "dropped_source_ids": dropped_source_ids,
                "requested_tokens": decision.requested_tokens,
                "allocated_tokens": decision.allocated_tokens,
                "used_tokens": decision.used_tokens,
                "component_drop_count": self._int_metadata(component_drop_counts.get(component)),
                "component_accounting": dropped_rows,
            }
            feedback.append(
                MaintenanceContextFeedback(
                    feedback_type=feedback_type,
                    suggested_action="record_budget_pressure_for_future_context",
                    source_refs=source_refs,
                    metadata=metadata,
                )
            )
        return feedback

    @staticmethod
    def _component_accounting_rows(metadata: dict[str, object]) -> list[dict[str, object]]:
        rows = metadata.get("component_accounting")
        if not isinstance(rows, list):
            return []
        return [dict(row) for row in rows if isinstance(row, dict)]

    @staticmethod
    def _dict_metadata(value: object) -> dict[str, object]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _int_metadata(value: object) -> int:
        return value if isinstance(value, int) else 0

    @staticmethod
    def _dropped_accounting_rows(
        rows: list[dict[str, object]],
        *,
        component: str,
        dropped_item_ids: list[str],
    ) -> list[dict[str, object]]:
        dropped_ids = set(dropped_item_ids)
        return [
            row
            for row in rows
            if row.get("component") == component
            and row.get("reason_code") == "budget_drop"
            and row.get("dropped") is True
            and (not dropped_ids or row.get("item_id") in dropped_ids)
        ]

    @staticmethod
    def _source_refs_for_dropped_items(
        request: AgentStepRequest,
        *,
        dropped_item_ids: list[str],
    ) -> list[SourceRef]:
        dropped_ids = set(dropped_item_ids)
        refs: list[SourceRef] = []
        seen: set[tuple[object, str, str | None]] = set()
        for diagnostic in request.context.diagnostics:
            if diagnostic.item_id not in dropped_ids:
                continue
            if not diagnostic.dropped or diagnostic.reason_code != "budget_drop":
                continue
            for source_ref in diagnostic.source_refs:
                key = (
                    source_ref.source_type,
                    source_ref.source_id,
                    source_ref.session_id,
                )
                if key in seen:
                    continue
                seen.add(key)
                refs.append(source_ref)
        return refs

    @staticmethod
    def _source_ids_from_accounting(rows: list[dict[str, object]]) -> list[str]:
        seen: set[str] = set()
        source_ids: list[str] = []
        for row in rows:
            raw_source_ids = row.get("source_ids")
            if not isinstance(raw_source_ids, list):
                continue
            for source_id in raw_source_ids:
                if not isinstance(source_id, str) or source_id in seen:
                    continue
                seen.add(source_id)
                source_ids.append(source_id)
        return source_ids

    @staticmethod
    def _looks_core_worthy(content: str) -> bool:
        normalized = content.lower()
        return any(
            marker in normalized
            for marker in (
                " prefers ",
                " preference",
                " likes ",
                " wants ",
                " always ",
            )
        )

    def _duplicate_pending_core_candidate(self, content: str) -> bool:
        normalized = self._normalize_content(content)
        for candidate in self.store.list_promotion_candidates(
            status="pending",
            target_layer="core",
        ):
            if self._normalize_content(candidate.content) == normalized:
                return True
        return False

    def _duplicate_core_block(self, content: str) -> bool:
        normalized = self._normalize_content(content)
        return any(
            self._normalize_content(block.value) == normalized
            for block in self.store.list_core_memory_blocks()
        )

    def _duplicate_archival_passage(self, content: str) -> bool:
        normalized = self._normalize_content(content)
        return any(
            self._normalize_content(passage.text) == normalized
            for passage in self.store.list_archival_passages()
        )

    @staticmethod
    def _normalize_content(content: str) -> str:
        return " ".join(content.split()).strip().lower()

    @staticmethod
    def _source_ids(source_refs: list[SourceRef]) -> list[str]:
        seen: set[str] = set()
        source_ids: list[str] = []
        for source_ref in source_refs:
            if source_ref.source_id in seen:
                continue
            seen.add(source_ref.source_id)
            source_ids.append(source_ref.source_id)
        return source_ids

    @staticmethod
    def _signal_id(signal_type: str, item_id: str) -> str:
        safe_item_id = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in item_id)
        return f"msig_{signal_type}_{safe_item_id}"

    @staticmethod
    def _tool_call_id(signal_id: str) -> str:
        return f"toolcall_{signal_id}"

    @staticmethod
    def _trace(
        *,
        step_id: str,
        session_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, object],
        source_refs: list[SourceRef] | None = None,
    ) -> KernelTraceEvent:
        return KernelTraceEvent(
            step_id=step_id,
            session_id=session_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
            source_refs=list(source_refs or []),
        )


__all__ = ["KernelMaintenanceAnalyzer"]
