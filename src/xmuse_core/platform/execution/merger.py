from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from memoryos_lite.observability import log_event

logger = logging.getLogger(__name__)


async def auto_merge(*, lane_id: str, lane: dict[str, Any], worktree: Path) -> bool:
    try:
        if not lane.get("branch"):
            log_event(
                logger,
                logging.INFO,
                "lane_no_branch_treated_as_applied",
                lane_id=lane_id,
            )
            return True

        diff_check = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        insertions = 0
        for line in diff_check.stdout.splitlines():
            if "insertion" in line or "deletion" in line:
                parts = line.split(",")
                for part in parts:
                    if "insertion" in part:
                        insertions += int(part.strip().split()[0])
        if insertions > 1000:
            log_event(
                logger,
                logging.WARNING,
                "lane_diff_too_large",
                lane_id=lane_id,
                insertions=insertions,
            )
            return False

        result = subprocess.run(
            ["git", "checkout", "main"],
            cwd=worktree, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log_event(
                logger,
                logging.WARNING,
                "checkout_main_failed",
                lane_id=lane_id,
                stderr=result.stderr,
            )
            return False

        merge_branch = lane_id

        result = subprocess.run(
            ["git", "merge", "--no-ff", merge_branch, "-m",
             f"feat(xmuse): merge lane {lane_id}"],
            cwd=worktree, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log_event(
                logger,
                logging.WARNING,
                "git_merge_failed",
                lane_id=lane_id,
                stderr=result.stderr,
            )
            subprocess.run(["git", "merge", "--abort"],
                           cwd=worktree, capture_output=True, timeout=5)
            return False
        return True
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "auto_merge_error",
            lane_id=lane_id,
            error=str(exc),
            exc_info=True,
        )
        return False
