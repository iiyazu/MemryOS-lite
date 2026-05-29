# xmuse Agent Framework + memoryOS Middleware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade xmuse from file-polling one-shot subprocess to session-based multi-agent framework with memoryOS as middleware memory layer.

**Architecture:** Two independent subsystems — (1) `src/xmuse_core/agents/` for session management, registry, and launcher adapters; (2) `src/memoryos_lite/middleware.py` + config additions for HTTP middleware. Both connect via memoryOS HTTP API.

**Tech Stack:** Python 3.11+, asyncio, FastAPI, Pydantic, pytest + pytest-asyncio

---

## File Structure

### xmuse Agent Framework (new)

| File | Responsibility |
|------|---------------|
| `src/xmuse_core/agents/__init__.py` | Public exports |
| `src/xmuse_core/agents/protocol.py` | AgentOutput, message type unions, protocol version |
| `src/xmuse_core/agents/registry.py` | AgentRegistry, AgentDescriptor, AgentRuntime, SessionConfig |
| `src/xmuse_core/agents/session.py` | AgentSession protocol, LocalSession implementation |
| `src/xmuse_core/agents/manager.py` | SessionManager (lifecycle, heartbeat, abort, orphan cleanup) |
| `src/xmuse_core/agents/consumer.py` | WorklistConsumer, TaskDescriptor |
| `src/xmuse_core/agents/launchers/__init__.py` | Launcher exports |
| `src/xmuse_core/agents/launchers/base.py` | LauncherAdapter protocol |
| `src/xmuse_core/agents/launchers/codex.py` | CodexLauncher |
| `src/xmuse_core/agents/launchers/claude_code.py` | ClaudeCodeLauncher |

### memoryOS Middleware (new + modify)

| File | Responsibility |
|------|---------------|
| `src/memoryos_lite/middleware.py` | RequestIdMiddleware, ApiKeyAuthMiddleware, StructuredLoggingMiddleware |
| `src/memoryos_lite/config.py` | Add api_key, cors_origins, log_format fields |
| `src/memoryos_lite/api/app.py` | Register middleware, add ingest-batch and summary endpoints |

### Tests

| File | Responsibility |
|------|---------------|
| `tests/test_xmuse_core_agents_protocol.py` | Message parsing, protocol version |
| `tests/test_xmuse_core_agents_registry.py` | Registry load, select strategy |
| `tests/test_xmuse_core_agents_session.py` | LocalSession stdin/stdout, abort, heartbeat |
| `tests/test_xmuse_core_agents_manager.py` | SessionManager lifecycle, orphan cleanup |
| `tests/test_xmuse_core_agents_consumer.py` | WorklistConsumer enqueue/dispatch |
| `tests/test_xmuse_core_agents_launchers.py` | Command building, prompt formatting |
| `tests/test_memoryos_middleware.py` | All three middleware classes + integration |

---

### Task 1: Protocol Messages and Types

**Files:**
- Create: `src/xmuse_core/agents/__init__.py`
- Create: `src/xmuse_core/agents/protocol.py`
- Test: `tests/test_xmuse_core_agents_protocol.py`

- [ ] **Step 1: Write failing tests for protocol message parsing**

```python
# tests/test_xmuse_core_agents_protocol.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_core_agents_protocol.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement protocol module**

Create `src/xmuse_core/agents/__init__.py`:
```python
"""xmuse agent framework — session-based multi-agent orchestration."""
```

Create `src/xmuse_core/agents/protocol.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_xmuse_core_agents_protocol.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/__init__.py src/xmuse_core/agents/protocol.py tests/test_xmuse_core_agents_protocol.py
git commit -m "feat(xmuse): add agent protocol message types and parser"
```

### Task 2: Agent Registry

**Files:**
- Create: `src/xmuse_core/agents/registry.py`
- Test: `tests/test_xmuse_core_agents_registry.py`

- [ ] **Step 1: Write failing tests**

Test `AgentRegistry.from_file()` loads agents from JSON config.
Test `select(["review"])` returns agent with matching capability.
Test `select(["review"], exclude_runtime=CODEX)` excludes Codex agents.
Test `select(["nonexistent"])` raises ValueError.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_core_agents_registry.py -v`

- [ ] **Step 3: Implement registry**

