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
from xmuse_core.agents.launchers.codex import CodexLauncher
from xmuse_core.agents.manager import SessionManager
from xmuse_core.agents.memoryos_client import MemoryOSClient
from xmuse_core.agents.registry import AgentRegistry, AgentRuntime

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

    memoryos = MemoryOSClient(base_url=args.memoryos_url)
    mgr = SessionManager(launchers=launchers, state_file=state_file)
    consumer = WorklistConsumer(registry=registry, session_mgr=mgr, max_concurrent=args.concurrency)

    lanes = load_lanes(Path(args.lanes))
    logger.info("Loaded %d pending lanes from %s", len(lanes), args.lanes)
    for task in lanes:
        await consumer.enqueue(task)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(_shutdown(consumer, mgr, memoryos))
        )

    logger.info("xmuse master loop started (concurrency=%d)", args.concurrency)
    await consumer.run()


async def _shutdown(
    consumer: WorklistConsumer, mgr: SessionManager, memoryos: MemoryOSClient
) -> None:
    logger.info("Shutdown signal received")
    consumer.shutdown()
    await mgr.graceful_shutdown()
    await memoryos.close()


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xmuse MVP master loop")
    parser.add_argument("--config", default="xmuse/agents.json", help="Agent registry config")
    parser.add_argument("--lanes", default="xmuse/feature_lanes.json", help="Feature lanes file")
    parser.add_argument("--memoryos-url", default="http://127.0.0.1:8000", help="MemoryOS API URL")
    parser.add_argument("--concurrency", type=int, default=2, help="Max concurrent agents")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(cli()))
