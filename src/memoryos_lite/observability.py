"""Prometheus business metrics for MemoryOS Lite.

All metrics are defined at module level. Engine code imports and
increments them at relevant call sites. The /metrics endpoint is
exposed via prometheus_client ASGI app mounted in api/app.py.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from prometheus_client import Counter, Histogram

_TRACE_ID: ContextVar[str | None] = ContextVar("memoryos_trace_id", default=None)
_REQUEST_ID: ContextVar[str | None] = ContextVar("memoryos_request_id", default=None)
_SESSION_ID: ContextVar[str | None] = ContextVar("memoryos_session_id", default=None)
_LANE_ID: ContextVar[str | None] = ContextVar("xmuse_lane_id", default=None)
_GRAPH_ID: ContextVar[str | None] = ContextVar("xmuse_graph_id", default=None)


def current_trace_id() -> str:
    trace_id = _TRACE_ID.get()
    if trace_id:
        return trace_id
    trace_id = uuid4().hex
    _TRACE_ID.set(trace_id)
    return trace_id


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


def current_observability_context() -> dict[str, str]:
    context = {
        "trace_id": current_trace_id(),
        "request_id": _REQUEST_ID.get(),
        "session_id": _SESSION_ID.get(),
        "lane_id": _LANE_ID.get(),
        "graph_id": _GRAPH_ID.get(),
    }
    return {key: value for key, value in context.items() if value}


def bind_observability_context(
    *,
    trace_id: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    lane_id: str | None = None,
    graph_id: str | None = None,
) -> None:
    if trace_id is not None:
        _TRACE_ID.set(trace_id)
    elif _TRACE_ID.get() is None:
        _TRACE_ID.set(uuid4().hex)
    if request_id is not None:
        _REQUEST_ID.set(request_id)
    if session_id is not None:
        _SESSION_ID.set(session_id)
    if lane_id is not None:
        _LANE_ID.set(lane_id)
    if graph_id is not None:
        _GRAPH_ID.set(graph_id)


@contextmanager
def observability_context(
    *,
    trace_id: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    lane_id: str | None = None,
    graph_id: str | None = None,
) -> Iterator[dict[str, str]]:
    trace_token = _TRACE_ID.set(trace_id or _TRACE_ID.get() or uuid4().hex)
    request_token = (
        _REQUEST_ID.set(request_id) if request_id is not None else None
    )
    session_token = (
        _SESSION_ID.set(session_id) if session_id is not None else None
    )
    lane_token = _LANE_ID.set(lane_id) if lane_id is not None else None
    graph_token = _GRAPH_ID.set(graph_id) if graph_id is not None else None
    try:
        yield current_observability_context()
    finally:
        _TRACE_ID.reset(trace_token)
        if request_token is not None:
            _REQUEST_ID.reset(request_token)
        if session_token is not None:
            _SESSION_ID.reset(session_token)
        if lane_token is not None:
            _LANE_ID.reset(lane_token)
        if graph_token is not None:
            _GRAPH_ID.reset(graph_token)


def _merge_extra(extra: Mapping[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
    merged = current_observability_context()
    if extra:
        merged.update(extra)
    merged.update({key: value for key, value in fields.items() if value is not None})
    return merged


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    extra: Mapping[str, Any] | None = None,
    exc_info: Any = None,
    **fields: Any,
) -> None:
    if not logger.isEnabledFor(level):
        return
    logger.log(
        level,
        event,
        extra=_merge_extra(extra, event=event, **fields),
        exc_info=exc_info,
    )

INGEST_TOTAL = Counter(
    "memoryos_ingest_total",
    "Total messages ingested",
)

PAGE_TOTAL = Counter(
    "memoryos_page_total",
    "Total memory pages created",
    ["mode"],
)

PAGE_ERRORS_TOTAL = Counter(
    "memoryos_page_errors_total",
    "Total paging failures",
    ["stage"],
)

CONTEXT_BUILD_SECONDS = Histogram(
    "memoryos_context_build_seconds",
    "build_context latency in seconds",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

CONTEXT_TOKENS = Histogram(
    "memoryos_context_tokens",
    "Tokens in returned ContextPackage",
    buckets=(50, 100, 200, 500, 1000, 2000, 4000, 8000),
)

CONTEXT_BUDGET_USED_RATIO = Histogram(
    "memoryos_context_budget_used_ratio",
    "Ratio of estimated_tokens / budget",
    buckets=(0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0),
)

RETRIEVAL_HITS = Histogram(
    "memoryos_retrieval_hits",
    "Number of search hits returned",
    buckets=(0, 1, 2, 3, 5, 8, 10, 20),
)

EMBEDDING_SECONDS = Histogram(
    "memoryos_embedding_seconds",
    "Embedding call latency in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)

CORE_OPERATION_SECONDS = Histogram(
    "memoryos_core_operation_seconds",
    "Latency for core MemoryOS and xmuse operations",
    ["component", "operation", "status"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 60.0),
)

CORE_OPERATION_TOTAL = Counter(
    "memoryos_core_operation_total",
    "Total core MemoryOS and xmuse operations",
    ["component", "operation", "status"],
)

CORE_OPERATION_ERRORS_TOTAL = Counter(
    "memoryos_core_operation_errors_total",
    "Total core MemoryOS and xmuse operation failures",
    ["component", "operation", "error_type"],
)


def record_core_operation(
    *,
    component: str,
    operation: str,
    elapsed_s: float,
    status: str,
    error_type: str | None = None,
) -> None:
    CORE_OPERATION_SECONDS.labels(
        component=component,
        operation=operation,
        status=status,
    ).observe(elapsed_s)
    CORE_OPERATION_TOTAL.labels(
        component=component,
        operation=operation,
        status=status,
    ).inc()
    if error_type is not None:
        CORE_OPERATION_ERRORS_TOTAL.labels(
            component=component,
            operation=operation,
            error_type=error_type,
        ).inc()


@contextmanager
def timed_core_operation(
    *,
    component: str,
    operation: str,
    logger: logging.Logger | None = None,
    log_success: bool = False,
    **fields: Any,
) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        elapsed_s = time.perf_counter() - start
        error_type = type(exc).__name__
        record_core_operation(
            component=component,
            operation=operation,
            elapsed_s=elapsed_s,
            status="error",
            error_type=error_type,
        )
        if logger is not None:
            log_event(
                logger,
                logging.ERROR,
                "core_operation_failed",
                component=component,
                operation=operation,
                status="error",
                latency_ms=round(elapsed_s * 1000, 3),
                error_type=error_type,
                exc_info=True,
                **fields,
            )
        raise
    else:
        elapsed_s = time.perf_counter() - start
        record_core_operation(
            component=component,
            operation=operation,
            elapsed_s=elapsed_s,
            status="ok",
        )
        if logger is not None and log_success:
            log_event(
                logger,
                logging.INFO,
                "core_operation_completed",
                component=component,
                operation=operation,
                status="ok",
                latency_ms=round(elapsed_s * 1000, 3),
                **fields,
            )
