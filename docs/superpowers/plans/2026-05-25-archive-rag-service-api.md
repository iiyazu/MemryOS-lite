# Archive RAG Service/API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Archive RAG through `MemoryOSService`, FastAPI, and CLI while preserving SQLite authority, source grounding, v3 archive eligibility, and optional Qdrant behavior.

**Architecture:** Add structured archive request/response schemas, then wire a narrow service API over the existing `MemoryOSArchiveRAG` and `MemoryStore` archive tables. FastAPI and CLI remain thin transport wrappers and never bypass v3 context eligibility.

**Tech Stack:** Python 3.11, Pydantic v2, FastAPI, Typer, SQLAlchemy, pytest, ruff, mypy, existing MemoryOS Lite service/store/composer modules.

---

## File Structure

- `src/memoryos_lite/schemas.py`
  - Add transport schemas for archive ingest, attachment, passage listing, diagnostics, and source refs.
- `src/memoryos_lite/store.py`
  - Extend archive passage listing with pagination and producer filtering.
- `src/memoryos_lite/engine.py`
  - Add `MemoryOSService` archive orchestration methods and idempotent ingest behavior.
- `src/memoryos_lite/api/app.py`
  - Add `POST /archives/ingest`, `POST /archives/attachments`, and `GET /archives/passages`.
- `src/memoryos_lite/cli.py`
  - Add `memoryos archive ingest`, `memoryos archive attach`, and `memoryos archive passages`.
- `tests/test_archive_service.py`
  - New service-level archive workflow tests.
- `tests/test_api.py`
  - Add FastAPI smoke coverage for archive endpoints.
- `tests/test_cli_archive.py`
  - New CLI smoke tests.
- `docs/archive-rag-boundary.md`
  - Add the service/API entry point note.

Keep the implementation YAGNI: no delete, reindex, versioning, auth, multipart upload, answer-generation API, detach, or attachment expiration.

---

### Task 1: Add Archive Transport Schemas

**Files:**
- Modify: `src/memoryos_lite/schemas.py`
- Test: `tests/test_archive_service.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_archive_service.py` with these initial tests:

```python
import pytest
from pydantic import ValidationError

from memoryos_lite.schemas import ArchiveDocumentIngestRequest, ArchiveSourceRefPayload


def _ref() -> dict[str, str]:
    return {"source_type": "document", "source_id": "doc_source"}


def test_archive_ingest_request_requires_exactly_one_identity_route() -> None:
    request = ArchiveDocumentIngestRequest(
        document_id="adoc_1",
        title="Spec",
        content="Project Helios launches in Lisbon.",
        source_refs=[_ref()],
        identity={"kind": "archive", "archive_id": "archive_1"},
    )

    assert request.identity.kind == "archive"
    assert request.identity.archive_id == "archive_1"

    with pytest.raises(ValidationError) as exc_info:
        ArchiveDocumentIngestRequest(
            document_id="adoc_bad",
            title="Bad",
            content="Bad",
            source_refs=[_ref()],
            identity={
                "kind": "archive",
                "archive_id": "archive_1",
                "source_id": "src_1",
            },
        )
    assert "source_id" in str(exc_info.value)
    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_archive_source_ref_payload_validates_manual_approval() -> None:
    with pytest.raises(ValidationError, match="manual source refs require approval_id"):
        ArchiveSourceRefPayload(source_type="manual", source_id="manual_1")

    ref = ArchiveSourceRefPayload(
        source_type="manual",
        source_id="manual_1",
        approval_id="approval_1",
    )
    assert ref.approval_id == "approval_1"
```

- [ ] **Step 2: Run schema tests to verify they fail**

Run:

```bash
uv run pytest tests/test_archive_service.py::test_archive_ingest_request_requires_exactly_one_identity_route tests/test_archive_service.py::test_archive_source_ref_payload_validates_manual_approval -q
```

Expected: FAIL with import errors for `ArchiveDocumentIngestRequest` and `ArchiveSourceRefPayload`.

- [ ] **Step 3: Add schema classes**

In `src/memoryos_lite/schemas.py`, add imports:

```python
from typing import Annotated, Any, Literal
```

