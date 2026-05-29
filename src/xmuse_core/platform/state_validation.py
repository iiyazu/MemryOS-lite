"""Validation framework for xmuse lane state files and transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from xmuse_core.platform.state_normalizer import RAW_LANE_STATUSES, normalize_lane_state


class StateValidationError(ValueError):
    """Raised when a lane state file or transition violates validation rules."""


@dataclass(frozen=True)
class StateValidationIssue:
    validator: str
    message: str
    lane_id: str | None = None

    def render(self) -> str:
        prefix = f"{self.validator}: "
        if self.lane_id:
            return f"{prefix}{self.lane_id}: {self.message}"
        return f"{prefix}{self.message}"


@dataclass(frozen=True)
class StateTransition:
    lane_id: str
    source_status: str
    target_status: str
    before: Mapping[str, Any]
    after: Mapping[str, Any]


@dataclass
class StateValidationReport:
    issues: list[StateValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(
        self,
        validator: str,
        message: str,
        *,
        lane_id: str | None = None,
    ) -> None:
        self.issues.append(
            StateValidationIssue(validator=validator, message=message, lane_id=lane_id)
        )

    def raise_if_invalid(self) -> None:
        if self.issues:
            raise StateValidationError("; ".join(issue.render() for issue in self.issues))


class StateSchemaValidator:
    """Validate the lane-state document and per-lane schema."""

    _LIST_FIELDS = {
        "capabilities",
        "depends_on",
        "gate_profiles",
        "review_evidence_refs",
    }
    _STRING_FIELDS = {
        "feature_id",
        "status",
        "prompt",
        "worktree",
        "graph_id",
        "resolution_id",
        "conversation_id",
        "failure_reason",
        "review_decision",
        "final_action_hold_id",
        "patch_lane_id",
    }
    _NONNEGATIVE_INT_FIELDS = {
        "retry_count",
        "review_retry_count",
        "graph_version",
    }

    def validate_document(self, state: Mapping[str, Any]) -> StateValidationReport:
        report = StateValidationReport()
        if not isinstance(state, Mapping):
            report.add("state_schema", "state must be an object")
            return report
        lanes = state.get("lanes")
        if not isinstance(lanes, list):
            report.add("state_schema", "lanes must be a list")
            return report

        seen_ids: set[str] = set()
        for index, lane in enumerate(lanes):
            if not isinstance(lane, dict):
                report.add("state_schema", f"lanes[{index}] must be an object")
                continue
            self._validate_lane(lane, report)
            lane_id = lane.get("feature_id")
            if isinstance(lane_id, str) and lane_id:
                if lane_id in seen_ids:
                    report.add(
                        "state_schema",
                        "duplicate feature_id",
                        lane_id=lane_id,
                    )
                seen_ids.add(lane_id)
        return report

    def validate_lane(self, lane: Mapping[str, Any]) -> StateValidationReport:
        report = StateValidationReport()
        self._validate_lane(lane, report)
        return report

    def _validate_lane(
        self,
        lane: Mapping[str, Any],
        report: StateValidationReport,
    ) -> None:
        lane_id = lane.get("feature_id")
        if not isinstance(lane_id, str) or not lane_id:
            report.add("state_schema", "feature_id must be a non-empty string")
            lane_id = None

        raw_status = lane.get("status")
        if not isinstance(raw_status, str) or not raw_status:
            report.add(
                "state_schema",
                "status must be a non-empty string",
                lane_id=lane_id,
            )
        elif raw_status not in RAW_LANE_STATUSES:
            report.add(
                "state_schema",
                f"unknown status: {raw_status}",
                lane_id=lane_id,
            )
        else:
            normalize_lane_state(dict(lane))

        for field_name in self._STRING_FIELDS:
            value = lane.get(field_name)
            if value is not None and not isinstance(value, str):
                report.add(
                    "state_schema",
                    f"{field_name} must be a string when present",
                    lane_id=lane_id,
                )

        for field_name in self._LIST_FIELDS:
            value = lane.get(field_name)
            if value is not None and not isinstance(value, list):
                report.add(
                    "state_schema",
                    f"{field_name} must be a list when present",
                    lane_id=lane_id,
                )

        for field_name in self._NONNEGATIVE_INT_FIELDS:
            value = lane.get(field_name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                report.add(
                    "state_schema",
                    f"{field_name} must be a non-negative integer when present",
                    lane_id=lane_id,
                )

        gate_passed = lane.get("gate_passed")
        if gate_passed is not None and not isinstance(gate_passed, bool):
            report.add(
                "state_schema",
                "gate_passed must be a boolean when present",
                lane_id=lane_id,
            )


class TransitionLegalityValidator:
    """Validate that a transition follows the configured lifecycle graph."""

    def __init__(self, transitions: Mapping[str, set[str]]) -> None:
        self._transitions = transitions

    def validate(self, transition: StateTransition) -> StateValidationReport:
        report = StateValidationReport()
        if transition.source_status not in RAW_LANE_STATUSES:
            report.add(
                "transition_legality",
                f"unknown source status: {transition.source_status}",
                lane_id=transition.lane_id,
            )
            return report
        if transition.target_status not in RAW_LANE_STATUSES:
            report.add(
                "transition_legality",
                f"unknown target status: {transition.target_status}",
                lane_id=transition.lane_id,
            )
            return report
        allowed = self._transitions.get(transition.source_status, set())
        if transition.target_status not in allowed:
            report.add(
                "transition_legality",
                f"cannot transition from {transition.source_status} to "
                f"{transition.target_status}",
                lane_id=transition.lane_id,
            )
        return report


class InvariantPreservationValidator:
    """Validate invariants that must survive every state transition."""

    _REVIEW_FAILURE_REASONS = {
        "review_timeout",
        "review_no_verdict",
        "review_non_zero_exit",
        "review_infra_unavailable",
        "review_spawn_failed",
    }
    _REVIEW_DECISIONS = {"merge", "rework", "patch-forward", "terminate"}

    def validate(self, transition: StateTransition) -> StateValidationReport:
        report = StateValidationReport()
        lane_id = transition.lane_id
        before = transition.before
        after = transition.after

        if after.get("feature_id") != before.get("feature_id"):
            report.add(
                "invariant_preservation",
                "feature_id cannot change during transition",
                lane_id=lane_id,
            )
        if after.get("status") != transition.target_status:
            report.add(
                "invariant_preservation",
                "post-transition status does not match target",
                lane_id=lane_id,
            )

        self._validate_monotonic_counter(
            "retry_count",
            before,
            after,
            report,
            lane_id=lane_id,
        )
        self._validate_monotonic_counter(
            "review_retry_count",
            before,
            after,
            report,
            lane_id=lane_id,
        )

        self._validate_lane_invariants(after, report, lane_id=lane_id)

        return report

    def validate_lane(self, lane: Mapping[str, Any]) -> StateValidationReport:
        report = StateValidationReport()
        lane_id = lane.get("feature_id")
        self._validate_lane_invariants(
            lane,
            report,
            lane_id=lane_id if isinstance(lane_id, str) and lane_id else None,
        )
        return report

    def validate_state(self, state: Mapping[str, Any]) -> StateValidationReport:
        report = StateValidationReport()
        lanes = state.get("lanes") if isinstance(state, Mapping) else None
        if not isinstance(lanes, list):
            return report
        for lane in lanes:
            if isinstance(lane, Mapping):
                report.issues.extend(self.validate_lane(lane).issues)
        return report

    def _validate_lane_invariants(
        self,
        lane: Mapping[str, Any],
        report: StateValidationReport,
        *,
        lane_id: str | None,
    ) -> None:
        status = str(lane.get("status"))
        failure_reason = lane.get("failure_reason")
        gate_passed = lane.get("gate_passed")

        if status in {"gated", "reviewed", "awaiting_final_action", "merged"}:
            if gate_passed is False:
                report.add(
                    "invariant_preservation",
                    f"{status} lanes cannot preserve gate_passed=false",
                    lane_id=lane_id,
                )

        if status == "gate_failed":
            if not isinstance(failure_reason, str) or not failure_reason:
                report.add(
                    "invariant_preservation",
                    "gate_failed lanes must record failure_reason",
                    lane_id=lane_id,
                )
            if gate_passed is True and failure_reason not in self._REVIEW_FAILURE_REASONS:
                report.add(
                    "invariant_preservation",
                    "gate_passed=true gate_failed lanes must be review failures",
                    lane_id=lane_id,
                )

        if status == "awaiting_final_action":
            hold_id = lane.get("final_action_hold_id")
            if not isinstance(hold_id, str) or not hold_id:
                report.add(
                    "invariant_preservation",
                    "awaiting_final_action lanes must record final_action_hold_id",
                    lane_id=lane_id,
                )

        review_decision = lane.get("review_decision")
        if review_decision is not None and review_decision not in self._REVIEW_DECISIONS:
            report.add(
                "invariant_preservation",
                f"unknown review_decision: {review_decision}",
                lane_id=lane_id,
            )

    def _validate_monotonic_counter(
        self,
        field_name: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        report: StateValidationReport,
        *,
        lane_id: str,
    ) -> None:
        previous = before.get(field_name, 0)
        current = after.get(field_name, 0)
        if isinstance(previous, bool) or isinstance(current, bool):
            return
        if not isinstance(previous, int) or not isinstance(current, int):
            return
        if current < previous:
            report.add(
                "invariant_preservation",
                f"{field_name} cannot decrease",
                lane_id=lane_id,
            )


class StateTransitionValidator:
    """Composite validator for lane-state documents and transitions."""

    def __init__(self, transitions: Mapping[str, set[str]]) -> None:
        self._schema = StateSchemaValidator()
        self._legality = TransitionLegalityValidator(transitions)
        self._invariants = InvariantPreservationValidator()

    def validate_state(self, state: Mapping[str, Any]) -> StateValidationReport:
        report = self._schema.validate_document(state)
        report.issues.extend(self._invariants.validate_state(state).issues)
        return report

    def validate_lane(self, lane: Mapping[str, Any]) -> StateValidationReport:
        report = self._schema.validate_lane(lane)
        report.issues.extend(self._invariants.validate_lane(lane).issues)
        return report

    def validate_transition(
        self,
        transition: StateTransition,
        *,
        state_after: Mapping[str, Any] | None = None,
    ) -> StateValidationReport:
        report = StateValidationReport()
        for validator_report in (
            self._schema.validate_lane(transition.before),
            self._schema.validate_lane(transition.after),
            self._legality.validate(transition),
            self._invariants.validate(transition),
        ):
            report.issues.extend(validator_report.issues)
        if state_after is not None:
            report.issues.extend(self.validate_state(state_after).issues)
        return report
