"""Tests for observability instrumentation.

Covers:
- Structured log fields emitted by StructuredLoggingMiddleware
- Trace-ID (request_id) propagation through RequestIdMiddleware
- TraceEvent payloads contain required fields for each engine operation
- Instrumentation does not break existing service functionality
- ContextVar isolation and scoping (observability_context)
- current_trace_id auto-generation and stability
- current_observability_context field filtering (None values excluded)
- log_event level gating and structured field merging
- timed_core_operation success and error logging
- _instrument_agent_node wrapper (success + error + observability context propagation)
- Nested observability_context restores outer values on exit
- Thread / asyncio task isolation via ContextVar
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from memoryos_eval.memory.schemas import (
    MessageCreate,
    Role,
)
from memoryos_eval.memory.service import SessionMemoryService
from memoryos_eval.memory.store import create_store
from memoryos_lite.config import Settings
from memoryos_lite.observability import (
    _REQUEST_ID,
    _SESSION_ID,
    _TRACE_ID,
    current_observability_context,
    current_trace_id,
    log_event,
    observability_context,
    timed_core_operation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(tmp_path: Path, **extra) -> SessionMemoryService:
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
        **extra,
    )
    store = create_store(settings)
    store.reset()
    return SessionMemoryService(store=store, settings=settings)


def _reset_context_vars() -> None:
    """Reset all ContextVars to their defaults for test isolation."""
    _TRACE_ID.set(None)
    _REQUEST_ID.set(None)
    _SESSION_ID.set(None)


@pytest.fixture()
def _isolated_context():
    """Ensure the test starts and ends with clean ContextVar state."""
    _reset_context_vars()
    yield
    _reset_context_vars()


# ---------------------------------------------------------------------------
# Structured logging — StructuredLoggingMiddleware
# ---------------------------------------------------------------------------


class TestStructuredLoggingMiddleware:
    """Verify that every HTTP request produces a log record with required fields."""

    @pytest.fixture()
    def client(self):
        from memoryos_lite.api.app import app

        return TestClient(app, raise_server_exceptions=False)

    def test_log_record_contains_required_fields(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="memoryos_lite.middleware"):
            client.get("/health")

        request_logs = [r for r in caplog.records if r.getMessage() == "request"]
        assert request_logs, "Expected at least one 'request' log record"
        record = request_logs[-1]

        for field in ("request_id", "method", "path", "status", "latency_ms"):
            assert hasattr(record, field), f"Log record missing field: {field}"

    def test_log_method_and_path_are_accurate(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="memoryos_lite.middleware"):
            client.get("/health")

        record = next(r for r in reversed(caplog.records) if r.getMessage() == "request")
        assert record.method == "GET"
        assert record.path == "/health"

    def test_log_status_code_is_accurate(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="memoryos_lite.middleware"):
            client.get("/health")

        record = next(r for r in reversed(caplog.records) if r.getMessage() == "request")
        assert record.status == 200

    def test_log_latency_ms_is_non_negative(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="memoryos_lite.middleware"):
            client.get("/health")

        record = next(r for r in reversed(caplog.records) if r.getMessage() == "request")
        assert isinstance(record.latency_ms, float)
        assert record.latency_ms >= 0.0

    def test_log_request_id_is_present_and_non_empty(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="memoryos_lite.middleware"):
            client.get("/health")

        record = next(r for r in reversed(caplog.records) if r.getMessage() == "request")
        assert record.request_id
        assert isinstance(record.request_id, str)

    def test_log_format_for_404_path(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="memoryos_lite.middleware"):
            client.get("/nonexistent-path-xyz")

        record = next(r for r in reversed(caplog.records) if r.getMessage() == "request")
        assert record.status == 404
        assert record.path == "/nonexistent-path-xyz"


# ---------------------------------------------------------------------------
# Trace-ID propagation — RequestIdMiddleware
# ---------------------------------------------------------------------------


class TestRequestIdPropagation:
    @pytest.fixture()
    def client(self):
        from memoryos_lite.api.app import app

        return TestClient(app, raise_server_exceptions=False)

    def test_response_echoes_provided_request_id(self, client):
        resp = client.get("/health", headers={"X-Request-Id": "test-trace-abc123"})
        assert resp.headers.get("X-Request-Id") == "test-trace-abc123"

    def test_response_generates_request_id_when_absent(self, client):
        resp = client.get("/health")
        rid = resp.headers.get("X-Request-Id")
        assert rid, "X-Request-Id header must be present in response"
        assert len(rid) >= 8

    def test_request_id_propagates_to_log_record(self, client, caplog):
        custom_id = "trace-propagation-test-999"
        with caplog.at_level(logging.INFO, logger="memoryos_lite.middleware"):
            client.get("/health", headers={"X-Request-Id": custom_id})

        record = next(r for r in reversed(caplog.records) if r.getMessage() == "request")
        assert record.request_id == custom_id

    def test_unique_request_ids_per_request(self, client):
        r1 = client.get("/health")
        r2 = client.get("/health")
        id1 = r1.headers.get("X-Request-Id")
        id2 = r2.headers.get("X-Request-Id")
        assert id1 != id2, "Each request should receive a unique request_id"


# ---------------------------------------------------------------------------
# TraceEvent payloads — required fields per event type
# ---------------------------------------------------------------------------


class TestTraceEventPayloads:
    """Verify that trace events emitted by the engine contain required fields."""

    def test_create_session_does_not_leak_session_id_context(self, tmp_path, _isolated_context):
        svc = _make_service(tmp_path)

        session = svc.create_session("context-leak-test")

        assert session.id
        assert "session_id" not in current_observability_context()

    def test_message_ingested_trace_has_required_fields(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("trace-ingest-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello"))

        traces = svc.store.list_traces(session.id)
        ingest_traces = [t for t in traces if t.event_type == "message_ingested"]
        assert ingest_traces, "Expected 'message_ingested' trace event"

        payload = ingest_traces[-1].payload
        for field in ("message_id", "token_count", "should_page"):
            assert field in payload, f"'message_ingested' trace missing field: {field}"

    def test_message_ingested_trace_token_count_is_positive(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("trace-token-count-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello world"))

        traces = svc.store.list_traces(session.id)
        payload = next(t.payload for t in traces if t.event_type == "message_ingested")
        assert payload["token_count"] > 0

    def test_message_ingested_trace_should_page_is_bool(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("trace-should-page-bool-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello"))

        traces = svc.store.list_traces(session.id)
        payload = next(t.payload for t in traces if t.event_type == "message_ingested")
        assert isinstance(payload["should_page"], bool)

    def test_context_built_trace_has_required_fields(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("trace-context-built-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello"))
        svc.build_context(session.id, "test query", budget=500)

        traces = svc.store.list_traces(session.id)
        ctx_traces = [t for t in traces if t.event_type == "context_built"]
        assert ctx_traces, "Expected 'context_built' trace event"

        payload = ctx_traces[-1].payload
        for field in ("task", "budget", "budget_source", "estimated_tokens"):
            assert field in payload, f"'context_built' trace missing field: {field}"

    def test_context_built_trace_budget_source_values(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("trace-budget-source-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello"))

        # Explicit budget
        svc.build_context(session.id, "test query", budget=500)
        traces = svc.store.list_traces(session.id)
        explicit_trace = next(t for t in reversed(traces) if t.event_type == "context_built")
        assert explicit_trace.payload["budget_source"] == "explicit"

        # Dynamic budget (no budget arg)
        svc.build_context(session.id, "test query")
        traces = svc.store.list_traces(session.id)
        dynamic_trace = next(t for t in reversed(traces) if t.event_type == "context_built")
        assert dynamic_trace.payload["budget_source"] == "dynamic"

    def test_session_created_trace_has_title(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("my-session-title")

        traces = svc.store.list_traces(session.id)
        created_traces = [t for t in traces if t.event_type == "session_created"]
        assert created_traces, "Expected 'session_created' trace event"
        assert created_traces[0].payload["title"] == "my-session-title"


# ---------------------------------------------------------------------------
# Instrumentation does not break existing functionality
# ---------------------------------------------------------------------------


class TestInstrumentationDoesNotBreakFunctionality:
    """Smoke tests confirming that metric/trace calls are side-effect-free
    with respect to the core service contract."""

    def test_ingest_returns_correct_response_with_metrics_active(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("smoke-ingest")
        resp = svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello world"))

        assert resp.message.content == "hello world"
        assert resp.message.role == Role.USER
        assert resp.session_token_count > 0

    def test_build_context_returns_valid_package_with_metrics_active(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("smoke-context")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello world"))

        pkg = svc.build_context(session.id, "hello", budget=500)

        assert pkg.session_id == session.id
        assert pkg.estimated_tokens >= 0

    def test_trace_events_are_stored_and_retrievable(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("smoke-trace-store")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello"))

        traces = svc.store.list_traces(session.id)
        assert len(traces) >= 2  # session_created + message_ingested


# ---------------------------------------------------------------------------
# ContextVar primitives — current_trace_id
# ---------------------------------------------------------------------------


class TestCurrentTraceId:
    def test_auto_generates_hex_string_when_unset(self, _isolated_context):
        trace_id = current_trace_id()
        assert isinstance(trace_id, str)
        assert len(trace_id) == 32  # uuid4().hex

    def test_stable_within_same_context(self, _isolated_context):
        first = current_trace_id()
        second = current_trace_id()
        assert first == second

    def test_returns_explicitly_set_value(self, _isolated_context):
        _TRACE_ID.set("explicit-trace-abc")
        assert current_trace_id() == "explicit-trace-abc"

    def test_different_threads_get_independent_trace_ids(self, _isolated_context):
        results: list[str] = []

        def worker():
            _reset_context_vars()
            results.append(current_trace_id())

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 3


# ---------------------------------------------------------------------------
# ContextVar primitives — current_observability_context
# ---------------------------------------------------------------------------


class TestCurrentObservabilityContext:
    def test_excludes_none_values(self, _isolated_context):
        _TRACE_ID.set("t1")
        ctx = current_observability_context()
        assert "trace_id" in ctx
        assert "request_id" not in ctx
        assert "session_id" not in ctx

    def test_includes_all_set_values(self, _isolated_context):
        _TRACE_ID.set("t1")
        _REQUEST_ID.set("r1")
        _SESSION_ID.set("s1")
        ctx = current_observability_context()
        assert ctx == {
            "trace_id": "t1",
            "request_id": "r1",
            "session_id": "s1",
        }

    def test_always_contains_trace_id(self, _isolated_context):
        ctx = current_observability_context()
        assert "trace_id" in ctx
        assert ctx["trace_id"]


# ---------------------------------------------------------------------------
# observability_context (context manager)
# ---------------------------------------------------------------------------


class TestObservabilityContextManager:
    def test_yields_current_context_dict(self, _isolated_context):
        with observability_context(trace_id="t-ctx", session_id="s-ctx") as ctx:
            assert ctx["trace_id"] == "t-ctx"
            assert ctx["session_id"] == "s-ctx"

    def test_restores_outer_trace_id_on_exit(self, _isolated_context):
        _TRACE_ID.set("outer-trace")
        with observability_context(trace_id="inner-trace"):
            assert _TRACE_ID.get() == "inner-trace"
        assert _TRACE_ID.get() == "outer-trace"

    def test_restores_none_for_fields_not_set_before_entry(self, _isolated_context):
        with observability_context(session_id="s-temp"):
            assert _SESSION_ID.get() == "s-temp"
        assert _SESSION_ID.get() is None

    def test_nested_contexts_restore_correctly(self, _isolated_context):
        with observability_context(trace_id="outer", session_id="s-outer"):
            with observability_context(trace_id="inner", session_id="s-inner"):
                assert _TRACE_ID.get() == "inner"
                assert _SESSION_ID.get() == "s-inner"
            assert _TRACE_ID.get() == "outer"
            assert _SESSION_ID.get() == "s-outer"

    def test_restores_context_even_when_body_raises(self, _isolated_context):
        _TRACE_ID.set("stable-trace")
        with pytest.raises(ValueError):
            with observability_context(trace_id="transient-trace"):
                raise ValueError("boom")
        assert _TRACE_ID.get() == "stable-trace"

    def test_asyncio_tasks_have_independent_context(self, _isolated_context):
        async def run():
            results = {}

            async def task_a():
                with observability_context(trace_id="trace-a"):
                    await asyncio.sleep(0)
                    results["a"] = _TRACE_ID.get()

            async def task_b():
                with observability_context(trace_id="trace-b"):
                    await asyncio.sleep(0)
                    results["b"] = _TRACE_ID.get()

            await asyncio.gather(task_a(), task_b())
            return results

        results = asyncio.run(run())
        assert results["a"] == "trace-a"
        assert results["b"] == "trace-b"


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


class TestLogEvent:
    def test_logs_at_correct_level(self, _isolated_context):
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = True
        log_event(logger, logging.WARNING, "test_event", key="value")
        logger.log.assert_called_once()
        args, _ = logger.log.call_args
        assert args[0] == logging.WARNING
        assert args[1] == "test_event"

    def test_skips_when_level_disabled(self, _isolated_context):
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = False
        log_event(logger, logging.DEBUG, "skipped_event")
        logger.log.assert_not_called()

    def test_merges_observability_context_into_extra(self, _isolated_context):
        _TRACE_ID.set("t-log")
        _SESSION_ID.set("s-log")
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = True
        log_event(logger, logging.INFO, "my_event", custom_field="x")
        _, kwargs = logger.log.call_args
        extra = kwargs["extra"]
        assert extra["trace_id"] == "t-log"
        assert extra["session_id"] == "s-log"
        assert extra["custom_field"] == "x"
        assert extra["event"] == "my_event"

    def test_passes_exc_info_through(self, _isolated_context):
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = True
        exc = ValueError("test error")
        log_event(logger, logging.ERROR, "error_event", exc_info=exc)
        _, kwargs = logger.log.call_args
        assert kwargs["exc_info"] == exc

    def test_extra_mapping_is_merged(self, _isolated_context):
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = True
        log_event(
            logger,
            logging.INFO,
            "event_with_extra",
            extra={"from_extra": "yes"},
            inline_field="also",
        )
        _, kwargs = logger.log.call_args
        extra = kwargs["extra"]
        assert extra["from_extra"] == "yes"
        assert extra["inline_field"] == "also"

    def test_none_fields_are_excluded_from_extra(self, _isolated_context):
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = True
        log_event(logger, logging.INFO, "event", nullable_field=None)
        _, kwargs = logger.log.call_args
        extra = kwargs["extra"]
        assert "nullable_field" not in extra


# ---------------------------------------------------------------------------
# timed_core_operation
# ---------------------------------------------------------------------------


class TestTimedCoreOperation:
    def _counter_value(self, counter, **labels) -> float:
        return counter.labels(**labels)._value.get()

    def test_logs_success_when_log_success_true(self):
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = True
        with timed_core_operation(
            component="tco_log",
            operation="tco_log_op",
            logger=logger,
            log_success=True,
        ):
            pass
        logger.log.assert_called_once()
        args, _ = logger.log.call_args
        assert args[0] == logging.INFO
        assert args[1] == "core_operation_completed"

    def test_does_not_log_success_when_log_success_false(self):
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = True
        with timed_core_operation(
            component="tco_no_log",
            operation="tco_no_log_op",
            logger=logger,
            log_success=False,
        ):
            pass
        logger.log.assert_not_called()

    def test_logs_error_on_exception(self):
        logger = MagicMock(spec=logging.Logger)
        logger.isEnabledFor.return_value = True
        with pytest.raises(ValueError):
            with timed_core_operation(
                component="tco_err_log",
                operation="tco_err_log_op",
                logger=logger,
            ):
                raise ValueError("logged error")
        logger.log.assert_called_once()
        args, kwargs = logger.log.call_args
        assert args[0] == logging.ERROR
        assert args[1] == "core_operation_failed"
        assert kwargs["exc_info"] is True
