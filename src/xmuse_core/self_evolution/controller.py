from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from xmuse_core.chat.store import ChatStore
from xmuse_core.platform.state_normalizer import normalize_lane_state, summarize_lane_states
from xmuse_core.self_evolution.adapters import ChatReader, LanesReader
from xmuse_core.self_evolution.models import (
    ClarificationRequest,
    ClarificationResolution,
    ClarificationStatus,
    EvolutionBudgetStatus,
    EvolutionBudgetWindow,
    EvolutionConversation,
    EvolutionDedupRecord,
    EvolutionDedupStatus,
    EvolutionGuardrailAction,
    EvolutionGuardrailDecision,
    EvolutionLineageRecord,
    EvolutionProposal,
    EvolutionProposalStatus,
    EvolutionReviewDecision,
    EvolutionReviewKind,
    NarrowingDecision,
    RunTerminalAggregation,
    RunTerminalStatus,
    StructuredEvidenceBundle,
)
from xmuse_core.self_evolution.store import SelfEvolutionStore
from xmuse_core.structuring.graph_store import LaneGraphStore
from xmuse_core.structuring.planner import build_lane_graph
from xmuse_core.structuring.projection import project_ready_lanes
from xmuse_core.structuring.verdict_store import VerdictStore

if TYPE_CHECKING:
    from xmuse_core.self_evolution.decomposer import TrackDecomposer

