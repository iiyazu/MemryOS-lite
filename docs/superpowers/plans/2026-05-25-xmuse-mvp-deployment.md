# xmuse MVP Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing agent framework into a runnable MVP that dispatches Codex CLI one-shot tasks from a JSON config, with memoryOS as knowledge layer.

**Architecture:** Single asyncio entry point (`xmuse/xmuse_main.py`) loads feature_lanes.json, enqueues tasks into WorklistConsumer, which dispatches via a simplified SessionManager using `codex exec` one-shot mode. MemoryOSClient provides context before execution and persists results after.

**Tech Stack:** Python 3.11+, asyncio, httpx, Codex CLI, FastAPI (memoryOS API)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `xmuse/xmuse_main.py` | CLI entry point, asyncio loop, signal handling |
| `xmuse/feature_lanes.json` | Human-edited task queue |
| `xmuse/agents.json` | Agent registry config |
| `src/xmuse_core/agents/memoryos_client.py` | Async HTTP client for memoryOS API |
| `src/xmuse_core/agents/launchers/codex.py` | Modify: one-shot `codex exec` mode |
| `src/xmuse_core/agents/manager.py` | Modify: one-shot dispatch (skip handshake) |
| `src/xmuse_core/agents/consumer.py` | Modify: adapt dispatch call signature |
| `tests/test_xmuse_mvp_main.py` | Integration test for main entry |
| `tests/test_xmuse_memoryos_client.py` | MemoryOSClient unit tests |

---

### Task 1: Adapt CodexLauncher for one-shot mode

**Files:**
- Modify: `src/xmuse_core/agents/launchers/codex.py`
- Modify: `tests/test_xmuse_core_agents_launchers.py`

- [ ] **Step 1: Update test for new build_command**

Add to `tests/test_xmuse_core_agents_launchers.py`:
```python
def test_codex_build_command_exec_mode():
    launcher = CodexLauncher()
    cmd = launcher.build_command("my-feature", Path("/tmp/worktree"))
    assert cmd == ["codex", "exec", "--approval-mode", "full-auto", "--cwd", "/tmp/worktree"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xmuse_core_agents_launchers.py::test_codex_build_command_exec_mode -v`
