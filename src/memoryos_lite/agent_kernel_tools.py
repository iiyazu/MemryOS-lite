from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from memoryos_lite.core_memory import CoreMemoryService
from memoryos_lite.memory_lifecycle import MemoryLifecycleService
from memoryos_lite.schemas import new_id, utc_now
from memoryos_lite.store import MemoryStore
from memoryos_lite.store_protocols import PromotionMaintenanceStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ApprovalState,
    ArchivalMemory,
    ArchiveAttachment,
    ArchiveEligibilityScope,
    IdentityScope,
    SourceRef,
    SourceType,
    ToolExecutionRequest,
    ToolExecutionResult,
)


def source_refs_for_tool_request(request: ToolExecutionRequest) -> list[SourceRef]:
    refs = list(request.source_refs)
    if refs and request.approval_id:
        return [
            source_ref.model_copy(update={"approval_id": request.approval_id})
            for source_ref in refs
        ]
    if refs:
        return refs
    if request.approval_id:
        return [
            SourceRef(
                source_type=SourceType.MANUAL,
                source_id=request.approval_id,
                approval_id=request.approval_id,
            )
        ]
    return []


@dataclass
class ArchiveMaintenanceService:
    store: MemoryStore

    def write(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        content = str(request.arguments.get("content") or "").strip()
        if not content:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="archive_write requires content",
            )
        source_refs = source_refs_for_tool_request(request)
        if not source_refs:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="archive_write requires source_refs or approval_id",
            )
        memory = self.store.add_archival_memory(
            ArchivalMemory(
                id=new_id("amem"),
                archive_id=str(request.arguments.get("archive_id") or request.session_id),
                memory_type=str(request.arguments.get("memory_type") or "fact"),  # type: ignore[arg-type]
                content=content,
                source_refs=source_refs,
                metadata={"producer": "agent_kernel", "tool_name": request.tool_name},
            ),
            actor="agent",
            reason=str(request.arguments.get("reason") or "agent kernel archive_write"),
        )
        self._ensure_session(request.session_id)
        self._create_attachment_if_missing(
            archive_id=memory.archive_id or request.session_id,
            scope_id=request.session_id,
            source_refs=source_refs,
            metadata={
                "producer": "agent_kernel",
                "tool_name": request.tool_name,
                "memory_id": memory.id,
            },
        )
        verification = self.verify_archive_write(
            request,
            memory_id=memory.id,
            archive_id=memory.archive_id,
        )
        return ToolExecutionResult(
            tool_name=request.tool_name,
            ok=True,
            result={"memory_id": memory.id, "archive_id": memory.archive_id},
            source_refs=source_refs,
            verification=verification,
        )

    def attach(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        archive_id = str(request.arguments.get("archive_id") or "").strip()
        if not archive_id:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="archive_attach requires archive_id",
            )
        scope_type = str(request.arguments.get("scope_type") or "session")
        scope_id = str(request.arguments.get("scope_id") or request.session_id)
        if scope_type != "session" or scope_id != request.session_id:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="archive_attach requires current session scope",
            )
        source_refs = source_refs_for_tool_request(request)
        if not source_refs:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="archive_attach requires source_refs or approval_id",
            )
        if not self.store.list_archival_passages(archive_id=archive_id):
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="archive_attach requires existing archive passages",
            )
        self._ensure_session(request.session_id)
        attachment = self._create_attachment_if_missing(
            archive_id=archive_id,
            scope_id=request.session_id,
            source_refs=source_refs,
            metadata={"producer": "agent_kernel", "tool_name": request.tool_name},
        )
        verification = self.verify_archive_attach(request, archive_id=archive_id)
        return ToolExecutionResult(
            tool_name=request.tool_name,
            ok=verification["status"] == "verified",
            result={"archive_id": archive_id, "attachment_id": attachment.id},
            source_refs=source_refs,
            verification=verification,
        )

    def verify_archive_write(
        self,
        request: ToolExecutionRequest,
        *,
        memory_id: str | None = None,
        archive_id: str | None = None,
    ) -> dict[str, Any]:
        memory_id = memory_id or str(request.arguments.get("memory_id") or "")
        archive_id = archive_id or str(request.arguments.get("archive_id") or request.session_id)
        passage_id = f"apsg_{memory_id}" if memory_id else None
        history = self.store.list_archival_memory_history(memory_id) if memory_id else []
        passages = self.store.list_archival_passages(archive_id=archive_id)
        attachments = self.store.list_archive_attachments(
            scope_type="session",
            scope_id=request.session_id,
        )
        eligibility = self.store.list_archival_passages_for_scope(
            ArchiveEligibilityScope(session_id=request.session_id)
        )
        eligible_passage_ids = {passage.id for passage in eligibility.eligible_passages}
        passage_found = passage_id is not None and any(
            passage.id == passage_id for passage in passages
        )
        session_attachment_found = any(
            attachment.archive_id == archive_id for attachment in attachments
        )
        eligible_for_session = passage_id is not None and passage_id in eligible_passage_ids
        history_found = bool(history)
        ok = history_found and passage_found and session_attachment_found and eligible_for_session
        return {
            "status": "verified" if ok else "failed",
            "memory_id": memory_id,
            "archive_id": archive_id,
            "passage_id": passage_id,
            "history_found": history_found,
            "passage_found": passage_found,
            "session_attachment_found": session_attachment_found,
            "eligible_for_session": eligible_for_session,
        }

    def verify_archive_attach(
        self,
        request: ToolExecutionRequest,
        *,
        archive_id: str | None = None,
    ) -> dict[str, Any]:
        archive_id = archive_id or str(request.arguments.get("archive_id") or "")
        attachments = self.store.list_archive_attachments(
            scope_type="session",
            scope_id=request.session_id,
        )
        passages = self.store.list_archival_passages(archive_id=archive_id)
        eligibility = self.store.list_archival_passages_for_scope(
            ArchiveEligibilityScope(session_id=request.session_id)
        )
        eligible_passage_ids = [
            passage.id
            for passage in eligibility.eligible_passages
            if passage.archive_id == archive_id
        ]
        attachment_found = any(attachment.archive_id == archive_id for attachment in attachments)
        eligible_archive_found = archive_id in eligibility.eligible_archive_ids
        ok = attachment_found and eligible_archive_found and bool(eligible_passage_ids)
        return {
            "status": "verified" if ok else "failed",
            "archive_id": archive_id,
            "attachment_found": attachment_found,
            "eligible_archive_found": eligible_archive_found,
            "eligible_passage_ids": eligible_passage_ids,
            "passage_count": len(passages),
        }

    def _ensure_session(self, session_id: str) -> None:
        if self.store.get_session(session_id) is not None:
            return
        with self.store.db() as db:
            db.execute(
                text(
                    """
                    insert or ignore into sessions (id, title, created_at)
                    values (:id, :title, :created_at)
                    """
                ),
                {
                    "id": session_id,
                    "title": session_id,
                    "created_at": utc_now(),
                },
            )

    def _create_attachment_if_missing(
        self,
        *,
        archive_id: str,
        scope_id: str,
        source_refs: list[SourceRef],
        metadata: dict[str, Any],
    ) -> ArchiveAttachment:
        for attachment in self.store.list_archive_attachments(
            scope_type="session",
            scope_id=scope_id,
        ):
            if attachment.archive_id == archive_id:
                return attachment
        attachment = ArchiveAttachment(
            id=new_id("aatt"),
            archive_id=archive_id,
            scope_type="session",
            scope_id=scope_id,
            source_refs=source_refs,
            metadata=metadata,
        )
        return self.store.create_archive_attachment(attachment)


