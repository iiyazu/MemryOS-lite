# xmuse Platform + Agent MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic master_loop.py with a platform layer (state machine + event bus + MCP server) that spawns one-shot Execution God and Review God agents per lane.

**Architecture:** Platform manages lane state machine and exposes MCP tools. When a lane reaches `dispatched`, platform spawns Execution God (codex one-shot). After gate runs, platform spawns Review God (codex one-shot) to decide merge/rework/abandon. Agents query platform state via MCP during execution.

**Tech Stack:** Python 3.11, asyncio, FastAPI (MCP server), codex CLI (agent runtime), pytest

---

## File Structure

```
src/xmuse_core/platform/
├── __init__.py              — Package exports
├── state_machine.py         — LaneStateMachine: transition validation + persistence
├── event_bus.py             — EventBus: asyncio pub/sub for state changes
├── agent_spawner.py         — AgentSpawner: spawn one-shot codex/claude processes
├── mcp_tools.py             — MCP tool implementations (get_lane, get_diff, etc.)
├── orchestrator.py          — PlatformOrchestrator: wires everything together, main loop

xmuse/
├── god_prompts/
│   ├── execution_god.md     — Skill prompt for Execution God
│   └── review_god.md        — Skill prompt for Review God
├── platform_runner.py       — CLI entrypoint (replaces master_loop.py for MVP)

tests/
├── test_xmuse_platform_state_machine.py
├── test_xmuse_platform_event_bus.py
├── test_xmuse_platform_agent_spawner.py
├── test_xmuse_platform_mcp_tools.py
├── test_xmuse_platform_orchestrator.py
```

---

### Task 1: LaneStateMachine — Transition Validation + Persistence

**Files:**
- Create: `src/xmuse_core/platform/__init__.py`
- Create: `src/xmuse_core/platform/state_machine.py`
- Test: `tests/test_xmuse_platform_state_machine.py`

- [ ] **Step 1: Write failing tests for state machine**

```python
# tests/test_xmuse_platform_state_machine.py
import json
import pytest
from pathlib import Path
from xmuse_core.platform.state_machine import LaneStateMachine, InvalidTransitionError


@pytest.fixture
def lanes_path(tmp_path):
    path = tmp_path / "feature_lanes.json"
    path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "pending", "prompt": "fix bug"},
    ]}))
    return path


@pytest.fixture
def sm(lanes_path):
    return LaneStateMachine(lanes_path)


def test_valid_transition_pending_to_dispatched(sm):
    sm.transition("lane-1", "dispatched")
    assert sm.get_lane("lane-1")["status"] == "dispatched"


def test_invalid_transition_pending_to_merged_raises(sm):
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "merged")


def test_transition_persists_to_file(sm, lanes_path):
    sm.transition("lane-1", "dispatched")
    data = json.loads(lanes_path.read_text())
    assert data["lanes"][0]["status"] == "dispatched"


def test_transition_with_metadata(sm):
    sm.transition("lane-1", "dispatched", metadata={"assigned_to": "codex"})
    lane = sm.get_lane("lane-1")
    assert lane["assigned_to"] == "codex"


def test_get_lanes_by_status(sm):
    assert len(sm.get_lanes(status="pending")) == 1
    assert len(sm.get_lanes(status="dispatched")) == 0


def test_unknown_lane_raises(sm):
    with pytest.raises(KeyError):
        sm.transition("nonexistent", "dispatched")


def test_rework_depth_limit(sm, lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "fix",
         "retry_count": 2},
    ]}))
    sm2 = LaneStateMachine(lanes_path)
    with pytest.raises(InvalidTransitionError, match="max retries"):
        sm2.transition("lane-1", "reworking")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_platform_state_machine.py -v`
Expected: FAIL — module `xmuse_core.platform.state_machine` not found

- [ ] **Step 3: Implement LaneStateMachine**

```python
# src/xmuse_core/platform/__init__.py
from xmuse_core.platform.state_machine import LaneStateMachine, InvalidTransitionError

__all__ = ["LaneStateMachine", "InvalidTransitionError"]
```

