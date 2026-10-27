"""Optional tracing (memoryos_lite.telemetry): off by default and import-free, a server span that
continues the caller's traceparent, graph-node and LLM spans for /curate with content hidden by
default, and the trace id in the request log."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memoryos_lite import telemetry
from memoryos_lite.api import app as api
from memoryos_lite.config import Settings
from memoryos_lite.curator.demo import _BROKEN, _CLEAN, DEMO_REQUEST
from memoryos_lite.engine import MemoryOSService

TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT = "00f067aa0ba902b7"
ENV = (
    "MEMORYOS_OTEL_ENABLED",
    "MEMORYOS_OTEL_CAPTURE_CONTENT",
    "MEMORYOS_OTEL_PROJECT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
)
RECALL = {
    "schema": "memoryos_recall/v1",
    "query": "amount",
    "budget_tokens": 500,
    "k": 1,
    "items": [{"id": "E1", "text": "amounts are integer cents", "kind": "decision", "seq": 1}],
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


def test_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not telemetry.enabled() and telemetry.project() == "xmuse"
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    assert telemetry.enabled()
    monkeypatch.setenv("MEMORYOS_OTEL_ENABLED", "0")
    assert not telemetry.enabled()
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    monkeypatch.setenv("MEMORYOS_OTEL_ENABLED", "1")
    monkeypatch.setenv("MEMORYOS_OTEL_PROJECT", "mine")
    assert telemetry.enabled() and telemetry.project() == "mine"


def test_off_imports_no_opentelemetry() -> None:
    env = {k: v for k, v in os.environ.items() if k not in ENV}
    code = (
        "import sys, memoryos_lite.api.app\n"
        "print([m for m in sys.modules if m.split('.')[0] in ('opentelemetry', 'openinference')])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"


def test_enabled_without_the_extra_runs_untraced(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("MEMORYOS_OTEL_ENABLED", "1")
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", None)  # import fails
    app = FastAPI()
    with caplog.at_level(logging.WARNING, "memoryos_lite.telemetry"):
        assert telemetry.setup(app) is False
    assert "otel extra is not installed" in caplog.text and app.user_middleware == []


# ---- traced: a copy of the real app (same routes, same middleware) ------------------------------


class FakeOpenAI(BaseHTTPRequestHandler):
    """Chat completions answering like ``memoryos demo curate``: broken first, clean after."""

    calls = 0

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("content-length", 0)))
        FakeOpenAI.calls += 1
        reply = _BROKEN if FakeOpenAI.calls == 1 else _CLEAN
        body = json.dumps(
            {
                "id": f"cmpl-{FakeOpenAI.calls}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "fake-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(reply)},
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
            }
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def llm_url() -> Iterator[str]:
    FakeOpenAI.calls = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()
    server.server_close()


def traced(monkeypatch: pytest.MonkeyPatch, tmp_path: Any, llm_url: str, capture: bool = False):
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("MEMORYOS_OTEL_ENABLED", "1")
    if capture:
        monkeypatch.setenv("MEMORYOS_OTEL_CAPTURE_CONTENT", "1")
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.router.routes.extend(api.app.router.routes)
    app.user_middleware = list(api.app.user_middleware)
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_llm_provider="openai",
        openai_api_key="sk-test-not-a-key",
        openai_base_url=llm_url,
        memoryos_model="fake-model",
        deepseek_api_key=None,
        opencode_api_key=None,
    )
    service = MemoryOSService(settings=settings)
    # the copied routes resolve overrides through the app that declared them
    monkeypatch.setitem(api.app.dependency_overrides, api.get_service, lambda: service)
    mem = InMemorySpanExporter()
    assert telemetry.setup(app, exporter=mem) is True
    return TestClient(app), mem


@pytest.fixture
def untrace() -> Iterator[None]:
    yield
    from openinference.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().uninstrument()  # process-wide: later tests run untraced


def by_name(spans: Any) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for s in spans:
        out.setdefault(s.name, []).append(s)
    return out


def test_a_request_continues_the_callers_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    llm_url: str,
    untrace: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, mem = traced(monkeypatch, tmp_path, llm_url)
    with caplog.at_level(logging.INFO, "memoryos_lite.middleware"):
        r = client.post("/recall", json=RECALL, headers={"traceparent": f"00-{TRACE}-{PARENT}-01"})
    assert r.status_code == 200 and r.headers["X-Request-Id"]  # request ids unchanged
    [server] = mem.get_finished_spans()  # no ASGI receive/send sub-spans
    assert server.name == "POST /recall" and str(server.kind) == "SpanKind.SERVER"
    assert format(server.context.trace_id, "032x") == TRACE
    assert server.parent is not None and format(server.parent.span_id, "016x") == PARENT
    res = server.resource.attributes
    assert res["service.name"] == "memoryos-lite" and res["openinference.project.name"] == "xmuse"
    [log] = [rec for rec in caplog.records if getattr(rec, "event", None) == "request"]
    assert log.trace_id == TRACE  # type: ignore[attr-defined]

    mem.clear()
    client.post("/recall", json=RECALL)
    [root] = mem.get_finished_spans()
    assert root.parent is None and format(root.context.trace_id, "032x") != TRACE


def test_curate_traces_graph_nodes_and_llm_calls_without_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, llm_url: str, untrace: None
) -> None:
    client, mem = traced(monkeypatch, tmp_path, llm_url)
    r = client.post(
        "/curate",
        json=DEMO_REQUEST.model_dump(mode="json"),
        headers={"traceparent": f"00-{TRACE}-{PARENT}-01"},
    )
    assert r.status_code == 200 and FakeOpenAI.calls == 2, r.text
    spans = mem.get_finished_spans()
    assert {format(s.context.trace_id, "032x") for s in spans} == {TRACE}
    ids = {s.context.span_id for s in spans}
    assert [s.name for s in spans if s.parent is None or s.parent.span_id not in ids] == [
        "POST /curate"
    ]  # one tree under the server span
    names = by_name(spans)
    assert {"LangGraph", "extract", "check", "repair", "consolidate"} <= set(names)
    llm = [s for s in spans if (s.attributes or {}).get("openinference.span.kind") == "LLM"]
    assert len(llm) == 2 and all(s.attributes["llm.token_count.total"] == 180 for s in llm)
    text = json.dumps([dict(s.attributes or {}) for s in spans])
    request_text = DEMO_REQUEST.model_dump_json()
    words = {w for w in request_text.lower().split() if len(w) > 8 and w.isalpha()}
    assert words and not [w for w in words if w in text.lower()]
    assert "sk-test-not-a-key" not in text


def test_content_is_recorded_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, llm_url: str, untrace: None
) -> None:
    client, mem = traced(monkeypatch, tmp_path, llm_url, capture=True)
    client.post("/curate", json=DEMO_REQUEST.model_dump(mode="json"))
    llm = [
        s
        for s in mem.get_finished_spans()
        if (s.attributes or {}).get("openinference.span.kind") == "LLM"
    ]
    assert llm and any(k.startswith("llm.input_messages") for k in llm[0].attributes or {})
