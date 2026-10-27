"""Optional OpenTelemetry tracing for the HTTP API.

Off unless ``MEMORYOS_OTEL_ENABLED=1`` or a standard ``OTEL_EXPORTER_OTLP_ENDPOINT`` /
``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` is set (``MEMORYOS_OTEL_ENABLED=0`` wins over both).
Off, nothing from OpenTelemetry is imported. On, :func:`setup` adds:

* one SERVER span per request that continues the caller's W3C ``traceparent`` (FastAPI
  instrumentation, without the ASGI ``receive``/``send`` sub-spans and without ``/health``);
* one span per LangGraph run, graph node and chat-model call (OpenInference), with prompts and
  completions hidden unless ``MEMORYOS_OTEL_CAPTURE_CONTENT=1``;
* the trace id as the structured logs' ``trace_id``, so log lines and traces match.

Spans go over OTLP/HTTP to the endpoint the standard variables name, else
``http://localhost:6006`` (Phoenix), tagged for the Phoenix project ``MEMORYOS_OTEL_PROJECT``
(default ``xmuse``). The packages come with the ``otel`` extra; enabled without them, the
service logs a warning and runs untraced.
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from memoryos_lite import __version__
from memoryos_lite.observability import observability_context

logger = logging.getLogger(__name__)

SERVICE_NAME = "memoryos-lite"
DEFAULT_ENDPOINT = "http://localhost:6006"
_TRUE = {"1", "true", "yes", "on"}
_ENDPOINT_VARS = ("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def enabled() -> bool:
    explicit = os.environ.get("MEMORYOS_OTEL_ENABLED", "").strip()
    if explicit:
        return explicit.lower() in _TRUE
    return any(os.environ.get(name) for name in _ENDPOINT_VARS)


def project() -> str:
    return os.environ.get("MEMORYOS_OTEL_PROJECT", "").strip() or "xmuse"


class TraceIdLogMiddleware:
    """Make the current span's trace id the log context's ``trace_id`` for the rest of the request.

    Installed right inside ``RequestIdMiddleware``, which sets ``trace_id`` to the request id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        if scope["type"] != "http" or not context.is_valid:
            await self.app(scope, receive, send)
            return
        with observability_context(trace_id=format(context.trace_id, "032x")):
            await self.app(scope, receive, send)


def _add_log_bridge(app: Any) -> None:
    from starlette.middleware import Middleware

    from memoryos_lite.middleware import RequestIdMiddleware

    classes = [m.cls for m in app.user_middleware]  # outermost first
    at = classes.index(RequestIdMiddleware) + 1 if RequestIdMiddleware in classes else 0
    app.user_middleware.insert(at, Middleware(TraceIdLogMiddleware))


def setup(app: Any, exporter: Any = None) -> bool:
    """Trace ``app`` when enabled; returns whether it did.

    ``exporter`` replaces the OTLP exporter and ships each span as it ends (tests).
    Call before the app serves its first request.
    """

    if not enabled():
        return False
    try:
        from openinference.instrumentation import TraceConfig
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    except ImportError:
        logger.warning(
            "tracing is enabled but the otel extra is not installed; running untraced "
            "(pip install 'memoryos-lite[otel]')"
        )
        return False

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": SERVICE_NAME,
                "service.version": __version__,
                "openinference.project.name": project(),
            }
        )
    )
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        # None lets the exporter read the standard variables itself; without them, Phoenix
        endpoint = None if any(os.environ.get(n) for n in _ENDPOINT_VARS) else DEFAULT_ENDPOINT
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint and endpoint + "/v1/traces"))
        )
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="/health$",  # liveness probes (container healthchecks every 30 s)
        exclude_spans=["receive", "send"],
    )
    capture = _flag("MEMORYOS_OTEL_CAPTURE_CONTENT")
    LangChainInstrumentor().instrument(
        tracer_provider=provider,
        config=TraceConfig(hide_inputs=not capture, hide_outputs=not capture),
    )
    _add_log_bridge(app)
    atexit.register(provider.shutdown)
    logger.info("tracing on: project %s, content %s", project(), "shown" if capture else "hidden")
    return True