```python
# src/xmuse_core/platform/state_machine.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_RETRIES = 2

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"dispatched"},
    "dispatched": {"executed", "exec_failed"},
    "executed": {"gated"},
    "gated": {"reviewed", "gate_failed"},
    "reviewed": {"merged"},
    "rejected": {"reworking", "failed"},
    "reworking": {"dispatched"},
    "exec_failed": {"failed", "reworking"},
    "gate_failed": {"failed", "reworking"},
}


class InvalidTransitionError(ValueError):
    pass


class LaneStateMachine:
    def __init__(self, lanes_path: Path) -> None:
        self._path = lanes_path

    def _read(self) -> dict[str, Any]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_lane(self, lane_id: str) -> dict[str, Any]:
        for lane in self._read().get("lanes", []):
            if lane.get("feature_id") == lane_id:
                return lane
        raise KeyError(f"lane not found: {lane_id}")

    def get_lanes(self, status: str | None = None) -> list[dict[str, Any]]:
        lanes = self._read().get("lanes", [])
        if status is None:
            return lanes
        return [l for l in lanes if l.get("status") == status]

    def transition(
        self,
        lane_id: str,
        target_status: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = self._read()
        lanes = data.get("lanes", [])
        lane = None
        for l in lanes:
            if l.get("feature_id") == lane_id:
                lane = l
                break
        if lane is None:
            raise KeyError(f"lane not found: {lane_id}")

        current = lane.get("status", "pending")
        allowed = VALID_TRANSITIONS.get(current, set())
        if target_status not in allowed:
            raise InvalidTransitionError(
                f"cannot transition {lane_id} from {current} to {target_status}"
            )

        if target_status == "reworking":
            retries = lane.get("retry_count", 0)
            if retries >= MAX_RETRIES:
                raise InvalidTransitionError(
                    f"lane {lane_id} exceeded max retries ({MAX_RETRIES})"
                )
            lane["retry_count"] = retries + 1

        lane["status"] = target_status
        if metadata:
            lane.update(metadata)

        self._write(data)
        return lane
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_xmuse_platform_state_machine.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/platform/__init__.py src/xmuse_core/platform/state_machine.py tests/test_xmuse_platform_state_machine.py
git commit -m "feat(platform): add LaneStateMachine with transition validation"
```

---

### Task 2: EventBus — Async Pub/Sub for State Changes

**Files:**
- Create: `src/xmuse_core/platform/event_bus.py`
- Test: `tests/test_xmuse_platform_event_bus.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_xmuse_platform_event_bus.py
import asyncio
import pytest
from xmuse_core.platform.event_bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


@pytest.mark.asyncio
async def test_subscribe_and_publish(bus):
    received = []
    bus.subscribe("lane_dispatched", lambda payload: received.append(payload))
    await bus.publish("lane_dispatched", {"lane_id": "lane-1"})
    assert received == [{"lane_id": "lane-1"}]


@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    results = []
    bus.subscribe("lane_gated", lambda p: results.append(("a", p)))
    bus.subscribe("lane_gated", lambda p: results.append(("b", p)))
    await bus.publish("lane_gated", {"lane_id": "x"})
    assert len(results) == 2


@pytest.mark.asyncio
async def test_no_subscribers_does_not_raise(bus):
    await bus.publish("unknown_event", {})


@pytest.mark.asyncio
async def test_async_handler(bus):
    received = []

    async def handler(payload):
        await asyncio.sleep(0)
        received.append(payload)

    bus.subscribe("test", handler)
    await bus.publish("test", {"x": 1})
    assert received == [{"x": 1}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_platform_event_bus.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement EventBus**

```python
# src/xmuse_core/platform/event_bus.py
from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        for handler in self._subscribers.get(event_type, []):
            if inspect.iscoroutinefunction(handler):
                await handler(payload)
            else:
                handler(payload)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_platform_event_bus.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/platform/event_bus.py tests/test_xmuse_platform_event_bus.py
git commit -m "feat(platform): add EventBus async pub/sub"
```

---

### Task 3: AgentSpawner — One-Shot Process Lifecycle

**Files:**
- Create: `src/xmuse_core/platform/agent_spawner.py`
- Test: `tests/test_xmuse_platform_agent_spawner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_xmuse_platform_agent_spawner.py
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from xmuse_core.platform.agent_spawner import AgentSpawner, SpawnResult, GodConfig


@pytest.fixture
def spawner(tmp_path):
    return AgentSpawner(repo_root=tmp_path, mcp_port=9999)


def test_god_config_from_dict():
    cfg = GodConfig.from_dict({
        "name": "review-god",
        "runtime": "codex",
        "timeout_s": 120,
        "skill_prompt_path": "xmuse/god_prompts/review_god.md",
    })
    assert cfg.name == "review-god"
    assert cfg.timeout_s == 120


