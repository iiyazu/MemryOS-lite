from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from functools import wraps
from typing import Any

from sqlalchemy.exc import IntegrityError

from memoryos_lite.archive_rag import (
    ArchiveRAGDiagnostic,
    ArchiveRAGIngestRequest,
    MemoryOSArchiveRAG,
)
from memoryos_lite.budget import DynamicBudget
from memoryos_lite.config import Settings, get_settings
from memoryos_lite.context_composer import V3ContextComposer
from memoryos_lite.curator import (
    Curator,
    CuratorLLM,
    build_advisory_v2_items,
    build_curator_llm,
)
from memoryos_lite.curator.curate import CurateRequest, CurateResponse
from memoryos_lite.observability import (
    current_observability_context,
    log_event,
    observability_context,
    timed_core_operation,
)
from memoryos_lite.retrieval import EmbeddingClient
from memoryos_lite.retrieval.archival_searcher import ArchivalPassageSearcher
from memoryos_lite.retrieval.archival_vector import (
    ArchivalEmbeddingConfig,
    ArchivalVectorIndex,
    LocalArchivalVectorStore,
)
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.retrieval.supersede import SupersededQuote, superseded_quotes
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveAttachmentResponse,
    ArchiveDiagnosticResponse,
    ArchiveDocumentIngestRequest,
    ArchiveDocumentIngestResponse,
    ArchiveSourceRefPayload,
    ContextEvidence,
    ContextPackage,
    IngestResponse,
    Message,
    MessageCreate,
    Role,
    Session,
    TraceEvent,
    new_id,
)
from memoryos_lite.store import MemoryStore, create_store
from memoryos_lite.tokenizer import TokenEstimator
from memoryos_lite.v3_contracts import (
    ArchiveAttachment,
    ContextComposerRequest,
    ContextLayerItem,
    ContextPackageV3,
    IdentityScope,
    SourceRef,
)

__all__ = ["MemoryOSService"]

logger = logging.getLogger(__name__)


class CurateUnavailableError(RuntimeError):
    """``/curate`` cannot run here; ``args[0]`` is a stable reason code."""

    @property
    def reason_code(self) -> str:
        return str(self.args[0])


def _instrument_engine_operation(operation: str):  # type: ignore[no-untyped-def]
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            raw_session_id = kwargs.get("session_id")
            session_id = (
                str(raw_session_id)
                if raw_session_id is not None
                else str(args[0])
                if args and isinstance(args[0], str)
                else None
            )
            with (
                observability_context(session_id=session_id),
                timed_core_operation(
                    component="engine",
                    operation=operation,
                    logger=logger,
                    session_id=session_id,
                ),
            ):
                return func(self, *args, **kwargs)

        return wrapper

    return decorator


