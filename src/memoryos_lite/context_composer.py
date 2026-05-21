from __future__ import annotations

from dataclasses import dataclass, field

from memoryos_lite.config import Settings
from memoryos_lite.retrieval.archival_searcher import ArchivalPassageSearcher
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import Message
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ContextComposerRequest,
    ContextLayerItem,
    ContextPackageV3,
    DiagnosticEvent,
    LayerBudgetDecision,
    SourceRef,
    SourceType,
    message_to_log_entry,
)


@dataclass
class V3ContextComposer:
    store: MemoryStore
    settings: Settings
    tokenizer: TokenEstimator = field(default_factory=TokenEstimator)
    recall_pipeline: RecallPipeline | None = None
    archival_searcher: ArchivalPassageSearcher = field(default_factory=ArchivalPassageSearcher)

    def __post_init__(self) -> None:
        if self.recall_pipeline is None:
            self.recall_pipeline = RecallPipeline(
                store=self.store,
                settings=self.settings,
                tokenizer=self.tokenizer,
            )

    def build(self, request: ContextComposerRequest) -> ContextPackageV3:
        query = request.retrieval_query or request.task
        package = ContextPackageV3(
            session_id=request.session_id,
            task=request.task,
            metadata={"memory_arch": "v3", "retrieval_query": query},
        )
        used = 0
        used = self._try_add_layer(
            package,
            budget=request.budget,
            used=used,
            layer="task",
            items=[
                ContextLayerItem(
                    layer="task",
                    item_id=f"task_{request.session_id}",
                    text=request.task,
                    estimated_tokens=self.tokenizer.count(request.task),
                    metadata={"reason": "task"},
                )
            ],
        )
        used = self._try_add_layer(
            package,
            budget=request.budget,
            used=used,
            layer="core",
            items=self._core_items(),
        )
        used = self._try_add_layer(
            package,
            budget=request.budget,
            used=used,
            layer="recall",
            items=self._recall_items(request, query),
        )
        used = self._try_add_layer(
            package,
            budget=request.budget,
            used=used,
            layer="archival",
            items=self._archival_items(query),
        )
        used = self._try_add_layer(
            package,
            budget=request.budget,
            used=used,
            layer="recent",
            items=self._recent_items(request.session_id),
        )
        package.metadata["estimated_tokens"] = used
        return package

    def _core_items(self) -> list[ContextLayerItem]:
        items: list[ContextLayerItem] = []
        for block in self.store.list_core_memory_blocks():
            text = f"{block.label}: {block.value}"
            items.append(
                ContextLayerItem(
                    layer="core",
                    item_id=block.id,
                    text=text,
                    estimated_tokens=self.tokenizer.count(text),
                    source_refs=list(block.source_refs),
                    metadata={
                        "label": block.label,
                        "description": block.description,
                        "reason": "core_memory_block",
                    },
                )
            )
        return items

    def _recall_items(
        self,
        request: ContextComposerRequest,
        query: str,
    ) -> list[ContextLayerItem]:
        assert self.recall_pipeline is not None
        recall = self.recall_pipeline.build_context(
            session_id=request.session_id,
            task=request.task,
            budget=request.budget,
            retrieval_query=query,
        )
        return [
            ContextLayerItem(
                layer="recall",
                item_id=evidence.message_id,
                text=evidence.text,
                estimated_tokens=evidence.estimated_tokens,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.MESSAGE,
                        source_id=evidence.message_id,
                        session_id=request.session_id,
                    )
                ],
                metadata={
                    "role": evidence.role.value,
                    "reason": evidence.reason,
                    **evidence.metadata,
                },
            )
            for evidence in recall.retrieved_evidence
        ]

    def _archival_items(self, query: str) -> list[ContextLayerItem]:
        passages = self.store.list_archival_passages()
        hits = self.archival_searcher.search(passages, query=query, top_k=5)
        return [
            ContextLayerItem(
                layer="archival",
                item_id=hit.passage.id,
                text=hit.passage.text,
                estimated_tokens=self.tokenizer.count(hit.passage.text),
                source_refs=list(hit.source_refs),
                metadata={
                    "reason": hit.reason,
                    "score": hit.score,
                    "source": hit.source,
                    **hit.metadata,
                },
            )
            for hit in hits
        ]

    def _recent_items(self, session_id: str) -> list[ContextLayerItem]:
        messages = self.store.list_messages(session_id)[-self.settings.recent_message_limit :]
        return [self._message_item(message) for message in messages]

    def _message_item(self, message: Message) -> ContextLayerItem:
        log_entry = message_to_log_entry(message)
        return ContextLayerItem(
            layer="recent",
            item_id=message.id,
            text=message.content,
            estimated_tokens=message.token_count or self.tokenizer.count(message.content),
            source_refs=list(log_entry.source_refs),
            metadata={"role": message.role.value, "reason": "recent_message"},
        )

    def _try_add_layer(
        self,
        package: ContextPackageV3,
        *,
        budget: int,
        used: int,
        layer: str,
        items: list[ContextLayerItem],
    ) -> int:
        layer_used = 0
        dropped: list[str] = []
        requested = sum(item.estimated_tokens for item in items)
        for item in items:
            if used + item.estimated_tokens <= budget:
                package.items.append(item)
                package.diagnostics.append(
                    self._diagnostic(item, included=True, dropped=False)
                )
                used += item.estimated_tokens
                layer_used += item.estimated_tokens
            else:
                dropped.append(item.item_id)
                package.diagnostics.append(
                    self._diagnostic(item, included=False, dropped=True)
                )
        package.budget_decisions.append(
            LayerBudgetDecision(
                layer=layer,  # type: ignore[arg-type]
                requested_tokens=requested,
                allocated_tokens=min(requested, max(0, budget - (used - layer_used))),
                used_tokens=layer_used,
                dropped_item_ids=dropped,
                reason_code="fit" if not dropped else "budget_drop",
            )
        )
        return used

    @staticmethod
    def _diagnostic(
        item: ContextLayerItem,
        *,
        included: bool,
        dropped: bool,
    ) -> DiagnosticEvent:
        diagnostic_layer = "message_log" if item.layer in {"task", "recent"} else item.layer
        return DiagnosticEvent(
            layer=diagnostic_layer,  # type: ignore[arg-type]
            event_type="select",
            item_id=item.item_id,
            reason_code=str(item.metadata.get("reason", item.layer)),
            score=item.metadata.get("score"),  # type: ignore[arg-type]
            included=included,
            dropped=dropped,
            budget_tokens=item.estimated_tokens,
            source_refs=list(item.source_refs),
            metadata=dict(item.metadata),
        )
