"""Tests for request context and structured logging.

Covers:
- Structured log fields (trace_id, request_id, session_id, event)
- Trace ID propagation across context boundaries and threads
- timed_core_operation success and error logging
- log_event format and field merging
- Middleware trace ID injection (unit-level and HTTP-level via TestClient)
- StructuredLoggingMiddleware emits required log fields per request
- log_event None-valued keyword fields are omitted from the record
- Instrumentation does not break existing functionality
"""

from __future__ import annotations

import logging
import threading
import time

import pytest

from memoryos_eval.memory.schemas import MessageCreate, Role
from memoryos_lite.observability import (
    current_observability_context,
    current_trace_id,
    log_event,
    observability_context,
    timed_core_operation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class CapturingHandler(logging.Handler):
    """Collects LogRecord instances emitted during a test."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def last(self) -> logging.LogRecord:
        assert self.records, "No log records captured"
        return self.records[-1]


# ---------------------------------------------------------------------------
# Context variable / trace ID propagation tests
# ---------------------------------------------------------------------------


class TestTraceIdPropagation:
    def test_current_trace_id_generates_hex_string(self) -> None:
        with observability_context():
            tid = current_trace_id()
        assert isinstance(tid, str)
        assert len(tid) == 32  # uuid4().hex is 32 hex chars

    def test_explicit_trace_id_is_preserved(self) -> None:
        with observability_context(trace_id="abc123") as ctx:
            assert ctx["trace_id"] == "abc123"
            assert current_trace_id() == "abc123"

    def test_trace_id_restored_after_context_exit(self) -> None:
        outer_tid = current_trace_id()
        with observability_context(trace_id="inner-trace"):
            assert current_trace_id() == "inner-trace"
        assert current_trace_id() == outer_tid

    def test_nested_contexts_isolate_trace_ids(self) -> None:
        with observability_context(trace_id="outer"):
            with observability_context(trace_id="inner") as inner_ctx:
                assert inner_ctx["trace_id"] == "inner"
            assert current_trace_id() == "outer"

    def test_trace_id_does_not_leak_across_threads(self) -> None:
        """Each thread must get its own independent trace ID."""
        results: dict[str, str] = {}

        def worker(name: str) -> None:
            with observability_context(trace_id=f"thread-{name}"):
                time.sleep(0.01)
                results[name] = current_trace_id()

        threads = [threading.Thread(target=worker, args=(str(i),)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(4):
            assert results[str(i)] == f"thread-{i}"

    def test_all_context_fields_set_and_returned(self) -> None:
        with observability_context(
            trace_id="t1",
            request_id="r1",
            session_id="s1",
        ) as ctx:
            assert ctx["trace_id"] == "t1"
            assert ctx["request_id"] == "r1"
            assert ctx["session_id"] == "s1"

    def test_current_observability_context_omits_none_fields(self) -> None:
        with observability_context(trace_id="only-trace"):
            ctx = current_observability_context()
        assert "trace_id" in ctx
        assert "request_id" not in ctx
        assert "session_id" not in ctx


# ---------------------------------------------------------------------------
# log_event structured field tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def capturing_logger():
    """Return (logger, handler) pair; handler is removed after the test."""
    handler = CapturingHandler()
    handler.setLevel(logging.DEBUG)
    lg = logging.getLogger("test.observability")
    lg.setLevel(logging.DEBUG)
    lg.addHandler(handler)
    yield lg, handler
    lg.removeHandler(handler)


class TestLogEventStructuredFields:
    def test_log_event_includes_trace_id(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        with observability_context(trace_id="trace-log-test"):
            log_event(lg, logging.INFO, "test_event")
        record = handler.last()
        assert record.trace_id == "trace-log-test"  # type: ignore[attr-defined]

    def test_log_event_includes_event_field(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        with observability_context(trace_id="t"):
            log_event(lg, logging.INFO, "my_event_name")
        record = handler.last()
        assert record.event == "my_event_name"  # type: ignore[attr-defined]

    def test_log_event_message_equals_event_name(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        with observability_context(trace_id="t"):
            log_event(lg, logging.INFO, "the_event_message")
        assert handler.last().getMessage() == "the_event_message"

    def test_log_event_includes_keyword_fields(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        with observability_context(trace_id="t"):
            log_event(lg, logging.WARNING, "ev", component="engine", status="ok")
        record = handler.last()
        assert record.component == "engine"  # type: ignore[attr-defined]
        assert record.status == "ok"  # type: ignore[attr-defined]

    def test_log_event_includes_all_context_fields(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        with observability_context(
            trace_id="t2",
            request_id="r2",
            session_id="s2",
        ):
            log_event(lg, logging.INFO, "full_context_event")
        record = handler.last()
        assert record.trace_id == "t2"  # type: ignore[attr-defined]
        assert record.request_id == "r2"  # type: ignore[attr-defined]
        assert record.session_id == "s2"  # type: ignore[attr-defined]

    def test_log_event_extra_mapping_merged(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        with observability_context(trace_id="t"):
            log_event(lg, logging.INFO, "ev", extra={"custom_key": "custom_val"})
        assert handler.last().custom_key == "custom_val"  # type: ignore[attr-defined]

    def test_log_event_respects_log_level_filter(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        lg.setLevel(logging.ERROR)
        with observability_context(trace_id="t"):
            log_event(lg, logging.DEBUG, "should_not_appear")
        assert not handler.records

    def test_log_event_with_exc_info_attaches_exception(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        try:
            raise ValueError("test exc")
        except ValueError:
            with observability_context(trace_id="exc-trace"):
                log_event(lg, logging.ERROR, "caught_error", exc_info=True)
        assert handler.records
        assert handler.last().exc_info is not None


# ---------------------------------------------------------------------------
# timed_core_operation context manager tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def timed_logger():
    handler = CapturingHandler()
    handler.setLevel(logging.DEBUG)
    lg = logging.getLogger("test.timed_op")
    lg.setLevel(logging.DEBUG)
    lg.addHandler(handler)
    yield lg, handler
    lg.removeHandler(handler)


class TestTimedCoreOperation:
    def test_success_logs_when_log_success_true(self, timed_logger) -> None:
        lg, handler = timed_logger
        with timed_core_operation(
            component="log_comp",
            operation="log_op",
            logger=lg,
            log_success=True,
        ):
            pass
        assert handler.records, "Expected a success log record"
        record = handler.last()
        assert record.getMessage() == "core_operation_completed"
        assert record.status == "ok"  # type: ignore[attr-defined]
        assert record.component == "log_comp"  # type: ignore[attr-defined]
        assert record.operation == "log_op"  # type: ignore[attr-defined]
        assert hasattr(record, "latency_ms")

    def test_success_no_log_when_log_success_false(self, timed_logger) -> None:
        lg, handler = timed_logger
        with timed_core_operation(
            component="nolog_comp",
            operation="nolog_op",
            logger=lg,
            log_success=False,
        ):
            pass
        assert not handler.records

    def test_error_logs_failure_event(self, timed_logger) -> None:
        lg, handler = timed_logger
        with pytest.raises(KeyError):
            with timed_core_operation(
                component="errlog_comp",
                operation="errlog_op",
                logger=lg,
            ):
                raise KeyError("missing")
        assert handler.records
        record = handler.last()
        assert record.getMessage() == "core_operation_failed"
        assert record.status == "error"  # type: ignore[attr-defined]
        assert record.error_type == "KeyError"  # type: ignore[attr-defined]
        assert hasattr(record, "latency_ms")

    def test_error_log_includes_trace_id(self, timed_logger) -> None:
        lg, handler = timed_logger
        with observability_context(trace_id="trace-timed"):
            with pytest.raises(OSError):
                with timed_core_operation(
                    component="trace_comp",
                    operation="trace_op",
                    logger=lg,
                ):
                    raise OSError("disk full")
        assert handler.last().trace_id == "trace-timed"  # type: ignore[attr-defined]

    def test_timed_operation_body_result_is_unaffected(self) -> None:
        result = []
        with timed_core_operation(component="reg_comp", operation="reg_op"):
            result.append(42)
        assert result == [42]


# ---------------------------------------------------------------------------
# Middleware trace ID injection (unit-level simulation)
# ---------------------------------------------------------------------------


class TestMiddlewareTraceIdInjection:
    def test_request_id_middleware_binds_trace_id(self) -> None:
        from uuid import uuid4

        request_id = uuid4().hex
        with observability_context(request_id=request_id, trace_id=request_id) as ctx:
            assert ctx["trace_id"] == request_id
            assert ctx["request_id"] == request_id

    def test_request_id_middleware_restores_context_after_request(self) -> None:
        from uuid import uuid4

        outer_trace = current_trace_id()
        request_id = uuid4().hex
        with observability_context(request_id=request_id, trace_id=request_id):
            assert current_trace_id() == request_id
        assert current_trace_id() == outer_trace


# ---------------------------------------------------------------------------
# Regression: instrumentation does not break existing functionality
# ---------------------------------------------------------------------------


class TestInstrumentationRegression:
    def test_observability_context_yields_dict(self) -> None:
        with observability_context(trace_id="reg-test") as ctx:
            assert isinstance(ctx, dict)
            assert ctx["trace_id"] == "reg-test"

    def test_ingest_does_not_raise_with_observability_context(self, service) -> None:
        session = service.create_session("regression")
        with observability_context(trace_id="reg-ingest", session_id=str(session.id)):
            service.ingest(session.id, MessageCreate(role=Role.USER, content="regression check"))

    def test_build_context_does_not_raise_with_observability_context(self, service) -> None:
        session = service.create_session("regression-ctx")
        service.ingest(
            session.id, MessageCreate(role=Role.USER, content="regression context build")
        )
        with observability_context(trace_id="reg-ctx", session_id=str(session.id)):
            result = service.build_context(session.id, "regression query", budget=500)
        assert result is not None


# ---------------------------------------------------------------------------
# log_event None-field filtering
# ---------------------------------------------------------------------------


class TestLogEventNoneFieldFiltering:
    def test_none_keyword_fields_omitted_from_record(self, capturing_logger) -> None:
        lg, handler = capturing_logger
        with observability_context(trace_id="t"):
            log_event(lg, logging.INFO, "ev", optional_field=None, present_field="yes")
        record = handler.last()
        # None-valued fields must not appear on the record
        assert not hasattr(record, "optional_field")
        assert record.present_field == "yes"  # type: ignore[attr-defined]

    def test_extra_mapping_none_values_are_passed_through(self, capturing_logger) -> None:
        """extra dict is merged verbatim; only **fields kwargs filter None."""
        lg, handler = capturing_logger
        with observability_context(trace_id="t"):
            log_event(lg, logging.INFO, "ev", extra={"explicit_none": None})
        record = handler.last()
        # extra values are merged as-is (no None filtering on the extra path)
        assert hasattr(record, "explicit_none")


# ---------------------------------------------------------------------------
# StructuredLoggingMiddleware HTTP-level tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_client():
    """Provide a Starlette TestClient wired to the MemoryOS FastAPI app."""
    from fastapi.testclient import TestClient

    from memoryos_lite.api.app import app

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestStructuredLoggingMiddleware:
    def test_response_echoes_x_request_id_header(self, test_client) -> None:
        resp = test_client.get("/health", headers={"X-Request-Id": "req-echo-test"})
        assert resp.headers.get("X-Request-Id") == "req-echo-test"

    def test_response_generates_x_request_id_when_absent(self, test_client) -> None:
        resp = test_client.get("/health")
        rid = resp.headers.get("X-Request-Id")
        assert rid and len(rid) == 32  # uuid4().hex

    def test_structured_log_emitted_per_request(self, test_client) -> None:
        handler = CapturingHandler()
        handler.setLevel(logging.DEBUG)
        mw_logger = logging.getLogger("memoryos_lite.middleware")
        mw_logger.setLevel(logging.DEBUG)
        mw_logger.addHandler(handler)
        try:
            test_client.get("/health", headers={"X-Request-Id": "log-field-test"})
        finally:
            mw_logger.removeHandler(handler)

        assert handler.records, "StructuredLoggingMiddleware must emit at least one log record"
        record = handler.last()
        assert record.getMessage() == "request"
        assert record.method == "GET"  # type: ignore[attr-defined]
        assert record.path == "/health"  # type: ignore[attr-defined]
        assert record.status == 200  # type: ignore[attr-defined]
        assert hasattr(record, "latency_ms")
        assert hasattr(record, "request_id")

    def test_structured_log_request_id_matches_header(self, test_client) -> None:
        handler = CapturingHandler()
        handler.setLevel(logging.DEBUG)
        mw_logger = logging.getLogger("memoryos_lite.middleware")
        mw_logger.setLevel(logging.DEBUG)
        mw_logger.addHandler(handler)
        try:
            test_client.get("/health", headers={"X-Request-Id": "match-rid-123"})
        finally:
            mw_logger.removeHandler(handler)

        record = handler.last()
        assert record.request_id == "match-rid-123"  # type: ignore[attr-defined]

    def test_structured_log_latency_ms_is_non_negative(self, test_client) -> None:
        handler = CapturingHandler()
        handler.setLevel(logging.DEBUG)
        mw_logger = logging.getLogger("memoryos_lite.middleware")
        mw_logger.setLevel(logging.DEBUG)
        mw_logger.addHandler(handler)
        try:
            test_client.get("/health")
        finally:
            mw_logger.removeHandler(handler)

        record = handler.last()
        assert record.latency_ms >= 0  # type: ignore[attr-defined]
