from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from memoryos_lite.schemas import new_id, utc_now
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ApprovalState,
    CoreMemoryBlock,
    MemoryHistoryEvent,
    SourceRef,
)

Actor = Literal["system", "user", "agent", "tool"]


def render_core_memory_blocks(blocks: list[CoreMemoryBlock]) -> str:
    lines = ["[Core Memory]"]
    for block in sorted(blocks, key=lambda b: (b.created_at, b.label, b.id)):
        if block.deleted_at is not None:
            continue
        lines.append(f"- {block.label} ({block.limit_tokens} tokens)")
        lines.append(f"  {block.description}")
        lines.append(f"  {block.value}")
    return "\n".join(lines)


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
            source_refs=refs,
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
    ) -> CoreMemoryBlock:
        refs = self._require_provenance(source_refs, approval_state)
        self._require_actor_and_reason(actor, reason)
        block = self._require_block(block_id)
        return self._persist_update(
            block=block,
            next_value=content,
            operation="update",
            source_refs=refs,
            actor=actor,
            reason=reason,
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
    ) -> CoreMemoryBlock:
        self._ensure_within_limit(next_value, block.limit_tokens)
        updated = block.model_copy(
            update={
                "value": next_value,
                "source_refs": source_refs,
                "updated_at": utc_now(),
            }
        )
        saved = self.store.update_core_memory_block(updated)
        if saved is None:
            raise KeyError(f"core memory block not found: {block.id}")
        event = MemoryHistoryEvent(
            memory_id=block.id,
            memory_type="core_block",
            operation=operation,
            actor=actor,
            reason=reason,
            before=block.model_dump(mode="json"),
            after=saved.model_dump(mode="json"),
            source_refs=source_refs,
        )
        self.store.append_core_memory_history(event)
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
                    source_type="manual",
                    source_id=approval_state.id,
                    approval_id=approval_state.id,
                )
            ]
        raise ValueError("core memory writes require source_refs or approved approval_state")
