"""Request context and structured logging for MemoryOS Lite.

The request id, trace id and session id travel in context variables so log
records and trace events can carry them without threading them through calls.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

_TRACE_ID: ContextVar[str | None] = ContextVar("memoryos_trace_id", default=None)
_REQUEST_ID: ContextVar[str | None] = ContextVar("memoryos_request_id", default=None)
_SESSION_ID: ContextVar[str | None] = ContextVar("memoryos_session_id", default=None)


def current_trace_id() -> str:
    trace_id = _TRACE_ID.get()
    if trace_id:
        return trace_id
    trace_id = uuid4().hex
    _TRACE_ID.set(trace_id)
    return trace_id


def current_observability_context() -> dict[str, str]:
    context = {
        "trace_id": current_trace_id(),
        "request_id": _REQUEST_ID.get(),
        "session_id": _SESSION_ID.get(),
    }
    return {key: value for key, value in context.items() if value}


@contextmanager
def observability_context(
    *,
    trace_id: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[dict[str, str]]:
    trace_token = _TRACE_ID.set(trace_id or _TRACE_ID.get() or uuid4().hex)
    request_token = _REQUEST_ID.set(request_id) if request_id is not None else None
    session_token = _SESSION_ID.set(session_id) if session_id is not None else None
    try:
        yield current_observability_context()
    finally:
        _TRACE_ID.reset(trace_token)
        if request_token is not None:
            _REQUEST_ID.reset(request_token)
        if session_token is not None:
            _SESSION_ID.reset(session_token)


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


@contextmanager
def timed_core_operation(
    *,
    component: str,
    operation: str,
    logger: logging.Logger | None = None,
    log_success: bool = False,
    **fields: Any,
) -> Iterator[None]:
    """Log a failed operation (and, with ``log_success``, a completed one) with its latency."""

    start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        if logger is not None:
            log_event(
                logger,
                logging.ERROR,
                "core_operation_failed",
                component=component,
                operation=operation,
                status="error",
                latency_ms=round((time.perf_counter() - start) * 1000, 3),
                error_type=type(exc).__name__,
                exc_info=True,
                **fields,
            )
        raise
    else:
        if logger is not None and log_success:
            log_event(
                logger,
                logging.INFO,
                "core_operation_completed",
                component=component,
                operation=operation,
                status="ok",
                latency_ms=round((time.perf_counter() - start) * 1000, 3),
                **fields,
            )
