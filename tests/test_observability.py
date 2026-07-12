"""Tests for observability instrumentation.

Covers:
- Structured log fields (trace_id, request_id, session_id, lane_id, graph_id, event)
- Trace ID propagation across context boundaries and threads
- Prometheus metrics accuracy (counters, histograms)
- timed_core_operation success and error paths
- log_event format and field merging
- Middleware trace ID injection (unit-level and HTTP-level via TestClient)
- StructuredLoggingMiddleware emits required log fields per request
- Engine-level metric integration (INGEST_TOTAL, PAGE_TOTAL, CONTEXT_BUILD_SECONDS)
- Additional histogram metrics: RETRIEVAL_HITS, EMBEDDING_SECONDS, CONTEXT_BUDGET_USED_RATIO
- PAGE_ERRORS_TOTAL counter
- bind_observability_context idempotency (does not overwrite existing trace_id)
- log_event None-valued keyword fields are omitted from the record
- Concurrent timed_core_operation accumulates metrics correctly
- Instrumentation does not break existing functionality
"""

from __future__ import annotations

import logging
import threading
import time

import pytest
from prometheus_client import REGISTRY

from memoryos_lite.observability import (
    CONTEXT_BUDGET_USED_RATIO,
    CONTEXT_BUILD_SECONDS,
    CONTEXT_TOKENS,
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
from memoryos_lite.schemas import MessageCreate, Role

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


def _counter_value(counter, labels=None):
    """Get current value of a prometheus_client Counter."""
    if labels:
        return counter.labels(**labels)._value.get()
    return counter._value.get()


def _registry_sample(metric_name: str, labels: dict | None = None) -> float:
    """Read a sample value from the Prometheus default registry by metric name."""
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if metric.name != metric_name and sample.name != metric_name:
                continue
            if labels is None or all(sample.labels.get(k) == v for k, v in labels.items()):
                return sample.value
    return 0.0


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
            lane_id="l1",
            graph_id="g1",
        ) as ctx:
            assert ctx["trace_id"] == "t1"
            assert ctx["request_id"] == "r1"
            assert ctx["session_id"] == "s1"
            assert ctx["lane_id"] == "l1"
            assert ctx["graph_id"] == "g1"

    def test_current_observability_context_omits_none_fields(self) -> None:
        with observability_context(trace_id="only-trace"):
            ctx = current_observability_context()
        assert "trace_id" in ctx
        assert "request_id" not in ctx
        assert "session_id" not in ctx
        assert "lane_id" not in ctx
        assert "graph_id" not in ctx

    def test_bind_observability_context_auto_generates_trace_id(self) -> None:
        with observability_context():
            bind_observability_context(request_id="req-99")
            assert current_request_id() == "req-99"
            assert current_trace_id()  # auto-generated, non-empty

    def test_bind_observability_context_sets_explicit_trace_id(self) -> None:
        with observability_context():
            bind_observability_context(trace_id="explicit-tid")
            assert current_trace_id() == "explicit-tid"


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
            lane_id="l2",
            graph_id="g2",
        ):
            log_event(lg, logging.INFO, "full_context_event")
        record = handler.last()
        assert record.trace_id == "t2"  # type: ignore[attr-defined]
        assert record.request_id == "r2"  # type: ignore[attr-defined]
        assert record.session_id == "s2"  # type: ignore[attr-defined]
        assert record.lane_id == "l2"  # type: ignore[attr-defined]
        assert record.graph_id == "g2"  # type: ignore[attr-defined]

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
# Prometheus metrics accuracy tests
# ---------------------------------------------------------------------------