Change the existing pydantic import to:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator
```

Add these classes after `SearchRequest`:

```python
class ArchiveSourceSpanPayload(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> "ArchiveSourceSpanPayload":
        if self.start > self.end:
            raise ValueError("span start must be less than or equal to end")
        return self


class ArchiveIdentityScopePayload(BaseModel):
    user_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    archive_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class ArchiveSourceRefPayload(BaseModel):
    source_type: Literal[
        "message",
        "episode",
        "document",
        "passage",
        "memory",
        "core_block",
        "tool_call",
        "approval",
        "manual",
    ]
    source_id: str = Field(min_length=1)
    session_id: str | None = None
    identity_scope: ArchiveIdentityScopePayload | None = None
    span: ArchiveSourceSpanPayload | None = None
    quote: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    approval_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_manual_approval(self) -> "ArchiveSourceRefPayload":
        if self.source_type == "manual" and not self.approval_id:
            raise ValueError("manual source refs require approval_id")
        return self


class ArchiveIdentityArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["archive"]
    archive_id: str = Field(min_length=1)


class ArchiveIdentitySource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["source"]
    source_id: str = Field(min_length=1)
    file_id: str | None = None


class ArchiveIdentityFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["file"]
    file_id: str = Field(min_length=1)


ArchiveDocumentIdentity = Annotated[
    ArchiveIdentityArchive | ArchiveIdentitySource | ArchiveIdentityFile,
    Field(discriminator="kind"),
]


class ArchiveDocumentIngestRequest(BaseModel):
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str
    source_refs: list[ArchiveSourceRefPayload] = Field(min_length=1)
    identity: ArchiveDocumentIdentity
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    producer: str = "explicit_document"


class ArchiveDiagnosticResponse(BaseModel):
    event_type: str
    reason_code: str
    item_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchiveDocumentIngestResponse(BaseModel):
    document_id: str
    chunk_ids: list[str]
    passage_ids: list[str]
    diagnostics: list[ArchiveDiagnosticResponse] = Field(default_factory=list)


class ArchiveAttachmentRequest(BaseModel):
    archive_id: str = Field(min_length=1)
    scope_type: Literal["agent", "project", "source", "user", "run", "session"]
    scope_id: str = Field(min_length=1)
    source_refs: list[ArchiveSourceRefPayload] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchiveAttachmentResponse(BaseModel):
    attachment_id: str
    archive_id: str
    scope_type: str
    scope_id: str
    passage_count: int
    diagnostics: list[ArchiveDiagnosticResponse] = Field(default_factory=list)


class ArchivePassageResponse(BaseModel):
    id: str
    document_id: str | None = None
    chunk_id: str | None = None
    archive_id: str | None = None
    source_id: str | None = None
    file_id: str | None = None
    text: str
    citation: ArchiveSourceSpanPayload | None = None
    source_refs: list[ArchiveSourceRefPayload] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchivePassageListResponse(BaseModel):
    passages: list[ArchivePassageResponse]
    limit: int
    offset: int
    total: int
```

- [ ] **Step 4: Run schema tests to verify they pass**

Run:

```bash
uv run pytest tests/test_archive_service.py::test_archive_ingest_request_requires_exactly_one_identity_route tests/test_archive_service.py::test_archive_source_ref_payload_validates_manual_approval -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit schemas**

```bash
git add src/memoryos_lite/schemas.py tests/test_archive_service.py
git commit -m "feat: add archive service schemas"
```

---

### Task 2: Add Store Pagination And Producer Filtering

**Files:**
- Modify: `src/memoryos_lite/store.py`
- Test: `tests/test_archival_store.py`

- [ ] **Step 1: Write failing store tests**

Append to `tests/test_archival_store.py`:

```python
def test_archival_passage_listing_supports_pagination_and_total(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    for index in range(3):
        store.create_archival_passage(
            ArchivalPassage(
                id=f"apsg_{index}",
                archive_id="archive_page",
                text=f"passage {index}",
                source_refs=[ref],
            )
        )

    page = store.list_archival_passages_page(archive_id="archive_page", limit=2, offset=1)

    assert page.total == 3
    assert [passage.id for passage in page.passages] == ["apsg_1", "apsg_2"]
    assert page.limit == 2
    assert page.offset == 1


def test_archival_passage_listing_filters_by_producer_metadata(tmp_path):
    store = _store(tmp_path)
    ref = _ref()
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_agent",
            archive_id="archive_1",
            text="agent passage",
            source_refs=[ref],
            metadata={"producer": "xmuse_review_agent"},
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="apsg_manual",
            archive_id="archive_1",
            text="manual passage",
            source_refs=[ref],
            metadata={"producer": "manual"},
        )
    )

    page = store.list_archival_passages_page(
        archive_id="archive_1",
        producer="xmuse_review_agent",
    )

    assert page.total == 1
    assert [passage.id for passage in page.passages] == ["apsg_agent"]
```

- [ ] **Step 2: Run store tests to verify they fail**

Run:

```bash
uv run pytest tests/test_archival_store.py::test_archival_passage_listing_supports_pagination_and_total tests/test_archival_store.py::test_archival_passage_listing_filters_by_producer_metadata -q
```

Expected: FAIL with `AttributeError: 'MemoryStore' object has no attribute 'list_archival_passages_page'`.

- [ ] **Step 3: Add page result type and store method**

In `src/memoryos_lite/store.py`, add this import near the top:

```python
from dataclasses import dataclass
```

Add this dataclass before `class MemoryStore`:

```python
@dataclass(frozen=True)
class ArchivalPassagePage:
    passages: list[ArchivalPassage]
    total: int
    limit: int
    offset: int
```

Add this method immediately after `list_archival_passages`:

```python
    def list_archival_passages_page(
        self,
        archive_id: str | None = None,
        source_id: str | None = None,
        file_id: str | None = None,
        producer: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> ArchivalPassagePage:
        normalized_limit = min(max(limit, 1), 500)
        normalized_offset = max(offset, 0)
        passages = self.list_archival_passages(
            archive_id=archive_id,
            source_id=source_id,
            file_id=file_id,
        )
        if producer is not None:
            passages = [
                passage
                for passage in passages
                if str(passage.metadata.get("producer") or "") == producer
            ]
        total = len(passages)
        return ArchivalPassagePage(
            passages=passages[normalized_offset : normalized_offset + normalized_limit],
            total=total,
            limit=normalized_limit,
            offset=normalized_offset,
        )
```

This is intentionally an O(n) prototype implementation: it reuses
`list_archival_passages()` and slices in memory after filtering. Do not expand
this slice into SQL-level pagination unless focused tests show the existing
store contract cannot support the service/API workflow.

- [ ] **Step 4: Run store tests to verify they pass**

Run:

```bash
uv run pytest tests/test_archival_store.py::test_archival_passage_listing_supports_pagination_and_total tests/test_archival_store.py::test_archival_passage_listing_filters_by_producer_metadata -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit store pagination**

```bash
git add src/memoryos_lite/store.py tests/test_archival_store.py
git commit -m "feat: page archival passage listings"
```

---

### Task 3: Add MemoryOSService Archive Methods

**Files:**
- Modify: `src/memoryos_lite/engine.py`
- Modify: `src/memoryos_lite/schemas.py`
- Test: `tests/test_archive_service.py`

- [ ] **Step 1: Write failing service workflow tests**

Append to `tests/test_archive_service.py`:

```python
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import ArchiveAttachmentRequest, ArchiveDocumentIngestRequest
from memoryos_lite.store import create_store


def _service(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


def test_service_archive_ingest_attach_and_context_preserve_source_span_quote(tmp_path):
    service = _service(tmp_path)
    session = service.create_session("archive-service")
    ref = {"source_type": "document", "source_id": "doc_1", "session_id": session.id}

    ingest = service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id="adoc_service",
            title="Service doc",
            content="Project Helios launches in Lisbon.",
            source_refs=[ref],
            identity={"kind": "archive", "archive_id": "archive_service"},
        )
    )
    attachment = service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id="archive_service",
            scope_type="session",
            scope_id=session.id,
            source_refs=[ref],
        )
    )
    context = service.build_context(
        session.id,
        "Where does Project Helios launch?",
        budget=120,
    )

    assert len(ingest.passage_ids) == 1
    passage_id = ingest.passage_ids[0]
    assert passage_id.startswith("apsg_")
    assert attachment.passage_count == 1
    archival = [
        item
        for item in context.metadata["v3_context"]["items"]
        if item["layer"] == "archival"
    ]
    assert archival[0]["item_id"] == passage_id
    assert archival[0]["source_refs"][0]["span"] == {"start": 0, "end": 34}
    assert archival[0]["source_refs"][0]["quote"] == "Project Helios launches in Lisbon."


