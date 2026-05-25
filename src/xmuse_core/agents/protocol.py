from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = "1.0"
MAX_MESSAGE_BYTES = 10 * 1024 * 1024

KNOWN_TYPES = {"pong", "heartbeat", "progress", "result", "error", "hello_ack"}


@dataclass
class StdoutMessage:
    type: str
    protocol_version: str | None = None
    runtime: str | None = None
    ts: str | None = None
    context_usage: float | None = None
    stage: str | None = None
    message: str | None = None
    status: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    code: str | None = None


def parse_stdout_line(line: str) -> StdoutMessage | None:
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    msg_type = data.get("type")
    if msg_type not in KNOWN_TYPES:
        return None
    return StdoutMessage(
        type=msg_type,
        protocol_version=data.get("protocol_version"),
        runtime=data.get("runtime"),
        ts=data.get("ts"),
        context_usage=data.get("context_usage"),
        stage=data.get("stage"),
        message=data.get("message"),
        status=data.get("status"),
        artifacts=data.get("artifacts", {}),
        code=data.get("code"),
    )


@dataclass
class AgentOutput:
    status: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def from_result(cls, msg: StdoutMessage) -> AgentOutput:
        return cls(status=msg.status or "unknown", artifacts=msg.artifacts)

    @classmethod
    def from_error(cls, msg: StdoutMessage) -> AgentOutput:
        return cls(status="error", error_code=msg.code, error_message=msg.message)


def format_stdin_message(msg_type: str, **kwargs: Any) -> str:
    payload = {"type": msg_type, **kwargs}
    return json.dumps(payload, ensure_ascii=False) + "\n"
