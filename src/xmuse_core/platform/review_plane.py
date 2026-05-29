"""ReviewPlaneController: persistent auditor for lane review work.

This module implements the ``review_plane`` blueprint track.  It makes Review
GOD a persistent auditor by:

1. Creating a ``ReviewTask`` when a lane enters review.
2. Accepting a ``ReviewVerdict`` emitted by Review GOD and persisting it.
3. Driving the lane state transition through ``VerdictAdapterResult``.
4. Recording the full task→verdict→transition lineage so that every
   ``approve``, ``requeue``, ``patch_forward``, and ``terminate`` decision is
   auditable from the store.

The controller is intentionally stateless between calls; all state lives in
``VerdictStore`` and the lane file managed by ``LaneStateMachine``.

Merge guards (evbundle_6259476d67dd414a8be293d1025ccb8c)
---------------------------------------------------------
Evidence bundle evbundle_6259476d67dd414a8be293d1025ccb8c showed a graph
lineage terminating without a proper merge verdict, leaving sibling lineages
stranded and the run-level terminal status ambiguous.

Three guards are added to prevent this:

``check_lineage_merge_completeness``
    Inspects every lane lineage in a graph and classifies each as
    ``merged``, ``terminated_without_merge``, or ``open``.  Returns a
    :class:`LineageMergeReport` that callers and the evidence bundle can
    use to surface incomplete terminations.

``assert_termination_safe``
    Called before a ``TERMINATE`` verdict is ingested.  Raises
    :class:`IncompleteLineageTerminationError` when the termination would
    leave one or more sibling lineages in the same graph open and without
    a merge verdict, preventing the review plane from allowing termination
    in an incomplete state.

``record_incomplete_termination``
    Writes a structured incomplete-termination signal into the verdict
    store for a lane that reached a terminal state without a merge verdict.
    The signal is picked up by ``assemble_evidence_bundle`` as a negative
    signal ref so the next planning cycle can reason about the gap.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xmuse_core.platform.final_action_gate import FinalActionGateStore
from xmuse_core.platform.state_machine import LaneStateMachine
from xmuse_core.platform.verdict_adapter import VerdictAdapterResult, adapt_review_verdict
from xmuse_core.structuring.models import (
    LaneGraph,
    ReviewDecision,
    ReviewTask,
    ReviewTaskStatus,
    ReviewVerdict,
    RunTerminalAggregation,
    RunTerminalStatus,
    StructuredEvidenceBundle,
)
from xmuse_core.structuring.verdict_store import (
    ClarificationStore,
    EvidenceBundleStore,
    VerdictStore,
)

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Merge-guard types
# ---------------------------------------------------------------------------

# Lane statuses that represent a clean merge outcome.
_MERGED_STATUSES: frozenset[str] = frozenset({"merged", "done", "completed"})

# Lane statuses that represent a terminal failure / stop without merge.
#
# ``gate_failed`` is intentionally excluded: the state machine allows it to
# retry, rework, or return to gated, so it is still an open/recoverable lineage
# until projected to ``failed``.
_FAILED_STATUSES: frozenset[str] = frozenset({"failed", "exec_failed"})

# Lane statuses that are still actively in-flight (not yet terminal).
_OPEN_STATUSES: frozenset[str] = frozenset(
    {
        "pending",
        "dispatched",
        "executed",
        "gated",
        "reviewed",
        "reworking",
        "awaiting_final_action",
        "rejected",
        "gate_failed",
    }
)


class RunTerminalAggregator:
    """Computes run-level terminal outcomes from all available evidence sources.

    This is the authoritative aggregation implementation for the
    blueprint-anchored self-evolution spec (evidence bundle
    evbundle_e72fecb39ee8439c8338891e9f4fd373).  It evaluates:

    - **Authoritative LaneGraph**: when provided, the canonical set of lanes
      for the run is seeded from ``LaneGraph.lanes`` rather than inferred
      solely from the lane-file ``graph_id`` field.  This prevents phantom
      lanes (lanes that were removed from the graph after projection) from
      keeping a run open indefinitely.
    - **Normalized lane execution states**: the current ``status`` field for
      each lane in the state machine.
    - **Verdict lineage**: whether each lane has at least one finalized MERGE
      verdict in the verdict store, used to distinguish a cleanly-merged lane
      from one that reached ``merged`` status without a review verdict.
    - **Patch-forward lineage**: ``source_lane_id`` transitive closure so that
      every descendant created through requeue, rework, or patch-forward is
      included in the aggregation.
    - **Final-action holds**: pending holds from ``FinalActionGateStore`` that
      block run completion even when all lane lineages are closed.
    - **Clarification objects**: open ``ClarificationObject`` records from
      ``ClarificationStore`` that represent blocked-for-input states.

    Lane-lineage closure classification
    ------------------------------------
    Each lane lineage is classified as one of:

    ``merged``
        The lane reached a merged/done/completed status **or** has at least
        one finalized MERGE verdict in the verdict store.

    ``terminated_without_merge``
        The lane reached a terminal failure state (``failed`` or
        ``exec_failed``) without a corresponding MERGE verdict.

    ``open``
        The lane is still in-flight (not yet in any terminal state) or has
        not yet been projected into the state machine.

    Run-level terminal status
    -------------------------
    ``in_progress``
        At least one lane lineage is still open.

    ``blocked_for_input``
        All lane lineages are closed, but at least one pending final-action
        hold or open clarification object remains unresolved.

    ``terminated``
        All lane lineages are closed; at least one closed via fail/stop
        semantics and no holds or clarifications are pending.

    ``merged``
        All lane lineages closed cleanly; no holds or clarifications pending.
    """

    def __init__(
        self,
        *,
        sm: LaneStateMachine,
        verdict_store: VerdictStore,
        final_action_store: FinalActionGateStore | None = None,
        clarification_store: ClarificationStore | None = None,
    ) -> None:
        self._sm = sm
        self._verdict_store = verdict_store
        self._final_action_store = final_action_store
        self._clarification_store = clarification_store

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def compute(
        self,
        graph_id: str,
        *,
        lane_graph: LaneGraph | None = None,
    ) -> RunTerminalAggregation:
        """Compute the run-level terminal status for *graph_id*.

        Args:
            graph_id: The lane graph ID of the run to aggregate.
            lane_graph: Optional authoritative :class:`LaneGraph`.  When
                provided its ``lanes`` list seeds the lane-ID collection so
                that the aggregation is not dependent on the ``graph_id``
                field being correctly stamped on every lane in the state
                machine.

        Returns:
            A :class:`RunTerminalAggregation` with the computed status and
            the full set of inputs used to reach that decision.
        """
        all_lanes = self._sm.get_lanes()
        lane_map: dict[str, dict[str, Any]] = {
            str(lane["feature_id"]): lane
            for lane in all_lanes
            if isinstance(lane.get("feature_id"), str)
        }

        # Step 1: collect the authoritative set of lane IDs for this run.
        graph_lane_ids = self._collect_lane_ids(graph_id, lane_graph, all_lanes)
        lane_id_set: set[str] = set(graph_lane_ids)

        # Step 2: classify each lane lineage.
        merged_lineages, failed_lineages, open_lineages = self._classify_lineages(
            graph_lane_ids, lane_map
        )

        # Step 3: check pending final-action holds.
        open_holds = self._collect_open_holds(lane_id_set)

        # Step 4: check open clarification objects (blocked-for-input).
        open_clarification_ids = self._collect_open_clarifications(lane_id_set)

        # Step 5: determine the run-level terminal status.
        computed_status = self._compute_status(
            open_lineages=open_lineages,
            open_holds=open_holds,
            open_clarification_ids=open_clarification_ids,
            failed_lineages=failed_lineages,
        )

        basis_parts = [
            f"graph_id={graph_id}",
            f"total_lane_lineages={len(graph_lane_ids)}",
            f"merged={len(merged_lineages)}",
            f"open={len(open_lineages)}",
            f"failed={len(failed_lineages)}",
            f"open_holds={len(open_holds)}",
            f"open_clarifications={len(open_clarification_ids)}",
        ]
        if lane_graph is not None:
            basis_parts.append(f"authoritative_graph={lane_graph.id}")

        return RunTerminalAggregation(
            graph_id=graph_id,
            status=computed_status,
            open_lane_lineages=open_lineages,
            failed_lineages=failed_lineages,
            open_final_action_holds=open_holds,
            open_clarification_ids=open_clarification_ids,
            basis="; ".join(basis_parts),
        )

    # ------------------------------------------------------------------
    # Lane-ID collection (authoritative LaneGraph + source_lane_id closure)
    # ------------------------------------------------------------------

    def _collect_lane_ids(
        self,
        graph_id: str,
        lane_graph: LaneGraph | None,
        all_lanes: list[dict[str, Any]],
    ) -> list[str]:
        """Return all lane IDs belonging to this run.

        Seeds from the authoritative ``LaneGraph`` when provided, otherwise
        falls back to lanes whose ``graph_id`` field matches.  In both cases
        the set is expanded via transitive ``source_lane_id`` closure to
        include every patch-forward and requeue descendant.
        """
        if lane_graph is not None:
            # Authoritative seed: use the LaneGraph's own lane list.
            seed_ids: list[str] = [node.feature_id for node in lane_graph.lanes]
        else:
            # Fallback: infer from the graph_id field on each lane.
            seed_ids = [
                str(lane["feature_id"])
                for lane in all_lanes
                if isinstance(lane.get("feature_id"), str) and lane.get("graph_id") == graph_id
            ]

        # Transitive source_lane_id closure: include every descendant created
        # through requeue, rework, or patch-forward continuation.
        collected: list[str] = list(seed_ids)
        seen: set[str] = set(collected)
        changed = True
        while changed:
            changed = False
            for lane in all_lanes:
                fid = lane.get("feature_id")
                src = lane.get("source_lane_id")
                if (
                    isinstance(fid, str)
                    and isinstance(src, str)
                    and src in seen
                    and fid not in seen
                ):
                    collected.append(fid)
                    seen.add(fid)
                    changed = True
        return collected

    # ------------------------------------------------------------------
    # Lane-lineage closure classification
    # ------------------------------------------------------------------

    def _classify_lineages(
        self,
        lane_ids: list[str],
        lane_map: dict[str, dict[str, Any]],
    ) -> tuple[list[str], list[str], list[str]]:
        """Classify each lane as merged, failed, or open.

        Returns:
            A ``(merged, failed, open)`` triple of lane-ID lists.

        Classification rules:

        - **merged**: status in ``_MERGED_STATUSES`` *or* the verdict store
          contains at least one finalized MERGE verdict for the lane.  Using
          the verdict store as a secondary signal means a lane that was
          force-transitioned to ``merged`` without going through the review
          plane is still classified correctly.
        - **failed**: status in ``_FAILED_STATUSES`` *and* no MERGE verdict.
          A failed lane that somehow received a MERGE verdict (e.g. via a
          manual override) is promoted to ``merged`` to avoid false negatives.
        - **open**: everything else, including lanes not yet projected into
          the state machine.
        """
        merged: list[str] = []
        failed: list[str] = []
        open_: list[str] = []

        for lane_id in lane_ids:
            lane = lane_map.get(lane_id)
            if lane is None:
                # Lane referenced in graph but not yet projected — still open.
                open_.append(lane_id)
                continue

            status = str(lane.get("status", "pending"))
            has_merge_verdict = self._has_merge_verdict(lane_id)

            if status in _MERGED_STATUSES or has_merge_verdict:
                merged.append(lane_id)
            elif status in _FAILED_STATUSES:
                failed.append(lane_id)
            else:
                open_.append(lane_id)

        return merged, failed, open_

    def _has_merge_verdict(self, lane_id: str) -> bool:
        """Return True if *lane_id* has at least one finalized MERGE verdict."""
        return any(
            v.status == "finalized" and v.decision == ReviewDecision.MERGE
            for v in self._verdict_store.list_verdicts_for_lane(lane_id)
        )

    # ------------------------------------------------------------------
    # Final-action hold detection
    # ------------------------------------------------------------------

    def _collect_open_holds(self, lane_id_set: set[str]) -> list[str]:
        """Return IDs of pending final-action holds for lanes in this run."""
        if self._final_action_store is None:
            return []
        return [
            hold.id
            for hold in self._final_action_store.list_actions()
            if hold.lane_id in lane_id_set and hold.status == "pending"
        ]

    # ------------------------------------------------------------------
    # Blocked-for-input detection (clarification objects)
    # ------------------------------------------------------------------

    def _collect_open_clarifications(self, lane_id_set: set[str]) -> list[str]:
        """Return IDs of open clarification objects for lanes in this run.

        A run is ``blocked_for_input`` when at least one open clarification
        exists and no lane lineage is still actively executable.  This method
        returns the raw clarification IDs; the terminal-status decision is
        made in :meth:`_compute_status`.
        """
        if self._clarification_store is None:
            return []
        return [
            c.clarification_id
            for c in self._clarification_store.list_open_for_lane_set(lane_id_set)
        ]

    # ------------------------------------------------------------------
    # Terminal-status decision
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_status(
        *,
        open_lineages: list[str],
        open_holds: list[str],
        open_clarification_ids: list[str],
        failed_lineages: list[str],
    ) -> RunTerminalStatus:
        """Derive the run-level terminal status from the classified inputs.

        Priority order (highest to lowest):

        1. ``in_progress`` — any lane lineage is still open.
        2. ``blocked_for_input`` — all lineages closed but a hold or
           clarification is pending.
        3. ``terminated`` — all lineages closed; at least one via fail
           semantics; no pending holds or clarifications.
        4. ``merged`` — all lineages closed cleanly; nothing pending.
        """
        if open_lineages:
            return RunTerminalStatus.IN_PROGRESS
        if open_holds or open_clarification_ids:
            return RunTerminalStatus.BLOCKED_FOR_INPUT
        if failed_lineages:
            return RunTerminalStatus.TERMINATED
        return RunTerminalStatus.MERGED


class IncompleteLineageTerminationError(RuntimeError):
    """Raised when a termination would leave graph lineages without a merge.

    The review plane raises this to prevent a ``TERMINATE`` verdict from being
    ingested when one or more sibling lineages in the same graph are still open
    or have already terminated without a merge verdict.  Callers must resolve
    the open lineages before the termination can proceed.

    Attributes:
        lane_id: The lane whose termination was blocked.
        graph_id: The graph that contains the incomplete lineages.
        open_lineages: Lane IDs that are still in-flight.
        unmerged_lineages: Lane IDs that terminated without a merge verdict.
    """

    def __init__(
        self,
        lane_id: str,
        graph_id: str,
        *,
        open_lineages: list[str],
        unmerged_lineages: list[str],
    ) -> None:
        self.lane_id = lane_id
        self.graph_id = graph_id
        self.open_lineages = list(open_lineages)
        self.unmerged_lineages = list(unmerged_lineages)
        parts: list[str] = [f"termination of lane {lane_id!r} in graph {graph_id!r} is unsafe:"]
        if open_lineages:
            parts.append(f"  open lineages: {open_lineages}")
        if unmerged_lineages:
            parts.append(f"  unmerged lineages: {unmerged_lineages}")
        super().__init__("\n".join(parts))


@dataclass
class LineageMergeReport:
    """Result of :meth:`ReviewPlaneController.check_lineage_merge_completeness`.

    Attributes:
        graph_id: The graph this report covers.
        merged_lineages: Lane IDs whose lineage closed via a merge verdict.
        terminated_without_merge: Lane IDs that reached a terminal failure
            state without ever receiving a merge verdict.
        open_lineages: Lane IDs that are still in-flight.
        is_complete: True when every lineage is merged and none are open or
            terminated without merge.
    """

    graph_id: str
    merged_lineages: list[str] = field(default_factory=list)
    terminated_without_merge: list[str] = field(default_factory=list)
    open_lineages: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True when all lineages are merged and none are incomplete."""
        return not self.terminated_without_merge and not self.open_lineages


