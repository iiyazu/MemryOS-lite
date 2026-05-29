from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from memoryos_lite.observability import log_event, observability_context

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid4().hex
        request.state.request_id = request_id
        with observability_context(request_id=request_id, trace_id=request_id):
            response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str | None = None):
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if not self._api_key:
            return await call_next(request)
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)
        key = request.headers.get("X-API-Key")
        if key != self._api_key:
            return JSONResponse(status_code=401, content={"detail": "invalid_api_key"})
        return await call_next(request)


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        request_id = getattr(request.state, "request_id", "unknown")
        log_event(
            logger,
            logging.INFO,
            "request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=round((time.monotonic() - start) * 1000, 2),
        )
        return response
