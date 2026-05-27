# xmuse GOD Session Layer Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 1 of the session-first xmuse migration: persistent GOD identities with stable addressing, a dedicated state-normalization module for mixed-run semantics, and dashboard visibility that no longer assumes sessions are keyed by `feature_id`.

**Architecture:** Keep the current MVP chat-to-lane and one-shot worker path running. Add a new persistent GOD session layer beside it, keyed by `god_session_id` and routed by `session_address` / `session_inbox_id`, while introducing a single normalization module that both runtime and dashboard can call to interpret legacy lane states during migration.

**Tech Stack:** Python 3.11, asyncio, FastAPI, dataclasses, json, pytest

---

## File Structure

```text
src/xmuse_core/platform/
├── state_normalizer.py              — Mixed-run lane status normalization and metrics helpers

src/xmuse_core/agents/
├── god_session_registry.py          — Stable GOD identity records, persistence, lookup by session id/address/inbox
├── god_session_layer.py             — Persistent CLI session orchestration for architect/execute/review GODs
└── manager.py                       — Leave one-shot worker flow intact; only touch if shared helpers are necessary

src/xmuse_core/routing/
└── session_router.py                — Router that resolves `session_address` to `god_session_id` and appends inbox work

xmuse/
└── dashboard_api.py                 — Read new session registry shape and normalized lane states

tests/
├── test_xmuse_state_normalizer.py
├── test_xmuse_god_session_registry.py
├── test_xmuse_god_session_layer.py
├── test_xmuse_session_router.py
└── test_xmuse_dashboard_api.py
```

---

### Task 1: Add the mixed-run state normalization module

**Files:**
- Create: `src/xmuse_core/platform/state_normalizer.py`
- Test: `tests/test_xmuse_state_normalizer.py`

- [ ] **Step 1: Write the failing normalization tests**

```python
# tests/test_xmuse_state_normalizer.py
from xmuse_core.platform.state_normalizer import (
    normalize_lane_state,
    summarize_lane_states,
)


def test_normalize_pending_to_ready() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "pending"})
    assert normalized.raw_status == "pending"
    assert normalized.normalized_status == "ready"
    assert normalized.is_terminal is False


def test_normalize_failed_prefers_specific_failure_reason() -> None:
    normalized = normalize_lane_state(
        {
            "feature_id": "lane-1",
            "status": "failed",
            "failure_reason": "gate_failed",
        }
    )
    assert normalized.normalized_status == "gate_failed"


def test_summarize_lane_states_aggregates_normalized_statuses() -> None:
    summary = summarize_lane_states(
        [
            {"feature_id": "lane-1", "status": "pending"},
            {"feature_id": "lane-2", "status": "merged"},
            {"feature_id": "lane-3", "status": "reworking"},
        ]
    )
    assert summary == {
        "total": 3,
        "ready": 1,
        "merged": 1,
        "requeued": 1,
        "terminal": 1,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xmuse_state_normalizer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.platform.state_normalizer'`

- [ ] **Step 3: Write the minimal normalization module**

```python
# src/xmuse_core/platform/state_normalizer.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedLaneState:
    feature_id: str
    raw_status: str
    normalized_status: str
    is_terminal: bool


_STATUS_MAP = {
    "pending": "ready",
    "dispatched": "dispatched",
    "executed": "executed",
    "gated": "under_review",
    "reviewed": "reviewed",
    "awaiting_final_action": "awaiting_final_action",
    "merged": "merged",
    "rejected": "requeued",
    "reworking": "requeued",
    "exec_failed": "exec_failed",
    "gate_failed": "gate_failed",
}

_TERMINAL = {"merged", "terminated", "exec_failed", "gate_failed"}


def normalize_lane_state(lane: dict[str, Any]) -> NormalizedLaneState:
    raw_status = str(lane.get("status") or "pending")
    failure_reason = lane.get("failure_reason")
    if raw_status == "failed":
        normalized = str(failure_reason) if isinstance(failure_reason, str) else "terminated"
    else:
        normalized = _STATUS_MAP.get(raw_status, raw_status)
    return NormalizedLaneState(
        feature_id=str(lane.get("feature_id", "")),
        raw_status=raw_status,
        normalized_status=normalized,
        is_terminal=normalized in _TERMINAL,
    )


def summarize_lane_states(lanes: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"total": len(lanes), "terminal": 0}
    for lane in lanes:
        normalized = normalize_lane_state(lane)
        counts[normalized.normalized_status] = counts.get(normalized.normalized_status, 0) + 1
        if normalized.is_terminal:
            counts["terminal"] += 1
    return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_xmuse_state_normalizer.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_xmuse_state_normalizer.py src/xmuse_core/platform/state_normalizer.py
git commit -m "feat: add xmuse mixed-run state normalizer"
```