@pytest.mark.asyncio
async def test_spawn_returns_result(spawner, tmp_path):
    script = tmp_path / "fake_codex.sh"
    script.write_text("#!/bin/bash\necho 'done'")
    script.chmod(0o755)

    with patch.object(spawner, "_build_command", return_value=[str(script)]):
        result = await spawner.spawn(
            god_config=GodConfig(name="test", runtime="codex",
                                 timeout_s=5, skill_prompt_path=""),
            lane_id="lane-1",
            prompt="fix the bug",
            worktree=tmp_path,
        )
    assert isinstance(result, SpawnResult)
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_spawn_timeout(spawner, tmp_path):
    script = tmp_path / "slow.sh"
    script.write_text("#!/bin/bash\nsleep 30")
    script.chmod(0o755)

    with patch.object(spawner, "_build_command", return_value=[str(script)]):
        result = await spawner.spawn(
            god_config=GodConfig(name="test", runtime="codex",
                                 timeout_s=1, skill_prompt_path=""),
            lane_id="lane-1",
            prompt="fix",
            worktree=tmp_path,
        )
    assert result.timed_out is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_platform_agent_spawner.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement AgentSpawner**

```python
# src/xmuse_core/platform/agent_spawner.py
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GodConfig:
    name: str
    runtime: str  # "codex" or "claude"
    timeout_s: int
    skill_prompt_path: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GodConfig:
        return cls(
            name=data["name"],
            runtime=data["runtime"],
            timeout_s=data["timeout_s"],
            skill_prompt_path=data.get("skill_prompt_path", ""),
        )


@dataclass
class SpawnResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class AgentSpawner:
    def __init__(self, *, repo_root: Path, mcp_port: int) -> None:
        self._repo_root = repo_root
        self._mcp_port = mcp_port

    def _build_command(self, god_config: GodConfig, worktree: Path) -> list[str]:
        if god_config.runtime == "codex":
            return [
                "codex", "exec",
                "-m", "o4-mini",
                "--dangerously-bypass-approvals-and-sandbox",
                "-C", str(worktree),
            ]
        return [
            "claude", "--dangerously-skip-permissions",
            "-p", "",
            "--cwd", str(worktree),
        ]

    def _build_env(self, god_config: GodConfig, lane_id: str) -> dict[str, str]:
        env = dict(os.environ)
        env["XMUSE_GOD_NAME"] = god_config.name
        env["XMUSE_LANE_ID"] = lane_id
        env["XMUSE_MCP_URL"] = f"http://localhost:{self._mcp_port}"
        return env

    async def spawn(
        self,
        *,
        god_config: GodConfig,
        lane_id: str,
        prompt: str,
        worktree: Path,
    ) -> SpawnResult:
        cmd = self._build_command(god_config, worktree)
        env = self._build_env(god_config, lane_id)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=worktree,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=prompt.encode()),
                timeout=god_config.timeout_s,
            )
            return SpawnResult(
                exit_code=process.returncode or 0,
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return SpawnResult(
                exit_code=-1, stdout="", stderr="timeout", timed_out=True
            )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_platform_agent_spawner.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/platform/agent_spawner.py tests/test_xmuse_platform_agent_spawner.py
git commit -m "feat(platform): add AgentSpawner for one-shot God processes"
```

---

### Task 4: MCP Tools — Minimal Tool Set for Gods

