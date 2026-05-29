from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from xmuse_core.skills.base import SkillProtocol, SkillResult
from xmuse_core.skills.models import LaneDefinition, LaneGraph, SpecToLanesInput

logger = logging.getLogger(__name__)


class SpecToLanesSkill(SkillProtocol):
    """Decompose a design spec into lanes with dependency graph and concurrency plan."""

    async def run(self, input: BaseModel) -> SkillResult:
        assert isinstance(input, SpecToLanesInput)
        feature_dir = self._feature_dir(input.feature_id)

        spec_content = Path(input.spec_path).read_text()
        prompt = self._build_prompt(input.feature_id, spec_content)
        worktree = self._resolve_worktree(input.feature_id)

        output = await self._ctx.session_manager.dispatch_one_shot(
            agent=self._ctx.registry.select(["code"]),
            feature_id=input.feature_id,
            prompt=prompt,
            worktree=worktree,
        )

        if output.status not in ("success", "done"):
            return SkillResult(
                status="failed",
                errors=[output.error_message or "decompose dispatch failed"],
            )

        raw_text = self._extract_text(output)
        lanes = self._parse_lanes(raw_text)

        errors = self._validate_graph(lanes)
        if errors:
            return SkillResult(status="failed", errors=errors)

        groups = self._compute_concurrency_groups(lanes)
        critical = self._compute_critical_path(lanes)

        graph = LaneGraph(
            source_spec=input.spec_path,
            lanes=lanes,
            concurrency_groups=groups,
            critical_path=critical,
        )

        graph_path = feature_dir / "lane_graph.json"
        graph_path.write_text(graph.model_dump_json(indent=2))

        return SkillResult(
            status="success",
            artifacts={"lane_graph": str(graph_path)},
            metadata={
                "lanes_count": len(lanes),
                "concurrency_groups": len(groups),
                "critical_path_length": len(critical),
            },
        )

    def _build_prompt(self, feature_id: str, spec_content: str) -> str:
        base = self._load_prompt("decompose_agent.md")
        return (
            f"{base}\n\n"
            f"## Feature: {feature_id}\n\n"
            f"## Design Spec\n\n{spec_content}\n\n"
            "## Output Format\n"
            "Return a JSON array of lane definitions in a fenced block:\n"
            "```json\n"
            '[{"feature_id": "...", "task_type": "execute", "prompt": "...", '
            '"capabilities": ["code"], "depends_on": [], '
            '"estimated_complexity": "small|medium|large"}]\n'
            "```\n"
            "Each lane must have a unique feature_id. Use depends_on to declare "
            "ordering constraints between lanes.\n"
        )

    def _load_prompt(self, name: str) -> str:
        path = self._ctx.prompt_dir / name
        return path.read_text().strip() if path.exists() else ""

    def _resolve_worktree(self, feature_id: str) -> Path:
        if self._ctx.worktree_resolver:
            return Path(self._ctx.worktree_resolver(feature_id))
        return Path.cwd()

    @staticmethod
    def _extract_text(output: Any) -> str:
        for key in ("lane_graph.json", "lanes", "stdout"):
            value = output.artifacts.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(output.artifacts, indent=2)

    def _parse_lanes(self, text: str) -> list[LaneDefinition]:
        data = _extract_fenced_json(text)
        if isinstance(data, list):
            return [LaneDefinition.model_validate(item) for item in data]
        if isinstance(data, dict) and "lanes" in data:
            return [LaneDefinition.model_validate(item) for item in data["lanes"]]
        return []

    @staticmethod
    def _validate_graph(lanes: list[LaneDefinition]) -> list[str]:
        errors: list[str] = []
        ids = {lane.feature_id for lane in lanes}
        seen: set[str] = set()
        for lane in lanes:
            if lane.feature_id in seen:
                errors.append(f"Duplicate feature_id: {lane.feature_id}")
            seen.add(lane.feature_id)
            for dep in lane.depends_on:
                if dep not in ids:
                    errors.append(f"{lane.feature_id} depends on unknown: {dep}")
            if lane.feature_id in lane.depends_on:
                errors.append(f"{lane.feature_id} depends on itself")
        # Cycle detection via Kahn's
        in_degree = {lane.feature_id: 0 for lane in lanes}
        for lane in lanes:
            for dep in lane.depends_on:
                if dep in in_degree:
                    in_degree[lane.feature_id] += 1
        queue = [fid for fid, deg in in_degree.items() if deg == 0]
        visited = 0
        adj: dict[str, list[str]] = defaultdict(list)
        for lane in lanes:
            for dep in lane.depends_on:
                if dep in in_degree:
                    adj[dep].append(lane.feature_id)
        while queue:
            node = queue.pop(0)
            visited += 1
            for dependent in adj[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        if visited < len(lanes):
            errors.append("Cycle detected in dependency graph")
        return errors

    @staticmethod
    def _compute_concurrency_groups(lanes: list[LaneDefinition]) -> list[list[str]]:
        in_degree = {lane.feature_id: 0 for lane in lanes}
        adj: dict[str, list[str]] = defaultdict(list)
        for lane in lanes:
            for dep in lane.depends_on:
                if dep in in_degree:
                    in_degree[lane.feature_id] += 1
                    adj[dep].append(lane.feature_id)
        groups: list[list[str]] = []
        ready = sorted(fid for fid, deg in in_degree.items() if deg == 0)
        while ready:
            groups.append(ready)
            next_ready: list[str] = []
            for fid in ready:
                for dependent in adj[fid]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_ready.append(dependent)
            ready = sorted(next_ready)
        return groups

    @staticmethod
    def _compute_critical_path(lanes: list[LaneDefinition]) -> list[str]:
        id_to_lane = {lane.feature_id: lane for lane in lanes}
        dist: dict[str, int] = {lane.feature_id: 0 for lane in lanes}
        pred: dict[str, str | None] = {lane.feature_id: None for lane in lanes}
        adj: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {lane.feature_id: 0 for lane in lanes}
        for lane in lanes:
            for dep in lane.depends_on:
                if dep in id_to_lane:
                    adj[dep].append(lane.feature_id)
                    in_degree[lane.feature_id] += 1
        queue = [fid for fid, deg in in_degree.items() if deg == 0]
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for dep in adj[node]:
                if dist[node] + 1 > dist[dep]:
                    dist[dep] = dist[node] + 1
                    pred[dep] = node
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)
        if not order:
            return []
        end = max(order, key=lambda x: dist[x])
        path: list[str] = []
        cur: str | None = end
        while cur is not None:
            path.append(cur)
            cur = pred[cur]
        path.reverse()
        return path


def _extract_fenced_json(text: str) -> Any:
    m = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None
