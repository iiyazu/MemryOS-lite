from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xmuse_core.platform.final_action_gate import PendingFinalAction
from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict


@dataclass
class VerdictAdapterResult:
    transition_status: str | None
    metadata: dict[str, Any]
    final_action: PendingFinalAction | None = None
    patch_lane: dict[str, Any] | None = None


def adapt_review_verdict(
    verdict: ReviewVerdict,
    *,
    lane: dict[str, Any],
    require_final_action_approval: bool,
) -> VerdictAdapterResult:
    metadata = {
        "review_verdict_id": verdict.id,
        "review_decision": verdict.decision.value,
        "review_summary": verdict.summary,
        "review_evidence_refs": list(verdict.evidence_refs),
    }

    if verdict.decision is ReviewDecision.REWORK:
        return VerdictAdapterResult(
            transition_status="rejected",
            metadata=metadata,
        )

    if verdict.decision is ReviewDecision.PATCH_FORWARD:
        instructions = verdict.patch_instructions or verdict.summary
        patch_lane = {
            "feature_id": f"{verdict.lane_id}-patch-forward",
            "task_type": "execute",
            "status": "pending",
            "prompt": instructions,
            "capabilities": list(lane.get("capabilities", ["code"])),
            "priority": int(lane.get("priority", 0)),
            "source_lane_id": verdict.lane_id,
        }
        for key in ("conversation_id", "resolution_id", "graph_id", "graph_version"):
            if lane.get(key) is not None:
                patch_lane[key] = lane[key]
        return VerdictAdapterResult(
            transition_status=None,
            metadata=metadata,
            patch_lane=patch_lane,
        )

    if verdict.decision is ReviewDecision.MERGE:
        if require_final_action_approval:
            return VerdictAdapterResult(
                transition_status=None,
                metadata=metadata,
                final_action=PendingFinalAction(
                    id=f"hold-{verdict.id}",
                    lane_id=verdict.lane_id,
                    verdict_id=verdict.id,
                    action="merge",
                    target_status="reviewed",
                    summary=verdict.summary,
                ),
            )
        return VerdictAdapterResult(transition_status="reviewed", metadata=metadata)

    if require_final_action_approval:
        return VerdictAdapterResult(
            transition_status=None,
            metadata=metadata | {"terminate_reason": verdict.terminate_reason},
            final_action=PendingFinalAction(
                id=f"hold-{verdict.id}",
                lane_id=verdict.lane_id,
                verdict_id=verdict.id,
                action="terminate",
                target_status="failed",
                summary=verdict.terminate_reason or verdict.summary,
            ),
        )

    return VerdictAdapterResult(
        transition_status="failed",
        metadata=metadata | {"terminate_reason": verdict.terminate_reason},
    )