@dataclass
class PromotionMaintenanceService:
    store: PromotionMaintenanceStore
    lifecycle: MemoryLifecycleService | None = None

    def __post_init__(self) -> None:
        if self.lifecycle is None:
            self.lifecycle = MemoryLifecycleService(
                self.store,
                CoreMemoryService(self.store, TokenEstimator()),
            )

    def request_core_promotion(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionResult:
        content = str(request.arguments.get("content") or "").strip()
        if not content:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="core_promotion_request requires content",
            )
        source_refs = source_refs_for_tool_request(request)
        if not source_refs:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="core_promotion_request requires source_refs or approval_id",
            )

        before = self._core_mutation_counts()
        label = str(request.arguments.get("label") or "promotion").strip()
        limit_tokens = int(request.arguments.get("limit_tokens") or 200)
        identity_scope = self._identity_scope_for_request(request)
        metadata = {
            "label": label,
            "limit_tokens": limit_tokens,
            "tool_name": request.tool_name,
            "approval_id": request.approval_id,
            "tool_call_id": request.tool_call_id,
            "selection_origin": request.selection_origin,
            "candidate_reason": request.candidate_reason,
            "approval": {
                "id": request.approval_id,
                "tool_name": request.tool_name,
                "requested_action": dict(request.arguments),
            },
            "tool_binding": {
                "session_id": request.session_id,
                "tool_call_id": request.tool_call_id,
            },
            "verification_baseline": before,
        }
        assert self.lifecycle is not None
        candidate = self.lifecycle.create_candidate(
            source_layer=str(request.arguments.get("source_layer") or "archival"),
            target_layer="core",
            operation="promote",
            content=content,
            source_refs=source_refs,
            identity_scope=identity_scope,
            reason=str(request.arguments.get("reason") or "agent kernel core promotion request"),
            confidence=float(request.arguments.get("confidence") or 1.0),
            write_source="explicit_instruction",
            metadata=metadata,
        )
        verification = self.verify_core_promotion_request(
            request,
            candidate_id=candidate.id,
        )
        return ToolExecutionResult(
            tool_name=request.tool_name,
            ok=verification["status"] == "verified",
            result={"candidate_id": candidate.id},
            source_refs=source_refs,
            verification=verification,
        )

    def verify_core_promotion_request(
        self,
        request: ToolExecutionRequest,
        *,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        candidate_id = candidate_id or str(request.arguments.get("candidate_id") or "")
        candidate = self.store.get_promotion_candidate(candidate_id) if candidate_id else None
        after = self._core_mutation_counts()
        before = {}
        if candidate is not None:
            baseline = candidate.metadata.get("verification_baseline")
            if isinstance(baseline, dict):
                before = baseline
        core_block_count_before = int(before.get("core_block_count", after["core_block_count"]))
        core_history_count_before = int(
            before.get("core_history_count", after["core_history_count"])
        )
        candidate_pending = candidate is not None and candidate.status == "pending"
        core_unchanged = (
            core_block_count_before == after["core_block_count"]
            and core_history_count_before == after["core_history_count"]
        )
        ok = candidate_pending and core_unchanged
        return {
            "status": "verified" if ok else "failed",
            "candidate_id": candidate_id,
            "candidate_found": candidate is not None,
            "candidate_pending": candidate_pending,
            "target_layer": candidate.target_layer if candidate is not None else None,
            "operation": candidate.operation if candidate is not None else None,
            "core_block_count_before": core_block_count_before,
            "core_block_count_after": after["core_block_count"],
            "core_history_count_before": core_history_count_before,
            "core_history_count_after": after["core_history_count"],
            "core_unchanged": core_unchanged,
        }

    def apply_core_candidate(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionResult:
        candidate_id = str(request.arguments.get("candidate_id") or "").strip()
        if not candidate_id:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="core_candidate_apply requires candidate_id",
            )
        if not request.approval_id:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="core_candidate_apply requires approved approval replay",
            )
        candidate = self.store.get_promotion_candidate(candidate_id)
        if candidate is None:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="core_candidate_apply requires existing candidate",
            )
        if candidate.target_layer != "core":
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error="core_candidate_apply requires core target candidate",
            )
        if candidate.status not in {"pending", "applied"}:
            return ToolExecutionResult(
                tool_name=request.tool_name,
                ok=False,
                error=f"core_candidate_apply cannot apply {candidate.status} candidate",
            )
        before = self._core_mutation_counts()
        approval = ApprovalState(
            id=request.approval_id,
            session_id=request.session_id,
            tool_name=request.tool_name,
            requested_action=dict(request.arguments),
            status="approved",
            requested_by="agent",
            approved_by="agent",
            source_refs=source_refs_for_tool_request(request),
            resolved_at=utc_now(),
            metadata={
                "reason": "approval resumed",
                "tool_call_id": request.tool_call_id,
                "selection_origin": request.selection_origin,
                "candidate_reason": request.candidate_reason,
            },
        )
        actor = str(request.arguments.get("actor") or "agent")
        assert self.lifecycle is not None
        applied = self.lifecycle.apply_candidate(
            candidate,
            actor=actor,
            approval_state=approval,
        )
        verification = self.verify_core_candidate_apply(
            request,
            candidate_id=applied.id,
            before=before,
            was_already_applied=candidate.status == "applied",
        )
        return ToolExecutionResult(
            tool_name=request.tool_name,
            ok=verification["status"] == "verified",
            result={"candidate_id": applied.id},
            source_refs=list(applied.source_refs),
            verification=verification,
        )

    def verify_core_candidate_apply(
        self,
        request: ToolExecutionRequest,
        *,
        candidate_id: str | None = None,
        before: dict[str, int] | None = None,
        was_already_applied: bool = False,
    ) -> dict[str, Any]:
        candidate_id = candidate_id or str(request.arguments.get("candidate_id") or "")
        candidate = self.store.get_promotion_candidate(candidate_id) if candidate_id else None
        after = self._core_mutation_counts()
        before = before or after
        matching_blocks = [
            block
            for block in self.store.list_core_memory_blocks()
            if block.metadata.get("promotion_candidate_id") == candidate_id
        ]
        candidate_applied = candidate is not None and candidate.status == "applied"
        approval_recorded = (
            candidate is not None
            and candidate.metadata.get("apply_approval_id") == request.approval_id
        )
        source_refs_preserved = (
            candidate is not None
            and bool(candidate.source_refs)
            and bool(matching_blocks)
            and {(ref.source_type, ref.source_id, ref.session_id) for ref in candidate.source_refs}
            <= {
                (ref.source_type, ref.source_id, ref.session_id)
                for block in matching_blocks
                for ref in block.source_refs
            }
        )
        core_mutated = (
            before["core_block_count"] != after["core_block_count"]
            or before["core_history_count"] != after["core_history_count"]
        )
        core_block_found = bool(matching_blocks)
        ok = (
            candidate_applied
            and approval_recorded
            and source_refs_preserved
            and core_block_found
            and (core_mutated or was_already_applied)
        )
        return {
            "status": "verified" if ok else "failed",
            "candidate_id": candidate_id,
            "candidate_found": candidate is not None,
            "candidate_applied": candidate_applied,
            "approval_recorded": approval_recorded,
            "source_refs_preserved": source_refs_preserved,
            "core_block_found": core_block_found,
            "matching_core_block_ids": [block.id for block in matching_blocks],
            "core_block_count_before": before["core_block_count"],
            "core_block_count_after": after["core_block_count"],
            "core_history_count_before": before["core_history_count"],
            "core_history_count_after": after["core_history_count"],
            "core_mutated": core_mutated,
            "was_already_applied": was_already_applied,
        }

    def _identity_scope_for_request(
        self,
        request: ToolExecutionRequest,
    ) -> IdentityScope:
        raw_scope = request.arguments.get("identity_scope")
        if isinstance(raw_scope, dict):
            return IdentityScope.model_validate(raw_scope)
        return IdentityScope(session_id=request.session_id)

    def _core_mutation_counts(self) -> dict[str, int]:
        with self.store.db() as db:
            block_count = int(db.scalar(text("select count(*) from core_memory_blocks")))
            history_count = int(db.scalar(text("select count(*) from core_memory_history")))
        return {
            "core_block_count": block_count,
            "core_history_count": history_count,
        }
