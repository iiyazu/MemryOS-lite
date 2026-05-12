from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from prometheus_client import make_asgi_app

from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import (
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
