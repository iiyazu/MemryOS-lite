from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RunTerminalStatus(StrEnum):
    """Authoritative run-level terminal outcomes.

    Computed by explicit aggregation over all lane lineages in a run graph,
    not inferred from a single lane state.  See the blueprint-anchored
    self-evolution spec, section "Run Terminal Aggregation".
    """

    MERGED = "merged"
    TERMINATED = "terminated"
    BLOCKED_FOR_INPUT = "blocked_for_input"
    IN_PROGRESS = "in_progress"


class RunTerminalAggregation(BaseModel):
    """Result of a run-level terminal status computation.

    Attributes:
        graph_id: The lane graph this aggregation covers.
        status: The computed terminal (or in-progress) status.
        open_lane_lineages: Lane IDs whose lineage is still open (not yet
            closed by a terminal verdict or state).
        failed_lineages: Lane IDs whose lineage closed via fail/stop semantics.
        open_final_action_holds: Hold IDs that are still pending resolution.
        open_clarification_ids: Clarification/blocked-for-input object IDs
            that are still open (reserved for future use; empty in v1).
        basis: Human-readable summary of the aggregation inputs used.
    """

    graph_id: str
    status: RunTerminalStatus
    open_lane_lineages: list[str] = Field(default_factory=list)
    failed_lineages: list[str] = Field(default_factory=list)
    open_final_action_holds: list[str] = Field(default_factory=list)
    open_clarification_ids: list[str] = Field(default_factory=list)
    basis: str = ""


class LaneNode(BaseModel):
    feature_id: str
    title: str | None = None
    prompt: str
    task_type: str = "execute"
    priority: int = 0
    capabilities: list[str] = Field(default_factory=lambda: ["code"])
    depends_on: list[str] = Field(default_factory=list)
    gate_profile: str | None = None
    gate_profiles: list[str] = Field(default_factory=list)
    source_lane_id: str | None = None
    feature_group: str | None = None


class LaneGraph(BaseModel):
    id: str
    conversation_id: str
    resolution_id: str
    version: int
    status: str = "planned"
    lanes: list[LaneNode] = Field(default_factory=list)


class ReviewDecision(StrEnum):
    MERGE = "merge"
    REWORK = "rework"
    PATCH_FORWARD = "patch-forward"
    TERMINATE = "terminate"


class ReviewVerdict(BaseModel):
    id: str
    lane_id: str
    decision: ReviewDecision
    status: str = "finalized"
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    patch_instructions: str | None = None
    terminate_reason: str | None = None
    # lineage: which task produced this verdict
    task_id: str | None = None
    created_at: str | None = None


class ReviewTaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VERDICT_EMITTED = "verdict_emitted"
    CANCELLED = "cancelled"


class StructuredEvidenceBundle(BaseModel):
    """Cross-run handoff bundle for self-evolution planning.

    Produced after a run reaches a terminal state.  Used by the architect GOD
    to draft the next evolution proposal.

    Evidence curation contract:
    - The controller may summarize, cluster, and rank evidence for planner
      efficiency.
    - Every cited or summarized item must retain a full primary reference in
      ``primary_refs``.
    - ``selection_policy_id`` and ``selection_policy_version`` must identify
      the evidence selection policy used to build the bundle.
    - Architect and review GODs must receive both the curated summary view and
      the primary references view.
    - Selection policy changes must be auditable so later reviewers can explain
      why an item was included or omitted.
    """

    bundle_id: str
    # graph_id of the terminal run
    source_run_id: str
    source_resolution_id: str | None = None
    selection_policy_id: str
    selection_policy_version: str
    summary: str
    run_terminal_status: RunTerminalStatus
    verdict_refs: list[str] = Field(default_factory=list)
    gate_report_refs: list[str] = Field(default_factory=list)
    # patch-forward / requeue lineage references
    lineage_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    # negative / debt signal references
    signal_refs: list[str] = Field(default_factory=list)
    # full primary references for every cited or summarized item
    primary_refs: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class ReviewTask(BaseModel):
    """A unit of review work queued for Review GOD.

    A ReviewTask is the authoritative record that review work was requested for
    a lane.  When Review GOD emits a verdict the task transitions to
    ``verdict_emitted`` and the verdict_id is recorded here, creating an
    auditable chain: lane → task → verdict → lane transition.
    """

    task_id: str
    lane_id: str
    graph_id: str | None = None
    resolution_id: str | None = None
    # snapshot of the lane prompt at task-creation time
    lane_prompt: str = ""
    # gate report reference that triggered this review task
    gate_report_ref: str | None = None
    status: ReviewTaskStatus = ReviewTaskStatus.PENDING
    # set when verdict is emitted
    verdict_id: str | None = None
    created_at: str
    updated_at: str | None = None


class ClarificationStatus(StrEnum):
    """Lifecycle status for a ClarificationObject.

    ``open``
        The clarification is blocking run progress; no executable lane can
        advance until this is resolved.
    ``resolved``
        The clarification has been answered and the block is lifted.
    ``cancelled``
        The clarification was withdrawn without a resolution (e.g. the lane
        was terminated before an answer arrived).
    """

    OPEN = "open"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class ClarificationObject(BaseModel):
    """A blocked-for-input record for a lane that cannot proceed without
    external information or clarification.

    This is the authoritative object for the ``blocked_for_input`` terminal
    state in the run-level aggregation contract.  A run is ``blocked_for_input``
    when at least one ``ClarificationObject`` with status ``open`` exists for
    any lane in the run and no executable lane can advance.

    Minimum fields match the blueprint-anchored self-evolution spec,
    "Run Terminal Aggregation → blocked_for_input" section.
    """

    clarification_id: str
    lane_id: str
    graph_id: str | None = None
    resolution_id: str | None = None
    # Human-readable description of what information is needed.
    question: str
    # Optional structured context for the blocking gap.
    context: dict[str, Any] = Field(default_factory=dict)
    status: ClarificationStatus = ClarificationStatus.OPEN
    # Set when the clarification is resolved.
    answer: str | None = None
    resolved_by: str | None = None
    created_at: str
    updated_at: str | None = None
