"""Adaptive context budget computation.

Determines the optimal token budget for build_context based on session
state, floating between Settings.rot_safe_budget (floor) and
Settings.hard_limit (ceiling).
"""

from __future__ import annotations

from memoryos_lite.config import Settings
from memoryos_lite.schemas import MemoryPage, Message
from memoryos_lite.tokenizer import TokenEstimator


class DynamicBudget:
    """Computes adaptive context budget from session state."""

    def __init__(self, settings: Settings, tokenizer: TokenEstimator) -> None:
        self.settings = settings
        self.tokenizer = tokenizer

    def compute(self, messages: list[Message], pages: list[MemoryPage], task: str) -> int:
        """Return budget in [rot_safe_budget, hard_limit] range.

        Signals that increase budget:
        - More stored pages → more memory to potentially retrieve
        - Longer/more complex task description
        - Higher message count (more context to preserve)
        """
        floor = self.settings.rot_safe_budget
        ceiling = self.settings.hard_limit

        # Each stored page adds ~200 tokens of headroom (capped at ceiling - floor)
        page_pressure = min(len(pages) * 200, ceiling - floor)

        # Complex tasks (longer descriptions) get up to 500 extra tokens
        task_tokens = self.tokenizer.count(task)
        task_pressure = min(task_tokens, 500)

        # Many messages suggest an active session that benefits from more budget
        message_pressure = min(len(messages) * 20, 400)

        budget = floor + page_pressure + task_pressure + message_pressure
        return min(max(budget, floor), ceiling)