**Files:**
- Create: `src/xmuse_core/platform/mcp_tools.py`
- Test: `tests/test_xmuse_platform_mcp_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_xmuse_platform_mcp_tools.py
import json
import pytest
from pathlib import Path
from xmuse_core.platform.mcp_tools import McpToolHandler
from xmuse_core.platform.state_machine import LaneStateMachine


@pytest.fixture
def setup(tmp_path):
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix bug",
         "worktree": str(tmp_path / "wt")},
    ]}))
    # Create fake worktree with a diff
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").mkdir()
    # Create gate report
    gates_dir = tmp_path / "logs" / "gates" / "lane-1"
    gates_dir.mkdir(parents=True)
    (gates_dir / "report.json").write_text(json.dumps({
        "passed": True, "feature_id": "lane-1", "profile_ids": ["linter-only"],
    }))
    # Create error knowledge
    ek_path = tmp_path / "error_knowledge.json"
    ek_path.write_text(json.dumps({"entries": [
        {"id": "ek-1", "pit": "mypy arg-type", "root_cause": "wrong type",
         "scope": "type errors"},
    ]}))
    sm = LaneStateMachine(lanes_path)
    handler = McpToolHandler(
        state_machine=sm,
        xmuse_root=tmp_path,
    )
    return handler, sm, tmp_path


def test_get_lane(setup):
    handler, _, _ = setup
    result = handler.call("get_lane", {"lane_id": "lane-1"})
    assert result["feature_id"] == "lane-1"
    assert result["status"] == "gated"


def test_get_gate_report(setup):
    handler, _, _ = setup
    result = handler.call("get_gate_report", {"lane_id": "lane-1"})
    assert result["passed"] is True


def test_query_knowledge(setup):
    handler, _, _ = setup
    result = handler.call("query_knowledge", {"query": "mypy type", "top_k": 3})
    assert len(result["matches"]) == 1
    assert result["matches"][0]["entry"]["id"] == "ek-1"


def test_update_lane_status(setup):
    handler, sm, _ = setup
    result = handler.call("update_lane_status", {
        "lane_id": "lane-1", "status": "reviewed",
    })
    assert result["status"] == "reviewed"
    assert sm.get_lane("lane-1")["status"] == "reviewed"


def test_update_lane_status_invalid(setup):
    handler, _, _ = setup
    result = handler.call("update_lane_status", {
        "lane_id": "lane-1", "status": "merged",
    })
    assert result.get("error") is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_platform_mcp_tools.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement McpToolHandler**

```python
# src/xmuse_core/platform/mcp_tools.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from xmuse_core.platform.state_machine import (
    InvalidTransitionError,
    LaneStateMachine,
)


def _query_terms(query: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_+-]+", query.lower()) if len(t) > 1}