---

### Task 2: Add a stable GOD session registry keyed by `god_session_id`

**Files:**
- Create: `src/xmuse_core/agents/god_session_registry.py`
- Test: `tests/test_xmuse_god_session_registry.py`

- [ ] **Step 1: Write the failing registry tests**

```python
# tests/test_xmuse_god_session_registry.py
from pathlib import Path

from xmuse_core.agents.god_session_registry import GodSessionRegistry


def test_create_session_record_uses_stable_identity_not_feature_id(tmp_path: Path) -> None:
    registry = GodSessionRegistry(tmp_path / "active_sessions.json")
    record = registry.create(
        role="execute",
        agent_name="codex-exec",
        runtime="codex",
        session_address="@execute",
        session_inbox_id="inbox-execute",
    )

    assert record.god_session_id.startswith("god-")
    assert record.session_address == "@execute"
    assert record.assignment_feature_id is None


def test_registry_can_lookup_by_address_and_inbox(tmp_path: Path) -> None:
    registry = GodSessionRegistry(tmp_path / "active_sessions.json")
    created = registry.create(
        role="review",
        agent_name="codex-review",
        runtime="codex",
        session_address="@review",
        session_inbox_id="inbox-review",
    )

    assert registry.get(created.god_session_id).session_address == "@review"
    assert registry.find_by_address("@review").god_session_id == created.god_session_id
    assert registry.find_by_inbox("inbox-review").god_session_id == created.god_session_id


def test_registry_updates_assignment_without_changing_identity(tmp_path: Path) -> None:
    registry = GodSessionRegistry(tmp_path / "active_sessions.json")
    created = registry.create(
        role="execute",
        agent_name="codex-exec",
        runtime="codex",
        session_address="@execute",
        session_inbox_id="inbox-execute",
    )

    updated = registry.assign(created.god_session_id, feature_id="lane-42")

    assert updated.god_session_id == created.god_session_id
    assert updated.assignment_feature_id == "lane-42"
    assert registry.get(created.god_session_id).assignment_feature_id == "lane-42"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xmuse_god_session_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.agents.god_session_registry'`

- [ ] **Step 3: Write the minimal registry**

```python
# src/xmuse_core/agents/god_session_registry.py
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class GodSessionRecord:
    god_session_id: str
    role: str
    agent_name: str
    runtime: str
    session_address: str
    session_inbox_id: str
    status: str = "starting"
    assignment_feature_id: str | None = None
    pid: int | None = None


class GodSessionRegistry:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def create(
        self,
        *,
        role: str,
        agent_name: str,
        runtime: str,
        session_address: str,
        session_inbox_id: str,
    ) -> GodSessionRecord:
        record = GodSessionRecord(
            god_session_id=f"god-{uuid.uuid4().hex[:12]}",
            role=role,
            agent_name=agent_name,
            runtime=runtime,
            session_address=session_address,
            session_inbox_id=session_inbox_id,
        )
        data = self._read()
        data["sessions"].append(asdict(record))
        self._write(data)
        return record

    def list(self) -> list[GodSessionRecord]:
        return [GodSessionRecord(**item) for item in self._read()["sessions"]]

    def get(self, god_session_id: str) -> GodSessionRecord:
        for item in self.list():
            if item.god_session_id == god_session_id:
                return item
        raise KeyError(god_session_id)

    def find_by_address(self, session_address: str) -> GodSessionRecord:
        for item in self.list():
            if item.session_address == session_address:
                return item
        raise KeyError(session_address)

    def find_by_inbox(self, session_inbox_id: str) -> GodSessionRecord:
        for item in self.list():
            if item.session_inbox_id == session_inbox_id:
                return item
        raise KeyError(session_inbox_id)

    def assign(self, god_session_id: str, *, feature_id: str | None) -> GodSessionRecord:
        data = self._read()
        for item in data["sessions"]:
            if item["god_session_id"] == god_session_id:
                item["assignment_feature_id"] = feature_id
                self._write(data)
                return GodSessionRecord(**item)
        raise KeyError(god_session_id)

    def _read(self) -> dict[str, list[dict[str, object]]]:
        if not self._path.exists():
            return {"sessions": []}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, payload: dict[str, list[dict[str, object]]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_xmuse_god_session_registry.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_xmuse_god_session_registry.py src/xmuse_core/agents/god_session_registry.py
git commit -m "feat: add stable xmuse god session registry"
```