_DEFAULT_SELECTION_POLICY_ID = "xmuse-self-evolution-bootstrap"
_DEFAULT_SELECTION_POLICY_VERSION = "21"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _stable_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SelfEvolutionController:
    def __init__(
        self,
        *,
        xmuse_root: Path | str,
        blueprint_path: Path | str,
        store_root: Path | str | None = None,
        lanes_path: Path | str | None = None,
        chat_db_path: Path | str | None = None,
        lanes_reader: LanesReader | None = None,
        chat_reader: ChatReader | None = None,
        decomposer: TrackDecomposer | None = None,
        verdict_store_path: Path | str | None = None,
    ) -> None:
        self._root = Path(xmuse_root)
        self._blueprint_path = Path(blueprint_path)
        self._lanes_path = (
            Path(lanes_path) if lanes_path is not None else self._root / "feature_lanes.json"
        )
        self._store = SelfEvolutionStore(store_root or self._root / "self_evolution")
        _chat_db_path = Path(chat_db_path) if chat_db_path is not None else self._root / "chat.db"
        self._lanes_reader = lanes_reader or LanesReader(self._lanes_path)
        self._chat_reader = chat_reader or ChatReader(_chat_db_path)
        self._chat = ChatStore(_chat_db_path)
        self._graph_store = LaneGraphStore(self._root / "lane_graphs")
        # Resolve the verdict store path.  When an explicit path is given, use
        # it.  Otherwise fall back to the canonical review_plane.json location
        # inside the xmuse root so that run terminal aggregation automatically
        # reads from the authoritative ReviewPlaneController store without
        # requiring explicit wiring at every call site.
        _resolved_verdict_path: Path | None
        if verdict_store_path is not None:
            _resolved_verdict_path = Path(verdict_store_path)
        else:
            _default = self._root / "review_plane.json"
            _resolved_verdict_path = _default if _default.exists() else None
        self._verdict_store: VerdictStore | None = (
            VerdictStore(_resolved_verdict_path) if _resolved_verdict_path is not None else None
        )
        if decomposer is None:
            from xmuse_core.self_evolution.decomposer import SingleLaneDecomposer

            decomposer = SingleLaneDecomposer(
                lane_id_factory=self._candidate_lane_id_for_track,
                prompt_factory=self._candidate_prompt_for_track,
            )
        self._decomposer = decomposer

    @property
    def store(self) -> SelfEvolutionStore:
        return self._store

    def aggregate_run_terminal(self, graph_id: str) -> RunTerminalAggregation:
        graph = self._graph_store.get(graph_id)
        lanes = self._read_lanes()
        lane_by_id = {
            str(lane.get("feature_id")): lane
            for lane in lanes
            if isinstance(lane, dict) and lane.get("feature_id")
        }
        graph_lane_ids = [node.feature_id for node in graph.lanes]
        lineage_lane_ids = self._lineage_lane_ids(graph.id, graph_lane_ids)
        lane_statuses: list[dict[str, Any]] = []
        blocked_objects: list[dict[str, Any]] = []

        for lane_id in lineage_lane_ids:
            lane = lane_by_id.get(lane_id)
            if lane is None:
                lane_statuses.append(
                    {
                        "feature_id": lane_id,
                        "raw_status": "unprojected",
                        "normalized_status": "waiting_dependency",
                        "terminal": False,
                    }
                )
                continue
            normalized = normalize_lane_state(lane)
            lane_status = {
                "feature_id": lane_id,
                "raw_status": normalized.raw_status,
                "normalized_status": normalized.normalized_status,
                "terminal": normalized.is_terminal,
            }
            if lane.get("review_decision"):
                lane_status["review_decision"] = str(lane["review_decision"])
            if lane.get("review_verdict_id"):
                lane_status["review_verdict_id"] = str(lane["review_verdict_id"])
            lane_statuses.append(lane_status)
            blocked = self._blocked_object_for_lane(lane)
            if blocked is not None and not normalized.is_terminal:
                blocked_objects.append(blocked)

        present_lineage_lanes = [
            lane_by_id[lane_id] for lane_id in lineage_lane_ids if lane_id in lane_by_id
        ]
        lane_counts = summarize_lane_states(present_lineage_lanes)
        final_action_holds: list[dict[str, Any]] = []
        for lane_id in lineage_lane_ids:
            lane = lane_by_id.get(lane_id)
            if lane is None:
                continue
            hold = self._final_action_hold_for_lane(lane)
            if hold is not None:
                final_action_holds.append(hold)
        verdict_lineage = self._build_verdict_lineage(lineage_lane_ids, lane_by_id)
        status, reason = self._aggregate_status(
            lane_statuses,
            blocked_objects,
            final_action_holds,
            verdict_lineage=verdict_lineage,
        )
        aggregation = RunTerminalAggregation(
            aggregation_id=_new_id("runagg"),
            run_id=graph.id,
            resolution_id=graph.resolution_id,
            graph_id=graph.id,
            status=status,
            terminal=status is not RunTerminalStatus.RUNNING,
            reason=reason,
            lane_counts=lane_counts,
            lane_statuses=lane_statuses,
            open_lineages=self._open_lineages(lane_by_id),
            blocked_objects=blocked_objects,
            final_action_holds=final_action_holds,
            verdict_lineage=verdict_lineage,
            created_at=_utc_now(),
        )
        return self._store.save_aggregation(aggregation)

    def build_evidence_bundle(
        self,
        aggregation: RunTerminalAggregation,
        *,
        selection_policy_id: str = _DEFAULT_SELECTION_POLICY_ID,
        selection_policy_version: str = _DEFAULT_SELECTION_POLICY_VERSION,
    ) -> StructuredEvidenceBundle:
        lanes = self._read_lanes()
        relevant_lanes = self._relevant_lanes_for_aggregation(lanes, aggregation)
        verdict_refs = [
            str(lane["review_verdict_id"])
            for lane in relevant_lanes
            if lane.get("review_verdict_id")
        ]
        lineage_refs = [
            f"lane:{lane['source_lane_id']}->{lane['feature_id']}"
            for lane in relevant_lanes
            if lane.get("source_lane_id") and lane.get("feature_id")
        ]
        gate_report_refs = self._gate_report_refs(relevant_lanes)
        primary_refs = [
            self._relative_ref(self._lanes_path),
            f"lane_graphs/{aggregation.graph_id}.json",
            self._relative_ref(self._blueprint_path),
        ]
        lane_signal_refs = self._lane_signal_refs(relevant_lanes, aggregation)
        signal_refs = [
            self._lane_counts_ref(aggregation),
            *lane_signal_refs,
            *self._gate_report_signal_refs(gate_report_refs),
            *self._gate_report_resolution_signal_refs(gate_report_refs),
            *self._gate_report_diagnostic_signal_refs(gate_report_refs),
            *self._gate_report_result_signal_refs(gate_report_refs),
        ]
        bundle = StructuredEvidenceBundle(
            bundle_id=_new_id("evbundle"),
            source_run_id=aggregation.run_id,
            source_resolution_id=aggregation.resolution_id,
            selection_policy_id=selection_policy_id,
            selection_policy_version=selection_policy_version,
            summary=self._evidence_summary(aggregation, signal_refs),
            run_terminal_status=aggregation.status,
            verdict_refs=verdict_refs,
            gate_report_refs=gate_report_refs,
            lineage_refs=lineage_refs,
            artifact_refs=primary_refs,
            signal_refs=signal_refs,
            primary_refs=primary_refs,
            created_at=_utc_now(),
        )
        return self._store.save_evidence_bundle(bundle)

    def draft_evolution_proposal(
        self,
        evidence: StructuredEvidenceBundle,
        *,
        author_session_id: str = "god-session-architect",
    ) -> EvolutionProposal:
        blueprint = self._read_blueprint()
        blueprint_set_id = self._extract_blueprint_field(blueprint, "blueprint_set_id") or (
            "xmuse-self-evolution-v0"
        )
        target_tracks = self._select_target_tracks(evidence, blueprint)
        primary_track = target_tracks[0] if target_tracks else "graph_authority"
        candidate_lanes = self._decomposer.decompose(primary_track, evidence)
        if not candidate_lanes:
            candidate_lanes = [
                {
                    "feature_id": self._candidate_lane_id(evidence, target_tracks),
                    "title": "Bootstrap the next xmuse self-evolution improvement",
                    "prompt": self._candidate_prompt(evidence, target_tracks),
                    "priority": 100,
                    "capabilities": ["code", "test"],
                    "depends_on": [],
                    "task_type": "execute",
                    "gate_profiles": ["xmuse-core"],
                    "feature_group": primary_track,
                }
            ]
        proposal = EvolutionProposal(
            proposal_id=_new_id("evprop"),
            source_run_id=evidence.source_run_id,
            blueprint_set_id=blueprint_set_id,
            target_track_ids=target_tracks,
            status=EvolutionProposalStatus.AWAITING_REVIEW,
            draft_version=1,
            author_session_id=author_session_id,
            scope_summary=self._compose_scope_summary(target_tracks),
            why_now=evidence.summary,
            evidence_bundle_id=evidence.bundle_id,
            candidate_graph={
                "lanes": candidate_lanes,
                "self_evolution": {
                    "source_run_id": evidence.source_run_id,
                    "evidence_bundle_id": evidence.bundle_id,
                    "blueprint_set_id": blueprint_set_id,
                    "target_track_ids": target_tracks,
                },
            },
            review_status="awaiting_review",
            created_at=_utc_now(),
        )
        return self._store.save_proposal(proposal)

    def review_proposal(
        self,
        proposal: EvolutionProposal,
        *,
        review_session_id: str = "god-session-review",
    ) -> EvolutionReviewDecision:
        lanes = proposal.candidate_graph.get("lanes")
        if not isinstance(lanes, list) or not lanes:
            decision = EvolutionReviewKind.REJECT
            rationale = "candidate graph has no executable lanes"
        elif not proposal.target_track_ids:
            decision = EvolutionReviewKind.REJECT
            rationale = "proposal targets no blueprint track"
        elif any(not isinstance(lane, dict) or not lane.get("feature_id") for lane in lanes):
            decision = EvolutionReviewKind.NARROW
            rationale = "candidate graph contains lanes without stable feature_id"
        else:
            decision = EvolutionReviewKind.APPROVE
            rationale = "candidate graph is scoped to the active blueprint and enters through lanes"

        review = EvolutionReviewDecision(
            decision_id=_new_id("evreview"),
            proposal_id=proposal.proposal_id,
            review_session_id=review_session_id,
            decision=decision,
            rationale=rationale,
            narrowing_decision=(
                NarrowingDecision(
                    decision_id=_new_id("narrow"),
                    proposal_id=proposal.proposal_id,
                    source_review_session_id=review_session_id,
                    source_draft_version=proposal.draft_version,
                    target_draft_version=proposal.draft_version + 1,
                    scope_constraints=["retain blueprint target and reduce invalid lane scope"],
                    required_graph_changes=["assign stable feature_id to every candidate lane"],
                    required_evidence_focus=[proposal.evidence_bundle_id],
                    rationale=rationale,
                    created_at=_utc_now(),
                )
                if decision is EvolutionReviewKind.NARROW
                else None
            ),
            created_at=_utc_now(),
        )
        self._store.save_review_decision(review)

        proposal.review_status = decision.value
        proposal.status = (
            EvolutionProposalStatus.APPROVED
            if decision is EvolutionReviewKind.APPROVE
            else EvolutionProposalStatus.REJECTED
            if decision is EvolutionReviewKind.REJECT
            else EvolutionProposalStatus.NARROWED_FOR_REDRAFT
        )
        self._store.save_proposal(proposal)
        return review

    def guardrail_check(
        self,
        proposal: EvolutionProposal,
        review: EvolutionReviewDecision,
        aggregation: RunTerminalAggregation,
    ) -> EvolutionGuardrailDecision:
        lanes = proposal.candidate_graph.get("lanes")
        base_checks = {
            "source_run_terminal": aggregation.terminal,
            "review_approved": review.decision is EvolutionReviewKind.APPROVE,
            "mission_envelope": proposal.blueprint_set_id.startswith("xmuse-self-evolution"),
            "candidate_lanes_serializable": isinstance(lanes, list) and bool(lanes),
            "target_tracks_present": bool(proposal.target_track_ids),
        }
        budget_window: EvolutionBudgetWindow | None = None
        budget_ok = True
        dedupe_ok = True
        dedup_key: str | None = None

        if all(base_checks.values()):
            now = _utc_now()
            budget_window, budget_ok = self._budget_window_for(proposal.source_run_id, now)
            dedup_key = self._dedup_identity(proposal)[0]
            dedupe_ok = not self._has_duplicate_evolution(proposal, dedup_key)

        checks = {
            **base_checks,
            "budget_window_active": budget_ok,
            "dedupe_clear": dedupe_ok,
        }
        reason_codes = [name for name, passed in checks.items() if not passed]
        action = (
            EvolutionGuardrailAction.CONTINUE
            if all(checks.values())
            else EvolutionGuardrailAction.HOLD
        )
        decision = EvolutionGuardrailDecision(
            decision_id=_new_id("evguard"),
            proposal_id=proposal.proposal_id,
            action=action,
            rationale=(
                "all bootstrap guardrails passed"
                if action is EvolutionGuardrailAction.CONTINUE
                else f"one or more bootstrap guardrails failed: {', '.join(reason_codes)}"
            ),
            source_run_id=proposal.source_run_id,
            reason_codes=reason_codes,
            budget_window_id=budget_window.window_id if budget_window is not None else None,
            dedup_key=dedup_key,
            terminal_aggregation_ref=aggregation.aggregation_id,
            checks=checks,
            created_at=_utc_now(),
        )
        self._store.save_guardrail_decision(decision)
        if action is not EvolutionGuardrailAction.CONTINUE:
            proposal.status = EvolutionProposalStatus.GUARDRAIL_BLOCKED
            self._store.save_proposal(proposal)
        return decision

    def land_evolution_run(
        self,
        proposal: EvolutionProposal,
        review: EvolutionReviewDecision,
        guardrail: EvolutionGuardrailDecision,
        evidence: StructuredEvidenceBundle,
    ) -> EvolutionLineageRecord:
        if guardrail.action is not EvolutionGuardrailAction.CONTINUE:
            raise RuntimeError("cannot land self-evolution proposal without continue guardrail")

        conversation = self._chat.create_conversation(
            title=f"xmuse self-evolution: {','.join(proposal.target_track_ids)}"
        )
        self._chat.add_message(
            conversation_id=conversation.id,
            author="evolution-controller",
            role="system",
            content=(
                "System-authored self-evolution run opened from "
                f"{evidence.source_run_id} using blueprint {proposal.blueprint_set_id}."
            ),
        )
        chat_proposal = self._chat.create_proposal(
            conversation_id=conversation.id,
            author=proposal.author_session_id,
            proposal_type="self-evolution-lane-plan",
            content=proposal.scope_summary,
            references=evidence.primary_refs,
        )
        resolution = self._chat.approve_proposal(
            proposal_id=chat_proposal.id,
            approved_by=[review.review_session_id],
            approval_mode="god-review",
            goal_summary=proposal.scope_summary,
            content=proposal.candidate_graph,
        )
        graph = build_lane_graph(resolution)
        self._graph_store.save(graph)
        project_ready_lanes(graph, self._lanes_path)
        self._record_landed_guardrail_side_effects(
            proposal,
            guardrail,
            spawned_run_id=graph.id,
        )

        proposal.status = EvolutionProposalStatus.LANDED
        proposal.spawned_conversation_id = conversation.id
        proposal.spawned_resolution_id = resolution.id
        self._store.save_proposal(proposal)
        self._store.save_conversation(
            EvolutionConversation(
                conversation_id=conversation.id,
                proposal_id=proposal.proposal_id,
                source_run_id=proposal.source_run_id,
                created_by="evolution-controller",
                created_at=_utc_now(),
            )
        )
        lineage = EvolutionLineageRecord(
            lineage_id=_new_id("evlineage"),
            source_run_id=proposal.source_run_id,
            source_resolution_id=evidence.source_resolution_id,
            evidence_bundle_id=evidence.bundle_id,
            evolution_proposal_id=proposal.proposal_id,
            review_decision_id=review.decision_id,
            guardrail_decision_id=guardrail.decision_id,
            spawned_conversation_id=conversation.id,
            spawned_proposal_id=chat_proposal.id,
            spawned_resolution_id=resolution.id,
            spawned_graph_id=graph.id,
            blueprint_set_id=proposal.blueprint_set_id,
            target_track_ids=list(proposal.target_track_ids),
            terminal_aggregation_ref=guardrail.terminal_aggregation_ref,
            created_at=_utc_now(),
        )
        return self._store.save_lineage(lineage)

    def dry_run_from_graph(self, graph_id: str) -> EvolutionLineageRecord:
        aggregation = self.aggregate_run_terminal(graph_id)
        if not aggregation.terminal:
            raise RuntimeError(f"source run is not terminal: {aggregation.status.value}")
        evidence = self.build_evidence_bundle(aggregation)
        proposal = self.draft_evolution_proposal(evidence)
        review = self.review_proposal(proposal)
        guardrail = self.guardrail_check(proposal, review, aggregation)
        return self.land_evolution_run(proposal, review, guardrail, evidence)

    def run_from_evidence_bundle(self, bundle_id: str) -> EvolutionLineageRecord:
        evidence = self._get_evidence_bundle(bundle_id)
        aggregation = self._aggregation_for_evidence(evidence)
        if not aggregation.terminal:
            raise RuntimeError(f"source run is not terminal: {aggregation.status.value}")
        evidence = self._hydrate_evidence_bundle(evidence, aggregation)
        proposal = self.draft_evolution_proposal(evidence)
        review = self.review_proposal(proposal)
        guardrail = self.guardrail_check(proposal, review, aggregation)
        return self.land_evolution_run(proposal, review, guardrail, evidence)

    def record_clarification_request(
        self,
        aggregation: RunTerminalAggregation,
    ) -> ClarificationRequest:
        """Persist a ClarificationRequest for a blocked_for_input run.

        This converts the loose blocked_objects from the aggregation into a
        formal, resumable ClarificationRequest object.  The request stays open
        until ``resolve_clarification`` is called with the provided information.
        """
        if aggregation.status is not RunTerminalStatus.BLOCKED_FOR_INPUT:
            raise ValueError(
                f"cannot record clarification request for non-blocked run: "
                f"{aggregation.status.value}"
            )
        blocked = aggregation.blocked_objects
        missing_parts = [
            str(obj.get("missing_input", "unspecified"))
            for obj in blocked
            if isinstance(obj, dict)
        ]
        missing_summary = "; ".join(missing_parts) if missing_parts else "unspecified"
        owner = "human"
        for obj in blocked:
            if isinstance(obj, dict) and obj.get("owner"):
                owner = str(obj["owner"])
                break
        resume_parts = [
            str(obj.get("resume_path", "provide information and resume graph"))
            for obj in blocked
            if isinstance(obj, dict) and obj.get("resume_path")
        ]
        resume_path = (
            resume_parts[0]
            if resume_parts
            else "provide information and reproject graph"
        )
        request = ClarificationRequest(
            request_id=_new_id("clarreq"),
            source_run_id=aggregation.run_id,
            aggregation_id=aggregation.aggregation_id,
            blocked_objects=list(blocked),
            missing_input_summary=missing_summary,
            owner=owner,
            resume_path=resume_path,
            status=ClarificationStatus.OPEN,
            created_at=_utc_now(),
        )
        return self._store.save_clarification_request(request)

    def expire_clarification(
        self,
        request: ClarificationRequest,
        *,
        reason: str = "no response received within the expected window",
    ) -> ClarificationRequest:
        """Mark an open ClarificationRequest as expired.

        An expired request means the system gave up waiting for the missing
        information.  The run remains blocked; a new clarification request can
        be opened if the information later becomes available.

        Raises ``ValueError`` if the request is not currently open.
        """
        if request.status is not ClarificationStatus.OPEN:
            raise ValueError(
                f"cannot expire clarification request with status: {request.status.value}"
            )
        request.status = ClarificationStatus.EXPIRED
        request.resolved_at = _utc_now()
        return self._store.save_clarification_request(request)

    def resolve_clarification(
        self,
        request: ClarificationRequest,
        provided_information: str,
        *,
        provided_by: str = "human",
        provided_context: dict[str, Any] | None = None,
    ) -> ClarificationResolution:
        """Accept provided information and spawn a follow-up resolution.

        The follow-up resolution re-enters the standard mainline:
        chat -> proposal -> approved resolution -> lane graph -> execution.

        The spawned graph carries the original blocked lane context plus the
        provided information so the next execution attempt has full context.
        """
        if request.status is not ClarificationStatus.OPEN:
            raise ValueError(
                f"cannot resolve clarification request with status: {request.status.value}"
            )
        now = _utc_now()
        resolution = ClarificationResolution(
            resolution_id=_new_id("clarres"),
            request_id=request.request_id,
            source_run_id=request.source_run_id,
            provided_information=provided_information,
            provided_context=provided_context or {},
            provided_by=provided_by,
            created_at=now,
        )
        # Build a follow-up candidate graph that resumes the blocked run
        candidate_lanes = self._clarification_resume_lanes(request, resolution)
        conversation = self._chat.create_conversation(
            title=f"xmuse clarification-recovery: {request.source_run_id}"
        )
        self._chat.add_message(
            conversation_id=conversation.id,
            author="evolution-controller",
            role="system",
            content=(
                f"Clarification provided for blocked run {request.source_run_id}. "
                f"Missing input: {request.missing_input_summary}. "
                f"Provided by: {provided_by}."
            ),
        )
        chat_proposal = self._chat.create_proposal(
            conversation_id=conversation.id,
            author=provided_by,
            proposal_type="clarification-recovery",
            content=(
                f"Resume blocked run {request.source_run_id} with provided information: "
                f"{provided_information}"
            ),
            references=[f"clarification_requests/{request.request_id}"],
        )
        candidate_graph: dict[str, Any] = {
            "lanes": candidate_lanes,
            "clarification_recovery": {
                "source_run_id": request.source_run_id,
                "request_id": request.request_id,
                "resolution_id": resolution.resolution_id,
                "provided_information": provided_information,
            },
        }
        chat_resolution = self._chat.approve_proposal(
            proposal_id=chat_proposal.id,
            approved_by=[provided_by],
            approval_mode="clarification-recovery",
            goal_summary=(
                f"Resume blocked run {request.source_run_id} with provided information"
            ),
            content=candidate_graph,
        )
        graph = build_lane_graph(chat_resolution)
        self._graph_store.save(graph)
        project_ready_lanes(graph, self._lanes_path)
        # Mark the request as resolved
        request.status = ClarificationStatus.RESOLVED
        request.resolved_at = now
        self._store.save_clarification_request(request)
        # Persist the resolution with spawned references
        resolution.spawned_conversation_id = conversation.id
        resolution.spawned_resolution_id = chat_resolution.id
        resolution.spawned_graph_id = graph.id
        return self._store.save_clarification_resolution(resolution)

    def _clarification_resume_lanes(
        self,
        request: ClarificationRequest,
        resolution: ClarificationResolution,
    ) -> list[dict[str, Any]]:
        """Build candidate lanes for a clarification-recovery follow-up run."""
        lane_id = (
            f"clarification-recovery-{request.source_run_id}-{resolution.resolution_id}"
        )
        slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", lane_id).strip("-").lower()
        lane_id = slug[:120]
        prompt = (
            f"Resume the blocked run {request.source_run_id} using the provided information. "
            f"Missing input was: {request.missing_input_summary}. "
            f"Provided information: {resolution.provided_information}. "
            f"Resume path: {request.resume_path}. "
            "Re-enter the standard mainline: chat -> proposal -> approved resolution "
            "-> lane graph -> execution."
        )
        return [
            {
                "feature_id": lane_id,
                "title": f"Resume blocked run {request.source_run_id}",
                "prompt": prompt,
                "priority": 100,
                "capabilities": ["code", "test"],
                "depends_on": [],
                "task_type": "execute",
                "gate_profiles": ["xmuse-core"],
                "feature_group": "clarification_recovery",
            }
        ]

    def _aggregate_status(
        self,
        lane_statuses: list[dict[str, Any]],
        blocked_objects: list[dict[str, Any]],
        final_action_holds: list[dict[str, Any]] | None = None,
        verdict_lineage: list[dict[str, Any]] | None = None,
    ) -> tuple[RunTerminalStatus, str]:
        if blocked_objects:
            return RunTerminalStatus.BLOCKED_FOR_INPUT, "one or more lanes request clarification"

        if not lane_statuses:
            return RunTerminalStatus.RUNNING, "no graph lanes have been projected yet"
        if any(not bool(item["terminal"]) for item in lane_statuses):
            if final_action_holds:
                return (
                    RunTerminalStatus.RUNNING,
                    "one or more lanes are awaiting final-action approval",
                )
            return RunTerminalStatus.RUNNING, "at least one graph lineage lane is not terminal"
        if all(item["normalized_status"] == "merged" for item in lane_statuses):
            return RunTerminalStatus.MERGED, "all graph lineage lanes merged"
        if self._has_unmerged_terminal_lineage(lane_statuses, verdict_lineage or []):
            return (
                RunTerminalStatus.RUNNING,
                "graph lineage merge coordination pending",
            )
        return RunTerminalStatus.TERMINATED, "at least one graph lineage terminalized without merge"

    def _has_unmerged_terminal_lineage(
        self,
        lane_statuses: list[dict[str, Any]],
        verdict_lineage: list[dict[str, Any]],
    ) -> bool:
        """Return True when a terminal lane still needs merge coordination."""

        merged_lane_ids = {
            str(entry.get("lane_id"))
            for entry in verdict_lineage
            if str(entry.get("decision", "")).lower() == "merge"
        }
        closed_lane_ids = merged_lane_ids | {
            str(entry.get("lane_id"))
            for entry in verdict_lineage
            if str(entry.get("decision", "")).lower() == "terminate"
        }
        for status in lane_statuses:
            lane_id = str(status.get("feature_id") or "")
            if not lane_id or lane_id in closed_lane_ids:
                continue
            if (
                bool(status.get("terminal"))
                and status.get("normalized_status") != "merged"
                and self._needs_lineage_merge_coordination(status)
            ):
                return True
        return False

    def _needs_lineage_merge_coordination(self, lane_status: dict[str, Any]) -> bool:
        """Review-rework terminal lanes are still active until merged or closed."""
        review_decision = str(lane_status.get("review_decision", "")).lower()
        return review_decision in {"rework", "patch-forward", "patch_forward"}

    def _get_evidence_bundle(self, bundle_id: str) -> StructuredEvidenceBundle:
        for bundle in self._store.list_evidence_bundles():
            if bundle.bundle_id == bundle_id:
                return bundle
        raise KeyError(f"unknown evidence bundle: {bundle_id}")

    def _aggregation_for_evidence(
        self,
        evidence: StructuredEvidenceBundle,
    ) -> RunTerminalAggregation:
        return self.aggregate_run_terminal(evidence.source_run_id)

    def _budget_window_for(
        self,
        source_run_id: str,
        now: str,
    ) -> tuple[EvolutionBudgetWindow, bool]:
        windows = self._store.list_budget_windows()
        for window in windows:
            matches_source = (
                window.origin_run_id == source_run_id
                or source_run_id in window.consumed_run_ids
            )
            if (
                matches_source
                and _parse_utc(now) >= _parse_utc(window.expires_at)
                and window.status != EvolutionBudgetStatus.EXPIRED
            ):
                window.status = EvolutionBudgetStatus.EXPIRED
                self._store.save_budget_window(window)
        matching_active = [
            window for window in windows
            if (
                window.origin_run_id == source_run_id
                or source_run_id in window.consumed_run_ids
            )
            and _parse_utc(now) < _parse_utc(window.expires_at)
        ]
        window = matching_active[-1] if matching_active else None
        if window is None:
            started = _parse_utc(now)
            window = EvolutionBudgetWindow(
                window_id=_new_id("evbudget"),
                origin_run_id=source_run_id,
                started_at=now,
                expires_at=(started + timedelta(hours=10))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                status=EvolutionBudgetStatus.ACTIVE,
                consumed_run_ids=[],
            )
            self._store.save_budget_window(window)

        active = _parse_utc(now) < _parse_utc(window.expires_at)
        next_status = (
            EvolutionBudgetStatus.ACTIVE if active else EvolutionBudgetStatus.EXPIRED
        )
        if window.status != next_status:
            window.status = next_status
            self._store.save_budget_window(window)
        return window, active

    def _consume_budget_window(
        self,
        budget_window: EvolutionBudgetWindow,
        source_run_id: str,
    ) -> None:
        if source_run_id not in budget_window.consumed_run_ids:
            budget_window.consumed_run_ids.append(source_run_id)
            self._store.save_budget_window(budget_window)

    def _record_landed_guardrail_side_effects(
        self,
        proposal: EvolutionProposal,
        guardrail: EvolutionGuardrailDecision,
        *,
        spawned_run_id: str,
    ) -> None:
        if guardrail.budget_window_id:
            budget_window = self._get_budget_window(guardrail.budget_window_id)
            self._consume_budget_window(budget_window, proposal.source_run_id)
            self._consume_budget_window(budget_window, spawned_run_id)
        if guardrail.dedup_key:
            dedup_key, signal_fingerprint, source_lineage_key = self._dedup_identity(proposal)
            self._record_dedup_continue(
                dedup_key=dedup_key,
                signal_fingerprint=signal_fingerprint,
                source_lineage_key=source_lineage_key,
                proposal=proposal,
            )

    def _get_budget_window(self, window_id: str) -> EvolutionBudgetWindow:
        for window in self._store.list_budget_windows():
            if window.window_id == window_id:
                return window
        raise KeyError(f"unknown self-evolution budget window: {window_id}")

    def _dedup_identity(self, proposal: EvolutionProposal) -> tuple[str, str, str]:
        evidence = self._maybe_get_evidence_bundle(proposal.evidence_bundle_id)
        signal_payload = {
            "run_terminal_status": (
                evidence.run_terminal_status.value if evidence is not None else None
            ),
            "signal_refs": (
                sorted(self._dedup_signal_refs(evidence.signal_refs))
                if evidence is not None
                else []
            ),
            "target_track_ids": sorted(proposal.target_track_ids),
        }
        lineage_payload = {
            "source_run_id": proposal.source_run_id,
            "source_resolution_id": evidence.source_resolution_id if evidence is not None else None,
            "verdict_refs": sorted(evidence.verdict_refs) if evidence is not None else [],
            "lineage_refs": sorted(evidence.lineage_refs) if evidence is not None else [],
            "target_track_ids": sorted(proposal.target_track_ids),
        }
        signal_fingerprint = _stable_digest(signal_payload)
        source_lineage_key = _stable_digest(lineage_payload)
        dedup_key = _stable_digest(
            {
                "signal_fingerprint": signal_fingerprint,
                "source_lineage_key": source_lineage_key,
            }
        )
        return dedup_key, signal_fingerprint, source_lineage_key

    def _dedup_signal_refs(self, signal_refs: list[str]) -> list[str]:
        refs: list[str] = []
        for signal in signal_refs:
            if (
                signal.startswith("gate_report:")
                or signal.startswith("gate_report_resolution:")
                or signal.startswith("gate_report_diagnostic:")
                or signal.startswith("gate_report_result:")
            ):
                continue
            if signal.startswith("lane_signal:"):
                refs.append(self._dedup_lane_signal_ref(signal))
            else:
                refs.append(signal)
        return refs

    def _dedup_lane_signal_ref(self, signal: str) -> str:
        try:
            payload = json.loads(signal.removeprefix("lane_signal:"))
        except json.JSONDecodeError:
            return signal
        if not isinstance(payload, dict):
            return signal
        payload.pop("manual_recovery", None)
        payload.pop("review_fallback", None)
        payload.pop("review_fallback_reason", None)
        payload.pop("review_recovery_reason", None)
        payload.pop("review_risks", None)
        payload.pop("review_scope_refs", None)
        return f"lane_signal:{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"

    def _maybe_get_evidence_bundle(self, bundle_id: str) -> StructuredEvidenceBundle | None:
        try:
            return self._get_evidence_bundle(bundle_id)
        except KeyError:
            return None

    def _has_duplicate_evolution(
        self,
        proposal: EvolutionProposal,
        dedup_key: str,
    ) -> bool:
        for record in self._store.list_dedup_records():
            if (
                record.dedup_key == dedup_key
                and record.last_proposal_id != proposal.proposal_id
                and record.status == EvolutionDedupStatus.CONTINUED
            ):
                return True
        for existing in self._store.list_proposals():
            if (
                existing.proposal_id != proposal.proposal_id
                and existing.status == EvolutionProposalStatus.LANDED
                and self._dedup_identity(existing)[0] == dedup_key
            ):
                return True
        return False

    def _record_dedup_continue(
        self,
        *,
        dedup_key: str,
        signal_fingerprint: str,
        source_lineage_key: str,
        proposal: EvolutionProposal,
    ) -> None:
        now = _utc_now()
        previous = next(
            (
                record for record in self._store.list_dedup_records()
                if record.dedup_key == dedup_key
            ),
            None,
        )
        record = EvolutionDedupRecord(
            dedup_key=dedup_key,
            signal_fingerprint=signal_fingerprint,
            source_lineage_key=source_lineage_key,
            target_track_ids=list(proposal.target_track_ids),
            first_seen_at=previous.first_seen_at if previous is not None else now,
            last_seen_at=now,
            last_proposal_id=proposal.proposal_id,
            status=EvolutionDedupStatus.CONTINUED,
        )
        self._store.save_dedup_record(record)

    def _read_lanes(self) -> list[dict[str, Any]]:
        return self._lanes_reader.list_lanes()

    def _lineage_lane_ids(
        self,
        graph_id: str,
        graph_lane_ids: list[str],
    ) -> list[str]:
        ordered = list(self._lanes_reader.lineage_lane_ids(graph_id))
        seen = set(ordered)
        for lane_id in graph_lane_ids:
            if lane_id not in seen:
                ordered.append(lane_id)
                seen.add(lane_id)
        return ordered

    def _blocked_object_for_lane(self, lane: dict[str, Any]) -> dict[str, Any] | None:
        return self._lanes_reader.blocked_object_for_lane(lane)

    def _final_action_hold_for_lane(self, lane: dict[str, Any]) -> dict[str, Any] | None:
        return self._lanes_reader.final_action_hold_for_lane(lane)

    def _open_lineages(self, lane_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        return self._lanes_reader.open_lineages(lane_by_id)

    def _build_verdict_lineage(
        self,
        lineage_lane_ids: list[str],
        lane_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build verdict lineage entries for each lane in the aggregation.

        When a VerdictStore is wired in, verdicts are read from the authoritative
        store.  When no store is available, the lane metadata field
        ``review_verdict_id`` is used as a fallback so the aggregation is still
        explainable from loose lane state.
        """
        result: list[dict[str, Any]] = []
        for lane_id in lineage_lane_ids:
            lane = lane_by_id.get(lane_id)
            if lane is None:
                continue
            if self._verdict_store is not None:
                verdicts = self._verdict_store.list_verdicts_for_lane(lane_id)
                for verdict in verdicts:
                    result.append(
                        {
                            "lane_id": lane_id,
                            "verdict_id": verdict.id,
                            "decision": verdict.decision.value
                            if hasattr(verdict.decision, "value")
                            else str(verdict.decision),
                            "summary": verdict.summary,
                            "source": "verdict_store",
                        }
                    )
            elif lane.get("review_verdict_id"):
                # Fallback: surface the verdict reference from lane metadata
                entry: dict[str, Any] = {
                    "lane_id": lane_id,
                    "verdict_id": str(lane["review_verdict_id"]),
                    "source": "lane_metadata",
                }
                if lane.get("review_decision"):
                    entry["decision"] = str(lane["review_decision"])
                if lane.get("review_summary"):
                    entry["summary"] = self._compact_signal_text(
                        str(lane["review_summary"]), 160
                    )
                result.append(entry)
        return result

    def _gate_report_refs(self, lanes: list[dict[str, Any]]) -> list[str]:
        refs: list[str] = []
        for lane in lanes:
            lane_id = lane.get("feature_id")
            if not lane_id:
                continue
            report_path = self._root / "logs" / "gates" / str(lane_id) / "report.json"
            if report_path.exists():
                refs.append(self._relative_ref(report_path))
        return refs

    def _relevant_lanes_for_aggregation(
        self,
        lanes: list[dict[str, Any]],
        aggregation: RunTerminalAggregation,
    ) -> list[dict[str, Any]]:
        lineage_lane_ids = {
            str(item["feature_id"])
            for item in aggregation.lane_statuses
            if isinstance(item.get("feature_id"), str)
        }
        return [
            lane for lane in lanes
            if isinstance(lane, dict)
            and (
                lane.get("graph_id") == aggregation.graph_id
                or lane.get("feature_id") in lineage_lane_ids
            )
        ]

    def _hydrate_evidence_bundle(
        self,
        evidence: StructuredEvidenceBundle,
        aggregation: RunTerminalAggregation,
    ) -> StructuredEvidenceBundle:
        lanes = self._read_lanes()
        relevant_lanes = self._relevant_lanes_for_aggregation(lanes, aggregation)
        gate_report_refs = self._merge_refs(
            evidence.gate_report_refs,
            self._gate_report_refs(relevant_lanes),
        )
        signal_refs = self._merge_refs(
            [
                signal for signal in evidence.signal_refs
                if not self._is_generated_signal_ref(signal)
            ],
            [
                self._lane_counts_ref(aggregation),
                *self._lane_signal_refs(relevant_lanes, aggregation),
                *self._gate_report_signal_refs(gate_report_refs),
                *self._gate_report_resolution_signal_refs(gate_report_refs),
                *self._gate_report_diagnostic_signal_refs(gate_report_refs),
                *self._gate_report_result_signal_refs(gate_report_refs),
            ],
        )
        verdict_refs = self._merge_refs(
            evidence.verdict_refs,
            [
                str(lane["review_verdict_id"])
                for lane in relevant_lanes
                if lane.get("review_verdict_id")
            ],
        )
        lineage_refs = self._merge_refs(
            evidence.lineage_refs,
            [
                f"lane:{lane['source_lane_id']}->{lane['feature_id']}"
                for lane in relevant_lanes
                if lane.get("source_lane_id") and lane.get("feature_id")
            ],
        )
        primary_refs = self._merge_refs(
            evidence.primary_refs,
            [
                self._relative_ref(self._lanes_path),
                f"lane_graphs/{aggregation.graph_id}.json",
                self._relative_ref(self._blueprint_path),
            ],
        )
        updated = evidence.model_copy(
            update={
                "summary": self._evidence_summary(aggregation, signal_refs),
                "run_terminal_status": aggregation.status,
                "selection_policy_version": self._hydrated_selection_policy_version(evidence),
                "verdict_refs": verdict_refs,
                "gate_report_refs": gate_report_refs,
                "lineage_refs": lineage_refs,
                "artifact_refs": self._merge_refs(evidence.artifact_refs, primary_refs),
                "signal_refs": signal_refs,
                "primary_refs": primary_refs,
            }
        )
        if updated != evidence:
            self._store.save_evidence_bundle(updated)
        return updated

    def _read_blueprint(self) -> str:
        return self._blueprint_path.read_text(encoding="utf-8")

    def _extract_blueprint_field(self, blueprint: str, field_name: str) -> str | None:
        match = re.search(rf"- `{re.escape(field_name)}`:\s*`([^`]+)`", blueprint)
        return match.group(1) if match else None

    def _select_target_tracks(
        self,
        evidence: StructuredEvidenceBundle,
        blueprint: str,
    ) -> list[str]:
        if evidence.run_terminal_status is RunTerminalStatus.BLOCKED_FOR_INPUT:
            return ["clarification_recovery"]
        track_order = self._blueprint_track_order(blueprint)
        if not track_order:
            return ["graph_authority"]
        landed_counts = self._landed_track_counts()
        return [
            min(
                track_order,
                key=lambda track: (landed_counts.get(track, 0), track_order.index(track)),
            )
        ]

    def _blueprint_track_order(self, blueprint: str) -> list[str]:
        priority_block = re.search(
            r"##\s*Priority\s*Policy.*?(?=\n##\s)", blueprint, flags=re.DOTALL | re.IGNORECASE
        )
        if priority_block:
            ordered = re.findall(r"\d+\.\s+`([a-z0-9_]+)`", priority_block.group(0))
            if ordered:
                return ordered
        track_block = re.search(
            r"##\s*Tracks(.*?)(?=\n##\s|\Z)", blueprint, flags=re.DOTALL | re.IGNORECASE
        )
        if track_block:
            return re.findall(r"###\s+([a-z0-9_]+)", track_block.group(1))
        return []

    def _landed_track_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self._store.list_lineage():
            for track in record.target_track_ids:
                counts[track] = counts.get(track, 0) + 1
        return counts

    def _compose_scope_summary(self, target_tracks: list[str]) -> str:
        if not target_tracks:
            return "Advance xmuse autonomous delivery through the next blueprint track."
        primary = target_tracks[0]
        return (
            f"Advance xmuse blueprint track '{primary}' for autonomous delivery: "
            f"address its next milestone with focused tests and lane evidence."
        )

    def _candidate_lane_id(
        self,
        evidence: StructuredEvidenceBundle,
        target_tracks: list[str],
    ) -> str:
        raw = f"self-evolution-{target_tracks[0]}-{evidence.source_run_id}"
        slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip("-").lower()
        return slug[:120]

    def _candidate_lane_id_for_track(
        self,
        evidence: StructuredEvidenceBundle,
        target_track: str,
    ) -> str:
        return self._candidate_lane_id(evidence, [target_track])

    def _candidate_prompt(
        self,
        evidence: StructuredEvidenceBundle,
        target_tracks: list[str],
    ) -> str:
        return (
            "Implement the next xmuse self-evolution improvement for tracks "
            f"{', '.join(target_tracks)}. Use evidence bundle {evidence.bundle_id}. "
            f"Focus first on evidence signals: {self._signal_summary(evidence.signal_refs)}. "
            "Preserve chat -> proposal -> approved resolution -> lane graph -> execution "
            "as the mainline, and add focused tests for the touched substrate."
        )

    def _candidate_prompt_for_track(
        self,
        evidence: StructuredEvidenceBundle,
        target_track: str,
    ) -> str:
        return self._candidate_prompt(evidence, [target_track])

    def _lane_counts_ref(self, aggregation: RunTerminalAggregation) -> str:
        return f"lane_counts:{json.dumps(aggregation.lane_counts, sort_keys=True)}"

    def _evidence_summary(
        self,
        aggregation: RunTerminalAggregation,
        signal_refs: list[str],
    ) -> str:
        lane_counts = self._lane_counts_summary(self._lane_counts_ref(aggregation))
        if lane_counts.startswith("lane_counts "):
            lane_counts = lane_counts.removeprefix("lane_counts ")
        summary = (
            f"Run {aggregation.run_id} terminal status is {aggregation.status.value}. "
            f"Reason: {aggregation.reason}. Lane counts: {lane_counts}."
        )
        if signal_refs:
            summary = f"{summary} Evidence signals: {self._signal_summary(signal_refs)}."
        return summary

    def _lane_signal_refs(
        self,
        lanes: list[dict[str, Any]],
        aggregation: RunTerminalAggregation,
    ) -> list[str]:
        status_by_id = {
            str(item.get("feature_id")): item
            for item in aggregation.lane_statuses
            if isinstance(item.get("feature_id"), str)
        }
        refs: list[str] = []
        for lane in lanes:
            lane_id = lane.get("feature_id")
            if not isinstance(lane_id, str) or not lane_id:
                continue
            status = status_by_id.get(lane_id, {})
            payload = {
                "feature_id": lane_id,
                "raw_status": status.get("raw_status", lane.get("status")),
                "normalized_status": status.get("normalized_status"),
                "terminal": bool(status.get("terminal")),
            }
            for key in (
                "failure_reason",
                "manual_recovery",
                "review_decision",
                "review_fallback",
                "review_fallback_reason",
                "gate_passed",
                "retry_count",
                "patch_lane_id",
            ):
                if key in lane:
                    payload[key] = lane[key]
            review_findings = self._review_finding_summaries(lane.get("review_summary"))
            if review_findings:
                payload["review_findings"] = review_findings
            review_scope_refs = self._review_scope_refs(lane.get("review_summary"))
            if review_scope_refs:
                payload["review_scope_refs"] = review_scope_refs
            review_risks = self._review_risk_summaries(lane.get("review_summary"))
            if review_risks:
                payload["review_risks"] = review_risks
            review_recovery_reason = self._review_recovery_reason(lane)
            if review_recovery_reason:
                payload["review_recovery_reason"] = review_recovery_reason
            if (
                payload.get("normalized_status") == "merged"
                or payload.get("review_decision") == "merge"
            ):
                review_confirmations = self._review_confirmation_summaries(
                    lane.get("review_summary")
                )
                if review_confirmations:
                    payload["review_confirmations"] = review_confirmations
            if (
                payload["terminal"]
                or payload.get("review_decision")
                or payload.get("failure_reason")
            ):
                refs.append(
                    f"lane_signal:{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
                )
        return refs

    def _signal_summary(self, signal_refs: list[str]) -> str:
        signal_text: list[str] = []
        ordered_refs = self._ordered_signal_summary_refs(signal_refs)
        max_signal_text = (
            6
            if any(
                signal.startswith("gate_report_diagnostic:")
                for signal in ordered_refs
            )
            else 5
        )
        for signal in ordered_refs:
            if signal.startswith("lane_signal:"):
                try:
                    payload = json.loads(signal.removeprefix("lane_signal:"))
                except json.JSONDecodeError:
                    signal_text.append(signal)
                    continue
                parts = [
                    f"lane {payload.get('feature_id', 'unknown')}",
                    f"status={payload.get('normalized_status', payload.get('raw_status'))}",
                ]
                if payload.get("review_decision"):
                    parts.append(f"review={payload['review_decision']}")
                if payload.get("review_fallback"):
                    parts.append(f"review_source={payload['review_fallback']}")
                    parts.append(f"review_fallback={payload['review_fallback']}")
                if payload.get("review_fallback_reason"):
                    parts.append(
                        "fallback_reason="
                        f"{self._compact_signal_text(str(payload['review_fallback_reason']), 80)}"
                    )
                if payload.get("review_recovery_reason"):
                    parts.append(
                        "recovery_reason="
                        f"{self._compact_signal_text(str(payload['review_recovery_reason']), 80)}"
                    )
                review_scope_refs = payload.get("review_scope_refs")
                if isinstance(review_scope_refs, list) and review_scope_refs:
                    reviewed = ",".join(str(ref) for ref in review_scope_refs[:2])
                    parts.append(
                        f"reviewed={self._compact_signal_text(reviewed, 140)}"
                    )
                if "gate_passed" in payload:
                    parts.append(
                        f"gate={'passed' if payload['gate_passed'] else 'failed'}"
                    )
                if payload.get("retry_count") is not None:
                    parts.append(f"retries={payload['retry_count']}")
                if payload.get("manual_recovery"):
                    parts.append(
                        "recovery="
                        f"{self._compact_signal_text(str(payload['manual_recovery']), 100)}"
                    )
                if payload.get("failure_reason"):
                    parts.append(f"failure={payload['failure_reason']}")
                review_findings = payload.get("review_findings")
                if isinstance(review_findings, list) and review_findings:
                    parts.append(
                        f"finding={self._compact_signal_text(str(review_findings[0]), 120)}"
                    )
                review_risks = payload.get("review_risks")
                if isinstance(review_risks, list) and review_risks:
                    parts.append(
                        f"risk={self._compact_risk_text(str(review_risks[0]), 120)}"
                    )
                review_confirmations = payload.get("review_confirmations")
                confirmation_parts: list[str] = []
                if isinstance(review_confirmations, list) and review_confirmations:
                    for confirmation in review_confirmations[:2]:
                        confirmation_parts.append(
                            "confirmation="
                            f"{self._compact_confirmation_text(str(confirmation), 120)}"
                        )
                signal = " ".join(parts)
                if confirmation_parts:
                    signal = f"{signal} {'; '.join(confirmation_parts)}"
                signal_text.append(signal)
            elif signal.startswith("lane_counts:"):
                signal_text.append(self._lane_counts_summary(signal))
            elif signal.startswith("gate_report:"):
                report_ref = signal.removeprefix("gate_report:")
                signal_text.append(self._gate_report_summary(report_ref))
            elif signal.startswith("gate_report_resolution:"):
                try:
                    payload = json.loads(signal.removeprefix("gate_report_resolution:"))
                except json.JSONDecodeError:
                    signal_text.append(signal)
                    continue
                signal_text.append(self._gate_report_resolution_summary(payload))
            elif signal.startswith("gate_report_diagnostic:"):
                try:
                    payload = json.loads(signal.removeprefix("gate_report_diagnostic:"))
                except json.JSONDecodeError:
                    signal_text.append(signal)
                    continue
                signal_text.append(self._gate_report_diagnostic_summary(payload))
            elif signal.startswith("gate_report_result:"):
                try:
                    payload = json.loads(signal.removeprefix("gate_report_result:"))
                except json.JSONDecodeError:
                    signal_text.append(signal)
                    continue
                command = self._gate_report_command_summary(payload)
                outcome = str(payload.get("outcome") or "unknown")
                stdout_summary = str(payload.get("stdout_summary") or "").strip()
                result = f"gate_command={command} -> {outcome}"
                if stdout_summary:
                    result = f"{result} ({stdout_summary})"
                signal_text.append(self._compact_confirmation_text(result, 160))
            else:
                signal_text.append(signal)
            if len(signal_text) >= max_signal_text:
                break
        return "; ".join(signal_text) if signal_text else "none"

    def _ordered_signal_summary_refs(self, signal_refs: list[str]) -> list[str]:
        lane_refs = self._rank_lane_signal_summary_refs(
            [signal for signal in signal_refs if signal.startswith("lane_signal:")]
        )
        lane_count_refs = [signal for signal in signal_refs if signal.startswith("lane_counts:")]
        other_refs = [
            signal
            for signal in signal_refs
            if not (
                signal.startswith("lane_signal:")
                or signal.startswith("lane_counts:")
                or signal.startswith("gate_report:")
                or signal.startswith("gate_report_resolution:")
                or signal.startswith("gate_report_diagnostic:")
                or signal.startswith("gate_report_result:")
            )
        ]
        gate_report_refs = [
            signal for signal in signal_refs if signal.startswith("gate_report:")
        ]
        gate_report_diagnostic_refs = [
            signal
            for signal in signal_refs
            if signal.startswith("gate_report_diagnostic:")
        ]
        gate_report_resolution_refs = [
            signal
            for signal in signal_refs
            if signal.startswith("gate_report_resolution:")
        ]
        gate_report_result_refs = [
            signal for signal in signal_refs if signal.startswith("gate_report_result:")
        ]
        if len(lane_refs) >= 3:
            return [
                *lane_refs[:2],
                *lane_count_refs[:1],
                *gate_report_refs[:1],
                *gate_report_result_refs[:1],
                *gate_report_diagnostic_refs[:1],
                *gate_report_resolution_refs[:1],
                *gate_report_refs[1:],
                *gate_report_result_refs[1:],
                *gate_report_diagnostic_refs[1:],
                *gate_report_resolution_refs[1:],
                *lane_refs[2:],
                *lane_count_refs[1:],
                *other_refs,
            ]
        return [
            *lane_refs,
            *lane_count_refs,
            *gate_report_refs,
            *gate_report_result_refs,
            *gate_report_diagnostic_refs,
            *gate_report_resolution_refs,
            *other_refs,
        ]

    def _rank_lane_signal_summary_refs(self, lane_refs: list[str]) -> list[str]:
        return [
            item
            for _, _, item in sorted(
                (
                    (self._lane_signal_summary_priority(item), index, item)
                    for index, item in enumerate(lane_refs)
                ),
                key=lambda item: (item[0], item[1]),
            )
        ]

    def _lane_signal_summary_priority(self, signal: str) -> int:
        try:
            payload = json.loads(signal.removeprefix("lane_signal:"))
        except json.JSONDecodeError:
            return 10
        if not isinstance(payload, dict):
            return 10
        if payload.get("manual_recovery") or payload.get("review_fallback"):
            return 0
        return 10

    def _gate_report_signal_refs(self, gate_report_refs: list[str]) -> list[str]:
        return [f"gate_report:{ref}" for ref in gate_report_refs if ref]

    def _gate_report_resolution_signal_refs(
        self,
        gate_report_refs: list[str],
    ) -> list[str]:
        signal_refs: list[str] = []
        for report_ref in gate_report_refs:
            payload = self._gate_report_resolution_payload(report_ref)
            if payload:
                signal_refs.append(
                    "gate_report_resolution:"
                    f"{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
                )
        return signal_refs

    def _gate_report_resolution_payload(
        self,
        report_ref: str,
    ) -> dict[str, Any] | None:
        report_path = self._resolve_xmuse_ref(report_ref)
        if not report_path.exists():
            return None
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        resolution_reasons = report.get("resolution_reasons")
        if not isinstance(resolution_reasons, dict):
            return None

        profile_reasons: list[dict[str, Any]] = []
        for profile_id in sorted(resolution_reasons):
            if not isinstance(profile_id, str) or not profile_id:
                continue
            raw_reasons = resolution_reasons.get(profile_id)
            if not isinstance(raw_reasons, list):
                continue
            reasons = [
                self._compact_signal_text(str(reason), 80)
                for reason in raw_reasons
                if isinstance(reason, str) and reason.strip()
            ][:3]
            if reasons:
                profile_reasons.append(
                    {
                        "profile_id": profile_id,
                        "reasons": reasons,
                    }
                )
            if len(profile_reasons) >= 3:
                break

        if not profile_reasons:
            return None
        return {"report_ref": report_ref, "profile_reasons": profile_reasons}

    def _gate_report_resolution_summary(self, payload: dict[str, Any]) -> str:
        report_ref = str(payload.get("report_ref") or "unknown")
        profile_reasons = payload.get("profile_reasons")
        parts = [f"gate_scope={report_ref}"]
        if isinstance(profile_reasons, list) and profile_reasons:
            first = profile_reasons[0]
            if isinstance(first, dict):
                profile_id = str(first.get("profile_id") or "unknown")
                reasons = first.get("reasons")
                parts.append(f"profile={profile_id}")
                if isinstance(reasons, list) and reasons:
                    parts.append(
                        f"reason={self._compact_signal_text(str(reasons[0]), 80)}"
                    )
                    if len(reasons) > 1:
                        parts.append(f"+{len(reasons) - 1} reasons")
            if len(profile_reasons) > 1:
                parts.append(f"+{len(profile_reasons) - 1} profiles")

        summary = " ".join(parts)
        if len(summary) > 220:
            parts[0] = (
                "gate_scope="
                f"{self._compact_gate_report_ref_for_diagnostic(report_ref)}"
            )
            summary = " ".join(parts)
        return self._compact_signal_text(summary, 240)

    def _gate_report_diagnostic_signal_refs(
        self,
        gate_report_refs: list[str],
    ) -> list[str]:
        signal_refs: list[str] = []
        for report_ref in gate_report_refs:
            payload = self._gate_report_diagnostic_payload(report_ref)
            if payload:
                signal_refs.append(
                    "gate_report_diagnostic:"
                    f"{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
                )
        return signal_refs

    def _gate_report_diagnostic_payload(
        self,
        report_ref: str,
    ) -> dict[str, Any] | None:
        report_path = self._resolve_xmuse_ref(report_ref)
        if not report_path.exists():
            return None
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        warnings = self._compact_report_messages(report.get("warnings"))
        nonblocking_failures = self._compact_report_messages(
            report.get("nonblocking_failures")
        )
        if not warnings and not nonblocking_failures:
            return None

        payload: dict[str, Any] = {"report_ref": report_ref}
        if warnings:
            payload["warnings"] = warnings
        if nonblocking_failures:
            payload["nonblocking_failures"] = nonblocking_failures
        return payload

    def _compact_report_messages(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        messages: list[str] = []
        for item in value:
            if isinstance(item, str):
                message = item
            elif isinstance(item, dict):
                message = self._report_message_from_mapping(item)
            else:
                continue
            message = self._compact_signal_text(message, 160)
            if message:
                messages.append(message)
            if len(messages) >= 2:
                break
        return messages

    def _report_message_from_mapping(self, item: dict[str, Any]) -> str:
        for key in ("message", "summary", "reason", "error"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(item, sort_keys=True, separators=(",", ":"), default=str)

    def _gate_report_diagnostic_summary(self, payload: dict[str, Any]) -> str:
        report_ref = str(payload.get("report_ref") or "unknown")
        parts = [f"gate_diagnostic={report_ref}"]
        warnings = payload.get("warnings")
        if isinstance(warnings, list) and warnings:
            parts.append(f"warning={self._compact_signal_text(str(warnings[0]), 120)}")
            if len(warnings) > 1:
                parts.append(f"+{len(warnings) - 1} warnings")
        nonblocking_failures = payload.get("nonblocking_failures")
        if isinstance(nonblocking_failures, list) and nonblocking_failures:
            parts.append(
                "nonblocking="
                f"{self._compact_signal_text(str(nonblocking_failures[0]), 120)}"
            )
            if len(nonblocking_failures) > 1:
                parts.append(f"+{len(nonblocking_failures) - 1} nonblocking")
        summary = " ".join(parts)
        if len(summary) > 220:
            parts[0] = (
                "gate_diagnostic="
                f"{self._compact_gate_report_ref_for_diagnostic(report_ref)}"
            )
            summary = " ".join(parts)
        return self._compact_signal_text(summary, 260)

    def _compact_gate_report_ref_for_diagnostic(self, report_ref: str) -> str:
        if len(report_ref) <= 84:
            return report_ref

        path_parts = Path(report_ref).parts
        if len(path_parts) >= 4:
            lane_id = path_parts[-2]
            compact_lane_id = self._compact_middle_text(lane_id, 44)
            candidate = "/".join([*path_parts[:-2], compact_lane_id, path_parts[-1]])
            if len(candidate) <= 84:
                return candidate
        return self._compact_middle_text(report_ref, 84)

    def _compact_middle_text(self, value: str, max_chars: int) -> str:
        if len(value) <= max_chars:
            return value
        if max_chars <= 3:
            return "." * max_chars
        head_chars = (max_chars - 3) // 2
        tail_chars = max_chars - 3 - head_chars
        return f"{value[:head_chars]}...{value[-tail_chars:]}"

    def _gate_report_summary(self, report_ref: str) -> str:
        parts = [f"gate_report={report_ref}"]
        report_path = self._resolve_xmuse_ref(report_ref)
        if not report_path.exists():
            return parts[0]
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return parts[0]

        outcome = self._gate_report_outcome(report)
        if outcome:
            parts.append(f"status={outcome}")
        blocking_passed = report.get("blocking_passed")
        if isinstance(blocking_passed, bool):
            parts.append(f"blocking={'passed' if blocking_passed else 'failed'}")
        profile_ids = report.get("profile_ids")
        if isinstance(profile_ids, list):
            profiles = [
                str(profile_id)
                for profile_id in profile_ids
                if isinstance(profile_id, str) and profile_id
            ]
            if profiles:
                parts.append(f"profiles={','.join(profiles[:3])}")
        return self._compact_signal_text(" ".join(parts), 180)

    def _gate_report_result_signal_refs(self, gate_report_refs: list[str]) -> list[str]:
        signal_refs: list[str] = []
        for report_ref in gate_report_refs:
            for payload in self._gate_report_result_payloads(report_ref)[:2]:
                signal_refs.append(
                    "gate_report_result:"
                    f"{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
                )
        return signal_refs

    def _gate_report_result_payloads(self, report_ref: str) -> list[dict[str, Any]]:
        report_path = self._resolve_xmuse_ref(report_ref)
        if not report_path.exists():
            return []
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        command_results = report.get("command_results")
        legacy_commands = report.get("commands")
        if not isinstance(command_results, list) and not isinstance(legacy_commands, list):
            return []

        payloads: list[dict[str, Any]] = []
        for result in command_results if isinstance(command_results, list) else []:
            if not isinstance(result, dict):
                continue
            returncode = result.get("returncode")
            if not isinstance(returncode, int):
                continue
            payload: dict[str, Any] = {
                "report_ref": report_ref,
                "command_id": str(result.get("command_id") or "command"),
                "profile_id": str(result.get("profile_id") or "unknown"),
                "returncode": returncode,
                "outcome": "passed" if returncode == 0 else "failed",
            }
            argv = result.get("argv")
            if isinstance(argv, list) and argv:
                payload["argv"] = [str(part) for part in argv]
            stdout_summary = self._gate_report_stdout_summary(result.get("stdout_path"))
            if stdout_summary:
                payload["stdout_summary"] = stdout_summary
            payloads.append(payload)
        if not payloads and isinstance(legacy_commands, list):
            report_outcome = self._gate_report_outcome(report)
            for index, command_entry in enumerate(legacy_commands, start=1):
                payload = self._legacy_gate_command_payload(
                    report_ref=report_ref,
                    command_entry=command_entry,
                    index=index,
                    report_outcome=report_outcome,
                )
                if payload:
                    payloads.append(payload)
        payloads.sort(
            key=lambda item: (
                item.get("outcome") == "passed",
                str(item.get("profile_id", "")),
                str(item.get("command_id", "")),
            )
        )
        return payloads

    def _gate_report_command_summary(self, payload: dict[str, Any]) -> str:
        argv = payload.get("argv")
        if isinstance(argv, list) and argv:
            return self._argv_command_summary([str(part) for part in argv])
        return str(payload.get("command") or payload.get("command_id") or "command")

    def _argv_command_summary(self, argv: list[str]) -> str:
        pytest_index = self._pytest_argv_index(argv)
        if pytest_index is None:
            return " ".join(argv)

        targets = [part for part in argv[pytest_index + 1 :] if self._is_pytest_target(part)]
        if len(targets) <= 4:
            return " ".join(argv)

        first_target_index = next(
            (
                index
                for index in range(pytest_index + 1, len(argv))
                if self._is_pytest_target(argv[index])
            ),
            len(argv),
        )
        shown_targets = targets[:2]
        hidden_count = len(targets) - len(shown_targets)
        return " ".join(
            [
                *argv[:first_target_index],
                *shown_targets,
                f"+{hidden_count} test files",
            ]
        )

    def _pytest_argv_index(self, argv: list[str]) -> int | None:
        for index, part in enumerate(argv):
            if Path(part).name == "pytest":
                return index
        return None

    def _is_pytest_target(self, value: str) -> bool:
        return (
            value.startswith("tests/")
            or value.startswith("test/")
            or value.endswith(".py")
            or "::" in value
        )

    def _legacy_gate_command_payload(
        self,
        *,
        report_ref: str,
        command_entry: Any,
        index: int,
        report_outcome: str | None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "report_ref": report_ref,
            "command_id": f"command_{index}",
            "profile_id": "unknown",
            "outcome": report_outcome or "unknown",
        }
        if isinstance(command_entry, str) and command_entry.strip():
            payload["command"] = self._compact_signal_text(command_entry, 240)
            return payload
        if not isinstance(command_entry, dict):
            return None

        command = command_entry.get("command")
        if isinstance(command, str) and command.strip():
            payload["command"] = self._compact_signal_text(command, 240)
        argv = command_entry.get("argv")
        if isinstance(argv, list) and argv:
            payload["argv"] = [str(part) for part in argv]
        if not payload.get("command") and not payload.get("argv"):
            return None

        command_id = command_entry.get("command_id")
        if isinstance(command_id, str) and command_id:
            payload["command_id"] = command_id
        profile_id = command_entry.get("profile_id")
        if isinstance(profile_id, str) and profile_id:
            payload["profile_id"] = profile_id
        returncode = command_entry.get("returncode")
        if isinstance(returncode, int):
            payload["returncode"] = returncode
            payload["outcome"] = "passed" if returncode == 0 else "failed"
        return payload

    def _gate_report_outcome(self, report: dict[str, Any]) -> str | None:
        passed = report.get("passed")
        if isinstance(passed, bool):
            return "passed" if passed else "failed"
        status = report.get("status")
        if isinstance(status, str):
            normalized = status.strip().lower().replace("_", "-")
            if normalized in {"passed", "pass", "success", "succeeded"}:
                return "passed"
            if normalized in {"failed", "fail", "failure", "error", "errored"}:
                return "failed"
            if normalized:
                return normalized
        return None

    def _gate_report_stdout_summary(self, stdout_path: Any) -> str | None:
        if not isinstance(stdout_path, str) or not stdout_path:
            return None
        path = self._resolve_xmuse_ref(stdout_path)
        if not path.exists() or not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        for raw_line in reversed(text[-65536:].splitlines()):
            line = self._compact_signal_text(raw_line.strip("= "), 160)
            lowered = line.lower()
            if not line:
                continue
            if (
                "all checks passed" in lowered
                or re.search(r"\b\d+\s+passed\b", lowered)
                or re.search(r"\b\d+\s+failed\b", lowered)
                or re.search(r"\b\d+\s+errors?\b", lowered)
            ):
                return line
        return None

    def _is_generated_signal_ref(self, signal: str) -> bool:
        return (
            signal.startswith("lane_counts:")
            or signal.startswith("lane_signal:")
            or signal.startswith("gate_report:")
            or signal.startswith("gate_report_resolution:")
            or signal.startswith("gate_report_diagnostic:")
            or signal.startswith("gate_report_result:")
        )

    def _lane_counts_summary(self, signal: str) -> str:
        try:
            counts = json.loads(signal.removeprefix("lane_counts:"))
        except json.JSONDecodeError:
            return signal
        if not isinstance(counts, dict):
            return signal

        ordered_keys = [
            key for key in ("total", "terminal", "merged", "terminated", "running")
            if key in counts
        ]
        ordered_keys.extend(
            sorted(
                key for key in counts
                if isinstance(key, str) and key not in ordered_keys
            )
        )
        parts = [
            f"{key}={counts[key]}"
            for key in ordered_keys
            if isinstance(counts.get(key), int)
        ]
        return f"lane_counts {' '.join(parts)}" if parts else signal

    def _review_scope_refs(self, value: Any) -> list[str]:
        if not isinstance(value, str) or not value.strip():
            return []

        refs: list[str] = []
        seen: set[str] = set()
        for raw_line in value.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            normalized = self._normalized_review_section_name(line)
            if normalized.startswith(("verification", "residual risk")):
                break
            if normalized in {"findings", "finding"}:
                continue
            for ref in self._review_scope_refs_from_line(line):
                if ref in seen:
                    continue
                refs.append(ref)
                seen.add(ref)
                if len(refs) >= 3:
                    return refs
        return refs

    def _review_scope_refs_from_line(self, line: str) -> list[str]:
        candidates = re.findall(r"\]\(([^)]+)\)", line)
        candidates.extend(
            re.findall(r"`([^`]*(?:src|tests|xmuse|docs)/[^`]*)`", line)
        )
        candidates.extend(
            re.findall(
                r"(?<![\w./-])(?:src|tests|xmuse|docs)/[^\s),;`]+"
                r"\.(?:py|md|json|toml|yaml|yml|ts|tsx|js|css)(?::\d+)?",
                line,
            )
        )
        refs: list[str] = []
        for candidate in candidates:
            ref = self._normalize_review_scope_ref(candidate)
            if ref:
                refs.append(ref)
        return refs

    def _normalized_review_section_name(self, line: str) -> str:
        normalized = re.sub(r"^#+\s*", "", line).strip()
        normalized = normalized.replace("**", "").replace("__", "").replace("`", "")
        return normalized.strip().lower().rstrip(":")

    def _normalize_review_scope_ref(self, value: str) -> str | None:
        ref = value.strip().strip("<>()[]`'\".,;")
        if not ref:
            return None
        ref = ref.replace("\\", "/").split("#", 1)[0].split("?", 1)[0]
        ref = re.sub(r":\d+(?::\d+)?$", "", ref)

        for marker in ("src/", "tests/", "xmuse/", "docs/"):
            index = ref.find(marker)
            if index >= 0:
                ref = ref[index:]
                break
        else:
            return None

        if not re.search(r"\.(?:py|md|json|toml|yaml|yml|ts|tsx|js|css)$", ref):
            return None
        return ref

    def _review_finding_summaries(self, value: Any) -> list[str]:
        if not isinstance(value, str) or not value.strip():
            return []

        findings: list[str] = []
        for raw_line in value.splitlines():
            line = self._compact_signal_text(raw_line, 220)
            if not line:
                continue
            line = re.sub(r"^(?:[-*]\s+|\d+[.)]\s*)", "", line).strip()
            line = line.replace("**", "").replace("__", "")
            if line.lower() in {"findings", "finding", "findings:"}:
                continue
            if not self._is_review_finding_line(line):
                continue
            findings.append(line)
            if len(findings) >= 2:
                break
        return findings

    def _review_confirmation_summaries(self, value: Any) -> list[str]:
        if not isinstance(value, str) or not value.strip():
            return []

        verification_confirmations: list[str] = []
        general_confirmations: list[str] = []
        in_verification_block = False
        pending_verification_command: str | None = None
        for raw_line in value.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            line = re.sub(r"^(?:[-*]\s+|\d+[.)]\s*)", "", line).strip()
            line = line.replace("**", "").replace("__", "").replace("`", "")
            lowered = line.lower().rstrip(":")
            if lowered.startswith("verification"):
                in_verification_block = True
                pending_verification_command = None
                continue
            if lowered in {"findings", "finding"}:
                in_verification_block = False
                pending_verification_command = None
                continue

            if lowered.startswith(("no blocking findings", "no findings")):
                confirmation_line = self._confirmation_evidence_text(line)
                if confirmation_line:
                    general_confirmations.append(
                        self._compact_confirmation_text(confirmation_line, 220)
                    )
            elif in_verification_block and self._verification_confirmation_passed(
                self._confirmation_evidence_lowered(line)
            ):
                confirmation_line = self._confirmation_evidence_text(line)
                if pending_verification_command and self._is_result_confirmation(
                    confirmation_line.lower().rstrip(":")
                ):
                    result_text = self._result_confirmation_text(confirmation_line)
                    confirmation_line = f"{pending_verification_command} -> {result_text}"
                pending_verification_command = None
                verification_confirmations.append(
                    self._compact_confirmation_text(confirmation_line, 220)
                )
            elif in_verification_block and self._looks_like_verification_command(line):
                pending_verification_command = self._compact_confirmation_text(line, 220)
            elif lowered.startswith("gate report") and "passing" in lowered:
                pending_verification_command = None
                confirmation_line = self._confirmation_evidence_text(line)
                if confirmation_line:
                    verification_confirmations.append(
                        self._compact_confirmation_text(confirmation_line, 220)
                    )

        max_confirmations = 2
        confirmations = self._select_review_confirmations(
            verification_confirmations,
            max_confirmations=max_confirmations,
        )
        if len(confirmations) < max_confirmations and general_confirmations:
            confirmations.append(general_confirmations[0])
        return confirmations

    def _review_risk_summaries(self, value: Any) -> list[str]:
        if not isinstance(value, str) or not value.strip():
            return []

        risks: list[str] = []
        in_residual_risk_block = False
        in_findings_block = False
        for raw_line in value.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            line = re.sub(r"^(?:[-*]\s+|\d+[.)]\s*)", "", line).strip()
            line = line.replace("**", "").replace("__", "").replace("`", "")
            lowered = line.lower().rstrip(":")
            inline_risk = self._inline_residual_risk_text(line)
            starts_residual_risk = self._starts_residual_risk_block(line)
            if starts_residual_risk or lowered == "residual risk":
                in_findings_block = False
                in_residual_risk_block = True
                if inline_risk:
                    risks.append(self._compact_risk_text(inline_risk, 220))
                if len(risks) >= 2:
                    break
                continue
            if self._is_review_section_heading(line):
                in_residual_risk_block = False
                in_findings_block = lowered in {"findings", "finding"}
                continue
            if self._is_review_finding_line(line):
                in_findings_block = True
            if in_findings_block:
                continue
            if inline_risk:
                risks.append(self._compact_risk_text(inline_risk, 220))
                in_residual_risk_block = starts_residual_risk
            elif in_residual_risk_block:
                risks.append(self._compact_risk_text(line, 220))

            if len(risks) >= 2:
                break
        return risks

    def _review_recovery_reason(self, lane: dict[str, Any]) -> str | None:
        if lane.get("review_recovery_reason"):
            return self._compact_signal_text(str(lane["review_recovery_reason"]), 80)
        if lane.get("review_fallback_reason"):
            return None

        text_parts = [
            str(lane.get("manual_recovery") or ""),
            str(lane.get("review_summary") or ""),
            str(lane.get("failure_reason") or ""),
        ]
        normalized = " ".join(text_parts).lower()
        if not normalized.strip():
            return None

        has_review_fallback_context = bool(lane.get("review_fallback")) or (
            "review fallback" in normalized
            or "stdout fallback" in normalized
            or "false-positive merge" in normalized
            or "false positive merge" in normalized
            or "misclassified" in normalized
        )
        if not has_review_fallback_context:
            return None

        reproduced = "reproduc" in normalized
        false_positive_merge = (
            "false-positive merge" in normalized
            or "false positive merge" in normalized
            or (
                "misclassified" in normalized
                and "merge" in normalized
            )
        )
        if reproduced and false_positive_merge:
            return "reproduced_finding_false_positive_merge"
        if reproduced:
            return "reproduced_finding_recovery"
        return None

    def _is_review_finding_line(self, line: str) -> bool:
        return re.match(r"(?i)^(critical|high|medium|low)\b[: -]", line) is not None

    def _inline_residual_risk_text(self, line: str) -> str | None:
        match = re.search(
            r"(?i)\b(?:the\s+)?(?:main\s+)?residual[-\s]+risk(?:\s+is|:)\s+(.+)",
            line,
        )
        if match is None:
            return None
        risk = match.group(1).strip()
        return risk or None

    def _starts_residual_risk_block(self, line: str) -> bool:
        return re.match(r"(?i)^\s*residual[-\s]+risk\s*:", line) is not None

    def _is_review_section_heading(self, line: str) -> bool:
        normalized = re.sub(r"^#+\s*", "", line).strip().lower().rstrip(":")
        return normalized in {
            "assumptions",
            "change summary",
            "findings",
            "finding",
            "open questions",
            "questions",
            "summary",
            "verification",
            "verification run",
        }

    def _select_review_confirmations(
        self,
        confirmations: list[str],
        *,
        max_confirmations: int,
    ) -> list[str]:
        if len(confirmations) <= max_confirmations:
            return confirmations

        broader_confirmations = [
            confirmation for confirmation in confirmations
            if not self._is_targeted_pytest_confirmation(confirmation)
        ]
        if len(broader_confirmations) >= max_confirmations:
            return broader_confirmations[:max_confirmations]
        return confirmations[:max_confirmations]

    def _is_targeted_pytest_confirmation(self, confirmation: str) -> bool:
        lowered = confirmation.lower()
        return "pytest" in lowered and "::" in confirmation

    def _verification_confirmation_passed(self, lowered: str) -> bool:
        if not lowered:
            return False
        if re.search(
            r"\b(?:failed|failures?|errors?|errored|non[-_ ]?zero|"
            r"traceback|exception|timeout|timed out)\b",
            lowered,
        ):
            return False
        if re.search(r"\bexit(?:ed)?[-_ ]?code\s*[:=]?\s*[1-9]\d*\b", lowered):
            return False
        return bool(
            lowered == "passed"
            or lowered.endswith("-> passed")
            or lowered.endswith(": passed")
            or "all checks passed" in lowered
            or re.search(r"\bpassed(?:\s*:\s*\d+\s+tests?)?\.?$", lowered)
            or re.search(r"\b\d+\s+passed\b", lowered)
            or re.search(
                r"\b(?:tests?|checks?|verification|suite|command)\s+passed\b",
                lowered,
            )
        )

    def _confirmation_evidence_lowered(self, line: str) -> str:
        return self._confirmation_evidence_text(line).lower().rstrip(":")

    def _confirmation_evidence_text(self, line: str) -> str:
        parts = re.split(
            r"(?i)\s+(?:the\s+)?(?:main\s+)?residual[-\s]+risk(?:\s+is\b|:)",
            line,
            maxsplit=1,
        )
        if len(parts) == 1:
            return line.strip()
        confirmation = parts[0].strip()
        return confirmation.rstrip(" .") + "." if confirmation else ""

    def _looks_like_verification_command(self, line: str) -> bool:
        lowered = line.lower()
        return (
            lowered.startswith(("uv run ", "pytest ", "ruff ", "python "))
            or " uv run " in lowered
            or " pytest " in lowered
            or " ruff " in lowered
        )

    def _is_result_confirmation(self, lowered: str) -> bool:
        return lowered.startswith(("result:", "result ", "outcome:", "outcome "))

    def _result_confirmation_text(self, line: str) -> str:
        return re.sub(r"(?i)^(?:result|outcome)\s*:?\s*", "", line).strip()

    def _compact_signal_text(self, value: str, max_chars: int) -> str:
        compact = " ".join(value.split())
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 3].rstrip() + "..."

    def _compact_confirmation_text(self, value: str, max_chars: int) -> str:
        compact = " ".join(value.split())
        if len(compact) <= max_chars:
            return compact

        match = re.search(r"(?:\s+->\s+|:\s+)[^:>]+$", compact)
        if match is None:
            return self._compact_signal_text(compact, max_chars)

        suffix = compact[match.start() :]
        head_chars = max_chars - len(suffix) - 3
        if head_chars < 24:
            return self._compact_signal_text(compact, max_chars)
        return f"{compact[:head_chars].rstrip()}...{suffix}"

    def _compact_risk_text(self, value: str, max_chars: int) -> str:
        compact = " ".join(value.split())
        if len(compact) <= max_chars:
            return compact
        untracked_summary = self._compact_untracked_risk_text(compact, max_chars)
        if untracked_summary:
            return untracked_summary
        return self._compact_middle_text(compact, max_chars)

    def _compact_untracked_risk_text(self, value: str, max_chars: int) -> str | None:
        if "untracked" not in value.lower():
            return None

        untracked_match = re.search(
            r"((?:src|tests|xmuse|docs)/[^\s,;]+(?:\s+is)?\s+untracked)",
            value,
            flags=re.IGNORECASE,
        )
        if untracked_match is None:
            return None

        prefix = value[: untracked_match.start()].rstrip(" .,;")
        prefix = re.sub(r"\s+(?:and|with)$", "", prefix, flags=re.IGNORECASE).strip()
        if not prefix:
            prefix = value[: max_chars // 3].rstrip(" .,;")
        tracked_diff_match = re.search(
            r"rather\s+than\s+a\s+clean\s+tracked\s+diff\.?",
            value,
            flags=re.IGNORECASE,
        )
        tail = tracked_diff_match.group(0).rstrip(".") + "." if tracked_diff_match else ""

        parts = [prefix.rstrip(" .,;"), untracked_match.group(1).rstrip(" .,;")]
        if tail:
            parts.append(tail)
        summary = "; ".join(parts)
        if len(summary) <= max_chars:
            return summary

        compact_parts = [
            self._compact_signal_text(parts[0], max(24, max_chars // 3)),
            parts[1],
        ]
        if tail:
            compact_parts.append(tail)
        summary = "; ".join(compact_parts)
        if len(summary) <= max_chars:
            return summary

        return self._compact_middle_text(summary, max_chars)

    def _hydrated_selection_policy_version(
        self,
        evidence: StructuredEvidenceBundle,
    ) -> str:
        if evidence.selection_policy_id == _DEFAULT_SELECTION_POLICY_ID:
            return _DEFAULT_SELECTION_POLICY_VERSION
        return evidence.selection_policy_version

    def _merge_refs(self, existing: list[str], additional: list[str]) -> list[str]:
        refs: list[str] = []
        seen: set[str] = set()
        for ref in [*existing, *additional]:
            if ref and ref not in seen:
                refs.append(ref)
                seen.add(ref)
        return refs

    def _relative_ref(self, path: Path) -> str:
        try:
            return path.relative_to(self._root).as_posix()
        except ValueError:
            try:
                return path.relative_to(self._root.parent).as_posix()
            except ValueError:
                return path.as_posix()

    def _resolve_xmuse_ref(self, ref: str) -> Path:
        path = Path(ref)
        return path if path.is_absolute() else self._root / path
