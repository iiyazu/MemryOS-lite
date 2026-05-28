"""God-picker logic extracted from PlatformOrchestrator.

Encapsulates the round-robin cursor and runtime-mode selection for
execution and review gods.
"""

from __future__ import annotations

from typing import Any, Callable

from xmuse_core.platform.agent_spawner import GodConfig


class GodPicker:
    """Selects execution/review god configs based on runtime mode.

    Parameters
    ----------
    runtime_mode:
        One of ``"codex"``, ``"claude"``, or ``"mixed"``.
    execution_gods:
        Ordered list of execution god configs to round-robin in mixed mode.
    review_gods:
        Ordered list of review god configs to round-robin in mixed mode.
    lane_reader:
        Callable that returns a lane dict given a lane_id, or raises KeyError.
    """

    def __init__(
        self,
        *,
        runtime_mode: str,
        execution_gods: list[GodConfig],
        review_gods: list[GodConfig],
        lane_reader: Callable[[str], dict[str, Any]],
    ) -> None:
        self._runtime_mode = runtime_mode
        self._execution_gods = execution_gods
        self._review_gods = review_gods
        self._lane_reader = lane_reader
        self._mixed_cursor = 0

    @property
    def runtime_mode(self) -> str:
        return self._runtime_mode

    @property
    def execution_gods(self) -> list[GodConfig]:
        return list(self._execution_gods)

    @property
    def review_gods(self) -> list[GodConfig]:
        return list(self._review_gods)

    @property
    def mixed_cursor(self) -> int:
        return self._mixed_cursor

    def pick_execution(self, lane_id: str) -> GodConfig:
        """Choose the execute-god runtime for *lane_id*.

        For ``mixed`` mode we round-robin codex/claude per lane to spread
        load across providers. Existing assignments are preserved by reading
        ``god_runtime`` metadata if it was already recorded.
        """
        if self._runtime_mode != "mixed":
            return self._execution_gods[0]
        try:
            lane = self._lane_reader(lane_id)
        except KeyError:
            lane = None
        if isinstance(lane, dict):
            recorded = lane.get("god_runtime")
            for god in self._execution_gods:
                if god.runtime == recorded:
                    return god
        idx = self._mixed_cursor % len(self._execution_gods)
        self._mixed_cursor += 1
        return self._execution_gods[idx]

    def pick_review(self, lane_id: str) -> GodConfig:
        """Choose the review-god runtime -- match the execute-god so logs align."""
        if self._runtime_mode != "mixed":
            return self._review_gods[0]
        try:
            lane = self._lane_reader(lane_id)
        except KeyError:
            lane = None
        recorded = lane.get("god_runtime") if isinstance(lane, dict) else None
        for god in self._review_gods:
            if god.runtime == recorded:
                return god
        return self._review_gods[0]