---

### Task 3: Implement the persistent GOD session layer

**Files:**
- Create: `src/xmuse_core/agents/god_session_layer.py`
- Modify: `src/xmuse_core/agents/registry.py`
- Test: `tests/test_xmuse_god_session_layer.py`

- [ ] **Step 1: Write the failing session-layer tests**

```python
# tests/test_xmuse_god_session_layer.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from xmuse_core.agents.god_session_layer import GodSessionLayer
from xmuse_core.agents.registry import AgentDescriptor, AgentRuntime, SessionConfig


class FakeLauncher:
    def build_command(self, feature_id, worktree):
        return ["fake-cli"]

    def build_env(self, feature_id):
        return {"XMUSE_FEATURE_ID": feature_id}

    def format_prompt(self, prompt, context):
        return prompt if not context else f"{context}\n\n{prompt}"


def _agent(name: str) -> AgentDescriptor:
    return AgentDescriptor(
        runtime=AgentRuntime.CODEX,
        name=name,
        capabilities=["chat"],
        session_config=SessionConfig(),
    )


@pytest.mark.asyncio
async def test_ensure_session_reuses_same_god_session_id(tmp_path: Path, monkeypatch) -> None:
    fake_local = AsyncMock()
    fake_local.pid = 321
    fake_local.is_alive.return_value = True
    fake_local.receive.return_value = None
    spawn = AsyncMock(return_value=fake_local)
    monkeypatch.setattr("xmuse_core.agents.god_session_layer.LocalSession.spawn", spawn)

    layer = GodSessionLayer(
        registry_path=tmp_path / "active_sessions.json",
        launchers={AgentRuntime.CODEX: FakeLauncher()},
    )

    first = await layer.ensure_session(role="execute", agent=_agent("exec-god"), worktree=tmp_path)
    second = await layer.ensure_session(role="execute", agent=_agent("exec-god"), worktree=tmp_path)

    assert first.god_session_id == second.god_session_id
    assert spawn.await_count == 1


@pytest.mark.asyncio
async def test_dispatch_message_targets_session_by_god_session_id_not_feature_id(tmp_path: Path, monkeypatch) -> None:
    fake_local = AsyncMock()
    fake_local.pid = 321
    fake_local.is_alive.return_value = True
    fake_local.receive.return_value = None
    spawn = AsyncMock(return_value=fake_local)
    monkeypatch.setattr("xmuse_core.agents.god_session_layer.LocalSession.spawn", spawn)

    layer = GodSessionLayer(
        registry_path=tmp_path / "active_sessions.json",
        launchers={AgentRuntime.CODEX: FakeLauncher()},
    )
    record = await layer.ensure_session(role="review", agent=_agent("review-god"), worktree=tmp_path)

    await layer.send_message(record.god_session_id, message_type="task", prompt="review lane-1", context="")

    sent = fake_local.send_typed.await_args_list[-1]
    assert sent.args[0] == "task"
    assert sent.kwargs["god_session_id"] == record.god_session_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xmuse_god_session_layer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.agents.god_session_layer'`

- [ ] **Step 3: Write the minimal persistent session layer**

```python
# src/xmuse_core/agents/god_session_layer.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xmuse_core.agents.god_session_registry import GodSessionRecord, GodSessionRegistry
from xmuse_core.agents.registry import AgentDescriptor, AgentRuntime
from xmuse_core.agents.session import LocalSession


@dataclass
class LiveGodSession:
    record: GodSessionRecord
    session: LocalSession


class GodSessionLayer:
    def __init__(self, *, registry_path: Path, launchers: dict[AgentRuntime, object]) -> None:
        self._registry = GodSessionRegistry(registry_path)
        self._launchers = launchers
        self._live: dict[str, LiveGodSession] = {}

    async def ensure_session(
        self,
        *,
        role: str,
        agent: AgentDescriptor,
        worktree: Path,
    ) -> GodSessionRecord:
        existing = self._find_live_role(role)
        if existing is not None and existing.session.is_alive():
            return existing.record

        launcher = self._launchers[agent.runtime]
        command = launcher.build_command(f"{role}-god", worktree)
        session = await LocalSession.spawn(command, env=launcher.build_env(f"{role}-god"))
        record = self._registry.create(
            role=role,
            agent_name=agent.name,
            runtime=agent.runtime.value,
            session_address=f"@{role}",
            session_inbox_id=f"inbox-{role}",
        )
        self._live[record.god_session_id] = LiveGodSession(record=record, session=session)
        return record

    async def send_message(
        self,
        god_session_id: str,
        *,
        message_type: str,
        prompt: str,
        context: str,
    ) -> None:
        live = self._live[god_session_id]
        await live.session.send_typed(
            message_type,
            god_session_id=god_session_id,
            prompt=prompt,
            context=context,
        )

    def _find_live_role(self, role: str) -> LiveGodSession | None:
        for live in self._live.values():
            if live.record.role == role:
                return live
        return None
```