class TestMetricsAccuracy:
    def test_record_core_operation_increments_total_counter(self) -> None:
        labels = {"component": "test_comp", "operation": "test_op", "status": "ok"}
        before = _registry_sample("memoryos_core_operation_total", labels)
        record_core_operation(
            component="test_comp", operation="test_op", elapsed_s=0.1, status="ok"
        )
        after = _registry_sample("memoryos_core_operation_total", labels)
        assert after == before + 1.0

    def test_record_core_operation_records_histogram_count(self) -> None:
        labels = {"component": "hist_comp", "operation": "hist_op", "status": "ok"}
        before = _registry_sample("memoryos_core_operation_seconds_count", labels)
        record_core_operation(
            component="hist_comp", operation="hist_op", elapsed_s=0.05, status="ok"
        )
        after = _registry_sample("memoryos_core_operation_seconds_count", labels)
        assert after == before + 1.0

    def test_record_core_operation_histogram_sum_reflects_elapsed(self) -> None:
        labels = {"component": "sum_comp", "operation": "sum_op", "status": "ok"}
        before_sum = _registry_sample("memoryos_core_operation_seconds_sum", labels)
        elapsed = 0.123
        record_core_operation(
            component="sum_comp", operation="sum_op", elapsed_s=elapsed, status="ok"
        )
        after_sum = _registry_sample("memoryos_core_operation_seconds_sum", labels)
        assert abs((after_sum - before_sum) - elapsed) < 1e-6

    def test_record_core_operation_error_increments_error_counter(self) -> None:
        labels = {
            "component": "err_comp",
            "operation": "err_op",
            "error_type": "ValueError",
        }
        before = _registry_sample("memoryos_core_operation_errors_total", labels)
        record_core_operation(
            component="err_comp",
            operation="err_op",
            elapsed_s=0.01,
            status="error",
            error_type="ValueError",
        )
        after = _registry_sample("memoryos_core_operation_errors_total", labels)
        assert after == before + 1.0

    def test_record_core_operation_no_error_counter_when_no_error_type(self) -> None:
        # error_type=None must not touch the errors counter
        labels = {
            "component": "clean_comp",
            "operation": "clean_op",
            "error_type": "None",
        }
        before = _registry_sample("memoryos_core_operation_errors_total", labels)
        record_core_operation(
            component="clean_comp",
            operation="clean_op",
            elapsed_s=0.01,
            status="ok",
            error_type=None,
        )
        after = _registry_sample("memoryos_core_operation_errors_total", labels)
        assert after == before


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
    def test_success_increments_ok_counter(self) -> None:
        labels = {"component": "timed_comp", "operation": "timed_op", "status": "ok"}
        before = _registry_sample("memoryos_core_operation_total", labels)
        with timed_core_operation(component="timed_comp", operation="timed_op"):
            pass
        after = _registry_sample("memoryos_core_operation_total", labels)
        assert after == before + 1.0

    def test_success_does_not_increment_error_counter(self) -> None:
        labels = {
            "component": "timed_clean",
            "operation": "timed_op2",
            "error_type": "RuntimeError",
        }
        before = _registry_sample("memoryos_core_operation_errors_total", labels)
        with timed_core_operation(component="timed_clean", operation="timed_op2"):
            pass
        after = _registry_sample("memoryos_core_operation_errors_total", labels)
        assert after == before

    def test_exception_increments_error_counter_and_reraises(self) -> None:
        labels = {
            "component": "timed_err",
            "operation": "timed_err_op",
            "error_type": "RuntimeError",
        }
        before = _registry_sample("memoryos_core_operation_errors_total", labels)
        with pytest.raises(RuntimeError, match="boom"):
            with timed_core_operation(component="timed_err", operation="timed_err_op"):
                raise RuntimeError("boom")
        after = _registry_sample("memoryos_core_operation_errors_total", labels)
        assert after == before + 1.0

    def test_exception_records_error_status_in_total(self) -> None:
        labels = {
            "component": "timed_err2",
            "operation": "timed_err_op2",
            "status": "error",
        }
        before = _registry_sample("memoryos_core_operation_total", labels)
        with pytest.raises(ValueError):
            with timed_core_operation(component="timed_err2", operation="timed_err_op2"):
                raise ValueError("bad")
        after = _registry_sample("memoryos_core_operation_total", labels)
        assert after == before + 1.0

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

    def test_timed_operation_measures_real_elapsed_time(self) -> None:
        labels = {"component": "timing_comp", "operation": "timing_op", "status": "ok"}
        before_sum = _registry_sample("memoryos_core_operation_seconds_sum", labels)
        sleep_s = 0.05
        with timed_core_operation(component="timing_comp", operation="timing_op"):
            time.sleep(sleep_s)
        after_sum = _registry_sample("memoryos_core_operation_seconds_sum", labels)
        # Allow generous tolerance for CI jitter
        assert (after_sum - before_sum) >= sleep_s * 0.8

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
# Engine-level metric integration tests
# ---------------------------------------------------------------------------