Create `src/xmuse_core/agents/registry.py` with:
- `AgentRuntime` enum (codex, claude_code)
- `SessionConfig` dataclass (transport, heartbeat_interval_s, heartbeat_timeout_s, max_context_tokens)
- `AgentDescriptor` dataclass (runtime, name, capabilities, session_config)
- `AgentRegistry` class with `from_file(path)` and `select(required, exclude_runtime)` methods
- select strategy: capability match → exclude_runtime filter → round-robin among candidates

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_registry.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/registry.py tests/test_xmuse_core_agents_registry.py
git commit -m "feat(xmuse): add agent registry with capability-based selection"
```

---

### Task 3: LocalSession Transport

**Files:**
- Create: `src/xmuse_core/agents/session.py`
- Test: `tests/test_xmuse_core_agents_session.py`

- [ ] **Step 1: Write failing tests**

Tests should cover:
- `LocalSession.send()` writes JSON-line to stdin
- `LocalSession.receive()` reads one JSON-line from stdout
- `LocalSession.abort()` sends SIGTERM, waits grace period, then SIGKILL
- `LocalSession.is_alive()` returns False after process exits
- Non-JSON stdout lines are skipped (returns None from receive)
- Consecutive 50 non-JSON lines triggers health warning flag

Use `asyncio.subprocess` with a simple echo script as mock agent:
```python
MOCK_AGENT = "import sys, json\nfor line in sys.stdin:\n    d=json.loads(line)\n    if d['type']=='ping': print(json.dumps({'type':'pong'}), flush=True)\n    elif d['type']=='task': print(json.dumps({'type':'result','status':'success','artifacts':{}}), flush=True)\n    elif d['type']=='abort': break\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_core_agents_session.py -v`

- [ ] **Step 3: Implement LocalSession**

Create `src/xmuse_core/agents/session.py` with:
- `AgentSession` Protocol (send, receive, abort, is_alive)
- `LocalSession` class using `asyncio.create_subprocess_exec`
- `send()`: encode JSON + newline, write to process.stdin, drain
- `receive()`: readline from stdout, attempt parse_stdout_line, skip non-JSON
- `abort()`: write abort message → SIGTERM → asyncio.wait_for(grace=10s) → SIGKILL
- `is_alive()`: process.returncode is None
- `_health_warning` flag set after 50 consecutive non-JSON lines

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_session.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/session.py tests/test_xmuse_core_agents_session.py
git commit -m "feat(xmuse): add LocalSession with stdin/stdout transport"
```

---

### Task 4: Launcher Adapters

**Files:**
- Create: `src/xmuse_core/agents/launchers/__init__.py`
- Create: `src/xmuse_core/agents/launchers/base.py`
- Create: `src/xmuse_core/agents/launchers/codex.py`
- Create: `src/xmuse_core/agents/launchers/claude_code.py`
- Test: `tests/test_xmuse_core_agents_launchers.py`

- [ ] **Step 1: Write failing tests**

Tests should cover:
- `CodexLauncher.build_command()` returns `["codex", "--cwd", worktree, "--quiet"]`
- `ClaudeCodeLauncher.build_command()` returns `["claude", "--cwd", worktree, "--output-format", "json"]`
- `CodexLauncher.format_prompt()` wraps task + context into Codex-compatible format
- `ClaudeCodeLauncher.format_prompt()` wraps task + context into Claude Code format
- Both launchers include environment variables (XMUSE_FEATURE_ID)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_core_agents_launchers.py -v`

- [ ] **Step 3: Implement launchers**

Create `src/xmuse_core/agents/launchers/base.py`:
- `LauncherAdapter` Protocol with `build_command`, `format_prompt`, `build_env`

Create `src/xmuse_core/agents/launchers/codex.py`:
- `CodexLauncher` implementing the protocol for Codex CLI session mode

Create `src/xmuse_core/agents/launchers/claude_code.py`:
- `ClaudeCodeLauncher` implementing the protocol for Claude Code CLI

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_launchers.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/launchers/ tests/test_xmuse_core_agents_launchers.py
git commit -m "feat(xmuse): add Codex and Claude Code launcher adapters"
```

---

### Task 5: SessionManager (Lifecycle + Heartbeat + Abort)

**Files:**
- Create: `src/xmuse_core/agents/manager.py`
- Test: `tests/test_xmuse_core_agents_manager.py`

- [ ] **Step 1: Write failing tests**

Tests should cover:
- `dispatch()` spawns process via launcher, creates LocalSession, registers in active map
- `abort(feature_id)` sends abort to session, removes from active map
- `ping_all()` sends ping to all active sessions
- Heartbeat timeout detection (mock session that never responds to ping)
- `cleanup_orphans()` reads active_sessions.json, kills matching PIDs
- `graceful_shutdown()` aborts all sessions, persists pending tasks
- State machine transitions: PENDING → STARTING → RUNNING → DONE / FAILED

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_core_agents_manager.py -v`

- [ ] **Step 3: Implement SessionManager**