class ReviewPlaneController:
    """Coordinates the full review lifecycle for a single lane.

    Usage::

        controller = ReviewPlaneController(
            lanes_path=Path("xmuse/feature_lanes.json"),
            store_path=Path("xmuse/review_plane.json"),
            final_actions_path=Path("xmuse/final_actions.json"),
        )

        # When a lane enters review (after gate passes):
        task = controller.open_review_task(lane_id="my-lane")

        # When Review GOD emits a verdict:
        result = controller.ingest_verdict(
            task_id=task.task_id,
            verdict=ReviewVerdict(
                id="verdict-abc",
                lane_id="my-lane",
                decision=ReviewDecision.MERGE,
                summary="No findings.",
            ),
            require_final_action_approval=False,
        )
        # result.transition_status is the new lane status (or None for holds)
    """

    def __init__(
        self,
        *,
        lanes_path: Path | str,
        store_path: Path | str,
        final_actions_path: Path | str,
        require_final_action_approval: bool = False,
        clarification_store_path: Path | str | None = None,
    ) -> None:
        self._lanes_path = Path(lanes_path)
        self._sm = LaneStateMachine(self._lanes_path)
        self._store = VerdictStore(Path(store_path))
        self._final_action_store = FinalActionGateStore(Path(final_actions_path))
        self._require_final_action_approval = require_final_action_approval
        self._clarification_store: ClarificationStore | None = (
            ClarificationStore(Path(clarification_store_path))
            if clarification_store_path is not None
            else None
        )

    @property
    def store(self) -> VerdictStore:
        return self._store

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------

    def open_review_task(
        self,
        lane_id: str,
        *,
        gate_report_ref: str | None = None,
    ) -> ReviewTask:
        """Create a ReviewTask for *lane_id* and persist it.

        If a pending task already exists for this lane it is returned as-is
        (idempotent).
        """
        existing = [
            t
            for t in self._store.list_tasks_for_lane(lane_id)
            if t.status == ReviewTaskStatus.PENDING
        ]
        if existing:
            return existing[-1]

        lane = self._sm.get_lane(lane_id)
        task = ReviewTask(
            task_id=_new_id("rtask"),
            lane_id=lane_id,
            graph_id=str(lane.get("graph_id") or "") or None,
            resolution_id=str(lane.get("resolution_id") or "") or None,
            lane_prompt=str(lane.get("prompt", "")),
            gate_report_ref=gate_report_ref,
            status=ReviewTaskStatus.PENDING,
            created_at=_utc_now(),
        )
        return self._store.save_task(task)

    def cancel_review_task(self, task_id: str) -> ReviewTask:
        """Mark a task as cancelled (e.g. lane was retried before verdict).

        The read-modify-write is performed atomically via
        :meth:`VerdictStore.cancel_task` so a concurrent verdict emission
        cannot silently overwrite the cancellation.
        """
        return self._store.cancel_task(task_id, updated_at=_utc_now())

    # ------------------------------------------------------------------
    # Verdict ingestion
    # ------------------------------------------------------------------

    def ingest_verdict(
        self,
        task_id: str,
        verdict: ReviewVerdict,
        *,
        require_final_action_approval: bool | None = None,
    ) -> VerdictAdapterResult:
        """Persist *verdict*, update the task, and drive the lane transition.

        Returns the ``VerdictAdapterResult`` so callers can act on
        ``transition_status``, ``final_action``, and ``patch_lane``.

        The lane state machine transition is **not** applied here; the caller
        (e.g. ``PlatformOrchestrator``) is responsible for calling
        ``sm.transition()``.  This keeps the controller side-effect-free with
        respect to the lane file and easy to test.

        Merge guard (evbundle_6259476d67dd414a8be293d1025ccb8c):
            When the verdict decision is ``TERMINATE``, :meth:`assert_termination_safe`
            is called before the verdict is persisted.  If the graph still has
            open or unmerged sibling lineages the call raises
            :class:`IncompleteLineageTerminationError` and the verdict is
            **not** stored, preventing the review plane from allowing
            termination in an incomplete state.
        """
        task = self._store.get_task(task_id)

        # Merge guard: block TERMINATE verdicts when sibling lineages are
        # still open or have already terminated without a merge verdict.
        if verdict.decision == ReviewDecision.TERMINATE:
            lane = self._sm.get_lane(verdict.lane_id)
            graph_id = lane.get("graph_id")
            if graph_id:
                self.assert_termination_safe(verdict.lane_id, str(graph_id))

        # Stamp the verdict with the task_id for lineage
        if verdict.task_id is None:
            verdict = verdict.model_copy(update={"task_id": task_id})
        if verdict.created_at is None:
            verdict = verdict.model_copy(update={"created_at": _utc_now()})

        # Stamp the task with updated_at before the atomic write so the
        # timestamp is consistent with the verdict's created_at.
        task = task.model_copy(update={"updated_at": _utc_now()})

        # Persist both records atomically: the task transitions to
        # verdict_emitted and its verdict_id is linked to verdict.id in a
        # single locked write.  This closes the split-brain window where
        # save_verdict and save_task were called separately and a crash (or
        # concurrent reader) could observe a verdict with no corresponding
        # verdict_emitted task.
        task, verdict = self._store.save_task_and_verdict(task, verdict)

        lane = self._sm.get_lane(verdict.lane_id)
        use_final_action = (
            require_final_action_approval
            if require_final_action_approval is not None
            else self._require_final_action_approval
        )
        result = adapt_review_verdict(
            verdict,
            lane=lane,
            require_final_action_approval=use_final_action,
        )

        # Persist the final-action hold if one was produced
        if result.final_action is not None:
            self._final_action_store.create_hold(
                lane_id=result.final_action.lane_id,
                verdict_id=result.final_action.verdict_id,
                action=result.final_action.action,
                target_status=result.final_action.target_status,
                summary=result.final_action.summary,
            )

        return result

    # ------------------------------------------------------------------
    # Lineage queries
    # ------------------------------------------------------------------

    def verdict_lineage_for_lane(self, lane_id: str) -> list[dict[str, Any]]:
        """Return the full task→verdict lineage for *lane_id*.

        Each entry is a dict with ``task`` and ``verdict`` keys (verdict may be
        None if the task has not yet emitted one).
        """
        tasks = self._store.list_tasks_for_lane(lane_id)
        verdicts_by_id = {v.id: v for v in self._store.list_verdicts_for_lane(lane_id)}
        lineage: list[dict[str, Any]] = []
        for task in tasks:
            verdict = verdicts_by_id.get(task.verdict_id or "") if task.verdict_id else None
            lineage.append(
                {
                    "task": task.model_dump(mode="json"),
                    "verdict": verdict.model_dump(mode="json") if verdict else None,
                }
            )
        return lineage

    def has_verdict_lineage(self, lane_id: str) -> bool:
        """Return True if *lane_id* has at least one finalized verdict."""
        return any(v.status == "finalized" for v in self._store.list_verdicts_for_lane(lane_id))

    def _has_merge_verdict(self, lane_id: str) -> bool:
        """Return True if *lane_id* has at least one finalized MERGE verdict."""
        return any(
            v.status == "finalized" and v.decision == ReviewDecision.MERGE
            for v in self._store.list_verdicts_for_lane(lane_id)
        )

    # ------------------------------------------------------------------
    # Merge guards (evbundle_6259476d67dd414a8be293d1025ccb8c)
    # ------------------------------------------------------------------

    def _collect_graph_lane_ids(self, graph_id: str) -> list[str]:
        """Return all lane IDs belonging to *graph_id* including lineage descendants."""
        all_lanes = self._sm.get_lanes()
        graph_lane_ids: list[str] = [
            str(lane["feature_id"])
            for lane in all_lanes
            if isinstance(lane.get("feature_id"), str) and lane.get("graph_id") == graph_id
        ]
        seen: set[str] = set(graph_lane_ids)
        changed = True
        while changed:
            changed = False
            for lane in all_lanes:
                fid = lane.get("feature_id")
                src = lane.get("source_lane_id")
                if (
                    isinstance(fid, str)
                    and isinstance(src, str)
                    and src in seen
                    and fid not in seen
                ):
                    graph_lane_ids.append(fid)
                    seen.add(fid)
                    changed = True
        return graph_lane_ids

    def check_lineage_merge_completeness(self, graph_id: str) -> LineageMergeReport:
        """Inspect every lane lineage in *graph_id* and classify its merge state.

        Each lane lineage is classified as one of:

        ``merged_lineages``
            The lane reached a merged/done/completed status **or** has at
            least one finalized MERGE verdict in the review plane.

        ``terminated_without_merge``
            The lane reached a terminal failure state (``failed`` or
            ``exec_failed``) without a corresponding MERGE verdict.  This is
            the incomplete-termination signal captured by
            evidence bundle evbundle_6259476d67dd414a8be293d1025ccb8c.

        ``open_lineages``
            The lane is still in-flight (not yet in any terminal state).

        Returns a :class:`LineageMergeReport` with the classification results.
        """
        graph_lane_ids = self._collect_graph_lane_ids(graph_id)
        all_lanes = self._sm.get_lanes()
        lane_map: dict[str, dict[str, Any]] = {
            str(lane["feature_id"]): lane
            for lane in all_lanes
            if isinstance(lane.get("feature_id"), str)
        }

        report = LineageMergeReport(graph_id=graph_id)
        for lane_id in graph_lane_ids:
            lane = lane_map.get(lane_id)
            if lane is None:
                # Lane referenced in graph but not yet projected — still open.
                report.open_lineages.append(lane_id)
                continue

            status = str(lane.get("status", "pending"))
            if status in _MERGED_STATUSES or self._has_merge_verdict(lane_id):
                report.merged_lineages.append(lane_id)
            elif status in _FAILED_STATUSES:
                report.terminated_without_merge.append(lane_id)
            else:
                report.open_lineages.append(lane_id)

        return report

    def assert_termination_safe(self, lane_id: str, graph_id: str) -> None:
        """Raise :class:`IncompleteLineageTerminationError` if termination is unsafe.

        A termination is considered unsafe when the graph still has sibling
        lineages that are either:

        - Still open (in-flight) — terminating now would strand them.
        - Already terminated without a merge verdict — the graph has an
          existing incomplete-termination signal that must be acknowledged
          before another termination is allowed.

        This guard is called by :meth:`ingest_verdict` before a
        ``TERMINATE`` verdict is persisted, preventing the review plane from
        allowing termination in an incomplete state.

        Args:
            lane_id: The lane whose termination is being requested.
            graph_id: The graph the lane belongs to.

        Raises:
            IncompleteLineageTerminationError: When the termination is unsafe.
        """
        report = self.check_lineage_merge_completeness(graph_id)

        # Exclude the lane being terminated from the sibling checks — it is
        # expected to be in-flight at this point.
        open_siblings = [lid for lid in report.open_lineages if lid != lane_id]
        unmerged_siblings = [lid for lid in report.terminated_without_merge if lid != lane_id]

        if open_siblings or unmerged_siblings:
            raise IncompleteLineageTerminationError(
                lane_id,
                graph_id,
                open_lineages=open_siblings,
                unmerged_lineages=unmerged_siblings,
            )

    def record_incomplete_termination(
        self,
        lane_id: str,
        graph_id: str,
        *,
        reason: str = "terminated_without_merge",
    ) -> ReviewVerdict:
        """Persist an incomplete-termination signal for *lane_id*.

        Called when a lane reaches a terminal failure state without a merge
        verdict.  The signal is stored as a synthetic ``TERMINATE`` verdict
        with ``status="incomplete_termination"`` so that:

        - :meth:`check_lineage_merge_completeness` can distinguish lanes that
          have been explicitly acknowledged from those that silently failed.
        - :meth:`assemble_evidence_bundle` picks it up as a negative signal
          ref, giving the next planning cycle a concrete reference to the gap.

        The verdict is idempotent: if an incomplete-termination verdict already
        exists for *lane_id* it is returned as-is without creating a duplicate.

        Args:
            lane_id: The lane that terminated without a merge verdict.
            graph_id: The graph the lane belongs to.
            reason: Human-readable reason for the incomplete termination.

        Returns:
            The persisted :class:`ReviewVerdict` for the incomplete termination.
        """
        # Idempotency: return existing incomplete-termination verdict if present.
        existing = [
            v
            for v in self._store.list_verdicts_for_lane(lane_id)
            if v.status == "incomplete_termination"
        ]
        if existing:
            return existing[-1]

        verdict_id = _new_id("incomplete-term")
        verdict = ReviewVerdict(
            id=verdict_id,
            lane_id=lane_id,
            decision=ReviewDecision.TERMINATE,
            status="incomplete_termination",
            summary=(
                f"Lane {lane_id!r} in graph {graph_id!r} reached a terminal state "
                f"without a merge verdict. Reason: {reason}. "
                f"Evidence bundle reference: evbundle_6259476d67dd414a8be293d1025ccb8c."
            ),
            terminate_reason=reason,
            created_at=_utc_now(),
        )
        self._store.save_verdict(verdict)
        logger.warning(
            "review_plane: incomplete termination recorded for lane %s in graph %s "
            "(reason=%s, verdict_id=%s)",
            lane_id,
            graph_id,
            reason,
            verdict_id,
        )
        return verdict

    def aggregate_run_terminal_status(
        self,
        graph_id: str,
        *,
        lane_graph: LaneGraph | None = None,
        final_action_store: FinalActionGateStore | None = None,
        clarification_store: ClarificationStore | None = None,
    ) -> RunTerminalAggregation:
        """Compute the run-level terminal status for *graph_id*.

        Delegates to :class:`RunTerminalAggregator` — the authoritative
        aggregation implementation for the blueprint-anchored self-evolution
        spec (evidence bundle evbundle_e72fecb39ee8439c8338891e9f4fd373).

        Inputs evaluated:

        - **Authoritative LaneGraph** (``lane_graph``): when provided, the
          canonical set of lanes for the run is seeded from
          ``LaneGraph.lanes`` rather than inferred from the ``graph_id``
          field on each lane.  This prevents phantom lanes from keeping a
          run open indefinitely.
        - **Normalized lane execution states**: the current ``status`` field
          for each lane in the state machine.
        - **Verdict lineage**: whether each lane has at least one finalized
          MERGE verdict in the verdict store.
        - **Patch-forward lineage**: ``source_lane_id`` transitive closure so
          that every descendant created through requeue, rework, or
          patch-forward is included.
        - **Final-action holds**: pending holds from ``FinalActionGateStore``
          that block run completion even when all lane lineages are closed.
          Falls back to the controller's own store when *final_action_store*
          is not provided.
        - **Clarification objects**: open ``ClarificationObject`` records from
          ``ClarificationStore`` that represent blocked-for-input states.
          Falls back to the controller's own store when *clarification_store*
          is not provided.

        Terminal outcomes:

        ``merged``
            Every lane lineage is closed cleanly; no holds or clarifications
            pending.

        ``terminated``
            Every lane lineage is closed; at least one via fail/stop
            semantics; no holds or clarifications pending.

        ``blocked_for_input``
            All lane lineages are closed, but at least one pending
            final-action hold or open clarification object remains
            unresolved.

        ``in_progress``
            At least one lane lineage is still open (not yet in a terminal
            state).
        """
        effective_final_action_store = final_action_store or self._final_action_store
        effective_clarification_store = clarification_store or self._clarification_store

        aggregator = RunTerminalAggregator(
            sm=self._sm,
            verdict_store=self._store,
            final_action_store=effective_final_action_store,
            clarification_store=effective_clarification_store,
        )
        return aggregator.compute(graph_id, lane_graph=lane_graph)

    def verdict_lineage_for_run(self, graph_id: str) -> list[dict[str, Any]]:
        """Return the full task→verdict lineage for every lane in *graph_id*.

        Reads the lane file to discover which lanes belong to the run, then
        returns the same task→verdict structure as
        :meth:`verdict_lineage_for_lane` for each lane.

        Lanes that have no review task are omitted.  The result is ordered by
        lane appearance in the graph (original lanes first, then any
        patch-forward or requeue descendants discovered through
        ``source_lane_id`` lineage).
        """
        all_lanes = self._sm.get_lanes()
        # Seed with lanes whose graph_id matches.
        graph_lane_ids: list[str] = [
            str(lane["feature_id"])
            for lane in all_lanes
            if isinstance(lane.get("feature_id"), str) and lane.get("graph_id") == graph_id
        ]
        # Expand to include source_lane_id descendants.
        seen: set[str] = set(graph_lane_ids)
        changed = True
        while changed:
            changed = False
            for lane in all_lanes:
                fid = lane.get("feature_id")
                src = lane.get("source_lane_id")
                if (
                    isinstance(fid, str)
                    and isinstance(src, str)
                    and src in seen
                    and fid not in seen
                ):
                    graph_lane_ids.append(fid)
                    seen.add(fid)
                    changed = True

        lineage: list[dict[str, Any]] = []
        for lane_id in graph_lane_ids:
            lane_lineage = self.verdict_lineage_for_lane(lane_id)
            lineage.extend(lane_lineage)
        return lineage

    # ------------------------------------------------------------------
    # Evidence bundle assembly
    # ------------------------------------------------------------------

    def _collect_bundle_lane_ids(
        self,
        graph_id: str,
        lane_graph: LaneGraph | None,
        all_lanes: list[dict[str, Any]],
    ) -> list[str]:
        """Collect run lane IDs using the same authority rules as aggregation."""
        if lane_graph is not None:
            seed_ids = [node.feature_id for node in lane_graph.lanes]
        else:
            seed_ids = [
                str(lane["feature_id"])
                for lane in all_lanes
                if isinstance(lane.get("feature_id"), str) and lane.get("graph_id") == graph_id
            ]

        collected: list[str] = []
        seen: set[str] = set()
        for lane_id in seed_ids:
            if lane_id not in seen:
                collected.append(lane_id)
                seen.add(lane_id)

        changed = True
        while changed:
            changed = False
            for lane in all_lanes:
                fid = lane.get("feature_id")
                src = lane.get("source_lane_id")
                if (
                    isinstance(fid, str)
                    and isinstance(src, str)
                    and src in seen
                    and fid not in seen
                ):
                    collected.append(fid)
                    seen.add(fid)
                    changed = True
        return collected

    @staticmethod
    def _append_unique_ref(refs: list[str], ref: str | None) -> None:
        """Append a non-empty string ref once, preserving first-seen order."""
        if ref and ref not in refs:
            refs.append(ref)

    @staticmethod
    def _append_primary_ref(
        primary_refs: list[dict[str, Any]],
        seen: set[str],
        ref: dict[str, Any],
    ) -> None:
        """Append a primary ref once using its normalized JSON shape."""
        key = json.dumps(ref, sort_keys=True, default=str)
        if key not in seen:
            primary_refs.append(ref)
            seen.add(key)

    @staticmethod
    def _looks_like_artifact_ref(value: str) -> bool:
        """Return True for strings that look like artifact paths or refs."""
        if not value or "\n" in value:
            return False
        suffixes = (
            ".json",
            ".md",
            ".txt",
            ".stdout",
            ".stderr",
            ".log",
            ".patch",
            ".diff",
        )
        prefixes = ("logs/", "xmuse/", "artifacts/", "reports/")
        return value.startswith(prefixes) or value.endswith(suffixes) or "/" in value

    def _collect_lane_artifact_refs(self, lane: dict[str, Any]) -> list[str]:
        """Collect explicit artifact refs from lane metadata."""
        refs: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, str):
                if self._looks_like_artifact_ref(value):
                    self._append_unique_ref(refs, value)
            elif isinstance(value, dict):
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, (list, tuple, set)):
                for nested in value:
                    visit(nested)

        for key in (
            "artifacts",
            "artifact_refs",
            "output_artifacts",
            "result_artifacts",
        ):
            if key in lane:
                visit(lane.get(key))

        for key, value in lane.items():
            if not isinstance(value, str):
                continue
            if key in {"worktree", "prompt", "failure_reason", "review_summary"}:
                continue
            if (
                key.endswith("_artifact")
                or key.endswith("_artifact_ref")
                or key.endswith("_artifact_path")
                or key in {"artifact_path", "result_path", "patch_path", "diff_path"}
            ) and self._looks_like_artifact_ref(value):
                self._append_unique_ref(refs, value)
        return refs

    def _resolve_bundle_ref_path(self, ref: str) -> Path | None:
        path = Path(ref)
        if path.is_absolute():
            return path if path.exists() else None
        candidate = self._lanes_path.parent / path
        return candidate if candidate.exists() else None

    def _collect_gate_report_artifacts(self, report_ref: str) -> list[str]:
        """Collect stdout/stderr artifacts referenced by a gate report."""
        path = self._resolve_bundle_ref_path(report_ref)
        if path is None:
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []

        refs: list[str] = []
        artifact_dir = payload.get("artifact_dir")
        if isinstance(artifact_dir, str) and self._looks_like_artifact_ref(artifact_dir):
            self._append_unique_ref(refs, artifact_dir)
        for result in payload.get("command_results", []):
            if not isinstance(result, dict):
                continue
            for key in ("stdout_path", "stderr_path"):
                value = result.get(key)
                if isinstance(value, str) and self._looks_like_artifact_ref(value):
                    self._append_unique_ref(refs, value)
        return refs

    def assemble_evidence_bundle(
        self,
        graph_id: str,
        *,
        lane_graph: LaneGraph | None = None,
        final_action_store: FinalActionGateStore | None = None,
        clarification_store: ClarificationStore | None = None,
        evidence_store: EvidenceBundleStore | None = None,
        selection_policy_id: str = "default-v1",
        selection_policy_version: str = "1",
    ) -> StructuredEvidenceBundle:
        """Assemble a StructuredEvidenceBundle from a terminal run.

        Collects the run terminal status, verdict lineage, gate report refs,
        patch-forward / requeue lineage refs, and negative signal refs.
        Every cited item is also recorded in ``primary_refs`` so the bundle
        satisfies the evidence curation contract from the spec.

        The bundle is persisted in *evidence_store* when provided.

        Args:
            graph_id: The lane graph ID of the terminal run.
            lane_graph: Optional authoritative :class:`LaneGraph`.  When
                provided its ``lanes`` list seeds the lane-ID collection so
                that the aggregation is not dependent on the ``graph_id``
                field being correctly stamped on every lane.
            final_action_store: Optional store used to check pending holds.
                Falls back to the controller's own store when not provided.
            clarification_store: Optional store used to check open
                clarification objects.  Falls back to the controller's own
                store when not provided.
            evidence_store: Optional store to persist the assembled bundle.
            selection_policy_id: Identifies the evidence selection policy.
            selection_policy_version: Version of the selection policy.

        Returns:
            The assembled :class:`StructuredEvidenceBundle`.
        """
        effective_final_action_store = final_action_store or self._final_action_store
        effective_clarification_store = clarification_store or self._clarification_store
        aggregation = self.aggregate_run_terminal_status(
            graph_id,
            lane_graph=lane_graph,
            final_action_store=effective_final_action_store,
            clarification_store=effective_clarification_store,
        )
        if aggregation.status is RunTerminalStatus.IN_PROGRESS:
            raise RuntimeError(f"source run is not terminal: {aggregation.status.value}")

        all_lanes = self._sm.get_lanes()
        graph_lane_ids = self._collect_bundle_lane_ids(graph_id, lane_graph, all_lanes)
        graph_lane_id_set = set(graph_lane_ids)
        lane_map: dict[str, dict[str, Any]] = {
            str(lane["feature_id"]): lane
            for lane in all_lanes
            if isinstance(lane.get("feature_id"), str)
        }

        # Collect verdict refs and gate report refs from the lineage.
        verdict_refs: list[str] = []
        gate_report_refs: list[str] = []
        lineage_refs: list[str] = []
        artifact_refs: list[str] = []
        signal_refs: list[str] = []
        primary_refs: list[dict[str, Any]] = []
        primary_seen: set[str] = set()
        verdict_decision_counts: dict[str, int] = {}
        processed_verdict_ids: set[str] = set()

        self._append_primary_ref(
            primary_refs,
            primary_seen,
            {
                "type": "run_terminal_aggregation",
                "ref": f"run_terminal_aggregation:{graph_id}",
                "lane_id": None,
                "graph_id": graph_id,
                "status": aggregation.status.value,
                "open_lane_lineages": aggregation.open_lane_lineages,
                "failed_lineages": aggregation.failed_lineages,
                "open_final_action_holds": aggregation.open_final_action_holds,
                "open_clarification_ids": aggregation.open_clarification_ids,
                "basis": aggregation.basis,
            },
        )
        self._append_primary_ref(
            primary_refs,
            primary_seen,
            {
                "type": "selection_policy",
                "lane_id": None,
                "graph_id": graph_id,
                "policy_id": selection_policy_id,
                "policy_version": selection_policy_version,
                "curation_contract": (
                    "cluster_by_evidence_class; summarize_counts_and_previews; "
                    "retain_full_primary_refs_for_all_cited_or_summarized_items"
                ),
            },
        )

        # Full primary lane references support the curation contract: the
        # summary can remain compact while dashboards and reviewers can still
        # reconstruct which lane states contributed to the bundle.
        for lane_id in graph_lane_ids:
            lane = lane_map.get(lane_id)
            if lane is None:
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "lane_status",
                        "lane_id": lane_id,
                        "graph_id": graph_id,
                        "status": "missing",
                    },
                )
                continue

            self._append_primary_ref(
                primary_refs,
                primary_seen,
                {
                    "type": "lane_status",
                    "lane_id": lane_id,
                    "graph_id": lane.get("graph_id") or graph_id,
                    "resolution_id": lane.get("resolution_id"),
                    "status": str(lane.get("status", "")),
                    "source_lane_id": lane.get("source_lane_id"),
                    "failure_reason": lane.get("failure_reason"),
                },
            )

            for artifact_ref in self._collect_lane_artifact_refs(lane):
                self._append_unique_ref(artifact_refs, artifact_ref)
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "artifact",
                        "lane_id": lane_id,
                        "graph_id": lane.get("graph_id") or graph_id,
                        "ref": artifact_ref,
                        "source": "lane_metadata",
                    },
                )

            for key in ("gate_report_ref", "gate_report_path", "gate_report"):
                value = lane.get(key)
                if not isinstance(value, str) or not value:
                    continue
                self._append_unique_ref(gate_report_refs, value)
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "gate_report",
                        "lane_id": lane_id,
                        "graph_id": lane.get("graph_id") or graph_id,
                        "ref": value,
                        "source": "lane_metadata",
                    },
                )
                for artifact_ref in self._collect_gate_report_artifacts(value):
                    self._append_unique_ref(artifact_refs, artifact_ref)
                    self._append_primary_ref(
                        primary_refs,
                        primary_seen,
                        {
                            "type": "artifact",
                            "lane_id": lane_id,
                            "graph_id": lane.get("graph_id") or graph_id,
                            "ref": artifact_ref,
                            "source": "gate_report",
                            "gate_report_ref": value,
                        },
                    )

        lineage: list[dict[str, Any]] = []
        for lane_id in graph_lane_ids:
            lineage.extend(self.verdict_lineage_for_lane(lane_id))

        for entry in lineage:
            task = entry.get("task")
            verdict = entry.get("verdict")
            if task:
                lane_id = str(task.get("lane_id", ""))
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "review_task",
                        "id": task["task_id"],
                        "lane_id": lane_id,
                        "graph_id": task.get("graph_id") or graph_id,
                        "resolution_id": task.get("resolution_id"),
                        "status": task.get("status"),
                        "verdict_id": task.get("verdict_id"),
                        "gate_report_ref": task.get("gate_report_ref"),
                    },
                )
                if task.get("gate_report_ref"):
                    gate_report_ref = str(task["gate_report_ref"])
                    self._append_unique_ref(gate_report_refs, gate_report_ref)
                    self._append_primary_ref(
                        primary_refs,
                        primary_seen,
                        {
                            "type": "gate_report",
                            "lane_id": lane_id,
                            "graph_id": task.get("graph_id") or graph_id,
                            "ref": gate_report_ref,
                            "task_id": task.get("task_id"),
                        },
                    )
                    for artifact_ref in self._collect_gate_report_artifacts(gate_report_ref):
                        self._append_unique_ref(artifact_refs, artifact_ref)
                        self._append_primary_ref(
                            primary_refs,
                            primary_seen,
                            {
                                "type": "artifact",
                                "lane_id": lane_id,
                                "graph_id": task.get("graph_id") or graph_id,
                                "ref": artifact_ref,
                                "source": "gate_report",
                                "gate_report_ref": gate_report_ref,
                            },
                        )
            if verdict:
                verdict_id = str(verdict["id"])
                decision = str(verdict["decision"])
                self._append_unique_ref(verdict_refs, verdict_id)
                processed_verdict_ids.add(verdict_id)
                verdict_decision_counts[decision] = verdict_decision_counts.get(decision, 0) + 1
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "review_verdict",
                        "ref": verdict_id,
                        "id": verdict_id,
                        "lane_id": verdict["lane_id"],
                        "graph_id": graph_id,
                        "decision": decision,
                        "status": verdict.get("status"),
                        "summary": verdict["summary"],
                        "task_id": verdict.get("task_id"),
                        "evidence_refs": verdict.get("evidence_refs", []),
                    },
                )
                for evidence_ref in verdict.get("evidence_refs", []) or []:
                    if isinstance(evidence_ref, str) and self._looks_like_artifact_ref(
                        evidence_ref
                    ):
                        self._append_unique_ref(artifact_refs, evidence_ref)
                        self._append_primary_ref(
                            primary_refs,
                            primary_seen,
                            {
                                "type": "artifact",
                                "lane_id": verdict["lane_id"],
                                "graph_id": graph_id,
                                "ref": evidence_ref,
                                "source": "review_verdict",
                                "verdict_id": verdict_id,
                            },
                        )

        # Include finalized verdicts that exist in the store even if the
        # corresponding ReviewTask lineage is unavailable.  Normal task→verdict
        # lineage remains the preferred path, but preserving orphan verdicts
        # keeps the bundle audit-complete for manually repaired stores.
        for lane_id in graph_lane_ids:
            for verdict in self._store.list_verdicts_for_lane(lane_id):
                if verdict.id in processed_verdict_ids:
                    continue
                verdict_id = verdict.id
                decision = str(verdict.decision)
                self._append_unique_ref(verdict_refs, verdict_id)
                processed_verdict_ids.add(verdict_id)
                verdict_decision_counts[decision] = verdict_decision_counts.get(decision, 0) + 1
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "review_verdict",
                        "ref": verdict_id,
                        "id": verdict_id,
                        "lane_id": verdict.lane_id,
                        "graph_id": graph_id,
                        "decision": decision,
                        "status": verdict.status,
                        "summary": verdict.summary,
                        "task_id": verdict.task_id,
                        "evidence_refs": verdict.evidence_refs,
                    },
                )
                for evidence_ref in verdict.evidence_refs:
                    if isinstance(evidence_ref, str) and self._looks_like_artifact_ref(
                        evidence_ref
                    ):
                        self._append_unique_ref(artifact_refs, evidence_ref)
                        self._append_primary_ref(
                            primary_refs,
                            primary_seen,
                            {
                                "type": "artifact",
                                "lane_id": verdict.lane_id,
                                "graph_id": graph_id,
                                "ref": evidence_ref,
                                "source": "review_verdict",
                                "verdict_id": verdict_id,
                            },
                        )

        # Collect lineage refs (patch-forward / requeue descendants).
        for lane in all_lanes:
            fid = lane.get("feature_id")
            src = lane.get("source_lane_id")
            if (
                isinstance(fid, str)
                and isinstance(src, str)
                and fid in graph_lane_id_set
                and src in graph_lane_id_set
            ):
                ref = f"lane:{fid}:source:{src}"
                self._append_unique_ref(lineage_refs, ref)
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "lane_lineage",
                        "ref": ref,
                        "lane_id": fid,
                        "graph_id": lane.get("graph_id") or graph_id,
                        "source_lane_id": src,
                        "status": str(lane.get("status", "")),
                        "failure_reason": lane.get("failure_reason"),
                    },
                )

        # Collect negative signal refs for failed lineages.
        # For each failed lineage that never received a merge verdict, record
        # an incomplete-termination signal (evbundle_6259476d67dd414a8be293d1025ccb8c)
        # so the next planning cycle has a concrete reference to the gap.
        for lane_id in aggregation.failed_lineages:
            lane = lane_map.get(lane_id)
            if lane:
                failure_reason = lane.get("failure_reason") or "unknown"
                ref = f"negative:lane:{lane_id}:{failure_reason}"
                self._append_unique_ref(signal_refs, ref)
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "negative_signal",
                        "ref": ref,
                        "lane_id": lane_id,
                        "graph_id": lane.get("graph_id") or graph_id,
                        "failure_reason": failure_reason,
                        "status": str(lane.get("status", "")),
                    },
                )

                # Merge guard: persist an incomplete-termination verdict for
                # any failed lineage that never received a merge verdict.
                # This is idempotent — duplicate calls return the existing verdict.
                if not self._has_merge_verdict(lane_id):
                    try:
                        incomplete_verdict = self.record_incomplete_termination(
                            lane_id,
                            graph_id,
                            reason=failure_reason,
                        )
                        if incomplete_verdict.id not in processed_verdict_ids:
                            verdict_id = incomplete_verdict.id
                            decision = str(incomplete_verdict.decision)
                            self._append_unique_ref(verdict_refs, verdict_id)
                            processed_verdict_ids.add(verdict_id)
                            verdict_decision_counts[decision] = (
                                verdict_decision_counts.get(decision, 0) + 1
                            )
                            self._append_primary_ref(
                                primary_refs,
                                primary_seen,
                                {
                                    "type": "review_verdict",
                                    "ref": verdict_id,
                                    "id": verdict_id,
                                    "lane_id": incomplete_verdict.lane_id,
                                    "graph_id": graph_id,
                                    "decision": decision,
                                    "status": incomplete_verdict.status,
                                    "summary": incomplete_verdict.summary,
                                    "task_id": incomplete_verdict.task_id,
                                    "evidence_refs": incomplete_verdict.evidence_refs,
                                },
                            )
                        incomplete_ref = (
                            f"incomplete_termination:lane:{lane_id}:{incomplete_verdict.id}"
                        )
                        self._append_unique_ref(signal_refs, incomplete_ref)
                        self._append_primary_ref(
                            primary_refs,
                            primary_seen,
                            {
                                "type": "incomplete_termination",
                                "ref": incomplete_ref,
                                "lane_id": lane_id,
                                "graph_id": lane.get("graph_id") or graph_id,
                                "verdict_id": incomplete_verdict.id,
                                "failure_reason": failure_reason,
                                "evidence_bundle_ref": "evbundle_6259476d67dd414a8be293d1025ccb8c",
                            },
                        )
                    except Exception:
                        logger.warning(
                            "review_plane: failed to record incomplete termination "
                            "for lane %s in graph %s",
                            lane_id,
                            graph_id,
                        )

        if effective_final_action_store is not None and aggregation.open_final_action_holds:
            hold_ids = set(aggregation.open_final_action_holds)
            for hold in effective_final_action_store.list_actions():
                if hold.id not in hold_ids:
                    continue
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "final_action_hold",
                        "id": hold.id,
                        "lane_id": hold.lane_id,
                        "graph_id": graph_id,
                        "verdict_id": hold.verdict_id,
                        "action": hold.action,
                        "target_status": hold.target_status,
                        "status": hold.status,
                        "summary": hold.summary,
                    },
                )

        if effective_clarification_store is not None and aggregation.open_clarification_ids:
            clarification_ids = set(aggregation.open_clarification_ids)
            for clarification in effective_clarification_store.list_all():
                if clarification.clarification_id not in clarification_ids:
                    continue
                self._append_primary_ref(
                    primary_refs,
                    primary_seen,
                    {
                        "type": "clarification",
                        "id": clarification.clarification_id,
                        "lane_id": clarification.lane_id,
                        "graph_id": clarification.graph_id or graph_id,
                        "resolution_id": clarification.resolution_id,
                        "status": clarification.status,
                        "question": clarification.question,
                        "context": clarification.context,
                    },
                )

        # Derive source_resolution_id from the first graph lane that has one.
        source_resolution_id: str | None = lane_graph.resolution_id if lane_graph else None
        for lane in all_lanes:
            if (
                not source_resolution_id
                and lane.get("feature_id") in graph_lane_id_set
                and lane.get("resolution_id")
            ):
                source_resolution_id = str(lane["resolution_id"])
                break

        # Build a curated summary.  The summary is intentionally clustered by
        # evidence class for planner efficiency; primary_refs retains the full
        # lane-scoped source references for every cited class.
        total = len(graph_lane_ids)
        status_value = aggregation.status.value
        decision_summary = (
            ", ".join(
                f"{decision}={count}" for decision, count in sorted(verdict_decision_counts.items())
            )
            or "none"
        )
        failed_preview = ", ".join(aggregation.failed_lineages[:5]) or "none"
        if len(aggregation.failed_lineages) > 5:
            failed_preview += f", +{len(aggregation.failed_lineages) - 5} more"
        open_preview = ", ".join(aggregation.open_lane_lineages[:5]) or "none"
        if len(aggregation.open_lane_lineages) > 5:
            open_preview += f", +{len(aggregation.open_lane_lineages) - 5} more"
        summary = (
            f"Run {graph_id} reached terminal status '{status_value}'. "
            f"Total lane lineages: {total}. "
            f"Open: {len(aggregation.open_lane_lineages)}. "
            f"Failed: {len(aggregation.failed_lineages)}. "
            f"Open holds: {len(aggregation.open_final_action_holds)}. "
            f"Open clarifications: {len(aggregation.open_clarification_ids)}. "
            f"Verdicts: {len(verdict_refs)}. "
            f"Gate reports: {len(gate_report_refs)}. "
            f"Artifacts: {len(artifact_refs)}. "
            f"Signals: {len(signal_refs)}. "
            f"Verdict decisions: {decision_summary}. "
            f"Failed lineages: {failed_preview}. "
            f"Open lineages: {open_preview}."
        )

        bundle = StructuredEvidenceBundle(
            bundle_id=_new_id("evbundle"),
            source_run_id=graph_id,
            source_resolution_id=source_resolution_id,
            selection_policy_id=selection_policy_id,
            selection_policy_version=selection_policy_version,
            summary=summary,
            run_terminal_status=aggregation.status,
            verdict_refs=verdict_refs,
            gate_report_refs=gate_report_refs,
            lineage_refs=lineage_refs,
            artifact_refs=artifact_refs,
            signal_refs=signal_refs,
            primary_refs=primary_refs,
            created_at=_utc_now(),
        )

        if evidence_store is not None:
            evidence_store.save(bundle)

        return bundle
