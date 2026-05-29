#!/usr/bin/env python3
"""xmuse Platform Runner — MVP entrypoint."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

from xmuse_core.chat.driver import ChatDriver
from xmuse_core.platform.orchestrator import PlatformOrchestrator
from xmuse_core.self_evolution import SelfEvolutionController
from xmuse_core.self_evolution.watcher import TerminalRunWatcher

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BLUEPRINT = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-05-28-xmuse-initial-self-evolution-blueprint.md"
)
logger = logging.getLogger(__name__)


async def run(
    lanes_path: Path,
    xmuse_root: Path,
    mcp_port: int,
    max_hours: float,
    max_concurrent: int,
    graph_id: str | None = None,
    resolution_id: str | None = None,
    require_final_action_approval: bool = False,
    god_runtime: str | None = None,
    auto_evolve: bool = False,
    blueprint_path: Path | None = None,
    decomposer_kind: str = "single",
    chat_driver_enabled: bool = False,
    chat_driver_model: str = "haiku",
) -> None:
    orch = PlatformOrchestrator(
        lanes_path=lanes_path,
        xmuse_root=xmuse_root,
        mcp_port=mcp_port,
        require_final_action_approval=require_final_action_approval,
        god_runtime=god_runtime,
    )

    watcher: TerminalRunWatcher | None = None
    if auto_evolve:
        decomposer = _build_decomposer(decomposer_kind)
        controller = SelfEvolutionController(
            xmuse_root=xmuse_root,
            blueprint_path=blueprint_path or DEFAULT_BLUEPRINT,
            decomposer=decomposer,
        )
        watcher = TerminalRunWatcher(controller)
        logger.info(
            "Auto-evolve enabled (blueprint=%s, decomposer=%s)",
            controller._blueprint_path,
            decomposer_kind,
        )

    chat_driver: ChatDriver | None = None
    if chat_driver_enabled:
        chat_driver = ChatDriver(
            chat_db_path=xmuse_root / "chat.db",
            model=chat_driver_model,
        )
        logger.info("Chat driver enabled (model=%s)", chat_driver_model)

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
        await orch.reconcile_status_changes()
        if watcher is not None and not in_flight:
            _drive_auto_evolve(watcher)
        if chat_driver is not None:
            _drive_chat(chat_driver)
        pending = _candidate_lanes(
            orch,
            graph_id=graph_id,
            resolution_id=resolution_id,
        )
        if not pending:
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=10.0)
            except TimeoutError:
                pass
            continue

        pending.sort(key=lambda lane: -lane.get("priority", 0))

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


def _drive_auto_evolve(watcher: TerminalRunWatcher) -> None:
    try:
        outcomes = watcher.tick()
    except Exception:
        logger.exception("auto-evolve tick failed; continuing")
        return
    for outcome in outcomes:
        if outcome.spawned is not None:
            logger.info(
                "auto-evolve: spawned %s from %s",
                outcome.spawned.spawned_graph_id,
                outcome.source_run_id,
            )
        elif outcome.skip_reason:
            logger.debug(
                "auto-evolve: skipped %s (%s)",
                outcome.source_run_id,
                outcome.skip_reason,
            )


def _drive_chat(driver: ChatDriver) -> None:
    try:
        outcomes = driver.tick()
    except Exception:
        logger.exception("chat-driver tick failed; continuing")
        return
    for outcome in outcomes:
        if outcome.reply_message_id:
            logger.info(
                "chat-driver: %s replied in %s (envelope=%s)",
                outcome.god_role,
                outcome.conversation_id,
                outcome.envelope_type,
            )
        elif outcome.skip_reason:
            logger.warning(
                "chat-driver: %s skipped %s (%s)",
                outcome.god_role,
                outcome.source_message_id,
                outcome.skip_reason,
            )


def _build_decomposer(kind: str):
    """Pick the decomposer backend.

    ``single`` (default) is the backward-compatible one-rich-lane behavior.
    ``deterministic-multi`` produces a 3-lane design/impl/tests chain per
    track. ``peer-chat`` shells out to claude -p once per chain step and
    parses a multi-feature JSON plan; falls back to ``single`` on failure.
    Returning ``None`` lets the controller construct its built-in default.
    """
    if kind == "single":
        return None  # controller wires SingleLaneDecomposer with its own factories
    if kind == "deterministic-multi":
        from xmuse_core.self_evolution.decomposer import DeterministicMultiLaneDecomposer

        return DeterministicMultiLaneDecomposer()
    if kind == "peer-chat":
        from xmuse_core.self_evolution.decomposer import SingleLaneDecomposer
        from xmuse_core.self_evolution.peer_chat_decomposer import PeerChatDecomposer

        # Closures referencing the controller's per-track factories happen
        # *after* controller construction; here we use track-only fallback
        # factories so PeerChatDecomposer can degrade without controller refs.
        fallback = SingleLaneDecomposer(
            lane_id_factory=lambda evidence, track: (
                f"self-evolution-{track}-{evidence.source_run_id}"[:120]
            ),
            prompt_factory=lambda evidence, track: (
                f"Implement the next xmuse self-evolution improvement for "
                f"track {track}. Use evidence bundle {evidence.bundle_id}. "
                f"Preserve chat -> proposal -> approved resolution -> lane "
                f"graph -> execution as the mainline."
            ),
        )
        return PeerChatDecomposer(fallback=fallback)
    raise ValueError(f"unknown decomposer kind: {kind!r}")


def _candidate_lanes(
    orch: PlatformOrchestrator,
    *,
    graph_id: str | None,
    resolution_id: str | None,
) -> list[dict]:
    lanes_by_id: dict[str, dict] = {}
    for status in ("pending", "reworking"):
        for lane in orch._sm.get_lanes(status=status):
            lane_id = lane.get("feature_id")
            if isinstance(lane_id, str):
                lanes_by_id[lane_id] = lane

    lanes = list(lanes_by_id.values())
    if graph_id is not None:
        lanes = [lane for lane in lanes if lane.get("graph_id") == graph_id]
    if resolution_id is not None:
        lanes = [lane for lane in lanes if lane.get("resolution_id") == resolution_id]
    return lanes


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="xmuse Platform Runner (MVP)")
    parser.add_argument("--lanes", type=Path, default=ROOT / "xmuse" / "feature_lanes.json")
    parser.add_argument("--mcp-port", type=int, default=8100)
    parser.add_argument("--max-hours", type=float, default=8.0)
    parser.add_argument("--max-concurrent", type=int, default=4)
    parser.add_argument("--graph-id")
    parser.add_argument("--resolution-id")
    parser.add_argument(
        "--require-final-action-approval",
        action="store_true",
        help="hold merge/terminate verdicts for external final-action approval",
    )
    parser.add_argument(
        "--god-runtime",
        choices=("codex", "claude", "mixed"),
        default=None,
        help="GOD CLI runtime (defaults to env XMUSE_GOD_RUNTIME or codex)",
    )
    parser.add_argument(
        "--auto-evolve",
        action="store_true",
        help="auto-spawn next self-evolution run when a graph terminalizes",
    )
    parser.add_argument(
        "--blueprint",
        type=Path,
        default=DEFAULT_BLUEPRINT,
        help="path to the active EvolutionBlueprintSet markdown",
    )
    parser.add_argument(
        "--decomposer",
        choices=("single", "deterministic-multi", "peer-chat"),
        default="single",
        help="how to decompose each chain step into lanes",
    )
    parser.add_argument(
        "--chat-driver",
        action="store_true",
        help="enable multi-GOD chat driver (architect/review reply to human messages)",
    )
    parser.add_argument(
        "--chat-driver-model",
        default="haiku",
        help="Claude model for chat-driver GOD replies (haiku|sonnet|opus)",
    )
    args = parser.parse_args()

    asyncio.run(run(
        lanes_path=args.lanes,
        xmuse_root=ROOT / "xmuse",
        mcp_port=args.mcp_port,
        max_hours=args.max_hours,
        max_concurrent=args.max_concurrent,
        graph_id=args.graph_id,
        resolution_id=args.resolution_id,
        require_final_action_approval=args.require_final_action_approval,
        god_runtime=args.god_runtime,
        auto_evolve=args.auto_evolve,
        blueprint_path=args.blueprint,
        decomposer_kind=args.decomposer,
        chat_driver_enabled=args.chat_driver,
        chat_driver_model=args.chat_driver_model,
    ))


if __name__ == "__main__":
    main()
