from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from xmuse_core.agents.consumer import TaskDescriptor, WorklistConsumer
from xmuse_core.agents.protocol import AgentOutput
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

    task = TaskDescriptor(
        feature_id="f1",
        task_type="execute",
        prompt="do it",
        required_capabilities=["code"],
    )
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
async def test_run_dispatches_two_lanes_concurrently_when_allowed():
    reg = _make_registry()
    started: set[str] = set()
    release = asyncio.Event()
    both_started = asyncio.Event()

    async def mock_dispatch(*, agent, feature_id, prompt, worktree):
        started.add(feature_id)
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return AgentOutput(status="success")

    mgr = AsyncMock()
    mgr.dispatch_one_shot = mock_dispatch
    completions = []
    consumer = WorklistConsumer(
        reg,
        mgr,
        max_concurrent=2,
        on_complete=lambda fid, status: completions.append((fid, status)),
    )

    await consumer.enqueue(TaskDescriptor(feature_id="f0", task_type="execute", prompt="x"))
    await consumer.enqueue(TaskDescriptor(feature_id="f1", task_type="execute", prompt="x"))

    run_task = asyncio.create_task(consumer.run())
    await asyncio.wait_for(both_started.wait(), timeout=0.5)
    release.set()
    await asyncio.wait_for(run_task, timeout=2.0)

    assert started == {"f0", "f1"}
    assert sorted(completions) == [("f0", "done"), ("f1", "done")]


@pytest.mark.asyncio
async def test_run_limits_concurrency_with_semaphore():
    reg = _make_registry()
    active = 0
    max_active = 0
    started: list[str] = []
    release = asyncio.Event()
    two_started = asyncio.Event()

    async def mock_dispatch(*, agent, feature_id, prompt, worktree):
        nonlocal active, max_active
        started.append(feature_id)
        active += 1
        max_active = max(max_active, active)
        if len(started) == 2:
            two_started.set()
        await release.wait()
        active -= 1
        return AgentOutput(status="success")

    mgr = AsyncMock()
    mgr.dispatch_one_shot = mock_dispatch
    consumer = WorklistConsumer(reg, mgr, max_concurrent=2)

    for i in range(3):
        await consumer.enqueue(TaskDescriptor(feature_id=f"f{i}", task_type="execute", prompt="x"))

    run_task = asyncio.create_task(consumer.run())
    await asyncio.wait_for(two_started.wait(), timeout=0.5)
    await asyncio.sleep(0.05)

    assert started == ["f0", "f1"]
    assert max_active == 2

    release.set()
    await asyncio.wait_for(run_task, timeout=2.0)

    assert started == ["f0", "f1", "f2"]
    assert max_active == 2


@pytest.mark.asyncio
async def test_failed_task_does_not_kill_other_dispatches():
    reg = _make_registry()
    release_success = asyncio.Event()
    good_started = asyncio.Event()
    completions = []

    async def mock_dispatch(*, agent, feature_id, prompt, worktree):
        if feature_id == "bad":
            raise RuntimeError("boom")
        good_started.set()
        await release_success.wait()
        return AgentOutput(status="success")

    mgr = AsyncMock()
    mgr.dispatch_one_shot = mock_dispatch
    consumer = WorklistConsumer(
        reg,
        mgr,
        max_concurrent=2,
        on_complete=lambda fid, status: completions.append((fid, status)),
    )

    await consumer.enqueue(TaskDescriptor(feature_id="bad", task_type="execute", prompt="x"))
    await consumer.enqueue(TaskDescriptor(feature_id="good", task_type="execute", prompt="x"))

    run_task = asyncio.create_task(consumer.run())
    await asyncio.wait_for(good_started.wait(), timeout=0.5)
    release_success.set()
    await asyncio.wait_for(run_task, timeout=2.0)

    assert sorted(completions) == [("bad", "failed"), ("good", "done")]


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
