from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from xmuse_core.skills.base import SkillResult

logger = logging.getLogger(__name__)


class SuperpowersBridge:
    """Optional adapter to delegate to superpowers plugin when available."""

    def __init__(self) -> None:
        self._enabled = os.environ.get("XMUSE_SUPERPOWERS", "").strip() == "1"

    @property
    def available(self) -> bool:
        return self._enabled

    def has_skill(self, name: str) -> bool:
        return self._enabled and name in self._SKILL_MAP

    async def delegate_brainstorm(self, input: Any, feature_dir: Path) -> SkillResult:
        """Format brainstorm as superpowers-compatible dispatch."""
        if not self._enabled:
            return SkillResult(status="failed", errors=["superpowers not enabled"])
        logger.info(
            "Delegating brainstorm to superpowers:brainstorming for %s",
            input.feature_id,
        )
        # Superpowers integration is handled by the calling agent's
        # session having the superpowers plugin loaded. We return a
        # marker so the caller knows to use the plugin skill invocation.
        return SkillResult(
            status="failed",
            errors=["superpowers delegation requires interactive session"],
            metadata={"superpowers_skill": "superpowers:brainstorming"},
        )

    _SKILL_MAP = {
        "brainstorming": "superpowers:brainstorming",
        "writing-plans": "superpowers:writing-plans",
        "subagent-driven-development": "superpowers:subagent-driven-development",
    }
