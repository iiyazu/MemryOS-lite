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
    max_concurrent: int,
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
            pass

    deadline = loop.time() + max_hours * 3600
    semaphore = asyncio.Semaphore(max_concurrent)
    in_flight: set[asyncio.Task] = set()
    logger.info("Platform started, max_hours=%.1f, concurrency=%d", max_hours, max_concurrent)

    while not shutdown.is_set() and loop.time() < deadline:
        pending = orch._sm.get_lanes(status="pending")
        if not pending:
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=10.0)
            except TimeoutError:
                pass
            continue

        pending.sort(key=lambda l: -l.get("priority", 0))

        for lane in pending:
            if len(in_flight) >= max_concurrent:
                done, in_flight = await asyncio.wait(
                    in_flight, return_when=asyncio.FIRST_COMPLETED
                )
                in_flight = set(in_flight)
            lane_id = lane["feature_id"]
            logger.info("Dispatching lane: %s (priority=%d)", lane_id, lane.get("priority", 0))

            async def _run(lid: str) -> None:
                async with semaphore:
                    await orch.dispatch_lane(lid)

            task = asyncio.create_task(_run(lane_id))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)

        await asyncio.sleep(5.0)

    if in_flight:
        await asyncio.gather(*in_flight, return_exceptions=True)
    logger.info("Platform shutting down")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="xmuse Platform Runner (MVP)")
    parser.add_argument("--lanes", type=Path, default=ROOT / "xmuse" / "feature_lanes.json")
    parser.add_argument("--mcp-port", type=int, default=9800)
    parser.add_argument("--max-hours", type=float, default=8.0)
    parser.add_argument("--max-concurrent", type=int, default=4)
    args = parser.parse_args()

    asyncio.run(run(
        lanes_path=args.lanes,
        xmuse_root=ROOT / "xmuse",
        mcp_port=args.mcp_port,
        max_hours=args.max_hours,
        max_concurrent=args.max_concurrent,
    ))


if __name__ == "__main__":
    main()