def test_service_archive_ingest_is_idempotent_for_same_document(tmp_path):
    service = _service(tmp_path)
    ref = {"source_type": "document", "source_id": "doc_1"}
    request = ArchiveDocumentIngestRequest(
        document_id="adoc_replay",
        title="Replay",
        content="Replay-safe content.",
        source_refs=[ref],
        identity={"kind": "archive", "archive_id": "archive_replay"},
    )

    first = service.ingest_archive_document(request)
    second = service.ingest_archive_document(request)

    assert first.passage_ids == second.passage_ids
    assert second.diagnostics[0].reason_code == "archive_ingest_idempotent_replay"


def test_service_archive_ingest_rejects_conflicting_document_id(tmp_path):
    service = _service(tmp_path)
    ref = {"source_type": "document", "source_id": "doc_1"}
    service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id="adoc_conflict",
            title="Conflict",
            content="Original content.",
            source_refs=[ref],
            identity={"kind": "archive", "archive_id": "archive_conflict"},
        )
    )

    with pytest.raises(ValueError, match="archive document conflict"):
        service.ingest_archive_document(
            ArchiveDocumentIngestRequest(
                document_id="adoc_conflict",
                title="Conflict",
                content="Changed content.",
                source_refs=[ref],
                identity={"kind": "archive", "archive_id": "archive_conflict"},
            )
        )