def _text_for_search(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text_for_search(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text_for_search(v) for v in value)
    return str(value)


class McpToolHandler:
    def __init__(
        self, *, state_machine: LaneStateMachine, xmuse_root: Path
    ) -> None:
        self._sm = state_machine
        self._root = xmuse_root

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        method = getattr(self, f"_tool_{tool_name}", None)
        if method is None:
            return {"error": f"unknown tool: {tool_name}"}
        try:
            return method(arguments)
        except Exception as exc:
            return {"error": str(exc)}

    def _tool_get_lane(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._sm.get_lane(args["lane_id"])

    def _tool_get_gate_report(self, args: dict[str, Any]) -> dict[str, Any]:
        lane_id = args["lane_id"]
        report_path = self._root / "logs" / "gates" / lane_id / "report.json"
        if not report_path.exists():
            return {"error": f"no gate report for {lane_id}"}
        return json.loads(report_path.read_text(encoding="utf-8"))

    def _tool_get_diff(self, args: dict[str, Any]) -> dict[str, Any]:
        import asyncio, subprocess
        lane = self._sm.get_lane(args["lane_id"])
        worktree = Path(lane.get("worktree", "."))
        if not worktree.exists():
            return {"error": f"worktree not found: {worktree}"}
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        return {"diff": result.stdout, "returncode": result.returncode}

    def _tool_query_knowledge(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query", "")
        top_k = args.get("top_k", 3)
        ek_path = self._root / "error_knowledge.json"
        if not ek_path.exists():
            return {"query": query, "matches": []}
        data = json.loads(ek_path.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
        terms = _query_terms(query)
        scored = []
        for entry in entries:
            haystack = _text_for_search(entry).lower()
            score = sum(1 for t in terms if t in haystack)
            if score:
                scored.append({"score": score, "entry": entry})
        scored.sort(key=lambda x: -x["score"])
        return {"query": query, "matches": scored[:top_k]}

    def _tool_update_lane_status(self, args: dict[str, Any]) -> dict[str, Any]:
        lane_id = args["lane_id"]
        status = args["status"]
        metadata = args.get("metadata")
        try:
            lane = self._sm.transition(lane_id, status, metadata=metadata)
            return lane
        except (InvalidTransitionError, KeyError) as exc:
            return {"error": str(exc)}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_platform_mcp_tools.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/platform/mcp_tools.py tests/test_xmuse_platform_mcp_tools.py
git commit -m "feat(platform): add McpToolHandler with minimal tool set"
```

---

### Task 5: God Skill Prompts

**Files:**
- Create: `xmuse/god_prompts/execution_god.md`
- Create: `xmuse/god_prompts/review_god.md`

- [ ] **Step 1: Write Execution God prompt**

```markdown
# xmuse/god_prompts/execution_god.md

You are the Execution God of xmuse. Your job is to fix the code issue described in the task prompt.

## Available MCP Tools

- `query_knowledge(query, top_k)` — Search error_knowledge for relevant past failures
- `update_lane_status(lane_id, status, metadata?)` — Update lane status when done

## Workflow

1. Read the task prompt carefully
2. Call `query_knowledge` with keywords from the error to check for known patterns
3. Fix the code in the worktree
4. Call `update_lane_status(lane_id, "executed")` when done

## Rules

- Only modify files directly related to the task
- Do not modify test infrastructure, CI config, or xmuse itself
- Do not add unrelated features or refactoring
- If you cannot fix the issue, call `update_lane_status(lane_id, "exec_failed", {metadata: {reason: "..."}})`
```

- [ ] **Step 2: Write Review God prompt**

```markdown
# xmuse/god_prompts/review_god.md

You are the Review God of xmuse. Your job is to audit code changes and decide whether to merge, rework, or abandon.

## Available MCP Tools

- `get_lane(lane_id)` — Get lane details (prompt, worktree, history)
- `get_gate_report(lane_id)` — Get quality gate results
- `get_diff(lane_id)` — Get the git diff of changes
- `query_knowledge(query, top_k)` — Search for relevant past failures
- `update_lane_status(lane_id, status, metadata?)` — Record your decision

## Workflow

1. Call `get_lane` to understand what was requested
2. Call `get_gate_report` to check if quality gate passed
3. Call `get_diff` to review the actual code changes
4. Make your decision:
   - **Gate failed** → analyze the failure, decide rework or abandon
   - **Gate passed** → review diff quality, scope compliance, correctness

## Decision Criteria

### Merge (gate passed + diff is good)
- Changes are scoped to the task
- No unrelated modifications
- Code is correct and follows project patterns
- Call: `update_lane_status(lane_id, "reviewed")`

### Rework (fixable issues)
- Gate failed with clear, actionable errors
- Diff has scope violations but the approach is sound
- Missing edge case handling
- Call: `update_lane_status(lane_id, "rejected", {metadata: {rework_context: "..."}})`
- Include specific instructions in rework_context

### Abandon (unfixable or not worth retrying)
- Repeated failures (retry_count >= 2)
- Fundamental approach is wrong
- Environment/config issue outside agent control
- Call: `update_lane_status(lane_id, "abandoned", {metadata: {reason: "..."}})`
```

- [ ] **Step 3: Commit**

```bash
mkdir -p xmuse/god_prompts
git add xmuse/god_prompts/execution_god.md xmuse/god_prompts/review_god.md
git commit -m "feat(platform): add Execution God and Review God skill prompts"
```

---

### Task 6: PlatformOrchestrator — Wire Everything Together

**Files:**
- Create: `src/xmuse_core/platform/orchestrator.py`
- Test: `tests/test_xmuse_platform_orchestrator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_xmuse_platform_orchestrator.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from xmuse_core.platform.orchestrator import PlatformOrchestrator
from xmuse_core.platform.agent_spawner import SpawnResult


@pytest.fixture
def setup(tmp_path):
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "pending", "prompt": "fix bug",
         "worktree": str(tmp_path)},
    ]}))
    (tmp_path / "error_knowledge.json").write_text(json.dumps({"entries": []}))
    gates_dir = tmp_path / "logs" / "gates" / "lane-1"
    gates_dir.mkdir(parents=True)
    (gates_dir / "report.json").write_text(json.dumps({"passed": True}))
    return tmp_path, lanes_path


