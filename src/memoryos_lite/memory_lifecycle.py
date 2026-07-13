from __future__ import annotations

from dataclasses import dataclass

from memoryos_lite.core_memory import CoreMemoryService
from memoryos_lite.schemas import new_id, utc_now
from memoryos_lite.store_protocols import MemoryLifecycleStore
from memoryos_lite.v3_contracts import (
    ApprovalState,
    ArchivalMemory,
    IdentityScope,
    PromotionCandidate,
    SourceRef,
)


@dataclass
class MemoryLifecycleService:
    store: MemoryLifecycleStore
    core_memory: CoreMemoryService | None = None

    def create_candidate(
        self,
        *,
        source_layer: str,
        target_layer: str,
        operation: str,
        content: str,
        source_refs: list[SourceRef],
        identity_scope: IdentityScope | None,
        reason: str,
        confidence: float,
        write_source: str,
        metadata: dict[str, object] | None = None,
    ) -> PromotionCandidate:
        if not source_refs:
            raise ValueError("promotion candidates require source_refs")
        candidate = PromotionCandidate(
            id=new_id("pcand"),
            source_layer=source_layer,  # type: ignore[arg-type]
            target_layer=target_layer,  # type: ignore[arg-type]
            operation=operation,  # type: ignore[arg-type]
            content=content,
            source_refs=list(source_refs),
            identity_scope=identity_scope,
            reason=reason,
            confidence=confidence,
            write_source=write_source,  # type: ignore[arg-type]
            metadata=metadata or {},
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        return self.store.create_promotion_candidate(candidate)

    def apply_candidate(
        self,
        candidate: PromotionCandidate,
        *,
        actor: str = "system",
        approval_state: ApprovalState | None = None,
    ) -> PromotionCandidate:
        if candidate.status == "applied":
            return candidate

        applied_metadata = dict(candidate.metadata)
        applied_metadata["applied_by"] = actor
        if approval_state is not None:
            applied_metadata["apply_approval_id"] = approval_state.id

        if candidate.target_layer == "core":
            if approval_state is None or approval_state.status != "approved":
                raise ValueError("core promotion requires approved approval_state")
            if self.core_memory is None:
                raise ValueError("core memory service is required for core promotion")
            label = str(candidate.metadata.get("label") or "promotion")
            provenance = {
                **candidate.metadata,
                "promotion_candidate_id": candidate.id,
                "approval_id": approval_state.id,
            }
            existing = self.core_memory.get_block_by_label(label)
            if existing is None:
                self.core_memory.create_block(
                    label=label,
                    description=candidate.reason,
                    value=candidate.content,
                    limit_tokens=int(candidate.metadata.get("limit_tokens", 200)),
                    source_refs=list(candidate.source_refs),
                    actor=actor,  # type: ignore[arg-type]
                    reason=candidate.reason,
                    approval_state=approval_state,
                    metadata=provenance,
                )
            else:
                self.core_memory.update_block(
                    existing.id,
                    candidate.content,
                    source_refs=list(candidate.source_refs),
                    actor=actor,  # type: ignore[arg-type]
                    reason=candidate.reason,
                    approval_state=approval_state,
                    metadata=provenance,
                )
            return self._mark_candidate_applied(
                candidate,
                metadata=applied_metadata,
            )

        memory = ArchivalMemory(
            id=candidate.id,
            archive_id=candidate.metadata.get("archive_id"),
            memory_type="knowledge",
            content=candidate.content,
            identity_scope=candidate.identity_scope,
            source_refs=list(candidate.source_refs),
            metadata={
                "promotion_candidate_id": candidate.id,
                **candidate.metadata,
            },
        )
        self.store.add_archival_memory(memory, actor=actor, reason=candidate.reason)
        return self._mark_candidate_applied(candidate, metadata=applied_metadata)

    def _mark_candidate_applied(
        self,
        candidate: PromotionCandidate,
        *,
        metadata: dict[str, object],
    ) -> PromotionCandidate:
        applied = candidate.model_copy(
            update={
                "status": "applied",
                "metadata": metadata,
                "updated_at": utc_now(),
            }
        )
        persisted = self.store.update_promotion_candidate_status(
            applied.id,
            status="applied",
            metadata=applied.metadata,
        )
        return persisted or applied


def recall_to_archival_candidate(
    content: str,
    *,
    source_refs: list[SourceRef],
    archive_id: str,
    reason: str,
    confidence: float,
) -> PromotionCandidate:
    return PromotionCandidate(
        source_layer="recall",
        target_layer="archival",
        operation="add",
        content=content,
        source_refs=source_refs,
        identity_scope=IdentityScope(archive_id=archive_id),
        reason=reason,
        confidence=confidence,
        write_source="message_extraction",
        metadata={"archive_id": archive_id},
    )


def archival_to_core_candidate(
    content: str,
    *,
    source_refs: list[SourceRef],
    reason: str,
    confidence: float,
    label: str,
    limit_tokens: int,
) -> PromotionCandidate:
    return PromotionCandidate(
        source_layer="archival",
        target_layer="core",
        operation="promote",
        content=content,
        source_refs=source_refs,
        identity_scope=None,
        reason=reason,
        confidence=confidence,
        write_source="sleep_consolidation",
        metadata={"label": label, "limit_tokens": limit_tokens},
    )


__all__ = [
    "MemoryLifecycleService",
    "archival_to_core_candidate",
    "recall_to_archival_candidate",
]