```python
# src/xmuse_core/agents/registry.py
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SessionConfig:
    transport: Literal["local", "remote"] = "local"
    heartbeat_interval_s: int = 30
    heartbeat_timeout_s: int = 300
    max_context_tokens: int | None = None
    persistent_role: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_xmuse_god_session_layer.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_xmuse_god_session_layer.py src/xmuse_core/agents/god_session_layer.py src/xmuse_core/agents/registry.py
git commit -m "feat: add persistent xmuse god session layer"
```

---

### Task 4: Add a router for `session_address` and `session_inbox_id`

**Files:**
- Create: `src/xmuse_core/routing/session_router.py`
- Test: `tests/test_xmuse_session_router.py`

- [ ] **Step 1: Write the failing router tests**

```python
# tests/test_xmuse_session_router.py
from pathlib import Path

from xmuse_core.agents.god_session_registry import GodSessionRegistry
from xmuse_core.routing.session_router import SessionRouter


def test_route_to_address_enqueues_message_in_target_inbox(tmp_path: Path) -> None:
    registry = GodSessionRegistry(tmp_path / "active_sessions.json")
    review = registry.create(
        role="review",
        agent_name="codex-review",
        runtime="codex",
        session_address="@review",
        session_inbox_id="inbox-review",
    )

    router = SessionRouter(
        registry=registry,
        inbox_root=tmp_path / "session_inboxes",
    )
    delivered = router.route(
        target_address="@review",
        sender_address="@human",
        message_type="task",
        payload={"text": "review lane-1"},
    )

    assert delivered.god_session_id == review.god_session_id
    inbox = router.read_inbox("inbox-review")
    assert inbox[0]["sender_address"] == "@human"
    assert inbox[0]["payload"]["text"] == "review lane-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xmuse_session_router.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'xmuse_core.routing.session_router'`

- [ ] **Step 3: Write the minimal router**

```python
# src/xmuse_core/routing/session_router.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xmuse_core.agents.god_session_registry import GodSessionRecord, GodSessionRegistry


class SessionRouter:
    def __init__(self, *, registry: GodSessionRegistry, inbox_root: Path | str) -> None:
        self._registry = registry
        self._root = Path(inbox_root)

    def route(
        self,
        *,
        target_address: str,
        sender_address: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> GodSessionRecord:
        record = self._registry.find_by_address(target_address)
        inbox_path = self._root / f"{record.session_inbox_id}.json"
        messages = self.read_inbox(record.session_inbox_id)
        messages.append(
            {
                "sender_address": sender_address,
                "message_type": message_type,
                "payload": payload,
            }
        )
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        inbox_path.write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
        return record

    def read_inbox(self, inbox_id: str) -> list[dict[str, Any]]:
        path = self._root / f"{inbox_id}.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_xmuse_session_router.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_xmuse_session_router.py src/xmuse_core/routing/session_router.py
git commit -m "feat: add xmuse session-address router"
```

---

### Task 5: Integrate normalized states and persistent sessions into dashboard reads

**Files:**
- Modify: `xmuse/dashboard_api.py`
- Modify: `tests/test_xmuse_dashboard_api.py`
- Test: `tests/test_xmuse_dashboard_api.py`

- [ ] **Step 1: Write the failing dashboard tests**

```python
# tests/test_xmuse_dashboard_api.py
def test_sessions_support_god_session_registry_shape(tmp_path):
    _write_json(
        tmp_path / "active_sessions.json",
        {
            "sessions": [
                {
                    "god_session_id": "god-1",
                    "role": "review",
                    "session_address": "@review",
                    "session_inbox_id": "inbox-review",
                    "status": "running",
                    "pid": 123,
                }
            ]
        },
    )

    response = _client(tmp_path).get("/api/sessions")

    assert response.status_code == 200
    assert response.json()["sessions"][0]["god_session_id"] == "god-1"
    assert response.json()["sessions"][0]["session_address"] == "@review"


def test_metrics_use_normalized_lane_states(tmp_path):
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {"feature_id": "lane-ready", "status": "pending", "prompt": "x"},
                {"feature_id": "lane-requeued", "status": "reworking", "prompt": "x"},
                {"feature_id": "lane-merged", "status": "merged", "prompt": "x"},
            ]
        },
    )

    response = _client(tmp_path).get("/api/metrics")

    assert response.status_code == 200
    assert response.json()["ready"] == 1
    assert response.json()["requeued"] == 1
    assert response.json()["done"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xmuse_dashboard_api.py::test_sessions_support_god_session_registry_shape tests/test_xmuse_dashboard_api.py::test_metrics_use_normalized_lane_states -q`