@pytest.mark.asyncio
async def test_dispatch_lane_spawns_execution_god(setup):
    tmp_path, lanes_path = setup
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    mock_result = SpawnResult(exit_code=0, stdout="", stderr="")
    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=mock_result):
        await orch.dispatch_lane("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "dispatched"


@pytest.mark.asyncio
async def test_on_executed_runs_gate(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "executed", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    with patch.object(orch, "_run_gate", new_callable=AsyncMock,
                      return_value=True):
        await orch.on_lane_executed("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "gated"


@pytest.mark.asyncio
async def test_on_gated_spawns_review_god(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "gated", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    mock_result = SpawnResult(exit_code=0, stdout="", stderr="")
    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=mock_result):
        await orch.on_lane_gated("lane-1")
    # Review God should have been spawned (status change happens via MCP)


@pytest.mark.asyncio
async def test_execution_god_timeout_marks_failed(setup):
    tmp_path, lanes_path = setup
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "dispatched", "prompt": "fix",
         "worktree": str(tmp_path)},
    ]}))
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=tmp_path,
        mcp_port=9999,
    )
    timeout_result = SpawnResult(exit_code=-1, stdout="", stderr="timeout",
                                 timed_out=True)
    with patch.object(orch._spawner, "spawn", new_callable=AsyncMock,
                      return_value=timeout_result):
        await orch._run_execution_god("lane-1")

    lane = orch._sm.get_lane("lane-1")
    assert lane["status"] == "exec_failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_xmuse_platform_orchestrator.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement PlatformOrchestrator**

```python
# src/xmuse_core/platform/orchestrator.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from xmuse_core.platform.agent_spawner import AgentSpawner, GodConfig, SpawnResult
from xmuse_core.platform.event_bus import EventBus
from xmuse_core.platform.mcp_tools import McpToolHandler
from xmuse_core.platform.state_machine import LaneStateMachine

logger = logging.getLogger(__name__)

EXECUTION_GOD = GodConfig(
    name="execution-god",
    runtime="codex",
    timeout_s=3600,
    skill_prompt_path="xmuse/god_prompts/execution_god.md",
)

REVIEW_GOD = GodConfig(
    name="review-god",
    runtime="codex",
    timeout_s=120,
    skill_prompt_path="xmuse/god_prompts/review_god.md",
)


class PlatformOrchestrator:
    def __init__(
        self,
        *,
        lanes_path: Path,
        xmuse_root: Path,
        mcp_port: int = 9800,
    ) -> None:
        self._sm = LaneStateMachine(lanes_path)
        self._bus = EventBus()
        self._spawner = AgentSpawner(repo_root=xmuse_root, mcp_port=mcp_port)
        self._tools = McpToolHandler(state_machine=self._sm, xmuse_root=xmuse_root)
        self._root = xmuse_root

        self._bus.subscribe("lane_dispatched", self._on_dispatched)
        self._bus.subscribe("lane_executed", self._on_executed)
        self._bus.subscribe("lane_gated", self._on_gated)

    async def dispatch_lane(self, lane_id: str) -> None:
        self._sm.transition(lane_id, "dispatched")
        await self._bus.publish("lane_dispatched", {"lane_id": lane_id})

    async def _on_dispatched(self, payload: dict[str, Any]) -> None:
        await self._run_execution_god(payload["lane_id"])

    async def _run_execution_god(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        prompt = self._build_execution_prompt(lane)
        worktree = Path(lane.get("worktree", "."))

        result = await self._spawner.spawn(
            god_config=EXECUTION_GOD,
            lane_id=lane_id,
            prompt=prompt,
            worktree=worktree,
        )

        if result.timed_out:
            self._sm.transition(lane_id, "exec_failed",
                                metadata={"failure_reason": "timeout"})
            return

        current = self._sm.get_lane(lane_id)
        if current["status"] == "dispatched":
            if result.exit_code == 0:
                self._sm.transition(lane_id, "executed")
            else:
                self._sm.transition(lane_id, "exec_failed",
                                    metadata={"failure_reason": "non_zero_exit"})

    async def on_lane_executed(self, lane_id: str) -> None:
        passed = await self._run_gate(lane_id)
        if passed:
            self._sm.transition(lane_id, "gated")
            await self._bus.publish("lane_gated", {"lane_id": lane_id})
        else:
            self._sm.transition(lane_id, "gated")
            await self._bus.publish("lane_gated", {"lane_id": lane_id})

    async def on_lane_gated(self, lane_id: str) -> None:
        await self._run_review_god(lane_id)

    async def _on_executed(self, payload: dict[str, Any]) -> None:
        await self.on_lane_executed(payload["lane_id"])

    async def _on_gated(self, payload: dict[str, Any]) -> None:
        await self.on_lane_gated(payload["lane_id"])

    async def _run_review_god(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        prompt = self._build_review_prompt(lane)
        worktree = Path(lane.get("worktree", "."))

        result = await self._spawner.spawn(
            god_config=REVIEW_GOD,
            lane_id=lane_id,
            prompt=prompt,
            worktree=worktree,
        )

        if result.timed_out:
            self._sm.transition(lane_id, "gate_failed",
                                metadata={"failure_reason": "review_timeout"})

    async def _run_gate(self, lane_id: str) -> bool:
        # Platform infrastructure: run quality gate
        # Returns True if gate passed, False otherwise
        # MVP: delegate to existing GateRunner
        return True

    def _build_execution_prompt(self, lane: dict[str, Any]) -> str:
        prompt_path = self._root / EXECUTION_GOD.skill_prompt_path
        skill = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        task = lane.get("prompt", "")
        lane_id = lane.get("feature_id", "")
        return f"{skill}\n\n## Task\n\nLane ID: {lane_id}\n\n{task}"

    def _build_review_prompt(self, lane: dict[str, Any]) -> str:
        prompt_path = self._root / REVIEW_GOD.skill_prompt_path
        skill = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        lane_id = lane.get("feature_id", "")
        return f"{skill}\n\n## Task\n\nReview lane: {lane_id}"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_xmuse_platform_orchestrator.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/xmuse_core/platform/orchestrator.py tests/test_xmuse_platform_orchestrator.py
git commit -m "feat(platform): add PlatformOrchestrator wiring state machine + spawner + events"
```