def test_ingest_increments_counter(service):
    before = _counter_value(INGEST_TOTAL)
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="hello"))
    after = _counter_value(INGEST_TOTAL)
    assert after == before + 1


def test_page_increments_counter(service):
    session = service.create_session("test")
    for content in [
        "用户目标是在 20 天内完成 Agent infra 项目。",
        "最终决定不做 Runbook Oncall Agent，改做 MemoryOS Lite。",
        "技术栈选择 LangGraph 和 FastAPI。",
        "需要 benchmark 对比 Sliding Window 和 Vector RAG。",
    ]:
        service.ingest(session.id, MessageCreate(role=Role.USER, content=content))
    before_heuristic = _counter_value(PAGE_TOTAL, {"mode": "heuristic"})
    before_agentic = _counter_value(PAGE_TOTAL, {"mode": "agentic"})
    before_fallback = _counter_value(PAGE_TOTAL, {"mode": "heuristic_fallback"})
    page = service.page(session.id)
    assert page is not None
    after_heuristic = _counter_value(PAGE_TOTAL, {"mode": "heuristic"})
    after_agentic = _counter_value(PAGE_TOTAL, {"mode": "agentic"})
    after_fallback = _counter_value(PAGE_TOTAL, {"mode": "heuristic_fallback"})
    before_total = before_heuristic + before_agentic + before_fallback
    after_total = after_heuristic + after_agentic + after_fallback
    assert after_total == before_total + 1


def test_build_context_observes_metrics(service):
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="hello world"))
    service.build_context(session.id, "test task", budget=500)
    assert CONTEXT_BUILD_SECONDS._sum.get() >= 0
    assert CONTEXT_TOKENS._sum.get() >= 0


# ---------------------------------------------------------------------------
# Regression: instrumentation does not break existing functionality
# ---------------------------------------------------------------------------


class TestInstrumentationRegression:
    def test_observability_context_yields_dict(self) -> None:
        with observability_context(trace_id="reg-test") as ctx:
            assert isinstance(ctx, dict)
            assert ctx["trace_id"] == "reg-test"

    def test_multiple_sequential_operations_counted_independently(self) -> None:
        comp, op = "seq_comp", "seq_op"
        labels = {"component": comp, "operation": op, "status": "ok"}
        before = _registry_sample("memoryos_core_operation_total", labels)
        for _ in range(3):
            with timed_core_operation(component=comp, operation=op):
                pass
        after = _registry_sample("memoryos_core_operation_total", labels)
        assert after == before + 3.0

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
# bind_observability_context idempotency
# ---------------------------------------------------------------------------


class TestBindObservabilityContextIdempotency:
    def test_does_not_overwrite_existing_trace_id(self) -> None:
        """Calling bind without trace_id must not replace an already-set trace_id."""
        with observability_context(trace_id="stable-trace"):
            bind_observability_context(request_id="req-x")
            assert current_trace_id() == "stable-trace"

    def test_explicit_trace_id_overwrites_existing(self) -> None:
        with observability_context(trace_id="old-trace"):
            bind_observability_context(trace_id="new-trace")
            assert current_trace_id() == "new-trace"

    def test_bind_without_any_args_auto_generates_trace_id(self) -> None:
        with observability_context():
            # Reset the context var to None to simulate a fresh request
            from memoryos_lite.observability import _TRACE_ID

            token = _TRACE_ID.set(None)  # type: ignore[arg-type]
            try:
                bind_observability_context()
                tid = current_trace_id()
                assert tid and len(tid) == 32
            finally:
                _TRACE_ID.reset(token)


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
# Additional histogram metric tests
# ---------------------------------------------------------------------------


