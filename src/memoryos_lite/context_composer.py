from __future__ import annotations

from dataclasses import dataclass, field

from memoryos_lite.config import Settings
from memoryos_lite.core_memory import render_core_memory_blocks
from memoryos_lite.retrieval.archival_searcher import ArchivalPassageSearcher
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import Message
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ArchiveEligibilityResult,
    ArchiveEligibilityScope,
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
        archival_items, archival_eligibility = self._archival_items(
            request,
            query,
        )
        used = self._try_add_layer(
            package,
            budget=request.budget,
            used=used,
            layer="archival",
            items=archival_items,
        )
        archival_item_ids = {item.item_id for item in archival_items}
        selected_archival_items = [
            item
            for item in package.items
            if item.layer == "archival" and item.item_id in archival_item_ids
        ]
        archival_eligibility = archival_eligibility.model_copy(
            update={
                "selected_passage_ids": [
                    item.item_id for item in selected_archival_items
                ],
                "selected_source_refs": [
                    self._source_ref_summary(source_ref)
                    for item in selected_archival_items
                    for source_ref in item.source_refs
                ],
            }
        )
        package.metadata["archival_eligibility"] = (
            archival_eligibility.diagnostics_payload()
        )
        package.diagnostics.extend(
            self._archival_eligibility_diagnostics(
                archival_eligibility,
                selected_items=selected_archival_items,
            )
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
            rendered = render_core_memory_blocks([block], tokenizer=self.tokenizer)
            metadata = rendered.metadata_by_block[block.id]
            items.append(
                ContextLayerItem(
                    layer="core",
                    item_id=block.id,
                    text=rendered.text,
                    estimated_tokens=self.tokenizer.count(rendered.text),
                    source_refs=list(block.source_refs),
                    metadata=metadata,
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

    def _archival_items(
        self,
        request: ContextComposerRequest,
        query: str,
    ) -> tuple[list[ContextLayerItem], ArchiveEligibilityResult]:
        scope = ArchiveEligibilityScope(
            session_id=request.session_id,
            identity_scope=request.identity_scope,
            source_ids=list(request.source_ids),
            archive_ids=list(request.archive_ids),
        )
        eligibility = self.store.list_archival_passages_for_scope(scope)
        passages = eligibility.eligible_passages
        hits = self.archival_searcher.search(passages, query=query, top_k=5)
        selected_ids = [hit.passage.id for hit in hits]
        selected_id_set = set(selected_ids)
        no_match_ids = [
            passage.id for passage in passages if passage.id not in selected_id_set
        ]
        eligibility = eligibility.model_copy(
            update={
                "no_match_passage_ids": no_match_ids,
            }
        )
        items = [
            ContextLayerItem(
                layer="archival",
                item_id=hit.passage.id,
                text=hit.passage.text,
                estimated_tokens=self.tokenizer.count(hit.passage.text),
                source_refs=list(hit.source_refs),
                metadata={
                    "reason": "archival_selected",
                    "match_reason": hit.reason,
                    "score": hit.score,
                    "source": hit.source,
                    **hit.metadata,
                },
            )
            for hit in hits
        ]
        return items, eligibility

    @staticmethod
    def _source_ref_summary(source_ref: SourceRef) -> dict[str, str | None]:
        return {
            "source_type": getattr(source_ref.source_type, "value", source_ref.source_type),
            "source_id": source_ref.source_id,
            "session_id": source_ref.session_id,
        }

    def _archival_eligibility_diagnostics(
        self,
        eligibility: ArchiveEligibilityResult,
        *,
        selected_items: list[ContextLayerItem],
    ) -> list[DiagnosticEvent]:
        diagnostics: list[DiagnosticEvent] = []
        selected_by_id = {item.item_id: item for item in selected_items}
        for item in selected_items:
            diagnostics.append(
                self._diagnostic(item, included=True, dropped=False).model_copy(
                    update={"event_type": "archival_selected"}
                )
            )
        eligible_by_id = {passage.id: passage for passage in eligibility.eligible_passages}
        for passage_id in eligibility.no_match_passage_ids:
            passage = eligible_by_id[passage_id]
            diagnostics.append(
                DiagnosticEvent(
                    layer="archival",
                    event_type="archival_eligible_no_match",
                    item_id=passage.id,
                    reason_code="archival_no_match",
                    included=False,
                    dropped=False,
                    source_refs=list(passage.source_refs),
                    metadata={
                        "archive_id": passage.archive_id,
                        "source_id": passage.source_id,
                    },
                )
            )
        for passage_id in eligibility.scope_excluded_passage_ids:
            diagnostics.append(
                DiagnosticEvent(
                    layer="archival",
                    event_type="archival_scope_excluded",
                    item_id=passage_id,
                    reason_code="archival_scope_excluded",
                    included=False,
                    dropped=False,
                    metadata={
                        "eligible_archive_ids": list(eligibility.eligible_archive_ids),
                    },
                )
            )
        if (
            not eligibility.eligible_archive_ids
            and not eligibility.scope.source_ids
            and not selected_by_id
        ):
            diagnostics.append(
                DiagnosticEvent(
                    layer="archival",
                    event_type="archival_no_attached_archive",
                    reason_code="archival_no_attached_archive",
                    included=False,
                    dropped=False,
                    metadata={"session_id": eligibility.scope.session_id},
                )
            )
        return diagnostics

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