Expected: FAIL (old command doesn't include "exec")

- [ ] **Step 3: Update CodexLauncher**

Replace `build_command` in `src/xmuse_core/agents/launchers/codex.py`:
```python
def build_command(self, feature_id: str, worktree: Path) -> list[str]:
    return ["codex", "exec", "--approval-mode", "full-auto", "--cwd", str(worktree)]
```

- [ ] **Step 4: Fix old test that expects the previous command format**

Update `test_codex_build_command` to match new format:
```python
def test_codex_build_command():
    launcher = CodexLauncher()
    cmd = launcher.build_command("my-feature", Path("/tmp/worktree"))
    assert cmd == ["codex", "exec", "--approval-mode", "full-auto", "--cwd", "/tmp/worktree"]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_launchers.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/xmuse_core/agents/launchers/codex.py tests/test_xmuse_core_agents_launchers.py
git commit -m "feat(xmuse): adapt CodexLauncher for one-shot codex exec mode"
```

---

### Task 2: Simplify SessionManager dispatch for one-shot mode

**Files:**
- Modify: `src/xmuse_core/agents/manager.py`
- Modify: `tests/test_xmuse_core_agents_manager.py`

- [ ] **Step 1: Write test for one-shot dispatch**

Add to `tests/test_xmuse_core_agents_manager.py`:
```python
ONE_SHOT_AGENT = """\
import sys
prompt = sys.stdin.read()
print(f"executed: {prompt.strip()}")
"""

@pytest.mark.asyncio
async def test_dispatch_one_shot(tmp_path):
    class OneShotLauncher:
        def build_command(self, feature_id, worktree):
            return [sys.executable, "-c", ONE_SHOT_AGENT]
        def format_prompt(self, task, context):
            return task
        def build_env(self, feature_id):
            return None
        def parse_output(self, msg):
            return None

    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: OneShotLauncher()},
        state_file=tmp_path / "active.json",
    )
    result = await mgr.dispatch_one_shot(
        agent=_make_agent(),
        feature_id="test-feature",
        prompt="do something",
        worktree=tmp_path,
    )
    assert result is not None
    assert result.status == "success"
    assert "executed: do something" in result.artifacts.get("stdout", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xmuse_core_agents_manager.py::test_dispatch_one_shot -v`
Expected: FAIL (dispatch_one_shot not defined)

- [ ] **Step 3: Implement dispatch_one_shot in SessionManager**

Add to `src/xmuse_core/agents/manager.py`:
```python
async def dispatch_one_shot(
    self,
    agent: AgentDescriptor,
    feature_id: str,
    prompt: str,
    worktree: Path,
    context: str = "",
    timeout: float = 1800.0,  # 30 min default
) -> AgentOutput:
    launcher = self._launchers[agent.runtime]
    cmd = launcher.build_command(feature_id, worktree)
    env = launcher.build_env(feature_id)
    formatted = launcher.format_prompt(prompt, context)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    active = ActiveSession(
        session=LocalSession(process),
        state=SessionState.RUNNING,
        feature_id=feature_id,
        agent=agent,
    )
    self._active[feature_id] = active
    self._persist_active()

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(input=formatted.encode()),
            timeout=timeout,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        self._active.pop(feature_id, None)
        self._persist_active()
        return AgentOutput(status="timeout", error_message="process timed out")

    self._active.pop(feature_id, None)
    self._persist_active()

    stdout_str = stdout_bytes.decode(errors="replace")
    stderr_str = stderr_bytes.decode(errors="replace")

    if process.returncode == 0:
        return AgentOutput(
            status="success",
            artifacts={"stdout": stdout_str, "stderr": stderr_str},
        )
    return AgentOutput(
        status="error",
        error_code=f"exit_{process.returncode}",
        error_message=stderr_str[:500] or stdout_str[:500],
        artifacts={"stdout": stdout_str, "stderr": stderr_str},
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_manager.py -v`
Expected: all PASS (old tests + new test)

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/manager.py tests/test_xmuse_core_agents_manager.py
git commit -m "feat(xmuse): add dispatch_one_shot for Codex exec one-shot mode"
```

---

### Task 3: Adapt WorklistConsumer to use dispatch_one_shot

**Files:**
- Modify: `src/xmuse_core/agents/consumer.py`
- Modify: `tests/test_xmuse_core_agents_consumer.py`

- [ ] **Step 1: Update consumer to unpack TaskDescriptor**

Replace the dispatch call in `src/xmuse_core/agents/consumer.py` `run()`:
```python
async def run(self) -> None:
    self._running_task = asyncio.current_task()
    while not self._shutdown_event.is_set():
        try:
            task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except TimeoutError:
            continue
        async with self._semaphore:
            agent = self._registry.select(
                task.required_capabilities,
                exclude_runtime=task.developed_by_runtime,
            )
            await self._session_mgr.dispatch_one_shot(
                agent=agent,
                feature_id=task.feature_id,
                prompt=task.prompt,
                worktree=Path(task.worktree) if task.worktree else Path("."),
            )
```

- [ ] **Step 2: Add `worktree` field to TaskDescriptor**

In `src/xmuse_core/agents/consumer.py`:
```python
@dataclass
class TaskDescriptor:
    feature_id: str
    task_type: Literal["execute", "review", "rework"]
    prompt: str
    worktree: str = "."
    required_capabilities: list[str] = field(default_factory=lambda: ["code"])
    developed_by_runtime: AgentRuntime | None = None
```

- [ ] **Step 3: Update consumer test to use dispatch_one_shot mock**

In `tests/test_xmuse_core_agents_consumer.py`, change mock setup:
```python
@pytest.mark.asyncio
async def test_run_dispatches_task():
    reg = _make_registry()
    mgr = AsyncMock()
    consumer = WorklistConsumer(reg, mgr, max_concurrent=4)

    task = TaskDescriptor(feature_id="f1", task_type="execute", prompt="do it",
                          worktree="/tmp/wt", required_capabilities=["code"])
    await consumer.enqueue(task)

    run_task = asyncio.create_task(consumer.run())
    await asyncio.sleep(0.1)
    consumer.shutdown()
    await asyncio.sleep(0.1)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    mgr.dispatch_one_shot.assert_called_once()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_core_agents_consumer.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/consumer.py tests/test_xmuse_core_agents_consumer.py
git commit -m "feat(xmuse): wire WorklistConsumer to dispatch_one_shot with TaskDescriptor"
```

---

### Task 4: MemoryOSClient

**Files:**
- Create: `src/xmuse_core/agents/memoryos_client.py`
- Test: `tests/test_xmuse_memoryos_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_xmuse_memoryos_client.py
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from xmuse_core.agents.memoryos_client import MemoryOSClient


@pytest.mark.asyncio
async def test_create_session():
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, json={"id": "ses_123", "title": "test", "created_at": "2026-01-01T00:00:00Z"}
    ))
    async with httpx.AsyncClient(transport=transport) as client:
        mos = MemoryOSClient(base_url="http://test", http_client=client)
        sid = await mos.create_session("feature:my-feat")
        assert sid == "ses_123"