Create `src/xmuse_core/agents/manager.py` with:
- `SessionState` enum (PENDING, STARTING, RUNNING, COMPLETING, DONE, ABORTING, TIMEOUT, FAILED)
- `ActiveSession` dataclass (session, state, feature_id, started_at, last_pong, missed_pings)
- `SessionManager` class:
  - `dispatch(agent, task)`: build command via launcher → spawn → hello handshake → send task
  - `abort(feature_id)`: send abort → wait → cleanup
  - `ping_all()`: iterate active sessions, send ping, track missed pongs
  - `check_timeouts()`: mark TIMEOUT if missed_pings > 10
  - `cleanup_orphans(instance_id)`: read active_sessions.json → kill stale PIDs
  - `graceful_shutdown()`: stop consuming → abort all → persist pending tasks
  - `_persist_active()`: write active_sessions.json with pid, feature_id, instance_id

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_manager.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/manager.py tests/test_xmuse_core_agents_manager.py
git commit -m "feat(xmuse): add SessionManager with lifecycle, heartbeat, and abort"
```

---

### Task 6: WorklistConsumer

**Files:**
- Create: `src/xmuse_core/agents/consumer.py`
- Test: `tests/test_xmuse_core_agents_consumer.py`

- [ ] **Step 1: Write failing tests**

Tests should cover:
- `enqueue()` adds TaskDescriptor to internal queue
- `run()` consumes tasks and calls session_mgr.dispatch
- Semaphore limits concurrent dispatches to max_concurrent (4)
- Task with `developed_by_runtime` passes exclude_runtime to registry.select
- Multiple tasks are processed in FIFO order

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_core_agents_consumer.py -v`

- [ ] **Step 3: Implement WorklistConsumer**

Create `src/xmuse_core/agents/consumer.py` with:
- `TaskDescriptor` dataclass (feature_id, task_type, prompt, required_capabilities, developed_by_runtime)
- `WorklistConsumer` class:
  - `__init__(registry, session_mgr, max_concurrent=4)`
  - `async run()`: main loop consuming from asyncio.Queue with semaphore
  - `async enqueue(task)`: put task into queue
  - `shutdown()`: set flag to stop consuming

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_consumer.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/consumer.py tests/test_xmuse_core_agents_consumer.py
git commit -m "feat(xmuse): add WorklistConsumer with async queue and concurrency limit"
```

---

### Task 7: memoryOS Middleware

**Files:**
- Create: `src/memoryos_lite/middleware.py`
- Modify: `src/memoryos_lite/config.py`
- Modify: `src/memoryos_lite/api/app.py`
- Test: `tests/test_memoryos_middleware.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_memoryos_middleware.py
import pytest
from fastapi.testclient import TestClient

def _make_app(api_key=None):
    """Create app with optional API key for testing."""
    import os
    if api_key:
        os.environ["MEMORYOS_API_KEY"] = api_key
    else:
        os.environ.pop("MEMORYOS_API_KEY", None)
    # Force reimport to pick up new env
    from memoryos_lite.api.app import app
    return app

def test_request_id_injected():
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/health")
    assert "X-Request-Id" in resp.headers
    assert len(resp.headers["X-Request-Id"]) == 32  # hex uuid

def test_request_id_preserved_from_client():
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/health", headers={"X-Request-Id": "my-custom-id"})
    assert resp.headers["X-Request-Id"] == "my-custom-id"

