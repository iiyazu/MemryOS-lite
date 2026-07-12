from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from memoryos_lite.schemas import new_id, utc_now
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ApprovalState,
    CoreMemoryBlock,
    SourceRef,
    SourceType,
)

Actor = Literal["system", "user", "agent", "tool"]


@dataclass(frozen=True)
class CoreMemoryRender:
    text: str
    metadata_by_block: dict[str, dict[str, object]]


def render_core_memory_blocks(
    blocks: list[CoreMemoryBlock],
    *,
    tokenizer: TokenEstimator,
) -> CoreMemoryRender:
    lines = ["<memory_blocks>"]
    metadata_by_block: dict[str, dict[str, object]] = {}
    for block in sorted(blocks, key=lambda b: (b.created_at, b.label, b.id)):
        if block.deleted_at is not None:
            continue
        tokens_current = tokenizer.count(block.value)
        source_refs = [_format_source_ref(ref) for ref in block.source_refs]
        block_metadata: dict[str, object] = {
            "label": block.label,
            "description": block.description,
            "read_only": block.read_only,
            "tags": list(block.tags),
            "metadata": dict(block.metadata),
            "tokens_current": tokens_current,
            "tokens_limit": block.limit_tokens,
            "source_ref_count": len(block.source_refs),
            "reason": "core_memory_block",
        }
        metadata_by_block[block.id] = block_metadata
        lines.extend(
            [
                f"<{block.label}>",
                "<description>",
                block.description,
                "</description>",
                "<metadata>",
                f"- read_only={str(block.read_only).lower()}",
                f"- tokens_current={tokens_current}",
                f"- tokens_limit={block.limit_tokens}",
                f"- tags={','.join(block.tags)}",
                f"- metadata={_format_metadata(block.metadata)}",
                "- sources=",
            ]
        )
        lines.extend(f"  - {source_ref}" for source_ref in source_refs)
        lines.extend(
            [
                "</metadata>",
                "<value>",
                block.value,
                "</value>",
                f"</{block.label}>",
            ]
        )
    lines.append("</memory_blocks>")
    return CoreMemoryRender(text="\n".join(lines), metadata_by_block=metadata_by_block)


def _format_source_ref(source_ref: SourceRef) -> str:
    source_type = getattr(source_ref.source_type, "value", source_ref.source_type)
    return f"{source_type}:{source_ref.source_id}"


def _format_metadata(metadata: dict[str, Any]) -> str:
    if not metadata:
        return "{}"
    return ",".join(f"{key}={metadata[key]}" for key in sorted(metadata))