class MemoryOSService:
    def __init__(
        self,
        store: MemoryStore | None = None,
        settings: Settings | None = None,
        embedding_client: EmbeddingClient | None = None,
        curator: Curator | None = None,
        curate_llm: CuratorLLM | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._curate_llm = curate_llm
        self.store = store or create_store(self.settings)
        self.tokenizer = TokenEstimator()
        self.embedding_client = embedding_client or self._default_embedding_client()
        archival_vector_index: ArchivalVectorIndex | None = None
        embedding_client_for_archival = self.embedding_client
        archival_embedding_dim = getattr(embedding_client_for_archival, "dim", None)
        if (
            self.settings.memoryos_archival_vector_enabled
            and embedding_client_for_archival is not None
            and isinstance(archival_embedding_dim, int)
            and archival_embedding_dim > 0
        ):
            archival_vector_index = ArchivalVectorIndex(
                embedding_client=embedding_client_for_archival,
                vector_store=LocalArchivalVectorStore(
                    dim=archival_embedding_dim,
                ),
                config=ArchivalEmbeddingConfig(
                    provider=self.settings.memoryos_embedding_provider,
                    model=self.settings.memoryos_embedding_model,
                    dim=archival_embedding_dim,
                ),
            )
        self.archival_searcher = ArchivalPassageSearcher(
            vector_index=archival_vector_index,
            passage_loader=self.store.get_archival_passages_by_ids,
        )
        self.dynamic_budget = DynamicBudget(self.settings, self.tokenizer)
        self.recall_pipeline = RecallPipeline(
            store=self.store,
            settings=self.settings,
            tokenizer=self.tokenizer,
            embedding_client=self.embedding_client,
        )
        self.v3_context_composer = V3ContextComposer(
            store=self.store,
            settings=self.settings,
            tokenizer=self.tokenizer,
            recall_pipeline=self.recall_pipeline,
            archival_searcher=self.archival_searcher,
        )
        if curator is not None:
            self.curator: Curator | None = curator
        elif self.settings.memoryos_curator_enabled:
            llm = None
            try:
                llm = build_curator_llm(self.settings)
            except Exception:
                # A missing optional remote stack degrades the curator; the
                # service keeps its non-curator behavior.
                llm = None
            self.curator = Curator(store=self.store, settings=self.settings, llm=llm)
        else:
            self.curator = None

    def _archive_rag(self) -> MemoryOSArchiveRAG:
        return MemoryOSArchiveRAG(self.store)

    def _source_refs_from_payloads(
        self,
        payloads: list[ArchiveSourceRefPayload],
    ) -> list[SourceRef]:
        return [SourceRef.model_validate(payload.model_dump(mode="json")) for payload in payloads]

    @staticmethod
    def _archive_content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _archive_identity_metadata(request: ArchiveDocumentIngestRequest) -> dict[str, str]:
        identity = request.identity
        if identity.kind == "archive":
            return {"identity_kind": "archive", "archive_id": identity.archive_id}
        if identity.kind == "source":
            metadata = {"identity_kind": "source", "source_id": identity.source_id}
            if identity.file_id is not None:
                metadata["file_id"] = identity.file_id
            return metadata
        return {"identity_kind": "file", "file_id": identity.file_id}

    @staticmethod
    def _archive_diagnostic_response(
        diagnostic: ArchiveRAGDiagnostic | ArchiveDiagnosticResponse,
    ) -> ArchiveDiagnosticResponse:
        if isinstance(diagnostic, ArchiveDiagnosticResponse):
            return diagnostic
        return ArchiveDiagnosticResponse(
            event_type=diagnostic.event_type,
            reason_code=diagnostic.reason_code,
            item_id=diagnostic.item_id,
            metadata=dict(diagnostic.metadata),
        )

    def ingest_archive_document(
        self,
        request: ArchiveDocumentIngestRequest,
    ) -> ArchiveDocumentIngestResponse:
        existing = self.store.get_archival_document(request.document_id)
        identity_metadata = self._archive_identity_metadata(request)
        content_hash = self._archive_content_hash(request.content)
        if existing is not None:
            existing_hash = str(existing.metadata.get("content_hash") or "")
            existing_identity = {
                key: str(existing.metadata[key])
                for key in identity_metadata
                if key in existing.metadata
            }
            if (
                existing.text == request.content
                and existing_hash == content_hash
                and existing_identity == identity_metadata
            ):
                chunks = self.store.list_archival_chunks(document_id=existing.id)
                passages = [
                    passage
                    for passage in self.store.list_archival_passages()
                    if passage.document_id == existing.id
                ]
                return ArchiveDocumentIngestResponse(
                    document_id=existing.id,
                    chunk_ids=[chunk.id for chunk in chunks],
                    passage_ids=[passage.id for passage in passages],
                    diagnostics=[
                        ArchiveDiagnosticResponse(
                            event_type="archive_ingest_replayed",
                            reason_code="archive_ingest_idempotent_replay",
                            item_id=existing.id,
                            metadata={"content_hash": content_hash},
                        )
                    ],
                )
            raise ValueError(f"archive document conflict: {request.document_id}")

        identity = request.identity
        archive_id = identity.archive_id if identity.kind == "archive" else None
        if identity.kind == "source":
            source_id = identity.source_id
            file_id = identity.file_id
        elif identity.kind == "file":
            source_id = None
            file_id = identity.file_id
        else:
            source_id = None
            file_id = None
        metadata = {
            **request.metadata,
            **identity_metadata,
            "content_hash": content_hash,
        }
        result = self._archive_rag().ingest(
            ArchiveRAGIngestRequest(
                document_id=request.document_id,
                archive_id=archive_id,
                title=request.title,
                content=request.content,
                source_refs=self._source_refs_from_payloads(request.source_refs),
                source_id=source_id,
                file_id=file_id,
                tags=list(request.tags),
                metadata=metadata,
                producer=request.producer,
            )
        )
        return ArchiveDocumentIngestResponse(
            document_id=result.document.id,
            chunk_ids=[chunk.id for chunk in result.chunks],
            passage_ids=[passage.id for passage in result.passages],
            diagnostics=[
                self._archive_diagnostic_response(diagnostic) for diagnostic in result.diagnostics
            ],
        )

    def attach_archive(
        self,
        request: ArchiveAttachmentRequest,
    ) -> ArchiveAttachmentResponse:
        attachment = self.store.create_archive_attachment(
            ArchiveAttachment(
                id=new_id("aatt"),
                archive_id=request.archive_id,
                scope_type=request.scope_type,
                scope_id=request.scope_id,
                source_refs=self._source_refs_from_payloads(request.source_refs),
                metadata=dict(request.metadata),
            )
        )
        passage_count = len(self.store.list_archival_passages(archive_id=request.archive_id))
        diagnostics: list[ArchiveDiagnosticResponse] = []
        if passage_count == 0:
            diagnostics.append(
                ArchiveDiagnosticResponse(
                    event_type="archive_attachment_empty",
                    reason_code="archive_has_no_passages",
                    item_id=request.archive_id,
                )
            )
        return ArchiveAttachmentResponse(
            attachment_id=attachment.id,
            archive_id=attachment.archive_id,
            scope_type=attachment.scope_type,
            scope_id=attachment.scope_id,
            passage_count=passage_count,
            diagnostics=diagnostics,
        )

    def _default_embedding_client(self) -> EmbeddingClient | None:
        provider = self.settings.memoryos_embedding_provider.strip().lower()
        if provider == "fastembed":
            try:
                from memoryos_lite.retrieval.providers.fastembed_client import (
                    FastEmbedClient,
                )

                return FastEmbedClient()
            except Exception:
                return None
        return None

    def create_session(self, title: str) -> Any:
        with timed_core_operation(
            component="engine",
            operation="create_session",
            logger=logger,
            log_success=True,
        ):
            session = self.store.create_session(title)
            self.trace(session.id, "session_created", {"title": title})
            log_event(
                logger,
                logging.INFO,
                "session_created",
                session_id=session.id,
            )
            return session

    def list_curated_advisories(self, session_id: str) -> list[dict[str, object]]:
        """Project curated memories into advisory v2 items for the host."""

        self._require_session(session_id)
        rows = self.store.list_curated_memories(session_id, limit=32)
        superseded_ids = sorted({row.supersedes_id for row in rows if row.supersedes_id})
        superseded_rows = self.store.get_curated_memories_by_ids(superseded_ids)
        return build_advisory_v2_items(rows, superseded_rows)

    def superseded_marks(self, session_id: str) -> list[SupersededQuote]:
        """Quotes that ground only superseded curated memories of this session."""

        self._require_session(session_id)
        return superseded_quotes(self.store.list_curated_memories(session_id, limit=64))

    def evidence_marks(
        self,
        session_id: str,
        requested: Sequence[SupersededQuote] = (),
    ) -> list[SupersededQuote]:
        """Host-sent marks plus, when enabled, this session's own superseded quotes."""

        marks = list(requested)
        if self.settings.memoryos_demote_superseded:
            marks.extend(self.superseded_marks(session_id))
        return marks

    def _json_llm(self) -> CuratorLLM:
        """The JSON-mode LLM for ``/curate``, built on first use."""

        llm = self._curate_llm
        if llm is None and self.curator is not None:
            llm = self.curator.llm
        if llm is None:
            if not self.settings.chat_api_key:
                raise CurateUnavailableError("curator_llm_key_missing")
            try:
                llm = build_curator_llm(self.settings)
            except Exception as exc:
                raise CurateUnavailableError("curator_llm_init_error") from exc
            self._curate_llm = llm
        if llm is None:
            raise CurateUnavailableError("curator_llm_key_missing")
        return llm

    def curate(self, request: CurateRequest) -> CurateResponse:
        """Stateless module curation (``POST /curate``); see ``curator.curate``.

        Raises :class:`CurateUnavailableError` when no LLM or no LangGraph runtime
        is available, and lets :class:`CuratorLLMError` through on provider errors.
        """

        llm = self._json_llm()
        try:
            from memoryos_lite.curator.graph import run_curate
        except ImportError as exc:
            raise CurateUnavailableError("curate_requires_langgraph") from exc
        with timed_core_operation(component="engine", operation="curate", logger=logger):
            response = run_curate(request, llm)
        log_event(
            logger,
            logging.INFO,
            "curate_completed",
            scope_id=request.scope_id,
            window=len(request.window),
            memories=len(response.memories),
            unaccounted=len(response.unaccounted),
            repairs=response.diagnostics.repairs,
        )
        return response

    def curator_status(self) -> dict[str, object]:
        """Report curator state without ever exposing provider secrets."""

        if self.curator is not None:
            return self.curator.status()
        return {
            "enabled": False,
            "state": "disabled",
            "reason_code": "curator_disabled",
            "model": self.settings.chat_model,
            "counters": {
                "sessions": 0,
                "runs": 0,
                "proposals": 0,
                "rejected_grounding": 0,
                "rejected_schema": 0,
                "llm_errors": 0,
            },
        }

    def _ensure_recall_index(self, session_id: str) -> None:
        """Backfill derived recall rows after an ingest or its replay.

        Message durability and derived episode indexing are intentionally
        separate transactions.  If a process dies after the message commit,
        the next idempotent retry must repair the missing index rather than
        returning a replay while leaving recall permanently incomplete.
        """
        created = self.store.ensure_episodes_for_session(session_id)
        if created:
            self.trace(session_id, "episode_indexed", {"created": created})

    def ingest(self, session_id: str, request: MessageCreate) -> IngestResponse:
        with (
            observability_context(session_id=session_id),
            timed_core_operation(
                component="engine",
                operation="ingest",
                logger=logger,
                session_id=session_id,
            ),
        ):
            self._require_session(session_id)
            if request.external_id is not None:
                existing = self.store.get_message_by_external_id(
                    session_id,
                    request.external_id,
                )
                if existing is not None:
                    expected = {
                        "role": request.role.value,
                        "content": request.content,
                        "metadata": request.metadata,
                    }
                    actual = {
                        "role": existing.role.value,
                        "content": existing.content,
                        "metadata": existing.metadata,
                    }
                    if json.dumps(expected, ensure_ascii=False, sort_keys=True) != json.dumps(
                        actual,
                        ensure_ascii=False,
                        sort_keys=True,
                    ):
                        raise ValueError(
                            "external_id conflict: request differs from stored message"
                        )
                    self._ensure_recall_index(session_id)
                    token_count = self.store.session_token_count(session_id)
                    should_page = token_count >= self.settings.rot_safe_budget
                    return IngestResponse(
                        message=existing,
                        should_page=should_page,
                        session_token_count=token_count,
                        replayed=True,
                    )
            message = Message(
                session_id=session_id,
                role=request.role,
                content=request.content,
                external_id=request.external_id,
                metadata=request.metadata,
                token_count=self.tokenizer.count(request.content),
            )
            try:
                self.store.add_message(message)
            except IntegrityError:
                # A unique (session_id, external_id) index arbitrates two
                # first-writers racing on the same idempotency key.  Re-read
                # the winner and apply the same replay/conflict contract as a
                # non-racing request; never leak a SQLite IntegrityError.
                if request.external_id is None:
                    raise
                existing = self.store.get_message_by_external_id(
                    session_id,
                    request.external_id,
                )
                if existing is None:
                    raise
                expected = {
                    "role": request.role.value,
                    "content": request.content,
                    "metadata": request.metadata,
                }
                actual = {
                    "role": existing.role.value,
                    "content": existing.content,
                    "metadata": existing.metadata,
                }
                if json.dumps(expected, ensure_ascii=False, sort_keys=True) != json.dumps(
                    actual,
                    ensure_ascii=False,
                    sort_keys=True,
                ):
                    raise ValueError(
                        "external_id conflict: request differs from stored message"
                    ) from None
                self._ensure_recall_index(session_id)
                token_count = self.store.session_token_count(session_id)
                should_page = token_count >= self.settings.rot_safe_budget
                return IngestResponse(
                    message=existing,
                    should_page=should_page,
                    session_token_count=token_count,
                    replayed=True,
                )
            self._ensure_recall_index(session_id)
            token_count = self.store.session_token_count(session_id)
            should_page = token_count >= self.settings.rot_safe_budget
            self.trace(
                session_id,
                "message_ingested",
                {
                    "message_id": message.id,
                    "token_count": message.token_count,
                    "should_page": should_page,
                },
            )
            return IngestResponse(
                message=message,
                should_page=should_page,
                session_token_count=token_count,
                replayed=False,
            )

    @_instrument_engine_operation("build_context")
    def build_context(
        self,
        session_id: str,
        task: str,
        budget: int | None = None,
        retrieval_query: str | None = None,
        include_global_core: bool = False,
    ) -> ContextPackage:
        """Compose bounded context with the v3 composer over v2 recall.

        ``include_global_core`` is accepted for request compatibility; there is
        no global core layer. Failures propagate; the host decides how to degrade.
        """
        self._require_session(session_id)
        effective_budget = (
            min(budget, self.settings.hard_limit)
            if budget is not None
            else self.dynamic_budget.compute(self.store.list_messages(session_id), task)
        )
        v3_package = self.v3_context_composer.build(
            ContextComposerRequest(
                session_id=session_id,
                task=task,
                budget=effective_budget,
                retrieval_query=retrieval_query,
                identity_scope=IdentityScope(session_id=session_id),
            )
        )
        package = self._context_package_from_v3(v3_package)
        self.trace(
            session_id,
            "context_built",
            {
                "task": task,
                "budget": effective_budget,
                "budget_source": "explicit" if budget is not None else "dynamic",
                "estimated_tokens": package.estimated_tokens,
                "memory_arch": "v3",
                "v3_layer_counts": package.metadata["v3_layer_counts"],
                "v3_budget_decisions": package.metadata["v3_budget_decisions"],
                "v3_component_accounting": package.metadata["v3_component_accounting"],
                "v3_final_context_trace": package.metadata["v3_final_context_trace"],
                "v3_component_token_totals": package.metadata["v3_component_token_totals"],
                "v3_component_drop_counts": package.metadata["v3_component_drop_counts"],
                "locomo_neighbor_diagnostics": package.metadata["locomo_neighbor_diagnostics"],
            },
        )
        return package

    def _context_package_from_v3(self, v3_package: ContextPackageV3) -> ContextPackage:
        package = ContextPackage(
            session_id=v3_package.session_id,
            task=v3_package.task,
            task_tokens=self.tokenizer.count(v3_package.task),
        )
        layer_counts: dict[str, int] = {}
        messages_by_id = {
            message.id: message for message in self.store.list_messages(v3_package.session_id)
        }
        for item in v3_package.items:
            layer_counts[item.layer] = layer_counts.get(item.layer, 0) + 1
            if item.layer == "core":
                package.pinned_core.append(item.text)
            elif item.layer == "recent":
                message = messages_by_id.get(item.item_id)
                if message is not None:
                    package.recent_messages.append(message)
            elif item.layer in {"recall", "archival", "fallback"}:
                message_ref = next(
                    (
                        ref
                        for ref in item.source_refs
                        if getattr(ref.source_type, "value", ref.source_type) == "message"
                    ),
                    None,
                )
                package.retrieved_evidence.append(
                    ContextEvidence(
                        message_id=message_ref.source_id if message_ref else item.item_id,
                        text=item.text,
                        role=Role.USER,
                        reason=str(item.metadata.get("reason", item.layer)),
                        estimated_tokens=item.estimated_tokens,
                        metadata={
                            "origin": item.layer,
                            "v3_item_id": item.item_id,
                            **item.metadata,
                        },
                    )
                )
        package.estimated_tokens = int(
            v3_package.metadata.get(
                "estimated_tokens",
                sum(item.estimated_tokens for item in v3_package.items),
            )
        )
        package.candidate_budget_dropped = sum(
            len(decision.dropped_item_ids) for decision in v3_package.budget_decisions
        )
        recall_candidate_message_ids = self._v3_source_ids(
            v3_package.items,
            layers={"recall"},
        )
        planned_evidence_message_ids = self._v3_source_ids(
            v3_package.items,
            layers={"recall", "archival"},
        )
        indexed_source_ids = self._v3_source_ids(
            v3_package.items,
            layers={"recall", "archival", "recent"},
        )
        package.metadata.update(
            {
                "memory_arch": "v3",
                "v3_context": v3_package.model_dump(mode="json"),
                "v3_layer_counts": layer_counts,
                "v3_budget_decisions": [
                    decision.model_dump(mode="json") for decision in v3_package.budget_decisions
                ],
                "v3_diagnostics": [
                    diagnostic.model_dump(mode="json") for diagnostic in v3_package.diagnostics
                ],
                "v3_component_accounting": v3_package.metadata.get(
                    "component_accounting",
                    [],
                ),
                "v3_final_context_trace": v3_package.metadata.get(
                    "final_context_trace",
                    [],
                ),
                "v3_component_token_totals": v3_package.metadata.get(
                    "component_token_totals",
                    {},
                ),
                "v3_component_included_counts": v3_package.metadata.get(
                    "component_included_counts",
                    {},
                ),
                "v3_component_drop_counts": v3_package.metadata.get(
                    "component_drop_counts",
                    {},
                ),
                "locomo_neighbor_diagnostics": v3_package.metadata.get(
                    "locomo_neighbor_diagnostics",
                    [],
                ),
                "recall_evidence_packets": v3_package.metadata.get(
                    "recall_evidence_packets",
                    [],
                ),
                "recall_candidate_session_ids": v3_package.metadata.get(
                    "recall_candidate_session_ids",
                    [],
                ),
                "recall_planned_session_ids": v3_package.metadata.get(
                    "recall_planned_session_ids",
                    [],
                ),
                "archival_eligibility": v3_package.metadata.get(
                    "archival_eligibility",
                    {},
                ),
                "indexed_source_ids": indexed_source_ids,
                "recall_indexed_source_ids": indexed_source_ids,
                "episode_candidate_message_ids": recall_candidate_message_ids,
                "recall_candidate_message_ids": recall_candidate_message_ids,
                "planned_evidence_message_ids": planned_evidence_message_ids,
                "recall_planned_message_ids": planned_evidence_message_ids,
                "budget_dropped_relevant": package.candidate_budget_dropped,
                "recall_budget_dropped": package.candidate_budget_dropped,
            }
        )
        return package

    @staticmethod
    def _v3_source_ids(
        items: list[ContextLayerItem],
        *,
        layers: set[str] | None = None,
    ) -> list[str]:
        source_ids: list[str] = []
        for item in items:
            if layers is not None and item.layer not in layers:
                continue
            for source_ref in item.source_refs:
                source_type = getattr(source_ref.source_type, "value", source_ref.source_type)
                if source_type == "message":
                    source_ids.append(source_ref.source_id)
        seen: set[str] = set()
        deduped: list[str] = []
        for source_id in source_ids:
            if source_id in seen:
                continue
            seen.add(source_id)
            deduped.append(source_id)
        return deduped

    def trace(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        payload = {**current_observability_context(), **payload}
        self.store.add_trace(
            TraceEvent(session_id=session_id, event_type=event_type, payload=payload)
        )

    def _require_session(self, session_id: str) -> Session:
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError(f"session not found: {session_id}")
        return session
