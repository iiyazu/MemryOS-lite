from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from memoryos_lite.observability import log_event

logger = logging.getLogger(__name__)


def get_changed_paths(worktree: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        return [p for p in result.stdout.strip().splitlines() if p]
    except Exception:
        return []


async def run_gate(*, lane_id: str, lane: dict[str, Any], root: Path) -> bool:
    worktree = Path(lane.get("worktree", "."))
    gate_profile = lane.get("gate_profile")
    gate_profiles = lane.get("gate_profiles")

    try:
        from xmuse_core.gates.loader import load_gate_config
        from xmuse_core.gates.resolver import GateProfileResolver
        from xmuse_core.gates.runner import GateRunner

        config_path = root / "gate_profiles.json"
        if not config_path.exists():
            log_event(logger, logging.WARNING, "gate_profiles_missing", lane_id=lane_id)
            return True

        config = load_gate_config(config_path, repo_root=root.parent)
        resolver = GateProfileResolver(config)

        explicit_profiles: list[str] = []
        if isinstance(gate_profiles, list):
            explicit_profiles.extend(str(profile) for profile in gate_profiles)
        if gate_profile:
            explicit_profiles.append(str(gate_profile))
        changed = get_changed_paths(worktree)
        warnings: list[str] = []
        resolver_changed_paths = changed
        if explicit_profiles:
            resolver_changed_paths = []
            if changed:
                warnings.append(
                    "explicit gate_profiles selected; full dirty-worktree "
                    "coverage is recorded but not used to reject this lane"
                )

        plan = resolver.resolve(
            feature_id=lane_id,
            worktree=worktree,
            explicit_profiles=explicit_profiles,
            changed_paths=resolver_changed_paths,
            warnings=warnings,
        )

        runner = GateRunner(
            repo_root=root.parent,
            logs_root=root / "logs" / "gates",
        )
        report = await runner.run(plan)
        log_event(
            logger,
            logging.INFO,
            "gate_completed",
            lane_id=lane_id,
            passed=report.passed,
        )
        return report.passed

    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "gate_failed",
            lane_id=lane_id,
            error=str(exc),
            exc_info=True,
        )
        return False
