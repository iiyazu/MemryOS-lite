from __future__ import annotations

import asyncio
import sys

import pytest
import pytest_asyncio

from xmuse_core.agents.session import LocalSession

MOCK_AGENT_SCRIPT = """\
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        continue
    if d.get("type") == "ping":
        print(json.dumps({"type": "pong"}), flush=True)
    elif d.get("type") == "task":
        print(json.dumps({"type": "result", "status": "success", "artifacts": {}}), flush=True)
    elif d.get("type") == "abort":
        break
"""

HANGING_AGENT_SCRIPT = """\
import time
time.sleep(60)
"""

BAD_OUTPUT_AGENT_SCRIPT = """\
import sys
for i in range(55):
    print(f"garbage line {i}", flush=True)
sys.exit(0)
"""


@pytest_asyncio.fixture
async def mock_session():
    session = await LocalSession.spawn([sys.executable, "-c", MOCK_AGENT_SCRIPT])
    yield session
    if session.is_alive():
        await session.abort(grace_period=2.0)


@pytest.mark.asyncio
async def test_send_and_receive_pong(mock_session):
    await mock_session.send_typed("ping")
    msg = await mock_session.receive()
    assert msg is not None
    assert msg.type == "pong"


@pytest.mark.asyncio
async def test_send_task_receive_result(mock_session):
    await mock_session.send_typed("task", feature_id="test", prompt="hello")
    msg = await mock_session.receive()
    assert msg is not None
    assert msg.type == "result"
    assert msg.status == "success"


@pytest.mark.asyncio
async def test_abort_terminates_process(mock_session):
    assert mock_session.is_alive()
    await mock_session.abort(grace_period=2.0)
    assert not mock_session.is_alive()


@pytest.mark.asyncio
async def test_is_alive_false_after_exit():
    session = await LocalSession.spawn([sys.executable, "-c", "pass"])
    await asyncio.sleep(0.2)
    assert not session.is_alive()


@pytest.mark.asyncio
async def test_abort_hanging_process():
    session = await LocalSession.spawn([sys.executable, "-c", HANGING_AGENT_SCRIPT])
    assert session.is_alive()
    await session.abort(grace_period=1.0)
    assert not session.is_alive()


@pytest.mark.asyncio
async def test_health_warning_on_bad_output():
    session = await LocalSession.spawn([sys.executable, "-c", BAD_OUTPUT_AGENT_SCRIPT])
    assert not session.health_warning
    for _ in range(55):
        msg = await session.receive()
        if msg is None and not session.is_alive():
            break
    assert session.health_warning