def test_service_file_only_archive_ingest_can_be_listed(tmp_path):
    service = _service(tmp_path)
    ref = {"source_type": "document", "source_id": "doc_file"}

    ingest = service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id="adoc_file",
            title="File scoped archive",
            content="File-only archive content.",
            source_refs=[ref],
            identity={"kind": "file", "file_id": "file_1"},
            producer="xmuse_review_agent",
        )
    )
    page = service.list_archive_passages(
        file_id="file_1",
        producer="xmuse_review_agent",
        limit=10,
        offset=0,
    )

    assert len(ingest.passage_ids) == 1
    assert ingest.passage_ids[0].startswith("apsg_")
    assert page.total == 1
    assert page.passages[0].file_id == "file_1"
    assert page.passages[0].metadata["producer"] == "xmuse_review_agent"


def test_service_archive_context_reports_lexical_fallback_without_qdrant(tmp_path):
    service = _service(tmp_path)
    session = service.create_session("archive-no-qdrant")
    ref = {
        "source_type": "document",
        "source_id": "doc_no_qdrant",
        "session_id": session.id,
    }
    ingest = service.ingest_archive_document(
        ArchiveDocumentIngestRequest(
            document_id="adoc_no_qdrant",
            title="No Qdrant doc",
            content="Shanghai rail lexical fallback.",
            source_refs=[ref],
            identity={"kind": "archive", "archive_id": "archive_no_qdrant"},
        )
    )
    service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id="archive_no_qdrant",
            scope_type="session",
            scope_id=session.id,
            source_refs=[ref],
        )
    )

    context = service.build_context(session.id, "Shanghai rail", budget=120)

    archival = [
        item
        for item in context.metadata["v3_context"]["items"]
        if item["layer"] == "archival"
    ]
    event_types = {
        row["event_type"] for row in context.metadata["v3_component_accounting"]
    }
    assert archival[0]["item_id"] == ingest.passage_ids[0]
    assert "archival_vector_unavailable" in event_types
    assert "archival_lexical_fallback" in event_types
```

- [ ] **Step 2: Run service workflow tests to verify they fail**

Run:

```bash
uv run pytest tests/test_archive_service.py::test_service_archive_ingest_attach_and_context_preserve_source_span_quote tests/test_archive_service.py::test_service_archive_ingest_is_idempotent_for_same_document tests/test_archive_service.py::test_service_archive_ingest_rejects_conflicting_document_id tests/test_archive_service.py::test_service_file_only_archive_ingest_can_be_listed tests/test_archive_service.py::test_service_archive_context_reports_lexical_fallback_without_qdrant -q
```

Expected: FAIL with `AttributeError: 'MemoryOSService' object has no attribute 'ingest_archive_document'`.

- [ ] **Step 3: Add conversion helpers in `engine.py`**

In `src/memoryos_lite/engine.py`, add imports:

```python
import hashlib
```

Add these imports from `memoryos_lite.archive_rag`:

```python
from memoryos_lite.archive_rag import ArchiveRAGDiagnostic, ArchiveRAGIngestRequest, MemoryOSArchiveRAG
```

Extend the `schemas` import list with:

```python
    ArchiveAttachmentRequest,
    ArchiveAttachmentResponse,
    ArchiveDiagnosticResponse,
    ArchiveDocumentIngestRequest,
    ArchiveDocumentIngestResponse,
    ArchivePassageListResponse,
    ArchivePassageResponse,
    ArchiveSourceRefPayload,
    ArchiveSourceSpanPayload,
    new_id,