@pytest.mark.asyncio
async def test_build_context():
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, json={"context": "some historical context"}
    ))
    async with httpx.AsyncClient(transport=transport) as client:
        mos = MemoryOSClient(base_url="http://test", http_client=client)
        ctx = await mos.build_context("ses_123", "fix the bug", budget=4096)
        assert "context" in ctx


@pytest.mark.asyncio
async def test_ingest():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient(transport=transport) as client:
        mos = MemoryOSClient(base_url="http://test", http_client=client)
        await mos.ingest("ses_123", "assistant", "I fixed the bug")


@pytest.mark.asyncio
async def test_degraded_mode_on_connection_error():
    transport = httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    async with httpx.AsyncClient(transport=transport) as client:
        mos = MemoryOSClient(base_url="http://test", http_client=client)
        sid = await mos.create_session("test")
        assert sid is None  # degraded, no crash
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_memoryos_client.py -v`

- [ ] **Step 3: Implement MemoryOSClient**

Create `src/xmuse_core/agents/memoryos_client.py`:
```python
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MemoryOSClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = http_client

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client:
            return self._client
        self._client = httpx.AsyncClient(base_url=self._base_url, headers=self._headers())
        return self._client

    async def create_session(self, title: str) -> str | None:
        try:
            client = await self._get_client()
            resp = await client.post(f"{self._base_url}/sessions", json={"title": title})
            resp.raise_for_status()
            return resp.json()["id"]
        except (httpx.HTTPError, KeyError) as e:
            logger.warning("memoryos create_session failed: %s", e)
            return None

    async def build_context(self, session_id: str, task: str, budget: int = 4096) -> str:
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self._base_url}/sessions/{session_id}/build-context",
                json={"task": task, "budget": budget},
            )
            resp.raise_for_status()
            return str(resp.json())
        except httpx.HTTPError as e:
            logger.warning("memoryos build_context failed: %s", e)
            return ""

    async def ingest(self, session_id: str, role: str, content: str) -> None:
        try:
            client = await self._get_client()
            await client.post(
                f"{self._base_url}/sessions/{session_id}/ingest",
                json={"role": role, "content": content},
            )
        except httpx.HTTPError as e:
            logger.warning("memoryos ingest failed: %s", e)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_memoryos_client.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/agents/memoryos_client.py tests/test_xmuse_memoryos_client.py