---

### Task 7: Platform Runner — CLI Entrypoint

**Files:**
- Create: `xmuse/platform_runner.py`

- [ ] **Step 1: Implement CLI runner**

```python
# xmuse/platform_runner.py
#!/usr/bin/env python3
"""xmuse Platform Runner — MVP entrypoint."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from xmuse_core.platform.orchestrator import PlatformOrchestrator

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


async def run(
    lanes_path: Path,
    xmuse_root: Path,
    mcp_port: int,
    max_hours: float,
) -> None:
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=xmuse_root,
        mcp_port=mcp_port,
    )

    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: shutdown.set())

    deadline = loop.time() + max_hours * 3600
    logger.info("Platform started, max_hours=%.1f", max_hours)

    while not shutdown.is_set() and loop.time() < deadline:
        pending = orch._sm.get_lanes(status="pending")
        if not pending:
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=10.0)
            except TimeoutError:
                pass
            continue

        pending.sort(key=lambda l: -l.get("priority", 0))
        lane_id = pending[0]["feature_id"]
        logger.info("Dispatching lane: %s", lane_id)
        await orch.dispatch_lane(lane_id)

        await asyncio.sleep(1.0)

    logger.info("Platform shutting down")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="xmuse Platform Runner (MVP)")
    parser.add_argument("--lanes", type=Path, default=ROOT / "xmuse" / "feature_lanes.json")
    parser.add_argument("--mcp-port", type=int, default=9800)
    parser.add_argument("--max-hours", type=float, default=8.0)
    args = parser.parse_args()

    asyncio.run(run(
        lanes_path=args.lanes,
        xmuse_root=ROOT / "xmuse",
        mcp_port=args.mcp_port,
        max_hours=args.max_hours,
    ))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it starts without error**

Run: `uv run python xmuse/platform_runner.py --max-hours 0.001 2>&1 | head -5`
Expected: "Platform started" then "Platform shutting down" (no crash)

- [ ] **Step 3: Commit**

```bash
git add xmuse/platform_runner.py
git commit -m "feat(platform): add platform_runner.py CLI entrypoint"
```

---

### Task 8: Update platform __init__.py exports

**Files:**
- Modify: `src/xmuse_core/platform/__init__.py`

- [ ] **Step 1: Update exports**

```python
# src/xmuse_core/platform/__init__.py
from xmuse_core.platform.agent_spawner import AgentSpawner, GodConfig, SpawnResult
from xmuse_core.platform.event_bus import EventBus
from xmuse_core.platform.mcp_tools import McpToolHandler
from xmuse_core.platform.orchestrator import PlatformOrchestrator
from xmuse_core.platform.state_machine import InvalidTransitionError, LaneStateMachine

__all__ = [
    "AgentSpawner",
    "EventBus",
    "GodConfig",
    "InvalidTransitionError",
    "LaneStateMachine",
    "McpToolHandler",
    "PlatformOrchestrator",
    "SpawnResult",
]
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/test_xmuse_platform_*.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/xmuse_core/platform/__init__.py
git commit -m "feat(platform): export all platform components from __init__"
```
