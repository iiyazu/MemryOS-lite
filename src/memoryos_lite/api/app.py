from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from prometheus_client import make_asgi_app

from memoryos_lite.config import Settings as _Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.middleware import (
    ApiKeyAuthMiddleware,
    RequestIdMiddleware,
    StructuredLoggingMiddleware,
)
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveAttachmentResponse,
    ArchiveDocumentIngestRequest,
    ArchiveDocumentIngestResponse,
    ArchivePassageListResponse,
    BuildContextRequest,
    CreateSessionRequest,
    IngestResponse,
    MemoryPage,
    MessageCreate,
    SearchRequest,
    Session,
    TraceEvent,
)


@lru_cache(maxsize=1)
def get_service() -> MemoryOSService:
    return MemoryOSService()


ServiceDep = Annotated[MemoryOSService, Depends(get_service)]
app = FastAPI(title="MemoryOS Lite", version="0.1.0")
app.mount("/metrics", make_asgi_app())

# Middleware (registration order is reverse of request processing order)
_settings = _Settings()
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(ApiKeyAuthMiddleware, api_key=_settings.memoryos_api_key)
app.add_middleware(RequestIdMiddleware)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions", response_model=Session)
def create_session(
    request: CreateSessionRequest,
    service: ServiceDep,
) -> Session:
    return service.create_session(request.title)


@app.post("/sessions/{session_id}/ingest", response_model=IngestResponse)
def ingest(
    session_id: str,
    request: MessageCreate,
    service: ServiceDep,
) -> IngestResponse:
    try:
        return service.ingest(session_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/page", response_model=MemoryPage | None)
def page(session_id: str, service: ServiceDep) -> MemoryPage | None:
    try:
        return service.page(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/sessions/{session_id}/build-context")
def build_context(
    session_id: str,
    request: BuildContextRequest,
    service: ServiceDep,
):
    try:
        return service.build_context(
            session_id=session_id,
            task=request.task,
            budget=request.budget,
            retrieval_query=request.retrieval_query,
            include_global_core=request.include_global_core,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@app.post("/memory/search")
def search(request: SearchRequest, service: ServiceDep):
    hits = service.search(
        query=request.query,
        top_k=request.top_k,
        session_id=request.session_id,
        limit=request.limit,
    )
    return [
        {
            "page": hit.page,
            "score": hit.score,
            "reason": hit.reason,
        }
        for hit in hits
    ]


@app.get("/memory/pages/{page_id}", response_model=MemoryPage)
def load_page(page_id: str, service: ServiceDep) -> MemoryPage:
    page = service.store.load_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"page not found: {page_id}")
    return page


@app.get("/sessions/{session_id}/trace", response_model=list[TraceEvent])
def trace(session_id: str, service: ServiceDep) -> list[TraceEvent]:
    try:
        service._require_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return service.store.list_traces(session_id)


@app.post("/sessions/{session_id}/ingest-batch")
def ingest_batch(
    session_id: str,
    request: dict,
    service: ServiceDep,
):
    try:
        service._require_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    messages = request.get("messages", [])
    results = []
    for msg in messages:
        msg_obj = MessageCreate(role=msg["role"], content=msg["content"])
        results.append(service.ingest(session_id, msg_obj))
    return results


@app.get("/sessions/{session_id}/summary")
def session_summary(session_id: str, service: ServiceDep):
    try:
        session = service._require_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    messages = service.store.list_messages(session_id)
    return {
        "session_id": session_id,
        "title": session.title,
        "message_count": len(messages),
        "last_activity": messages[-1].created_at if messages else None,
    }
