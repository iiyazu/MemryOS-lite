"""E2E smoke test: full dispatch cycle with a mock codex script."""
import asyncio
import sys
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
            return f"{context}\n---\n{task}"
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

    run_task = asyncio.create_task(consumer.run())
    await asyncio.sleep(1.0)
    consumer.shutdown()
    await asyncio.sleep(0.5)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    assert len(mgr.active_sessions) == 0
