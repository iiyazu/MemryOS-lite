from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from memoryos_lite import __version__
from memoryos_lite.config import Settings as _Settings
from memoryos_lite.curator import CuratorLLMError
from memoryos_lite.curator.curate import CurateRequest, CurateResponse
from memoryos_lite.engine import CurateUnavailableError, MemoryOSService
from memoryos_lite.middleware import (
    ApiKeyAuthMiddleware,
    RequestIdMiddleware,
    StructuredLoggingMiddleware,
)
from memoryos_lite.recall import (
    RecallRequest,
    RecallResponse,
    SimilarRequest,
    SimilarResponse,
    SimilarUnavailableError,
)


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
    # Constructing the service here is intentional: it proves that the offline
    # FastEmbed model loads before ``similar`` is advertised.  The response
    # exposes only fixed capability names, never model paths or errors.
    semantic_ready = False
    if service.embedding_client is not None:
        try:
            # FastEmbed loads its ONNX model lazily; touching ``dim`` is the
            # capability proof, not merely an import check.
            semantic_ready = service.embedding_client.dim > 0
        except Exception:
            semantic_ready = False
    # The hub reads ``capabilities`` at startup and skips what is missing.
    curate = ["curate", "curate.collab"] if service.curate_ready() else []
    return {
        "status": "ok",
        "version": __version__,
        "capabilities": [*curate, "recall", *(["similar"] if semantic_ready else [])],
    }


@app.post("/recall", response_model=RecallResponse)
def recall(request: RecallRequest, service: ServiceDep) -> RecallResponse:
    """Stateless, deterministic ranking of caller-supplied items; no LLM, no storage."""

    return service.recall(request)


@app.post("/similar", response_model=SimilarResponse)
def similar(request: SimilarRequest, service: ServiceDep) -> SimilarResponse:
    """Near-duplicate pairs by dense cosine; 503 ``similar_unavailable`` without embeddings."""

    try:
        return service.similar(request)
    except SimilarUnavailableError as exc:
        raise HTTPException(status_code=503, detail="similar_unavailable") from exc


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