git commit -m "feat(xmuse): add MemoryOSClient with degraded mode on failure"
```

---

### Task 5: xmuse_main.py entry point

**Files:**
- Create: `xmuse/xmuse_main.py`
- Create: `xmuse/agents.json`
- Create: `xmuse/feature_lanes.json`
- Test: `tests/test_xmuse_mvp_main.py`

- [ ] **Step 1: Create agents.json config**

Create `xmuse/agents.json`:
```json
{
  "agents": [
    {
      "runtime": "codex",
      "name": "codex-worker-1",
      "capabilities": ["code", "test", "review"],
      "session_config": {
        "transport": "local",
        "heartbeat_interval_s": 30
      }
    }
  ]
}
```

- [ ] **Step 2: Create empty feature_lanes.json**

Create `xmuse/feature_lanes.json`:
```json
{
  "lanes": []
}
```

- [ ] **Step 3: Write test for lane loading**

```python
# tests/test_xmuse_mvp_main.py
import json
from pathlib import Path

import pytest


def test_load_lanes(tmp_path):
    lanes_file = tmp_path / "lanes.json"
    lanes_file.write_text(json.dumps({"lanes": [
        {"feature_id": "f1", "task_type": "execute", "prompt": "do it",
         "worktree": "/tmp/wt", "branch": "feat/f1", "capabilities": ["code"]},
        {"feature_id": "f2", "task_type": "execute", "prompt": "do other",
         "worktree": "/tmp/wt2", "branch": "feat/f2", "capabilities": ["code"],
         "status": "done"},
    ]}))

    # Import after creating file
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "xmuse"))
    from xmuse_main import load_lanes

    lanes = load_lanes(lanes_file)
    assert len(lanes) == 1  # skips "done" lanes
    assert lanes[0].feature_id == "f1"


def test_load_lanes_empty(tmp_path):
    lanes_file = tmp_path / "lanes.json"
    lanes_file.write_text(json.dumps({"lanes": []}))

    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "xmuse"))
    from xmuse_main import load_lanes

    lanes = load_lanes(lanes_file)
    assert lanes == []
```

- [ ] **Step 4: Implement xmuse_main.py**

Create `xmuse/xmuse_main.py`:
```python
#!/usr/bin/env python3
"""xmuse MVP — asyncio entry point for session-based agent orchestration."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from xmuse_core.agents.consumer import TaskDescriptor, WorklistConsumer
from xmuse_core.agents.manager import SessionManager
from xmuse_core.agents.memoryos_client import MemoryOSClient
from xmuse_core.agents.registry import AgentRegistry, AgentRuntime
from xmuse_core.agents.launchers.codex import CodexLauncher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("xmuse")


def load_lanes(path: Path) -> list[TaskDescriptor]:
    data = json.loads(path.read_text())
    tasks = []
    for lane in data.get("lanes", []):
        if lane.get("status") == "done":
            continue
        tasks.append(TaskDescriptor(
            feature_id=lane["feature_id"],
            task_type=lane.get("task_type", "execute"),
            prompt=lane["prompt"],
            worktree=lane.get("worktree", "."),
            required_capabilities=lane.get("capabilities", ["code"]),
        ))
    return tasks


async def main(args: argparse.Namespace) -> None:
    registry = AgentRegistry.from_file(Path(args.config))
    launchers = {AgentRuntime.CODEX: CodexLauncher()}
    state_file = Path("xmuse/active_sessions.json")

    mgr = SessionManager(launchers=launchers, state_file=state_file)
    consumer = WorklistConsumer(registry=registry, session_mgr=mgr, max_concurrent=args.concurrency)

    lanes = load_lanes(Path(args.lanes))
    logger.info("Loaded %d pending lanes from %s", len(lanes), args.lanes)
    for task in lanes:
        await consumer.enqueue(task)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown(consumer, mgr)))

    logger.info("xmuse master loop started (concurrency=%d)", args.concurrency)
    await consumer.run()


async def _shutdown(consumer: WorklistConsumer, mgr: SessionManager) -> None:
    logger.info("Shutdown signal received")
    consumer.shutdown()
    await mgr.graceful_shutdown()


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xmuse MVP master loop")
    parser.add_argument("--config", default="xmuse/agents.json", help="Agent registry config")
    parser.add_argument("--lanes", default="xmuse/feature_lanes.json", help="Feature lanes file")
    parser.add_argument("--memoryos-url", default="http://127.0.0.1:8000", help="MemoryOS API URL")
    parser.add_argument("--concurrency", type=int, default=2, help="Max concurrent agents")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(cli()))
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_xmuse_mvp_main.py -v`
Expected: all PASS

- [ ] **Step 6: Verify xmuse_main.py starts and exits cleanly with empty lanes**

Run: `timeout 3 python xmuse/xmuse_main.py --lanes xmuse/feature_lanes.json 2>&1 || true`
Expected: starts, logs "Loaded 0 pending lanes", then exits on timeout (no crash)

- [ ] **Step 7: Commit**

```bash
git add xmuse/xmuse_main.py xmuse/agents.json xmuse/feature_lanes.json tests/test_xmuse_mvp_main.py
git commit -m "feat(xmuse): add MVP main entry point with lane loading and asyncio loop"
```

---

### Task 6: End-to-end smoke test with mock agent

**Files:**
- Create: `tests/test_xmuse_mvp_e2e.py`

- [ ] **Step 1: Write E2E test using a mock script as "codex"**

```python
# tests/test_xmuse_mvp_e2e.py
"""E2E smoke test: full dispatch cycle with a mock codex script."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest

from xmuse_core.agents.consumer import TaskDescriptor, WorklistConsumer
from xmuse_core.agents.manager import SessionManager
from xmuse_core.agents.registry import AgentDescriptor, AgentRegistry, AgentRuntime, SessionConfig


MOCK_CODEX = """\
import sys
prompt = sys.stdin.read()
print(f"MOCK_CODEX executed: {prompt.strip()}")
"""


class MockCodexLauncher:
    def build_command(self, feature_id, worktree):
        return [sys.executable, "-c", MOCK_CODEX]

    def format_prompt(self, task, context):
        if context:
            return f"{context}\\n---\\n{task}"
        return task

    def build_env(self, feature_id):
        return None

    def parse_output(self, msg):
        return None


@pytest.mark.asyncio
async def test_full_dispatch_cycle(tmp_path):
    registry = AgentRegistry([
        AgentDescriptor(AgentRuntime.CODEX, "mock-codex", ["code", "test"], SessionConfig()),
    ])
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: MockCodexLauncher()},
        state_file=tmp_path / "active.json",
    )
    consumer = WorklistConsumer(registry=registry, session_mgr=mgr, max_concurrent=2)

    task = TaskDescriptor(
        feature_id="test-e2e",
        task_type="execute",
        prompt="Fix the flaky test in test_store.py",
        worktree=str(tmp_path),
        required_capabilities=["code"],
    )
    await consumer.enqueue(task)

    # Run consumer with a timeout so it doesn't hang
    run_task = asyncio.create_task(consumer.run())
    await asyncio.sleep(1.0)
    consumer.shutdown()
    await asyncio.sleep(0.5)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    # Verify no active sessions remain
    assert len(mgr.active_sessions) == 0
```

- [ ] **Step 2: Run E2E test**

Run: `uv run pytest tests/test_xmuse_mvp_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_xmuse_mvp_e2e.py
git commit -m "test(xmuse): add E2E smoke test for full dispatch cycle"
```

---

### Task 7: Integration verification

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/test_xmuse_core*.py tests/test_memoryos_middleware.py tests/test_memoryos_agent_endpoints.py tests/test_xmuse_mvp*.py tests/test_xmuse_memoryos_client.py -v`
Expected: all PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/xmuse_core/agents/ xmuse/xmuse_main.py`
Expected: no errors (or fix any found)

- [ ] **Step 3: Verify startup with real config**

Run: `timeout 3 python xmuse/xmuse_main.py 2>&1; echo "exit: $?"`
Expected: clean startup log, exits on timeout with no crash

- [ ] **Step 4: Final commit if fixes needed**

```bash
git add -u
git commit -m "fix: resolve lint/test issues from MVP integration"
```