```

Extend the `v3_contracts` import list with:

```python
    ArchivalPassage,
    ArchiveAttachment,
    SourceRef,
```

Add these helper methods inside `MemoryOSService` after `__init__`:

```python
    def _archive_rag(self) -> MemoryOSArchiveRAG:
        return MemoryOSArchiveRAG(self.store)

    def _source_refs_from_payloads(
        self,
        payloads: list[ArchiveSourceRefPayload],
    ) -> list[SourceRef]:
        return [
            SourceRef.model_validate(payload.model_dump(mode="json"))
            for payload in payloads
        ]

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
```

- [ ] **Step 4: Add service archive methods**

Add these methods inside `MemoryOSService` after the helper methods:

```python
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
                self._archive_diagnostic_response(diagnostic)
                for diagnostic in result.diagnostics
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

    def list_archive_passages(
        self,
        *,
        archive_id: str | None = None,
        source_id: str | None = None,
        file_id: str | None = None,
        producer: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ArchivePassageListResponse:
        page = self.store.list_archival_passages_page(
            archive_id=archive_id,
            source_id=source_id,
            file_id=file_id,
            producer=producer,
            limit=limit,
            offset=offset,
        )
        return ArchivePassageListResponse(
            passages=[self._archive_passage_response(passage) for passage in page.passages],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )

    def _archive_passage_response(self, passage: ArchivalPassage) -> ArchivePassageResponse:
        citation = None
        if passage.citation is not None:
            citation = ArchiveSourceSpanPayload(
                start=passage.citation.start,
                end=passage.citation.end,
            )
        return ArchivePassageResponse(
            id=passage.id,
            document_id=passage.document_id,
            chunk_id=passage.chunk_id,
            archive_id=passage.archive_id,
            source_id=passage.source_id,
            file_id=passage.file_id,
            text=passage.text,
            citation=citation,
            source_refs=[
                ArchiveSourceRefPayload.model_validate(ref.model_dump(mode="json"))
                for ref in passage.source_refs
            ],
            tags=list(passage.tags),
            metadata=dict(passage.metadata),
        )
```

- [ ] **Step 5: Run service tests to verify they pass**

Run:

```bash
uv run pytest tests/test_archive_service.py -q
```

Expected: all tests in `tests/test_archive_service.py` pass.

- [ ] **Step 6: Commit service methods**

```bash
git add src/memoryos_lite/engine.py src/memoryos_lite/schemas.py tests/test_archive_service.py
git commit -m "feat: expose archive rag through service"
```

---

### Task 4: Add FastAPI Archive Endpoints

**Files:**
- Modify: `src/memoryos_lite/api/app.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API smoke test**

Append to `tests/test_api.py`:

```python
def test_api_archive_ingest_attach_and_list(service):
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app)
    try:
        session_response = client.post("/sessions", json={"title": "api-archive"})
        assert session_response.status_code == 200
        session_id = session_response.json()["id"]
        ref = {"source_type": "document", "source_id": "doc_api", "session_id": session_id}

        ingest_response = client.post(
            "/archives/ingest",
            json={
                "document_id": "adoc_api",
                "title": "API archive",
                "content": "API archive says Project Helios launches in Lisbon.",
                "source_refs": [ref],
                "identity": {"kind": "archive", "archive_id": "archive_api"},
            },
        )
        assert ingest_response.status_code == 200, ingest_response.text
        passage_ids = ingest_response.json()["passage_ids"]
        assert len(passage_ids) == 1
        assert passage_ids[0].startswith("apsg_")

        attach_response = client.post(
            "/archives/attachments",
            json={
                "archive_id": "archive_api",
                "scope_type": "session",
                "scope_id": session_id,
                "source_refs": [ref],
            },
        )
        assert attach_response.status_code == 200, attach_response.text
        assert attach_response.json()["passage_count"] == 1

        list_response = client.get(
            "/archives/passages",
            params={"archive_id": "archive_api", "limit": 10, "offset": 0},
        )
        assert list_response.status_code == 200, list_response.text
        assert list_response.json()["total"] == 1
        assert list_response.json()["passages"][0]["id"] == passage_ids[0]
        assert list_response.json()["passages"][0]["source_refs"][0]["quote"]
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run API test to verify it fails**

Run:

```bash
uv run pytest tests/test_api.py::test_api_archive_ingest_attach_and_list -q
```

Expected: FAIL with `404 Not Found` for `/archives/ingest`.

- [ ] **Step 3: Add endpoint imports**

In `src/memoryos_lite/api/app.py`, extend the `schemas` import list with:

```python
    ArchiveAttachmentRequest,
    ArchiveAttachmentResponse,
    ArchiveDocumentIngestRequest,
    ArchiveDocumentIngestResponse,
    ArchivePassageListResponse,
```

- [ ] **Step 4: Add FastAPI endpoints**

Add these endpoint functions after `build_context`:

```python
@app.post("/archives/ingest", response_model=ArchiveDocumentIngestResponse)
def ingest_archive_document(
    request: ArchiveDocumentIngestRequest,
    service: ServiceDep,
) -> ArchiveDocumentIngestResponse:
    try:
        return service.ingest_archive_document(request)
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if "conflict" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@app.post("/archives/attachments", response_model=ArchiveAttachmentResponse)
def attach_archive(
    request: ArchiveAttachmentRequest,
    service: ServiceDep,
) -> ArchiveAttachmentResponse:
    try:
        return service.attach_archive(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/archives/passages", response_model=ArchivePassageListResponse)
def list_archive_passages(
    service: ServiceDep,
    archive_id: str | None = None,
    source_id: str | None = None,
    file_id: str | None = None,
    producer: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ArchivePassageListResponse:
    return service.list_archive_passages(
        archive_id=archive_id,
        source_id=source_id,
        file_id=file_id,
        producer=producer,
        limit=limit,
        offset=offset,
    )
```

- [ ] **Step 5: Run API tests**

Run:

```bash
uv run pytest tests/test_api.py -q
```

Expected: all API tests pass.

- [ ] **Step 6: Commit API endpoints**

```bash
git add src/memoryos_lite/api/app.py tests/test_api.py
git commit -m "feat: add archive rag api endpoints"
```

---

### Task 5: Add CLI Archive Commands

**Files:**
- Modify: `src/memoryos_lite/cli.py`
- Test: `tests/test_cli_archive.py`

- [ ] **Step 1: Write failing CLI smoke test**

Create `tests/test_cli_archive.py`:

```python
from typer.testing import CliRunner

from memoryos_lite.cli import app
from memoryos_lite.config import get_settings


def test_archive_cli_ingest_attach_and_passages(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path / ".memoryos"))
    runner = CliRunner()

    try:
        ingest = runner.invoke(
            app,
            [
                "archive",
                "ingest",
                "--document-id",
                "adoc_cli",
                "--archive-id",
                "archive_cli",
                "--title",
                "CLI archive",
                "--content",
                "CLI archive says Project Helios launches in Lisbon.",
                "--source-type",
                "document",
                "--source-id",
                "doc_cli",
            ],
        )
        assert ingest.exit_code == 0, ingest.output
        assert "apsg_" in ingest.output
        assert "adoc_cli" in ingest.output

        attach = runner.invoke(
            app,
            [
                "archive",
                "attach",
                "--archive-id",
                "archive_cli",
                "--scope-type",
                "session",
                "--scope-id",
                "ses_cli",
                "--source-type",
                "document",
                "--source-id",
                "doc_cli",
            ],
        )
        assert attach.exit_code == 0, attach.output
        assert "archive_cli" in attach.output

        passages = runner.invoke(
            app,
            ["archive", "passages", "--archive-id", "archive_cli"],
        )
        assert passages.exit_code == 0, passages.output
        assert "apsg_" in passages.output
    finally:
        get_settings.cache_clear()
```

- [ ] **Step 2: Run CLI test to verify it fails**

Run:

```bash
uv run pytest tests/test_cli_archive.py::test_archive_cli_ingest_attach_and_passages -q
```

Expected: FAIL because the `archive` Typer group does not exist.

- [ ] **Step 3: Add CLI archive typer and imports**

In `src/memoryos_lite/cli.py`, change the typing import to:

```python
from typing import Annotated, Any, Literal, cast
```

In `src/memoryos_lite/cli.py`, extend the schemas import:

```python
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveDocumentIngestRequest,
    ArchiveSourceRefPayload,
    MessageCreate,
    Role,
)
```

Add after `eval_app = Typer(...)`:

```python
archive_app = Typer(help="Ingest and inspect source-backed archive documents")
```

Add after `app.add_typer(eval_app, name="eval")`:

```python
app.add_typer(archive_app, name="archive")
```

Add this helper near `_message_text`:

```python
ArchiveScopeType = Literal["agent", "project", "source", "user", "run", "session"]
ARCHIVE_SCOPE_TYPES: set[ArchiveScopeType] = {
    "agent",
    "project",
    "source",
    "user",
    "run",
    "session",
}


def _cli_service() -> MemoryOSService:
    return MemoryOSService(settings=get_settings())


def _archive_scope_type(value: str) -> ArchiveScopeType:
    normalized = value.strip().lower()
    if normalized not in ARCHIVE_SCOPE_TYPES:
        raise ValueError(
            "archive scope type must be one of: "
            + ", ".join(sorted(ARCHIVE_SCOPE_TYPES))
        )
    return cast(ArchiveScopeType, normalized)


def _archive_source_ref_payload(
    *,
    source_type: str,
    source_id: str,
    session_id: str | None = None,
) -> ArchiveSourceRefPayload:
    return ArchiveSourceRefPayload.model_validate(
        {
            "source_type": source_type,
            "source_id": source_id,
            "session_id": session_id,
        }
    )
```

- [ ] **Step 4: Add CLI commands**

Add these command functions before the `eval_app` commands:

```python
@archive_app.command("ingest")
def archive_ingest(
    document_id: Annotated[str, Option("--document-id")],
    archive_id: Annotated[str | None, Option("--archive-id")] = None,
    source_id: Annotated[str | None, Option("--source-doc-id")] = None,
    file_id: Annotated[str | None, Option("--file-id")] = None,
    title: Annotated[str, Option("--title")] = "Archive document",
    content: Annotated[str, Option("--content")] = "",
    source_type: Annotated[str, Option("--source-type")] = "document",
    source_ref_id: Annotated[str, Option("--source-id")] = "manual_source",
    session_id: Annotated[str | None, Option("--session-id")] = None,
) -> None:
    identity: dict[str, object]
    if archive_id:
        identity = {"kind": "archive", "archive_id": archive_id}
    elif source_id:
        identity = {"kind": "source", "source_id": source_id, "file_id": file_id}
    elif file_id:
        identity = {"kind": "file", "file_id": file_id}
    else:
        raise ValueError(
            "archive ingest requires --archive-id, --source-doc-id, or --file-id"
        )
    service = _cli_service()
    response = service.ingest_archive_document(
        ArchiveDocumentIngestRequest.model_validate(
            {
                "document_id": document_id,
                "title": title,
                "content": content,
                "source_refs": [
                    _archive_source_ref_payload(
                        source_type=source_type,
                        source_id=source_ref_id,
                        session_id=session_id,
                    )
                ],
                "identity": identity,
            }
        )
    )
    table = Table(title="Archive ingest")
    table.add_column("document")
    table.add_column("passages")
    table.add_row(response.document_id, ", ".join(response.passage_ids))
    console.print(table)


@archive_app.command("attach")
def archive_attach(
    archive_id: Annotated[str, Option("--archive-id")],
    scope_type: Annotated[str, Option("--scope-type")],
    scope_id: Annotated[str, Option("--scope-id")],
    source_type: Annotated[str, Option("--source-type")] = "document",
    source_ref_id: Annotated[str, Option("--source-id")] = "manual_source",
    session_id: Annotated[str | None, Option("--session-id")] = None,
) -> None:
    service = _cli_service()
    response = service.attach_archive(
        ArchiveAttachmentRequest(
            archive_id=archive_id,
            scope_type=_archive_scope_type(scope_type),
            scope_id=scope_id,
            source_refs=[
                _archive_source_ref_payload(
                    source_type=source_type,
                    source_id=source_ref_id,
                    session_id=session_id,
                )
            ],
        )
    )
    table = Table(title="Archive attachment")
    table.add_column("archive")
    table.add_column("scope")
    table.add_column("passages")
    table.add_row(
        response.archive_id,
        f"{response.scope_type}:{response.scope_id}",
        str(response.passage_count),
    )
    console.print(table)


@archive_app.command("passages")
def archive_passages(
    archive_id: Annotated[str | None, Option("--archive-id")] = None,
    source_id: Annotated[str | None, Option("--source-doc-id")] = None,
    file_id: Annotated[str | None, Option("--file-id")] = None,
    producer: Annotated[str | None, Option("--producer")] = None,
    limit: Annotated[int, Option("--limit")] = 100,
    offset: Annotated[int, Option("--offset")] = 0,
) -> None:
    service = _cli_service()
    response = service.list_archive_passages(
        archive_id=archive_id,
        source_id=source_id,
        file_id=file_id,
        producer=producer,
        limit=limit,
        offset=offset,
    )
    table = Table(title="Archive passages")
    table.add_column("id")
    table.add_column("archive")
    table.add_column("source")
    for passage in response.passages:
        table.add_row(
            passage.id,
            passage.archive_id or "",
            passage.source_id or passage.file_id or "",
        )
    console.print(table)
```

- [ ] **Step 5: Run CLI test to verify it passes**

Run:

```bash
uv run pytest tests/test_cli_archive.py -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit CLI commands**

```bash
git add src/memoryos_lite/cli.py tests/test_cli_archive.py
git commit -m "feat: add archive rag cli commands"
```

---

### Task 6: Documentation And Verification

**Files:**
- Modify: `docs/archive-rag-boundary.md`
- Verify: focused tests, hard eval

- [ ] **Step 1: Update archive boundary docs**

In `docs/archive-rag-boundary.md`, add this section before `## Non-Claims`:

```markdown
## Service/API Boundary

`MemoryOSService` is the application entry point for archive RAG ingestion.
FastAPI and CLI commands call service methods instead of manipulating the store
directly.

Minimal service-backed surfaces:

- `POST /archives/ingest`
- `POST /archives/attachments`
- `GET /archives/passages`
- `memoryos archive ingest`
- `memoryos archive attach`
- `memoryos archive passages`

These surfaces do not bypass v3 archive eligibility. Retrieved archive passages
enter normal context through `build_context()`.

`GET /archives/passages` uses the current SQLite store listing path and applies
pagination in memory. This is O(n) for the first service/API slice; SQL-level
pagination is a later scale-up task, not part of this prototype integration.
```

- [ ] **Step 2: Run focused archive/service/API/CLI tests**

Run:

```bash
uv run pytest tests/test_archive_service.py tests/test_archival_store.py tests/test_archive_rag_boundary.py tests/test_archival_searcher.py tests/test_archival_vector.py tests/test_context_composer.py tests/test_engine.py tests/test_api.py tests/test_cli_archive.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run lint and targeted mypy**

Run:

```bash
uv run ruff check src/memoryos_lite/archive_rag.py src/memoryos_lite/store.py src/memoryos_lite/engine.py src/memoryos_lite/api/app.py src/memoryos_lite/cli.py src/memoryos_lite/schemas.py tests/test_archive_service.py tests/test_api.py tests/test_cli_archive.py
```

Expected: `All checks passed!`

Run:

```bash
uv run mypy src/memoryos_lite/archive_rag.py src/memoryos_lite/store.py src/memoryos_lite/engine.py src/memoryos_lite/api/app.py src/memoryos_lite/cli.py src/memoryos_lite/schemas.py
```

Expected: `Success: no issues found`.

- [ ] **Step 4: Run hard eval**

Run:

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Expected: `accuracy=1.00` and `source=1.00`.

- [ ] **Step 5: Check diff scope**

Run:

```bash
git diff --name-status feat/phase-2.5-3-retrieval-agent..HEAD
```

Expected: only archive RAG, service/API/CLI, schema, tests, and docs files touched. No `xmuse` or `xmuse_core` deletions.

- [ ] **Step 6: Commit docs and final verification state**

```bash
git add docs/archive-rag-boundary.md
git commit -m "docs: document archive rag service boundary"
```

Do not run full pytest unless the user explicitly asks for it. Report that focused tests, lint, targeted mypy, and hard eval are the completed gates.
