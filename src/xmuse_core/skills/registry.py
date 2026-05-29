from __future__ import annotations

from typing import Any

from xmuse_core.skills.base import SkillMeta, SkillProtocol


class SkillRegistry:
    """Dict-based skill registry with explicit registration."""

    def __init__(self) -> None:
        self._skills: dict[str, type[SkillProtocol]] = {}

    def register(self, name: str, cls: type[SkillProtocol], *, version: str = "1.0", tags: list[str] | None = None) -> None:
        cls._skill_meta = SkillMeta(name=name, version=version, tags=tags or [])
        self._skills[name] = cls

    def get(self, name: str) -> type[SkillProtocol] | None:
        return self._skills.get(name)

    def list_skills(self) -> list[SkillMeta]:
        return [cls._skill_meta for cls in self._skills.values()]

    def instantiate(self, name: str, context: Any) -> SkillProtocol:
        cls = self._skills.get(name)
        if cls is None:
            raise KeyError(f"Skill not registered: {name}")
        return cls(context)
