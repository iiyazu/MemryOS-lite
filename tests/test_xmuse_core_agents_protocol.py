from __future__ import annotations

import pytest

from xmuse_core.agents.protocol import (
    PROTOCOL_VERSION,
    AgentOutput,
    parse_stdout_line,
    format_stdin_message,
)


def test_protocol_version_is_1_0():
    assert PROTOCOL_VERSION == "1.0"


def test_parse_pong():
    msg = parse_stdout_line('{"type": "pong"}')
    assert msg is not None
    assert msg.type == "pong"


def test_parse_heartbeat():
    msg = parse_stdout_line(
        '{"type": "heartbeat", "ts": "2026-05-25T10:00:00Z", "context_usage": 0.45}'
    )
    assert msg is not None
    assert msg.type == "heartbeat"
    assert msg.context_usage == 0.45


def test_parse_result_success():
    msg = parse_stdout_line(
        '{"type": "result", "status": "success", "artifacts": {"result_md": "done"}}'
    )
    assert msg is not None
    assert msg.type == "result"
    assert msg.status == "success"


def test_parse_error():
    msg = parse_stdout_line('{"type": "error", "code": "timeout", "message": "LLM timed out"}')
    assert msg is not None
    assert msg.type == "error"
    assert msg.code == "timeout"


def test_parse_invalid_json_returns_none():
    assert parse_stdout_line("not json at all") is None


def test_parse_unknown_type_returns_none():
    assert parse_stdout_line('{"type": "unknown_xyz"}') is None


def test_format_stdin_ping():
    line = format_stdin_message("ping")
    assert line == '{"type": "ping"}\n'


def test_format_stdin_task():
    line = format_stdin_message("task", feature_id="f1", prompt="do it")
    import json
    data = json.loads(line)
    assert data["type"] == "task"
    assert data["feature_id"] == "f1"


def test_agent_output_from_result():
    msg = parse_stdout_line(
        '{"type": "result", "status": "success", "artifacts": {"verdict": {"pass": true}}}'
    )
    output = AgentOutput.from_result(msg)
    assert output.status == "success"
    assert output.artifacts["verdict"] == {"pass": True}