def test_api_key_rejects_invalid():
    app = _make_app(api_key="secret123")
    client = TestClient(app)
    resp = client.post("/sessions", json={"title": "test"}, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401

def test_api_key_allows_valid():
    app = _make_app(api_key="secret123")
    client = TestClient(app)
    resp = client.get("/health", headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200

def test_api_key_skips_health_without_key():
    app = _make_app(api_key="secret123")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200  # health is exempt

def test_no_api_key_configured_allows_all():
    app = _make_app(api_key=None)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_memoryos_middleware.py -v`

- [ ] **Step 3: Add config fields**

Add to `src/memoryos_lite/config.py` Settings class:
```python
    # Middleware
    memoryos_api_key: str | None = None
    memoryos_cors_origins: str = "*"
    memoryos_log_format: str = "text"
```

- [ ] **Step 4: Create middleware module**

Create `src/memoryos_lite/middleware.py` with:
- `RequestIdMiddleware`: inject/preserve X-Request-Id
- `ApiKeyAuthMiddleware`: check X-API-Key header, skip for /health and /metrics
- `StructuredLoggingMiddleware`: log request_id, method, path, status, latency_ms

- [ ] **Step 5: Register middleware in app.py**

Modify `src/memoryos_lite/api/app.py`:
- Import middleware classes and CORSMiddleware
- Register in correct order (StructuredLogging → ApiKeyAuth → RequestId → CORS)
- Add after `app = FastAPI(...)` line

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_memoryos_middleware.py -v`
Also run: `uv run pytest tests/ -k "test_api or test_health" -v` to verify existing tests still pass

- [ ] **Step 7: Commit**

```bash
git add src/memoryos_lite/middleware.py src/memoryos_lite/config.py src/memoryos_lite/api/app.py tests/test_memoryos_middleware.py
git commit -m "feat(memoryos): add HTTP middleware (request_id, api_key auth, structured logging)"
```

---

### Task 7.5: memoryOS Agent Endpoints (ingest-batch + summary)

**Files:**
- Modify: `src/memoryos_lite/api/app.py`
- Modify: `src/memoryos_lite/schemas.py` (add request/response models)
- Test: `tests/test_memoryos_middleware.py` (extend)

- [ ] **Step 1: Write failing tests for new endpoints**

Test `POST /sessions/{id}/ingest-batch` accepts list of MessageCreate, returns list of IngestResponse.
Test `GET /sessions/{id}/summary` returns session title, message count, last activity timestamp.
Test both endpoints return 404 for nonexistent session.
Test both endpoints require API key when configured.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_memoryos_middleware.py -v -k "batch or summary"`

- [ ] **Step 3: Add schema models**

Add to `src/memoryos_lite/schemas.py`:
- `IngestBatchRequest`: `messages: list[MessageCreate]`
- `SessionSummaryResponse`: `session_id: str, title: str, message_count: int, last_activity: str | None`

- [ ] **Step 4: Implement endpoints in app.py**

Add `POST /sessions/{id}/ingest-batch`: iterate messages, call `service.ingest()` for each, return list.
Add `GET /sessions/{id}/summary`: call `service.get_session()` + count messages, return summary.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_memoryos_middleware.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/api/app.py src/memoryos_lite/schemas.py tests/test_memoryos_middleware.py
git commit -m "feat(memoryos): add ingest-batch and session summary endpoints"
```

---

### Task 7.7: SessionManager ↔ memoryOS Integration

**Files:**
- Modify: `src/xmuse_core/agents/manager.py`
- Test: `tests/test_xmuse_core_agents_manager.py` (extend)

- [ ] **Step 1: Write failing tests for memoryOS integration**

Test `dispatch()` calls memoryOS `POST /sessions` to create session before spawning agent.
Test `dispatch()` calls `POST /sessions/{id}/build-context` and passes result as context in stdin task message.
Test on receiving `progress` with `stage="decision"`, manager calls `POST /sessions/{id}/ingest`.
Test on session completion, manager calls `POST /sessions/{id}/ingest` with final result.
Test memoryOS unreachable → session still proceeds (degraded mode), no exception raised.

Use `httpx.MockTransport` or `respx` to mock memoryOS HTTP calls.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_core_agents_manager.py -v -k "memoryos"`

- [ ] **Step 3: Add memoryOS client to SessionManager**

Add `MemoryOSClient` helper class in `manager.py`:
- `__init__(base_url: str, api_key: str | None)`
- `async create_session(title: str) -> str` (returns session_id)
- `async build_context(session_id: str, task: str, budget: int) -> str`
- `async ingest(session_id: str, role: str, content: str) -> None`
- All methods catch `httpx.HTTPError` and log warning (degraded mode)

Wire into SessionManager.dispatch() lifecycle:
1. Before spawn: create_session + build_context
2. On decision progress: ingest
3. On completion: ingest final result

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_manager.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/manager.py tests/test_xmuse_core_agents_manager.py
git commit -m "feat(xmuse): integrate SessionManager with memoryOS API for knowledge persistence"
```

---

### Task 8: Integration Verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run full xmuse_core test suite**

Run: `uv run pytest tests/test_xmuse_core*.py -v`
Expected: all existing + new tests PASS

- [ ] **Step 2: Run memoryos test suite (fast)**

Run: `uv run pytest tests/ -m "not slow" -q --timeout=120`
Expected: all PASS, no regressions

- [ ] **Step 3: Run type checking**

Run: `uv run mypy src/xmuse_core/agents/ src/memoryos_lite/middleware.py`
Expected: no errors

- [ ] **Step 4: Run linter**

Run: `uv run ruff check src/xmuse_core/agents/ src/memoryos_lite/middleware.py`
Expected: no errors

- [ ] **Step 5: Final commit (if any fixes needed)**

```bash
git add -u
git commit -m "fix: resolve type/lint issues from agent framework implementation"
```