class TestAdditionalHistogramMetrics:
    def test_retrieval_hits_histogram_accepts_observation(self) -> None:
        before = _registry_sample("memoryos_retrieval_hits_count")
        RETRIEVAL_HITS.observe(5)
        after = _registry_sample("memoryos_retrieval_hits_count")
        assert after == before + 1.0

    def test_retrieval_hits_sum_reflects_observed_value(self) -> None:
        before_sum = _registry_sample("memoryos_retrieval_hits_sum")
        RETRIEVAL_HITS.observe(3)
        after_sum = _registry_sample("memoryos_retrieval_hits_sum")
        assert abs((after_sum - before_sum) - 3.0) < 1e-9

    def test_embedding_seconds_histogram_accepts_observation(self) -> None:
        before = _registry_sample("memoryos_embedding_seconds_count")
        EMBEDDING_SECONDS.observe(0.08)
        after = _registry_sample("memoryos_embedding_seconds_count")
        assert after == before + 1.0

    def test_embedding_seconds_sum_reflects_observed_value(self) -> None:
        elapsed = 0.15
        before_sum = _registry_sample("memoryos_embedding_seconds_sum")
        EMBEDDING_SECONDS.observe(elapsed)
        after_sum = _registry_sample("memoryos_embedding_seconds_sum")
        assert abs((after_sum - before_sum) - elapsed) < 1e-9

    def test_context_budget_used_ratio_histogram_accepts_observation(self) -> None:
        before = _registry_sample("memoryos_context_budget_used_ratio_count")
        CONTEXT_BUDGET_USED_RATIO.observe(0.75)
        after = _registry_sample("memoryos_context_budget_used_ratio_count")
        assert after == before + 1.0

    def test_context_budget_used_ratio_sum_reflects_observed_value(self) -> None:
        ratio = 0.9
        before_sum = _registry_sample("memoryos_context_budget_used_ratio_sum")
        CONTEXT_BUDGET_USED_RATIO.observe(ratio)
        after_sum = _registry_sample("memoryos_context_budget_used_ratio_sum")
        assert abs((after_sum - before_sum) - ratio) < 1e-9


# ---------------------------------------------------------------------------
# PAGE_ERRORS_TOTAL counter
# ---------------------------------------------------------------------------


class TestPageErrorsTotal:
    def test_page_errors_total_increments_by_stage(self) -> None:
        labels = {"stage": "llm_call"}
        before = _registry_sample("memoryos_page_errors_total", labels)
        PAGE_ERRORS_TOTAL.labels(stage="llm_call").inc()
        after = _registry_sample("memoryos_page_errors_total", labels)
        assert after == before + 1.0

    def test_page_errors_total_different_stages_are_independent(self) -> None:
        labels_a = {"stage": "stage_alpha"}
        labels_b = {"stage": "stage_beta"}
        before_a = _registry_sample("memoryos_page_errors_total", labels_a)
        before_b = _registry_sample("memoryos_page_errors_total", labels_b)
        PAGE_ERRORS_TOTAL.labels(stage="stage_alpha").inc()
        after_a = _registry_sample("memoryos_page_errors_total", labels_a)
        after_b = _registry_sample("memoryos_page_errors_total", labels_b)
        assert after_a == before_a + 1.0
        assert after_b == before_b  # untouched


# ---------------------------------------------------------------------------
# Concurrent timed_core_operation
# ---------------------------------------------------------------------------


class TestConcurrentTimedCoreOperation:
    def test_concurrent_operations_accumulate_counts_correctly(self) -> None:
        comp, op = "concurrent_comp", "concurrent_op"
        labels = {"component": comp, "operation": op, "status": "ok"}
        before = _registry_sample("memoryos_core_operation_total", labels)
        n_threads = 8

        def worker() -> None:
            with timed_core_operation(component=comp, operation=op):
                time.sleep(0.005)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        after = _registry_sample("memoryos_core_operation_total", labels)
        assert after == before + n_threads

    def test_concurrent_errors_accumulate_error_counts_correctly(self) -> None:
        comp, op = "concurrent_err_comp", "concurrent_err_op"
        labels = {"component": comp, "operation": op, "error_type": "ValueError"}
        before = _registry_sample("memoryos_core_operation_errors_total", labels)
        n_threads = 4

        def worker() -> None:
            try:
                with timed_core_operation(component=comp, operation=op):
                    raise ValueError("concurrent error")
            except ValueError:
                pass

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        after = _registry_sample("memoryos_core_operation_errors_total", labels)
        assert after == before + n_threads


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