@dataclass
class CoreMemoryService:
    store: MemoryStore
    tokenizer: TokenEstimator

    def create_block(
        self,
        *,
        label: str,
        description: str,
        value: str,
        limit_tokens: int,
        source_refs: list[SourceRef],
        actor: Actor,
        reason: str,
        approval_state: ApprovalState | None = None,
        read_only: bool = False,
        tags: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> CoreMemoryBlock:
        refs = self._require_provenance(source_refs, approval_state)
        self._require_actor_and_reason(actor, reason)
        self._ensure_within_limit(value, limit_tokens)
        now = utc_now()
        block = CoreMemoryBlock(
            id=new_id("core"),
            label=label,
            description=description,
            value=value,
            limit_tokens=limit_tokens,
            read_only=read_only,
            tags=list(tags or []),
            source_refs=refs,
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        return self.store.create_core_memory_block(block, actor=actor, reason=reason)

    def append_block(
        self,
        block_id: str,
        addition: str,
        *,
        source_refs: list[SourceRef],
        actor: Actor,
        reason: str,
        approval_state: ApprovalState | None = None,
    ) -> CoreMemoryBlock:
        refs = self._require_provenance(source_refs, approval_state)
        self._require_actor_and_reason(actor, reason)
        block = self._require_block(block_id)
        self._ensure_mutable(block)
        separator = "\n\n"
        next_value = block.value + (separator if block.value else "") + addition
        return self._persist_update(
            block=block,
            next_value=next_value,
            operation="update",
            source_refs=refs,
            actor=actor,
            reason=reason,
        )

    def get_block_by_label(
        self,
        label: str,
        *,
        include_deleted: bool = False,
    ) -> CoreMemoryBlock | None:
        matches = [
            block
            for block in self.store.list_core_memory_blocks(include_deleted=include_deleted)
            if block.label == label
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError(f"multiple live core memory blocks share label {label!r}")
        return matches[0]

    def replace_block(
        self,
        block_id: str,
        *,
        old: str,
        content: str,
        source_refs: list[SourceRef],
        actor: Actor,
        reason: str,
        approval_state: ApprovalState | None = None,
    ) -> CoreMemoryBlock:
        refs = self._require_provenance(source_refs, approval_state)
        self._require_actor_and_reason(actor, reason)
        if not old:
            raise ValueError("replace core memory updates require old")
        block = self._require_block(block_id)
        self._ensure_mutable(block)
        if old not in block.value:
            raise ValueError("replace old value was not found")
        next_value = block.value.replace(old, content, 1)
        return self._persist_update(
            block=block,
            next_value=next_value,
            operation="replace",
            source_refs=refs,
            actor=actor,
            reason=reason,
        )

    def update_block(
        self,
        block_id: str,
        content: str,
        *,
        source_refs: list[SourceRef],
        actor: Actor,
        reason: str,
        approval_state: ApprovalState | None = None,
        metadata: dict[str, object] | None = None,
    ) -> CoreMemoryBlock:
        refs = self._require_provenance(source_refs, approval_state)
        self._require_actor_and_reason(actor, reason)
        block = self._require_block(block_id)
        self._ensure_mutable(block)
        return self._persist_update(
            block=block,
            next_value=content,
            operation="update",
            source_refs=refs,
            actor=actor,
            reason=reason,
            metadata=metadata,
        )

    def delete_block(
        self,
        block_id: str,
        *,
        source_refs: list[SourceRef],
        actor: Actor,
        reason: str,
        approval_state: ApprovalState | None = None,
    ) -> CoreMemoryBlock:
        refs = self._require_provenance(source_refs, approval_state)
        self._require_actor_and_reason(actor, reason)
        block = self._require_block(block_id)
        self._ensure_mutable(block)
        deleted = self.store.delete_core_memory_block(
            block_id,
            source_refs=refs,
            actor=actor,
            reason=reason,
        )
        if deleted is None:
            raise KeyError(f"core memory block not found: {block_id}")
        return deleted

    def _persist_update(
        self,
        *,
        block: CoreMemoryBlock,
        next_value: str,
        operation: Literal["update", "replace"],
        source_refs: list[SourceRef],
        actor: Actor,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> CoreMemoryBlock:
        self._ensure_within_limit(next_value, block.limit_tokens)
        updated = block.model_copy(
            update={
                "value": next_value,
                "source_refs": source_refs,
                "metadata": {**block.metadata, **(metadata or {})},
                "updated_at": utc_now(),
            }
        )
        saved = self.store.update_core_memory_block(
            updated,
            actor=actor,
            reason=reason,
            source_refs=source_refs,
            operation=operation,
        )
        if saved is None:
            raise KeyError(f"core memory block not found: {block.id}")
        return saved

    def _require_block(self, block_id: str) -> CoreMemoryBlock:
        block = self.store.get_core_memory_block(block_id)
        if block is None:
            raise KeyError(f"core memory block not found: {block_id}")
        return block

    def _ensure_within_limit(self, value: str, limit_tokens: int) -> None:
        if self.tokenizer.count(value) > limit_tokens:
            raise ValueError("core memory block exceeds limit_tokens")

    @staticmethod
    def _ensure_mutable(block: CoreMemoryBlock) -> None:
        if block.read_only:
            raise ValueError("read-only core memory block cannot be mutated")

    @staticmethod
    def _require_actor_and_reason(actor: Actor, reason: str) -> None:
        if not actor:
            raise ValueError("core memory writes require actor")
        if not reason:
            raise ValueError("core memory writes require reason")

    @staticmethod
    def _require_provenance(
        source_refs: list[SourceRef],
        approval_state: ApprovalState | None,
    ) -> list[SourceRef]:
        if source_refs:
            return source_refs
        if approval_state is not None and approval_state.status == "approved":
            return [
                SourceRef(
                    source_type=SourceType.MANUAL,
                    source_id=approval_state.id,
                    approval_id=approval_state.id,
                )
            ]
        raise ValueError("core memory writes require source_refs or approved approval_state")
