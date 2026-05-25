from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from xmuse_core.agents.consumer import TaskDescriptor, WorklistConsumer
from xmuse_core.agents.registry import AgentDescriptor, AgentRegistry, AgentRuntime, SessionConfig


def _make_registry():
    return AgentRegistry([
        AgentDescriptor(AgentRuntime.CODEX, "w1", ["code", "test"], SessionConfig()),
        AgentDescriptor(AgentRuntime.CLAUDE_CODE, "r1", ["code", "review"], SessionConfig()),
    ])


@pytest.mark.asyncio
async def test_enqueue_increases_pending():
    reg = _make_registry()
    mgr = AsyncMock()
    consumer = WorklistConsumer(reg, mgr)
    task = TaskDescriptor(feature_id="f1", task_type="execute", prompt="do it")
    await consumer.enqueue(task)
    assert consumer.pending_count == 1


@pytest.mark.asyncio
async def test_run_dispatches_task():
    reg = _make_registry()
    mgr = AsyncMock()
    consumer = WorklistConsumer(reg, mgr, max_concurrent=4)

    task = TaskDescriptor(feature_id="f1", task_type="execute", prompt="do it", required_capabilities=["code"])
    await consumer.enqueue(task)

    # Run consumer for a short time
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


@pytest.mark.asyncio
async def test_fifo_order():
    reg = _make_registry()
    dispatch_order = []

    async def mock_dispatch(*, agent, feature_id, prompt, worktree):
        dispatch_order.append(feature_id)

    mgr = AsyncMock()
    mgr.dispatch_one_shot = mock_dispatch
    consumer = WorklistConsumer(reg, mgr, max_concurrent=4)

    for i in range(3):
        await consumer.enqueue(TaskDescriptor(feature_id=f"f{i}", task_type="execute", prompt="x"))

    run_task = asyncio.create_task(consumer.run())
    await asyncio.sleep(0.2)
    consumer.shutdown()
    await asyncio.sleep(0.1)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    assert dispatch_order == ["f0", "f1", "f2"]


@pytest.mark.asyncio
async def test_exclude_runtime_for_review():
    reg = _make_registry()
    selected_agents = []

    async def mock_dispatch(*, agent, feature_id, prompt, worktree):
        selected_agents.append(agent)

    mgr = AsyncMock()
    mgr.dispatch_one_shot = mock_dispatch
    consumer = WorklistConsumer(reg, mgr)

    task = TaskDescriptor(
        feature_id="f1", task_type="review", prompt="review this",
        required_capabilities=["review"],
        developed_by_runtime=AgentRuntime.CODEX,
    )
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

    assert len(selected_agents) == 1
    assert selected_agents[0].runtime == AgentRuntime.CLAUDE_CODE


@pytest.mark.asyncio
async def test_shutdown_stops_consumer():
    reg = _make_registry()
    mgr = AsyncMock()
    consumer = WorklistConsumer(reg, mgr)

    run_task = asyncio.create_task(consumer.run())
    consumer.shutdown()
    await asyncio.sleep(1.5)
    assert run_task.done() or run_task.cancelled()
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass
