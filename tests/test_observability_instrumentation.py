"""Tests for observability instrumentation.

Covers:
- Structured log fields emitted by StructuredLoggingMiddleware
- Prometheus metrics accuracy (INGEST_TOTAL, PAGE_TOTAL, PAGE_ERRORS_TOTAL,
  CONTEXT_BUILD_SECONDS, CONTEXT_TOKENS, CONTEXT_BUDGET_USED_RATIO,
  RETRIEVAL_HITS, EMBEDDING_SECONDS)
- Trace-ID (request_id) propagation through RequestIdMiddleware
- TraceEvent payloads contain required fields for each engine operation
- Instrumentation does not break existing service functionality
- ContextVar isolation and scoping (observability_context, bind_observability_context)
- current_trace_id auto-generation and stability
- current_observability_context field filtering (None values excluded)
- log_event level gating and structured field merging
- record_core_operation Prometheus counter/histogram increments
- timed_core_operation success and error paths
- _instrument_agent_node wrapper (success + error + observability context propagation)
- Nested observability_context restores outer values on exit
- Thread / asyncio task isolation via ContextVar
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.observability import (
    _GRAPH_ID,
    _LANE_ID,
    _REQUEST_ID,
    _SESSION_ID,
    _TRACE_ID,
    CONTEXT_BUDGET_USED_RATIO,
    CONTEXT_BUILD_SECONDS,
    CONTEXT_TOKENS,
    CORE_OPERATION_ERRORS_TOTAL,
    CORE_OPERATION_SECONDS,
    CORE_OPERATION_TOTAL,
    EMBEDDING_SECONDS,
    INGEST_TOTAL,
    PAGE_ERRORS_TOTAL,
    PAGE_TOTAL,
    RETRIEVAL_HITS,
    bind_observability_context,
    current_observability_context,
    current_request_id,
    current_trace_id,
    log_event,
    observability_context,
    record_core_operation,
    timed_core_operation,
)
from memoryos_lite.schemas import (
    MemoryPage,
    MemoryPageDraft,
    MemoryPatch,
    MessageCreate,
    PatchOperation,
    Role,
)
from memoryos_lite.store import create_store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(tmp_path: Path, **extra) -> MemoryOSService:
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        rot_safe_budget=12,
        recent_message_limit=2,
        memoryos_memory_arch="v1",
        memoryos_paging_mode="heuristic",
        memoryos_recall_pipeline="v1",
        **extra,
    )
    store = create_store(settings)
    store.reset()
    return MemoryOSService(store=store, settings=settings)


def _reset_context_vars() -> None:
    """Reset all ContextVars to their defaults for test isolation."""
    _TRACE_ID.set(None)
    _REQUEST_ID.set(None)
    _SESSION_ID.set(None)
    _LANE_ID.set(None)
    _GRAPH_ID.set(None)


@pytest.fixture()
def _isolated_context():
    """Ensure the test starts and ends with clean ContextVar state."""
    _reset_context_vars()
    yield
    _reset_context_vars()


def _metric_value(metric, labels: dict[str, str] | None = None) -> float:
    """Read the current value of a prometheus Counter (total sample).

    Uses REGISTRY.get_sample_value which is the official prometheus_client
    test API and works across all metric types.
    """
    name = metric._name + "_total"
    value = REGISTRY.get_sample_value(name, labels or {})
    if value is None:
        # Counter may not have been incremented yet — treat as 0
        return 0.0
    return value


def _histogram_count(metric, labels: dict[str, str] | None = None) -> float:
    """Return the observation count of a Histogram."""
    name = metric._name + "_count"
    value = REGISTRY.get_sample_value(name, labels or {})
    if value is None:
        return 0.0
    return value


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
# Prometheus metrics — INGEST_TOTAL
# ---------------------------------------------------------------------------


class TestIngestTotalMetric:
    def test_ingest_increments_counter(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("ingest-metric-test")

        before = _metric_value(INGEST_TOTAL)
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello world"))
        after = _metric_value(INGEST_TOTAL)

        assert after == before + 1

    def test_ingest_increments_once_per_call(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("ingest-multi-metric")

        before = _metric_value(INGEST_TOTAL)
        for i in range(5):
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=f"msg {i}"))
        after = _metric_value(INGEST_TOTAL)

        assert after == before + 5


# ---------------------------------------------------------------------------
# Prometheus metrics — PAGE_TOTAL and PAGE_ERRORS_TOTAL
# ---------------------------------------------------------------------------


class TestPageMetrics:
    def test_page_total_increments_on_successful_page(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("page-metric-test")
        # Force paging threshold to be very low
        svc.settings.rot_safe_budget = 1

        before = _metric_value(PAGE_TOTAL, {"mode": "heuristic"})
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
            "技术栈选择 LangGraph 和 FastAPI。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        svc.page(session.id)
        after = _metric_value(PAGE_TOTAL, {"mode": "heuristic"})

        assert after >= before + 1

    def test_page_errors_total_increments_on_verify_failure(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("page-error-metric-test")

        before = _metric_value(PAGE_ERRORS_TOTAL, {"stage": "verify"})

        # Inject a draft with an invalid source_message_id to trigger verify failure
        bad_draft = MemoryPageDraft(
            title="Bad Draft",
            summary="This draft has an invalid source ref.",
            facts=["some fact"],
            source_message_ids=["nonexistent_msg_id"],
        )
        with patch.object(
            svc.paging_agent,
            "create_drafts",
            return_value=([bad_draft], "heuristic", None),
        ):
            svc.page(session.id)

        after = _metric_value(PAGE_ERRORS_TOTAL, {"stage": "verify"})
        assert after >= before + 1


# ---------------------------------------------------------------------------
# Prometheus metrics — CONTEXT_BUILD_SECONDS, CONTEXT_TOKENS, CONTEXT_BUDGET_USED_RATIO
# ---------------------------------------------------------------------------


class TestContextBuildMetrics:
    def test_context_build_seconds_observed_on_build_context(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("ctx-build-seconds-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="test message"))

        before = _histogram_count(CONTEXT_BUILD_SECONDS)
        svc.build_context(session.id, "test query", budget=500)
        after = _histogram_count(CONTEXT_BUILD_SECONDS)

        assert after == before + 1

    def test_context_tokens_observed_on_build_context(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("ctx-tokens-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="test message"))

        before = _histogram_count(CONTEXT_TOKENS)
        svc.build_context(session.id, "test query", budget=500)
        after = _histogram_count(CONTEXT_TOKENS)

        assert after == before + 1

    def test_context_budget_used_ratio_observed_on_build_context(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("ctx-budget-ratio-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="test message"))

        before = _histogram_count(CONTEXT_BUDGET_USED_RATIO)
        svc.build_context(session.id, "test query", budget=500)
        after = _histogram_count(CONTEXT_BUDGET_USED_RATIO)

        assert after == before + 1

    def test_context_budget_ratio_is_between_zero_and_one(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("ctx-budget-ratio-range-test")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="test message"))

        # Capture the ratio by patching the observe call
        observed_ratios: list[float] = []
        original_observe = CONTEXT_BUDGET_USED_RATIO.observe

        def capturing_observe(value):
            observed_ratios.append(value)
            return original_observe(value)

        with patch.object(CONTEXT_BUDGET_USED_RATIO, "observe", side_effect=capturing_observe):
            svc.build_context(session.id, "test query", budget=500)

        assert observed_ratios, "CONTEXT_BUDGET_USED_RATIO.observe was not called"
        for ratio in observed_ratios:
            assert 0.0 <= ratio <= 1.0, f"Budget ratio {ratio} out of [0, 1] range"


# ---------------------------------------------------------------------------
# Prometheus metrics — RETRIEVAL_HITS
# ---------------------------------------------------------------------------


class TestRetrievalHitsMetric:
    def test_retrieval_hits_observed_on_search(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("retrieval-hits-test")
        svc.settings.rot_safe_budget = 1
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        svc.page(session.id)

        before = _histogram_count(RETRIEVAL_HITS)
        svc.search("Agent infra", session_id=session.id)
        after = _histogram_count(RETRIEVAL_HITS)

        assert after == before + 1

    def test_retrieval_hits_value_matches_actual_hits(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("retrieval-hits-value-test")
        svc.settings.rot_safe_budget = 1
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        svc.page(session.id)

        observed_values: list[float] = []
        original_observe = RETRIEVAL_HITS.observe

        def capturing_observe(value):
            observed_values.append(value)
            return original_observe(value)

        with patch.object(RETRIEVAL_HITS, "observe", side_effect=capturing_observe):
            hits = svc.search("Agent infra", session_id=session.id)

        assert observed_values, "RETRIEVAL_HITS.observe was not called"
        assert observed_values[-1] == len(hits)


# ---------------------------------------------------------------------------
# Prometheus metrics — EMBEDDING_SECONDS
# ---------------------------------------------------------------------------


class TestEmbeddingSecondsMetric:
    def test_embedding_seconds_observed_when_embedding_client_present(self, tmp_path):
        from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient

        svc = _make_service(tmp_path)
        svc.embedding_client = DeterministicEmbeddingClient()
        svc.settings.rot_safe_budget = 1
        session = svc.create_session("embedding-seconds-test")
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))

        before = _histogram_count(EMBEDDING_SECONDS)
        svc.page(session.id)
        after = _histogram_count(EMBEDDING_SECONDS)

        assert after >= before + 1

    def test_embedding_seconds_not_observed_without_embedding_client(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.embedding_client = None
        svc.settings.rot_safe_budget = 1
        session = svc.create_session("no-embedding-test")
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))

        before = _histogram_count(EMBEDDING_SECONDS)
        svc.page(session.id)
        after = _histogram_count(EMBEDDING_SECONDS)

        assert after == before


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

    def test_page_committed_trace_has_required_fields(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.settings.rot_safe_budget = 1
        session = svc.create_session("trace-page-committed-test")
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
            "技术栈选择 LangGraph 和 FastAPI。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        svc.page(session.id)

        traces = svc.store.list_traces(session.id)
        page_traces = [t for t in traces if t.event_type == "page_committed"]
        assert page_traces, "Expected 'page_committed' trace event"

        payload = page_traces[-1].payload
        for field in ("page_id", "source_message_ids", "paging_mode"):
            assert field in payload, f"'page_committed' trace missing field: {field}"

    def test_page_committed_trace_source_message_ids_is_list(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.settings.rot_safe_budget = 1
        session = svc.create_session("trace-source-ids-list-test")
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
            "技术栈选择 LangGraph 和 FastAPI。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        svc.page(session.id)

        traces = svc.store.list_traces(session.id)
        payload = next(t.payload for t in traces if t.event_type == "page_committed")
        assert isinstance(payload["source_message_ids"], list)

    def test_patch_verified_trace_has_required_fields(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.settings.rot_safe_budget = 1
        session = svc.create_session("trace-patch-verified-test")
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
            "技术栈选择 LangGraph 和 FastAPI。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        page = svc.page(session.id)
        assert page is not None

        patch = MemoryPatch(
            operation=PatchOperation.ADD,
            target_page_id=page.id,
            new_text="新增事实：用户偏好 Python。",
            reason="test patch",
        )
        svc.commit_patch(session.id, patch)

        traces = svc.store.list_traces(session.id)
        patch_traces = [t for t in traces if t.event_type in ("patch_verified", "patch_rejected")]
        assert patch_traces, "Expected patch trace event"

        payload = patch_traces[-1].payload
        for field in ("patch_id", "errors", "conflicts"):
            assert field in payload, f"Patch trace missing field: {field}"

    def test_session_created_trace_has_title(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("my-session-title")

        traces = svc.store.list_traces(session.id)
        created_traces = [t for t in traces if t.event_type == "session_created"]
        assert created_traces, "Expected 'session_created' trace event"
        assert created_traces[0].payload["title"] == "my-session-title"

    def test_memory_searched_trace_has_required_fields(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.settings.rot_safe_budget = 1
        session = svc.create_session("trace-search-test")
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        svc.page(session.id)
        svc.search("Agent infra", session_id=session.id)

        traces = svc.store.list_traces(session.id)
        search_traces = [t for t in traces if t.event_type == "memory_searched"]
        assert search_traces, "Expected 'memory_searched' trace event"

        payload = search_traces[-1].payload
        assert "query" in payload
        assert "hits" in payload
        assert isinstance(payload["hits"], list)


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

    def test_search_returns_hits_with_metrics_active(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.settings.rot_safe_budget = 1
        session = svc.create_session("smoke-search")
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))
        svc.page(session.id)

        hits = svc.search("Agent infra", session_id=session.id)
        assert isinstance(hits, list)

    def test_page_returns_memory_page_with_metrics_active(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.settings.rot_safe_budget = 1
        session = svc.create_session("smoke-page")
        for content in [
            "用户目标是完成 Agent infra 项目。",
            "最终决定做 MemoryOS Lite。",
            "技术栈选择 LangGraph 和 FastAPI。",
        ]:
            svc.ingest(session.id, MessageCreate(role=Role.USER, content=content))

        page = svc.page(session.id)
        assert page is not None
        assert isinstance(page, MemoryPage)

    def test_trace_events_are_stored_and_retrievable(self, tmp_path):
        svc = _make_service(tmp_path)
        session = svc.create_session("smoke-trace-store")
        svc.ingest(session.id, MessageCreate(role=Role.USER, content="hello"))

        traces = svc.store.list_traces(session.id)
        assert len(traces) >= 2  # session_created + message_ingested

    def test_metrics_endpoint_returns_prometheus_text(self):
        from memoryos_lite.api.app import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        # Prometheus text format always starts with "# HELP" or metric lines
        assert b"memoryos_" in resp.content or b"# HELP" in resp.content


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
# ContextVar primitives — current_request_id
# ---------------------------------------------------------------------------


class TestCurrentRequestId:
    def test_returns_none_when_unset(self, _isolated_context):
        assert current_request_id() is None

    def test_returns_set_value(self, _isolated_context):
        _REQUEST_ID.set("req-123")
        assert current_request_id() == "req-123"


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
        assert "lane_id" not in ctx
        assert "graph_id" not in ctx

    def test_includes_all_set_values(self, _isolated_context):
        _TRACE_ID.set("t1")
        _REQUEST_ID.set("r1")
        _SESSION_ID.set("s1")
        _LANE_ID.set("l1")
        _GRAPH_ID.set("g1")
        ctx = current_observability_context()
        assert ctx == {
            "trace_id": "t1",
            "request_id": "r1",
            "session_id": "s1",
            "lane_id": "l1",
            "graph_id": "g1",
        }

    def test_always_contains_trace_id(self, _isolated_context):
        ctx = current_observability_context()
        assert "trace_id" in ctx
        assert ctx["trace_id"]


# ---------------------------------------------------------------------------
# ContextVar primitives — bind_observability_context
# ---------------------------------------------------------------------------


class TestBindObservabilityContext:
    def test_sets_provided_fields(self, _isolated_context):
        bind_observability_context(
            trace_id="t-bind",
            request_id="r-bind",
            session_id="s-bind",
            lane_id="l-bind",
            graph_id="g-bind",
        )
        assert _TRACE_ID.get() == "t-bind"
        assert _REQUEST_ID.get() == "r-bind"
        assert _SESSION_ID.get() == "s-bind"
        assert _LANE_ID.get() == "l-bind"
        assert _GRAPH_ID.get() == "g-bind"

    def test_auto_generates_trace_id_when_not_provided_and_unset(self, _isolated_context):
        bind_observability_context(session_id="s-auto")
        trace_id = _TRACE_ID.get()
        assert trace_id is not None
        assert len(trace_id) == 32

    def test_does_not_overwrite_existing_trace_id_when_not_provided(self, _isolated_context):
        _TRACE_ID.set("existing-trace")
        bind_observability_context(session_id="s-keep")
        assert _TRACE_ID.get() == "existing-trace"

    def test_none_fields_are_not_written(self, _isolated_context):
        _SESSION_ID.set("original-session")
        bind_observability_context(trace_id="t-partial")
        assert _SESSION_ID.get() == "original-session"


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

    def test_lane_and_graph_ids_are_scoped(self, _isolated_context):
        with observability_context(lane_id="lane-1", graph_id="graph-1"):
            assert _LANE_ID.get() == "lane-1"
            assert _GRAPH_ID.get() == "graph-1"
        assert _LANE_ID.get() is None
        assert _GRAPH_ID.get() is None

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
# record_core_operation
# ---------------------------------------------------------------------------


class TestRecordCoreOperation:
    def _counter_value(self, counter, **labels) -> float:
        return counter.labels(**labels)._value.get()

    def _histogram_count(self, histogram, **labels) -> int:
        return int(_histogram_count(histogram, labels))

    def test_increments_total_counter_on_success(self):
        before = self._counter_value(
            CORE_OPERATION_TOTAL,
            component="rco_comp",
            operation="rco_op_ok",
            status="ok",
        )
        record_core_operation(
            component="rco_comp",
            operation="rco_op_ok",
            elapsed_s=0.01,
            status="ok",
        )
        after = self._counter_value(
            CORE_OPERATION_TOTAL,
            component="rco_comp",
            operation="rco_op_ok",
            status="ok",
        )
        assert after == before + 1

    def test_increments_error_counter_when_error_type_provided(self):
        before = self._counter_value(
            CORE_OPERATION_ERRORS_TOTAL,
            component="rco_comp_err",
            operation="rco_op_err",
            error_type="ValueError",
        )
        record_core_operation(
            component="rco_comp_err",
            operation="rco_op_err",
            elapsed_s=0.05,
            status="error",
            error_type="ValueError",
        )
        after = self._counter_value(
            CORE_OPERATION_ERRORS_TOTAL,
            component="rco_comp_err",
            operation="rco_op_err",
            error_type="ValueError",
        )
        assert after == before + 1

    def test_does_not_increment_error_counter_when_no_error_type(self):
        before = self._counter_value(
            CORE_OPERATION_ERRORS_TOTAL,
            component="rco_no_err",
            operation="rco_no_err_op",
            error_type="RuntimeError",
        )
        record_core_operation(
            component="rco_no_err",
            operation="rco_no_err_op",
            elapsed_s=0.01,
            status="ok",
            error_type=None,
        )
        after = self._counter_value(
            CORE_OPERATION_ERRORS_TOTAL,
            component="rco_no_err",
            operation="rco_no_err_op",
            error_type="RuntimeError",
        )
        assert after == before

    def test_observes_histogram_on_success(self):
        before = self._histogram_count(
            CORE_OPERATION_SECONDS,
            component="rco_hist",
            operation="rco_hist_op",
            status="ok",
        )
        record_core_operation(
            component="rco_hist",
            operation="rco_hist_op",
            elapsed_s=0.1,
            status="ok",
        )
        after = self._histogram_count(
            CORE_OPERATION_SECONDS,
            component="rco_hist",
            operation="rco_hist_op",
            status="ok",
        )
        assert after == before + 1


# ---------------------------------------------------------------------------
# timed_core_operation
# ---------------------------------------------------------------------------


class TestTimedCoreOperation:
    def _counter_value(self, counter, **labels) -> float:
        return counter.labels(**labels)._value.get()

    def test_records_ok_on_success(self):
        before = self._counter_value(
            CORE_OPERATION_TOTAL,
            component="tco_comp",
            operation="tco_op_ok",
            status="ok",
        )
        with timed_core_operation(component="tco_comp", operation="tco_op_ok"):
            pass
        after = self._counter_value(
            CORE_OPERATION_TOTAL,
            component="tco_comp",
            operation="tco_op_ok",
            status="ok",
        )
        assert after == before + 1

    def test_records_error_and_reraises_on_exception(self):
        before_err = self._counter_value(
            CORE_OPERATION_TOTAL,
            component="tco_comp",
            operation="tco_op_err",
            status="error",
        )
        before_err_counter = self._counter_value(
            CORE_OPERATION_ERRORS_TOTAL,
            component="tco_comp",
            operation="tco_op_err",
            error_type="RuntimeError",
        )
        with pytest.raises(RuntimeError, match="timed failure"):
            with timed_core_operation(component="tco_comp", operation="tco_op_err"):
                raise RuntimeError("timed failure")

        after_err = self._counter_value(
            CORE_OPERATION_TOTAL,
            component="tco_comp",
            operation="tco_op_err",
            status="error",
        )
        after_err_counter = self._counter_value(
            CORE_OPERATION_ERRORS_TOTAL,
            component="tco_comp",
            operation="tco_op_err",
            error_type="RuntimeError",
        )
        assert after_err == before_err + 1
        assert after_err_counter == before_err_counter + 1

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

    def test_elapsed_time_is_positive(self):
        captured: list[float] = []
        original_record = record_core_operation

        def capturing_record(**kwargs):
            captured.append(kwargs["elapsed_s"])
            original_record(**kwargs)

        with patch(
            "memoryos_lite.observability.record_core_operation",
            side_effect=capturing_record,
        ):
            with timed_core_operation(component="tco_timing", operation="tco_sleep_op"):
                time.sleep(0.01)

        assert captured
        assert captured[0] >= 0.005


# ---------------------------------------------------------------------------
# _instrument_agent_node (graph-v1 observability wrapper)
# ---------------------------------------------------------------------------


class TestInstrumentAgentNode:
    """Tests for agent_graph._instrument_agent_node — the per-node observability wrapper."""

    def _make_state(self, session_id: str = "sess-instr") -> dict:
        return {"session_id": session_id, "lineage_id": "lin-test"}

    def test_wrapper_calls_underlying_function(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        called_with = []

        def my_node(state):
            called_with.append(state)
            return state

        wrapped = _instrument_agent_node("my_node", my_node, default_session_id="default")
        state = self._make_state()
        result = wrapped(state)
        assert called_with == [state]
        assert result is state

    def test_wrapper_records_ok_metric_on_success(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        before = CORE_OPERATION_TOTAL.labels(
            component="agent_graph",
            operation="instr_ok_node",
            status="ok",
        )._value.get()

        wrapped = _instrument_agent_node("instr_ok_node", lambda s: s, default_session_id="sess")
        wrapped(self._make_state())

        after = CORE_OPERATION_TOTAL.labels(
            component="agent_graph",
            operation="instr_ok_node",
            status="ok",
        )._value.get()
        assert after == before + 1

    def test_wrapper_records_error_metric_and_reraises(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        before_err = CORE_OPERATION_TOTAL.labels(
            component="agent_graph",
            operation="instr_err_node",
            status="error",
        )._value.get()

        def failing_node(state):
            raise RuntimeError("node failure")

        wrapped = _instrument_agent_node("instr_err_node", failing_node, default_session_id="sess")
        with pytest.raises(RuntimeError, match="node failure"):
            wrapped(self._make_state())

        after_err = CORE_OPERATION_TOTAL.labels(
            component="agent_graph",
            operation="instr_err_node",
            status="error",
        )._value.get()
        assert after_err == before_err + 1

    def test_wrapper_propagates_session_id_into_observability_context(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        captured_session: list[str | None] = []

        def capturing_node(state):
            captured_session.append(_SESSION_ID.get())
            return state

        wrapped = _instrument_agent_node(
            "capture_node", capturing_node, default_session_id="default-sess"
        )
        wrapped({"session_id": "explicit-sess", "lineage_id": None})
        assert captured_session == ["explicit-sess"]

    def test_wrapper_uses_default_session_id_when_state_has_none(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        captured_session: list[str | None] = []

        def capturing_node(state):
            captured_session.append(_SESSION_ID.get())
            return state

        wrapped = _instrument_agent_node(
            "default_sess_node", capturing_node, default_session_id="fallback-sess"
        )
        wrapped({})
        assert captured_session == ["fallback-sess"]

    def test_wrapper_propagates_lineage_id_as_lane_id(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        captured_lane: list[str | None] = []

        def capturing_node(state):
            captured_lane.append(_LANE_ID.get())
            return state

        wrapped = _instrument_agent_node("lane_node", capturing_node, default_session_id="sess")
        wrapped({"session_id": "sess", "lineage_id": "lin-abc"})
        assert captured_lane == ["lin-abc"]

    def test_wrapper_restores_context_after_node_error(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        _SESSION_ID.set("outer-session")

        def failing_node(state):
            raise ValueError("inner failure")

        wrapped = _instrument_agent_node(
            "restore_node", failing_node, default_session_id="inner-session"
        )
        with pytest.raises(ValueError):
            wrapped({"session_id": "inner-session", "lineage_id": None})

        # The outer session_id must be restored after the context manager exits
        assert _SESSION_ID.get() == "outer-session"

    def test_wrapper_does_not_set_lane_id_when_lineage_id_is_none(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        captured_lane: list[str | None] = []

        def capturing_node(state):
            captured_lane.append(_LANE_ID.get())
            return state

        wrapped = _instrument_agent_node("no_lane_node", capturing_node, default_session_id="sess")
        wrapped({"session_id": "sess"})
        # lineage_id absent → lane_id should not be set inside the node
        assert captured_lane == [None]

    def test_error_counter_uses_exception_class_name(self, _isolated_context):
        from memoryos_lite.agent_graph import _instrument_agent_node

        before = CORE_OPERATION_ERRORS_TOTAL.labels(
            component="agent_graph",
            operation="typed_err_node",
            error_type="KeyError",
        )._value.get()

        def key_error_node(state):
            raise KeyError("missing key")

        wrapped = _instrument_agent_node(
            "typed_err_node", key_error_node, default_session_id="sess"
        )
        with pytest.raises(KeyError):
            wrapped(self._make_state())

        after = CORE_OPERATION_ERRORS_TOTAL.labels(
            component="agent_graph",
            operation="typed_err_node",
            error_type="KeyError",
        )._value.get()
        assert after == before + 1