Expected: FAIL because `/api/sessions` drops `god_session_id` shape and `/api/metrics` does not expose normalized counts

- [ ] **Step 3: Update dashboard reads to use the shared module**

```python
# xmuse/dashboard_api.py
from xmuse_core.platform.state_normalizer import normalize_lane_state, summarize_lane_states


def _read_sessions(base_dir: Path) -> list[Any]:
    data = _read_json(_json_path(base_dir, "active_sessions.json"), {"sessions": []})
    if isinstance(data, dict):
        sessions = data.get("sessions", [])
        if isinstance(sessions, list):
            return sessions
    return []


def _lane_with_status(lane: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(lane)
    state = normalize_lane_state(lane)
    normalized["status"] = state.raw_status
    normalized["effective_status"] = state.normalized_status
    return normalized


@app.get("/api/metrics")
def metrics() -> dict[str, int | float | None]:
    data = _load_lanes(root)
    lanes = [lane for lane in data["lanes"] if isinstance(lane, dict)]
    summary = summarize_lane_states(lanes)
    durations = [
        duration
        for lane in lanes
        if (duration := _duration_seconds(lane)) is not None
    ]
    avg_time = round(sum(durations) / len(durations), 2) if durations else None
    return {
        "total": summary["total"],
        "done": summary.get("merged", 0),
        "ready": summary.get("ready", 0),
        "requeued": summary.get("requeued", 0),
        "failed": summary.get("terminated", 0) + summary.get("gate_failed", 0) + summary.get("exec_failed", 0),
        "avg_time_seconds": avg_time,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_xmuse_dashboard_api.py::test_sessions_support_god_session_registry_shape tests/test_xmuse_dashboard_api.py::test_metrics_use_normalized_lane_states -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add xmuse/dashboard_api.py tests/test_xmuse_dashboard_api.py
git commit -m "feat: normalize xmuse dashboard session and lane state reads"
```

---

### Task 6: Run the focused Phase 1 regression suite

**Files:**
- Test: `tests/test_xmuse_state_normalizer.py`
- Test: `tests/test_xmuse_god_session_registry.py`
- Test: `tests/test_xmuse_god_session_layer.py`
- Test: `tests/test_xmuse_session_router.py`
- Test: `tests/test_xmuse_dashboard_api.py`
- Test: `tests/test_xmuse_core_agents_manager.py`

- [ ] **Step 1: Run the focused suite**

Run:

```bash
uv run pytest \
  tests/test_xmuse_state_normalizer.py \
  tests/test_xmuse_god_session_registry.py \
  tests/test_xmuse_god_session_layer.py \
  tests/test_xmuse_session_router.py \
  tests/test_xmuse_dashboard_api.py \
  tests/test_xmuse_core_agents_manager.py -q
```

Expected: PASS

- [ ] **Step 2: Run a broader xmuse backend regression**

Run:

```bash
uv run pytest \
  tests/test_xmuse_chat_api.py \
  tests/test_xmuse_mvp_e2e_chat_to_lane.py \
  tests/test_xmuse_platform_orchestrator.py \
  tests/test_xmuse_platform_runner.py \
  tests/test_xmuse_mcp_server.py -q
```

Expected: PASS

- [ ] **Step 3: Commit the verification snapshot**

```bash
git add .
git commit -m "test: verify xmuse phase 1 god session migration slice"
```

---

## Self-Review

- Spec coverage:
  - persistent `god_session_id` / address / inbox: Tasks 2-4
  - mixed-run normalization module: Tasks 1 and 5
  - dashboard compatibility with new sessions and normalized statuses: Task 5
  - worker one-shot flow left intact: Task 3 scope and Task 6 regressions
- Placeholder scan:
  - no `TODO`, `TBD`, or “similar to above” placeholders remain
- Type consistency:
  - `god_session_id`, `session_address`, `session_inbox_id`, and `effective_status` are named consistently across tasks
