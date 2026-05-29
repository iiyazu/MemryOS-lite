from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillMeta:
    name: str
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)


@dataclass
class SkillContext:
    """Injected dependencies for skills."""

    registry: Any  # AgentRegistry
    session_manager: Any  # SessionManager
    skill_registry: Any  # SkillRegistry
    feature_root: Path = field(default_factory=lambda: Path("xmuse/work/features"))
    prompt_dir: Path = field(default_factory=lambda: Path("xmuse/prompts"))
    lanes_path: Path = field(default_factory=lambda: Path("xmuse/feature_lanes.json"))
    worktree_resolver: Any = None  # Callable[[str], Path] | None


class SkillResult(BaseModel):
    status: str  # "success" | "failed" | "needs_review"
    artifacts: dict[str, str] = {}
    errors: list[str] = []
    metadata: dict[str, Any] = {}


class SkillProtocol(ABC):
    """Base class for all xmuse skills."""

    _skill_meta: SkillMeta

    def __init__(self, context: SkillContext) -> None:
        self._ctx = context

    @abstractmethod
    async def run(self, input: BaseModel) -> SkillResult: ...

    @property
    def name(self) -> str:
        return self._skill_meta.name

    def _feature_dir(self, feature_id: str) -> Path:
        d = self._ctx.feature_root / feature_id
        d.mkdir(parents=True, exist_ok=True)
        return d
