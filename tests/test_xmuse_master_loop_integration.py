from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "xmuse"))


def _write_lanes(path: Path, lanes: list[dict]) -> None:
    path.write_text(json.dumps({"lanes": lanes}))


def _read_lanes(path: Path) -> list[dict]:
    return json.loads(path.read_text())["lanes"]


def test_master_loop_cli_accepts_legacy_xmuse_main_args() -> None:
    from master_loop import parse_args

    args = parse_args(
        [
            "--lanes",
            "custom_lanes.json",
            "--config",
            "custom_agents.json",
            "--memoryos-url",
            "http://memoryos.test",
            "--concurrency",
            "3",
            "--max-hours",
            "2.5",
        ]
    )

    assert args.lanes == "custom_lanes.json"
    assert args.config == "custom_agents.json"
    assert args.memoryos_url == "http://memoryos.test"
    assert args.concurrency == 3
    assert args.max_hours == 2.5


def test_from_defaults_wires_memoryos_and_on_complete(tmp_path, monkeypatch) -> None:
    import master_loop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [{"feature_id": "lane-1", "prompt": "do it", "worktree": str(tmp_path)}],
    )
    captured: dict[str, object] = {}

    class FakeRegistry:
        @classmethod
        def from_file(cls, path: Path) -> FakeRegistry:
            captured["agents_path"] = path
            return cls()

    class FakeSessionManager:
        def __init__(self, *, launchers, state_file, memoryos_client=None) -> None:
            captured["launchers"] = launchers
            captured["state_file"] = state_file
            captured["memoryos_client"] = memoryos_client

    class FakeConsumer:
        def __init__(self, *, registry, session_mgr, max_concurrent, on_complete=None) -> None:
            captured["registry"] = registry
            captured["session_mgr"] = session_mgr
            captured["max_concurrent"] = max_concurrent
            captured["on_complete"] = on_complete

        def shutdown(self) -> None:
            pass

    monkeypatch.setattr(master_loop, "AgentRegistry", FakeRegistry)
    monkeypatch.setattr(master_loop, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(master_loop, "WorklistConsumer", FakeConsumer)
    monkeypatch.setattr(master_loop, "CodexLauncher", lambda: object())

    loop = master_loop.MasterLoop.from_defaults(
        lanes_path=lanes_path,
        agents_path=Path("custom_agents.json"),
        memoryos_url="http://memoryos.test",
        max_concurrent=4,
    )

    assert loop.consumer is captured["session_mgr"] or loop.consumer is not None
    assert captured["agents_path"] == Path("custom_agents.json")
    assert captured["max_concurrent"] == 4
    memoryos_client = captured["memoryos_client"]
    assert memoryos_client._base_url == "http://memoryos.test"

    on_complete = captured["on_complete"]
    assert callable(on_complete)
    on_complete("lane-1", "done")
    assert _read_lanes(lanes_path)[0]["status"] == "done"


@pytest.mark.asyncio
async def test_error_knowledge_injects_context_before_dispatch(tmp_path, monkeypatch) -> None:
    from master_loop import MasterLoop

    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"[]", b""

    class FakeConsumer:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        async def dispatch_task(self, task) -> str:
            self.prompts.append(task.prompt)
            return "done"

        def shutdown(self) -> None:
            pass

    class FakeGate:
        async def check(self, worktree: Path):
            return argparse.Namespace(passed=True, errors=[])

    class FakeReworkLoop:
        async def run(self, lane, initial_gate_result, dispatch_fn, gate):
            return argparse.Namespace(status="done")

    class FakeKnowledge:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def inject_context(self, prompt: str) -> str:
            self.prompts.append(prompt)
            return f"LESSON CONTEXT\n\n{prompt}"

    async def fake_exec(*args, **kwargs):
        return FakeProcess()

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [{"feature_id": "lane-1", "prompt": "original prompt", "worktree": str(tmp_path)}],
    )
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    consumer = FakeConsumer()
    knowledge = FakeKnowledge()
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=consumer,
        quality_gate=FakeGate(),
        rework_loop=FakeReworkLoop(),
        error_knowledge=knowledge,
        max_hours=1,
        max_concurrent=1,
    )

    summary = await loop.run()

    assert summary.successful_lanes == 1
    assert knowledge.prompts == ["original prompt"]
    assert consumer.prompts[0].startswith("LESSON CONTEXT\n\noriginal prompt")
    assert "SCOPE CONSTRAINT" in consumer.prompts[0]


@pytest.mark.asyncio
async def test_xmuse_main_delegates_to_master_loop(monkeypatch) -> None:
    import master_loop
    import xmuse_main

    called: dict[str, object] = {}
    args = argparse.Namespace(lanes="lanes.json")

    async def fake_main(received_args):
        called["args"] = received_args
        return "summary"

    monkeypatch.setattr(master_loop, "main", fake_main)

    result = await xmuse_main.main(args)

    assert result == "summary"
    assert called["args"] is args
