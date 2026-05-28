"""Pure-function prompt builders extracted from PlatformOrchestrator.

Each function takes a lane dict and the xmuse root path, returning the
assembled prompt string or structured verdict object.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict


def build_execution_prompt(
    lane: dict[str, Any],
    *,
    xmuse_root: Path,
    skill_prompt_path: str,
) -> str:
    """Build the full execution-god prompt for *lane*."""
    prompt_path = xmuse_root / skill_prompt_path
    skill = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    task = lane.get("prompt", "")
    lid = lane.get("feature_id", "")
    return f"{skill}\n\n## Task\n\nLane ID: {lid}\n\n{task}"


def build_review_prompt(
    lane: dict[str, Any],
    *,
    xmuse_root: Path,
    skill_prompt_path: str,
) -> str:
    """Build the full review-god prompt for *lane*."""
    prompt_path = xmuse_root / skill_prompt_path
    skill = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    lid = lane.get("feature_id", "")
    return f"{skill}\n\n## Task\n\nReview lane: {lid}"


def build_review_verdict(lane: dict[str, Any]) -> ReviewVerdict:
    """Construct a ReviewVerdict from lane metadata."""
    raw_decision = lane.get("review_decision", ReviewDecision.MERGE.value)
    try:
        decision = ReviewDecision(str(raw_decision))
    except ValueError:
        decision = ReviewDecision.MERGE

    evidence_refs = lane.get("review_evidence_refs", [])
    if not isinstance(evidence_refs, list):
        evidence_refs = []

    return ReviewVerdict(
        id=str(lane.get("review_verdict_id", f"verdict-{lane.get('feature_id', 'lane')}")),
        lane_id=str(lane.get("feature_id", "")),
        decision=decision,
        summary=str(lane.get("review_summary", lane.get("decision_reason", "reviewed"))),
        evidence_refs=[str(item) for item in evidence_refs],
        patch_instructions=(
            str(lane["patch_instructions"])
            if lane.get("patch_instructions") is not None
            else None
        ),
        terminate_reason=(
            str(lane["terminate_reason"]) if lane.get("terminate_reason") is not None else None
        ),
    )
