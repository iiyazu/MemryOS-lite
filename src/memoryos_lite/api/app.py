from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from memoryos_lite import __version__
from memoryos_lite.config import Settings as _Settings
from memoryos_lite.curator import CuratorLLMError
from memoryos_lite.curator.curate import CURATE_SCHEMA, CurateRequest, CurateResponse
from memoryos_lite.engine import CurateUnavailableError, MemoryOSService
from memoryos_lite.middleware import (
    ApiKeyAuthMiddleware,
    RequestIdMiddleware,
    StructuredLoggingMiddleware,
)
from memoryos_lite.retrieval.supersede import SupersededQuote
from memoryos_lite.schemas import (
    ArchiveAttachmentRequest,
    ArchiveAttachmentResponse,
    ArchiveDocumentIngestRequest,
    ArchiveDocumentIngestResponse,
    BuildContextRequest,
    BuildContextResponseProfile,
    CreateSessionRequest,
    IngestResponse,
    MessageCreate,
    Session,
)
from memoryos_lite.source_evidence import build_source_evidence


@lru_cache(maxsize=1)
def get_service() -> MemoryOSService:
    return MemoryOSService()


ServiceDep = Annotated[MemoryOSService, Depends(get_service)]


app = FastAPI(title="MemoryOS Lite", version=__version__)

# Middleware (registration order is reverse of request processing order)
_settings = _Settings()
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(ApiKeyAuthMiddleware, api_key=_settings.memoryos_api_key)
app.add_middleware(RequestIdMiddleware)


@app.get("/health")
def health(service: ServiceDep) -> dict[str, object]:
    # Constructing the service here is intentional: for the managed
    # full-local profile this proves that the offline FastEmbed model can be
    # loaded before Workroom reports Hybrid readiness.  The response exposes
    # only booleans and fixed capability names, never model paths or errors.
    semantic_ready = False
    if service.embedding_client is not None:
        try:
            # FastEmbed loads its ONNX model lazily; touching ``dim`` is the
            # capability proof, not merely an import check.
            semantic_ready = service.embedding_client.dim > 0
        except Exception:
            semantic_ready = False
    return {
        "status": "ok",
        "version": __version__,
        "capabilities": {
            "build_context_profiles": [
                BuildContextResponseProfile.FULL.value,
                BuildContextResponseProfile.SOURCE_EVIDENCE_V1.value,
                BuildContextResponseProfile.SOURCE_EVIDENCE_V2.value,
            ],
            "hybrid": {
                "lexical": True,
                "semantic": semantic_ready,
                "rrf": semantic_ready,
            },
            "message_ingest": True,
            "curate": CURATE_SCHEMA,
        },
    }


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
        detail = str(exc)
        raise HTTPException(
            status_code=409 if detail.startswith("external_id conflict") else 404,
            detail=detail,
        ) from exc


@app.post("/sessions/{session_id}/build-context")
def build_context(
    session_id: str,
    request: BuildContextRequest,
    service: ServiceDep,
):
    try:
        package = service.build_context(
            session_id=session_id,
            task=request.task,
            budget=request.budget,
            retrieval_query=request.retrieval_query,
            include_global_core=request.include_global_core,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if request.response_profile in {
        BuildContextResponseProfile.SOURCE_EVIDENCE_V1,
        BuildContextResponseProfile.SOURCE_EVIDENCE_V2,
    }:
        try:
            if request.response_profile is BuildContextResponseProfile.SOURCE_EVIDENCE_V2:
                marks = [
                    SupersededQuote(quote=m.quote, current=m.current) for m in request.superseded
                ]
                return build_source_evidence(package, schema_version="v2", superseded=marks)
            return build_source_evidence(package)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return package


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


@app.post("/curate", response_model=CurateResponse)
def curate(request: CurateRequest, service: ServiceDep) -> CurateResponse:
    """Stateless module curation: the caller sends state, MemoryOS returns new versions.

    503 means curation cannot run here (no LLM key or runtime); 502 means the
    provider call failed. Neither leaks provider error text.
    """

    try:
        return service.curate(request)
    except CurateUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.reason_code) from exc
    except CuratorLLMError as exc:
        raise HTTPException(status_code=502, detail="curator_llm_error") from exc
