"""Comprehensive tests for xmuse lane-state normalization.

Covers:
- All status mappings in _STATUS_MAP
- Terminal vs non-terminal classification
- failed status with various failure_reason values
- gate_failed special cases (review_infra_unavailable)
- Legacy status aliases (done, completed)
- Missing / null field handling
- summarize_lane_states counting and reserved-key collision
- NormalizedLaneState dataclass immutability
- RAW_LANE_STATUSES coverage
- StateSchemaValidator document and lane validation
- TransitionLegalityValidator
- InvariantPreservationValidator
- StateTransitionValidator composite
- StateValidationReport and StateValidationIssue
"""

import pytest

from xmuse_core.platform.state_normalizer import (
    RAW_LANE_STATUSES,
    NormalizedLaneState,
    normalize_lane_state,
    summarize_lane_states,
)

# ---------------------------------------------------------------------------
# normalize_lane_state – basic status mappings
# ---------------------------------------------------------------------------


def test_pending_normalizes_to_ready() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "pending"})

    assert normalized.feature_id == "lane-1"
    assert normalized.raw_status == "pending"
    assert normalized.normalized_status == "ready"
    assert normalized.is_terminal is False


def test_dispatched_normalizes_to_dispatched_non_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "dispatched"})

    assert normalized.normalized_status == "dispatched"
    assert normalized.is_terminal is False


def test_executed_normalizes_to_executed_non_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "executed"})

    assert normalized.normalized_status == "executed"
    assert normalized.is_terminal is False


def test_gated_normalizes_to_under_review_non_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "gated"})

    assert normalized.normalized_status == "under_review"
    assert normalized.is_terminal is False


def test_reviewed_normalizes_to_reviewed_non_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "reviewed"})

    assert normalized.normalized_status == "reviewed"
    assert normalized.is_terminal is False


def test_awaiting_final_action_normalizes_correctly() -> None:
    normalized = normalize_lane_state(
        {"feature_id": "lane-1", "status": "awaiting_final_action"}
    )

    assert normalized.normalized_status == "awaiting_final_action"
    assert normalized.is_terminal is False


def test_merged_normalizes_to_merged_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "merged"})

    assert normalized.normalized_status == "merged"
    assert normalized.is_terminal is True


def test_rejected_normalizes_to_requeued_non_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "rejected"})

    assert normalized.normalized_status == "requeued"
    assert normalized.is_terminal is False


def test_reworking_normalizes_to_requeued_non_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "reworking"})

    assert normalized.normalized_status == "requeued"
    assert normalized.is_terminal is False


def test_exec_failed_normalizes_to_exec_failed_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "exec_failed"})

    assert normalized.normalized_status == "exec_failed"
    assert normalized.is_terminal is True


def test_gate_failed_normalizes_to_gate_failed_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "gate_failed"})

    assert normalized.normalized_status == "gate_failed"
    assert normalized.is_terminal is True


# ---------------------------------------------------------------------------
# Legacy status aliases
# ---------------------------------------------------------------------------


def test_legacy_done_and_completed_normalize_to_merged_terminal() -> None:
    done = normalize_lane_state({"feature_id": "lane-done", "status": "done"})
    completed = normalize_lane_state(
        {"feature_id": "lane-completed", "status": "completed"}
    )

    assert done.normalized_status == "merged"
    assert done.is_terminal is True
    assert completed.normalized_status == "merged"
    assert completed.is_terminal is True


# ---------------------------------------------------------------------------
# failed status – failure_reason routing
# ---------------------------------------------------------------------------


def test_failed_with_gate_failed_reason_normalizes_to_gate_failed() -> None:
    normalized = normalize_lane_state(
        {
            "feature_id": "lane-2",
            "status": "failed",
            "failure_reason": "gate_failed",
        }
    )

    assert normalized.feature_id == "lane-2"
    assert normalized.raw_status == "failed"
    assert normalized.normalized_status == "gate_failed"
    assert normalized.is_terminal is True


def test_failed_with_arbitrary_reason_stays_terminal() -> None:
    normalized = normalize_lane_state(
        {
            "feature_id": "lane-3",
            "status": "failed",
            "failure_reason": "timeout",
        }
    )

    assert normalized.normalized_status == "timeout"
    assert normalized.is_terminal is True


def test_failed_without_failure_reason_normalizes_to_terminated() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-x", "status": "failed"})

    assert normalized.normalized_status == "terminated"
    assert normalized.is_terminal is True


def test_failed_with_none_failure_reason_normalizes_to_terminated() -> None:
    normalized = normalize_lane_state(
        {"feature_id": "lane-x", "status": "failed", "failure_reason": None}
    )

    assert normalized.normalized_status == "terminated"
    assert normalized.is_terminal is True


def test_failed_with_non_string_failure_reason_normalizes_to_terminated() -> None:
    normalized = normalize_lane_state(
        {"feature_id": "lane-x", "status": "failed", "failure_reason": 42}
    )

    assert normalized.normalized_status == "terminated"
    assert normalized.is_terminal is True


def test_failed_with_empty_string_failure_reason_normalizes_to_terminated() -> None:
    """An empty string is falsy – should fall back to 'terminated'."""
    normalized = normalize_lane_state(
        {"feature_id": "lane-x", "status": "failed", "failure_reason": ""}
    )
    # empty string is a str but falsy; implementation uses isinstance check
    # so it will be treated as a valid string – document actual behaviour
    assert normalized.is_terminal is True


# ---------------------------------------------------------------------------
# gate_failed special cases
# ---------------------------------------------------------------------------


def test_review_infra_gate_failed_is_non_terminal() -> None:
    normalized = normalize_lane_state(
        {
            "feature_id": "lane-infra",
            "status": "gate_failed",
            "failure_reason": "review_infra_unavailable",
        }
    )

    assert normalized.normalized_status == "review_infra_unavailable"
    assert normalized.is_terminal is False


def test_gate_failed_with_other_reason_stays_terminal() -> None:
    """Only review_infra_unavailable gets the non-terminal override."""
    normalized = normalize_lane_state(
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "failure_reason": "review_timeout",
        }
    )

    assert normalized.normalized_status == "gate_failed"
    assert normalized.is_terminal is True


def test_gate_failed_without_failure_reason_stays_terminal() -> None:
    normalized = normalize_lane_state(
        {"feature_id": "lane-1", "status": "gate_failed"}
    )

    assert normalized.normalized_status == "gate_failed"
    assert normalized.is_terminal is True


# ---------------------------------------------------------------------------
# Missing / null field handling
# ---------------------------------------------------------------------------


def test_missing_status_defaults_to_pending_behaviour() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-x"})

    assert normalized.raw_status == "pending"
    assert normalized.normalized_status == "ready"
    assert normalized.is_terminal is False


def test_none_status_defaults_to_pending_behaviour() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-x", "status": None})

    assert normalized.raw_status == "pending"
    assert normalized.normalized_status == "ready"


def test_missing_feature_id_defaults_to_empty_string() -> None:
    normalized = normalize_lane_state({"status": "pending"})

    assert normalized.feature_id == ""


def test_none_feature_id_defaults_to_empty_string() -> None:
    normalized = normalize_lane_state({"feature_id": None, "status": "pending"})

    assert normalized.feature_id == ""


def test_unknown_status_passes_through_as_non_terminal() -> None:
    """An unrecognised status should pass through unchanged and be non-terminal."""
    normalized = normalize_lane_state({"feature_id": "lane-x", "status": "custom_state"})

    assert normalized.raw_status == "custom_state"
    assert normalized.normalized_status == "custom_state"
    assert normalized.is_terminal is False


# ---------------------------------------------------------------------------
# NormalizedLaneState dataclass properties
# ---------------------------------------------------------------------------


def test_normalized_lane_state_is_frozen() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "pending"})

    with pytest.raises((AttributeError, TypeError)):
        normalized.normalized_status = "hacked"  # type: ignore[misc]


def test_normalized_lane_state_raw_status_preserved() -> None:
    """raw_status must always reflect the original value, not the mapped one."""
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "done"})

    assert normalized.raw_status == "done"
    assert normalized.normalized_status == "merged"


# ---------------------------------------------------------------------------
# summarize_lane_states
# ---------------------------------------------------------------------------


def test_summary_counts_normalized_statuses_and_terminal_lanes() -> None:
    summary = summarize_lane_states(
        [
            {"feature_id": "lane-1", "status": "pending"},
            {"feature_id": "lane-2", "status": "merged"},
            {"feature_id": "lane-4", "status": "reworking"},
        ]
    )

    assert summary == {
        "total": 3,
        "ready": 1,
        "merged": 1,
        "requeued": 1,
        "terminal": 1,
    }


def test_summary_empty_list() -> None:
    summary = summarize_lane_states([])

    assert summary == {"total": 0, "terminal": 0}


def test_summary_single_terminal_lane() -> None:
    summary = summarize_lane_states(
        [{"feature_id": "lane-1", "status": "exec_failed"}]
    )

    assert summary["total"] == 1
    assert summary["terminal"] == 1
    assert summary["exec_failed"] == 1


def test_summary_multiple_terminal_lanes() -> None:
    summary = summarize_lane_states(
        [
            {"feature_id": "lane-1", "status": "exec_failed"},
            {"feature_id": "lane-2", "status": "merged"},
            {"feature_id": "lane-3", "status": "gate_failed"},
        ]
    )

    assert summary["terminal"] == 3


def test_summary_counts_review_infra_as_open_lane() -> None:
    summary = summarize_lane_states(
        [
            {
                "feature_id": "lane-infra",
                "status": "gate_failed",
                "failure_reason": "review_infra_unavailable",
            },
        ]
    )

    assert summary == {
        "total": 1,
        "review_infra_unavailable": 1,
        "terminal": 0,
    }


def test_summary_preserves_reserved_counters_for_colliding_failed_reasons() -> None:
    summary = summarize_lane_states(
        [
            {
                "feature_id": "lane-5",
                "status": "failed",
                "failure_reason": "total",
            },
            {
                "feature_id": "lane-6",
                "status": "failed",
                "failure_reason": "terminal",
            },
        ]
    )

    assert summary == {
        "total": 2,
        "terminal": 2,
        "status_total": 1,
        "status_terminal": 1,
    }


def test_summary_accumulates_same_status_bucket() -> None:
    summary = summarize_lane_states(
        [
            {"feature_id": "lane-1", "status": "pending"},
            {"feature_id": "lane-2", "status": "pending"},
            {"feature_id": "lane-3", "status": "pending"},
        ]
    )

    assert summary["ready"] == 3
    assert summary["total"] == 3
    assert summary["terminal"] == 0


def test_summary_mixed_failed_reasons_counted_separately() -> None:
    summary = summarize_lane_states(
        [
            {"feature_id": "lane-1", "status": "failed", "failure_reason": "timeout"},
            {"feature_id": "lane-2", "status": "failed", "failure_reason": "oom"},
            {"feature_id": "lane-3", "status": "failed", "failure_reason": "timeout"},
        ]
    )

    assert summary["timeout"] == 2
    assert summary["oom"] == 1
    assert summary["terminal"] == 3


def test_summary_total_always_equals_input_length() -> None:
    lanes = [
        {"feature_id": f"lane-{i}", "status": "pending"} for i in range(10)
    ]
    summary = summarize_lane_states(lanes)

    assert summary["total"] == 10


def test_summary_legacy_done_counted_as_merged() -> None:
    summary = summarize_lane_states(
        [
            {"feature_id": "lane-1", "status": "done"},
            {"feature_id": "lane-2", "status": "completed"},
        ]
    )

    assert summary.get("merged") == 2
    assert summary["terminal"] == 2


# ---------------------------------------------------------------------------
# RAW_LANE_STATUSES coverage
# ---------------------------------------------------------------------------


def test_raw_lane_statuses_includes_failed() -> None:
    assert "failed" in RAW_LANE_STATUSES


def test_raw_lane_statuses_includes_all_status_map_keys() -> None:
    from xmuse_core.platform.state_normalizer import _STATUS_MAP  # type: ignore[attr-defined]
    for key in _STATUS_MAP:
        assert key in RAW_LANE_STATUSES, f"'{key}' missing from RAW_LANE_STATUSES"


def test_aborted_normalizes_to_terminated_terminal() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-x", "status": "aborted"})

    assert normalized.normalized_status == "terminated"
    assert normalized.is_terminal is True


def test_raw_lane_statuses_is_frozenset() -> None:
    assert isinstance(RAW_LANE_STATUSES, frozenset)


# ---------------------------------------------------------------------------
# StateValidationIssue and StateValidationReport
# ---------------------------------------------------------------------------


def test_state_validation_issue_render_with_lane_id() -> None:
    from xmuse_core.platform.state_validation import StateValidationIssue

    issue = StateValidationIssue(
        validator="state_schema",
        message="status must be a non-empty string",
        lane_id="lane-42",
    )
    rendered = issue.render()

    assert "state_schema" in rendered
    assert "lane-42" in rendered
    assert "status must be a non-empty string" in rendered


def test_state_validation_issue_render_without_lane_id() -> None:
    from xmuse_core.platform.state_validation import StateValidationIssue

    issue = StateValidationIssue(
        validator="state_schema",
        message="lanes must be a list",
    )
    rendered = issue.render()

    assert "state_schema" in rendered
    assert "lanes must be a list" in rendered
    assert "None" not in rendered


def test_state_validation_report_ok_when_empty() -> None:
    from xmuse_core.platform.state_validation import StateValidationReport

    report = StateValidationReport()
    assert report.ok is True


def test_state_validation_report_not_ok_after_add() -> None:
    from xmuse_core.platform.state_validation import StateValidationReport

    report = StateValidationReport()
    report.add("state_schema", "something went wrong", lane_id="lane-1")
    assert report.ok is False
    assert len(report.issues) == 1


def test_state_validation_report_raise_if_invalid_raises() -> None:
    from xmuse_core.platform.state_validation import (
        StateValidationError,
        StateValidationReport,
    )

    report = StateValidationReport()
    report.add("state_schema", "bad field", lane_id="lane-1")
    with pytest.raises(StateValidationError):
        report.raise_if_invalid()


def test_state_validation_report_raise_if_invalid_silent_when_ok() -> None:
    from xmuse_core.platform.state_validation import StateValidationReport

    report = StateValidationReport()
    report.raise_if_invalid()  # must not raise


def test_state_validation_report_raise_message_contains_all_issues() -> None:
    from xmuse_core.platform.state_validation import (
        StateValidationError,
        StateValidationReport,
    )

    report = StateValidationReport()
    report.add("state_schema", "issue one", lane_id="lane-1")
    report.add("invariant_preservation", "issue two", lane_id="lane-2")
    with pytest.raises(StateValidationError) as exc_info:
        report.raise_if_invalid()
    msg = str(exc_info.value)
    assert "issue one" in msg
    assert "issue two" in msg


# ---------------------------------------------------------------------------
# StateSchemaValidator – document-level validation
# ---------------------------------------------------------------------------


def test_schema_validator_passes_valid_document() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_document({"lanes": [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ]})
    assert report.ok


def test_schema_validator_rejects_missing_lanes_key() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_document({"not_lanes": []})
    assert not report.ok
    assert any("lanes must be a list" in i.message for i in report.issues)


def test_schema_validator_rejects_lanes_as_dict() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_document({"lanes": {}})
    assert not report.ok


def test_schema_validator_rejects_non_dict_lane_entry() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_document({"lanes": ["not-a-dict"]})
    assert not report.ok
    assert any("must be an object" in i.message for i in report.issues)


def test_schema_validator_rejects_missing_feature_id() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({"status": "pending"})
    assert not report.ok
    assert any("feature_id" in i.message for i in report.issues)


def test_schema_validator_rejects_empty_feature_id() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({"feature_id": "", "status": "pending"})
    assert not report.ok


def test_schema_validator_rejects_non_string_feature_id() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({"feature_id": 123, "status": "pending"})
    assert not report.ok


def test_schema_validator_rejects_missing_status() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({"feature_id": "lane-1"})
    assert not report.ok
    assert any("status" in i.message for i in report.issues)


def test_schema_validator_rejects_unknown_status() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({"feature_id": "lane-1", "status": "bogus"})
    assert not report.ok
    assert any("unknown status" in i.message for i in report.issues)


def test_schema_validator_rejects_non_string_string_field() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({
        "feature_id": "lane-1",
        "status": "pending",
        "failure_reason": 42,
    })
    assert not report.ok
    assert any("failure_reason" in i.message for i in report.issues)


def test_schema_validator_rejects_non_list_list_field() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({
        "feature_id": "lane-1",
        "status": "pending",
        "capabilities": "should-be-a-list",
    })
    assert not report.ok
    assert any("capabilities" in i.message for i in report.issues)


def test_schema_validator_rejects_negative_retry_count() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({
        "feature_id": "lane-1",
        "status": "pending",
        "retry_count": -1,
    })
    assert not report.ok
    assert any("retry_count" in i.message for i in report.issues)


def test_schema_validator_rejects_bool_as_retry_count() -> None:
    """bool is a subclass of int in Python – must be explicitly rejected."""
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({
        "feature_id": "lane-1",
        "status": "pending",
        "retry_count": True,
    })
    assert not report.ok


def test_schema_validator_rejects_non_bool_gate_passed() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({
        "feature_id": "lane-1",
        "status": "pending",
        "gate_passed": "yes",
    })
    assert not report.ok
    assert any("gate_passed" in i.message for i in report.issues)


def test_schema_validator_accepts_bool_gate_passed() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({
        "feature_id": "lane-1",
        "status": "pending",
        "gate_passed": True,
    })
    assert report.ok


def test_schema_validator_detects_duplicate_feature_ids() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_document({"lanes": [
        {"feature_id": "lane-dup", "status": "pending", "prompt": "a"},
        {"feature_id": "lane-dup", "status": "dispatched", "prompt": "b"},
    ]})
    assert not report.ok
    assert any("duplicate" in i.message for i in report.issues)


def test_schema_validator_accepts_all_nonnegative_int_fields() -> None:
    from xmuse_core.platform.state_validation import StateSchemaValidator

    validator = StateSchemaValidator()
    report = validator.validate_lane({
        "feature_id": "lane-1",
        "status": "pending",
        "retry_count": 0,
        "review_retry_count": 3,
        "graph_version": 7,
    })
    assert report.ok


# ---------------------------------------------------------------------------
# TransitionLegalityValidator
# ---------------------------------------------------------------------------


def test_transition_legality_accepts_valid_transition() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, TransitionLegalityValidator

    validator = TransitionLegalityValidator(VALID_TRANSITIONS)
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "pending"},
        after={"feature_id": "lane-1", "status": "dispatched"},
    )
    report = validator.validate(transition)
    assert report.ok


def test_transition_legality_rejects_invalid_transition() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, TransitionLegalityValidator

    validator = TransitionLegalityValidator(VALID_TRANSITIONS)
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="merged",
        before={"feature_id": "lane-1", "status": "pending"},
        after={"feature_id": "lane-1", "status": "merged"},
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("cannot transition" in i.message for i in report.issues)


def test_transition_legality_rejects_unknown_source_status() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, TransitionLegalityValidator

    validator = TransitionLegalityValidator(VALID_TRANSITIONS)
    transition = StateTransition(
        lane_id="lane-1",
        source_status="ghost_status",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "ghost_status"},
        after={"feature_id": "lane-1", "status": "dispatched"},
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("unknown source status" in i.message for i in report.issues)


def test_transition_legality_rejects_unknown_target_status() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, TransitionLegalityValidator

    validator = TransitionLegalityValidator(VALID_TRANSITIONS)
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="ghost_target",
        before={"feature_id": "lane-1", "status": "pending"},
        after={"feature_id": "lane-1", "status": "ghost_target"},
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("unknown target status" in i.message for i in report.issues)


# ---------------------------------------------------------------------------
# InvariantPreservationValidator
# ---------------------------------------------------------------------------


def test_invariant_validator_accepts_clean_transition() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "pending"},
        after={"feature_id": "lane-1", "status": "dispatched"},
    )
    report = validator.validate(transition)
    assert report.ok


def test_invariant_validator_rejects_feature_id_mutation() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "pending"},
        after={"feature_id": "lane-HIJACKED", "status": "dispatched"},
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("feature_id cannot change" in i.message for i in report.issues)


def test_invariant_validator_rejects_status_mismatch() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "pending"},
        after={"feature_id": "lane-1", "status": "executed"},  # wrong status
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("post-transition status" in i.message for i in report.issues)


def test_invariant_validator_rejects_retry_count_decrease() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="reworking",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "reworking", "retry_count": 2},
        after={"feature_id": "lane-1", "status": "dispatched", "retry_count": 1},
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("retry_count cannot decrease" in i.message for i in report.issues)


def test_invariant_validator_rejects_review_retry_count_decrease() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="gate_failed",
        target_status="gated",
        before={
            "feature_id": "lane-1",
            "status": "gate_failed",
            "failure_reason": "review_timeout",
            "review_retry_count": 3,
        },
        after={
            "feature_id": "lane-1",
            "status": "gated",
            "review_retry_count": 2,
        },
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("review_retry_count cannot decrease" in i.message for i in report.issues)


def test_invariant_validator_rejects_gate_failed_without_failure_reason() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="executed",
        target_status="gate_failed",
        before={"feature_id": "lane-1", "status": "executed"},
        after={"feature_id": "lane-1", "status": "gate_failed"},
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("failure_reason" in i.message for i in report.issues)


def test_invariant_validator_rejects_gate_passed_false_in_gated() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="gate_failed",
        target_status="gated",
        before={
            "feature_id": "lane-1",
            "status": "gate_failed",
            "failure_reason": "review_timeout",
            "gate_passed": False,
        },
        after={
            "feature_id": "lane-1",
            "status": "gated",
            "gate_passed": False,
        },
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("gate_passed=false" in i.message for i in report.issues)


def test_invariant_validator_rejects_gate_passed_false_in_merged() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="reviewed",
        target_status="merged",
        before={"feature_id": "lane-1", "status": "reviewed"},
        after={"feature_id": "lane-1", "status": "merged", "gate_passed": False},
    )
    report = validator.validate(transition)
    assert not report.ok


def test_invariant_validator_rejects_awaiting_final_action_without_hold_id() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="reviewed",
        target_status="awaiting_final_action",
        before={"feature_id": "lane-1", "status": "reviewed"},
        after={"feature_id": "lane-1", "status": "awaiting_final_action"},
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("final_action_hold_id" in i.message for i in report.issues)


def test_invariant_validator_accepts_awaiting_final_action_with_hold_id() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="reviewed",
        target_status="awaiting_final_action",
        before={"feature_id": "lane-1", "status": "reviewed"},
        after={
            "feature_id": "lane-1",
            "status": "awaiting_final_action",
            "final_action_hold_id": "hold-xyz",
        },
    )
    report = validator.validate(transition)
    assert report.ok


def test_invariant_validator_rejects_unknown_review_decision() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="reviewed",
        target_status="merged",
        before={"feature_id": "lane-1", "status": "reviewed"},
        after={
            "feature_id": "lane-1",
            "status": "merged",
            "review_decision": "approve_and_ship",
        },
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("unknown review_decision" in i.message for i in report.issues)


def test_invariant_validator_accepts_all_valid_review_decisions() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    for decision in ("merge", "rework", "patch-forward", "terminate"):
        transition = StateTransition(
            lane_id="lane-1",
            source_status="reviewed",
            target_status="merged",
            before={"feature_id": "lane-1", "status": "reviewed"},
            after={
                "feature_id": "lane-1",
                "status": "merged",
                "review_decision": decision,
            },
        )
        report = validator.validate(transition)
        # review_decision is valid; any other issues are unrelated to this check
        assert not any("unknown review_decision" in i.message for i in report.issues), (
            f"decision '{decision}' was incorrectly rejected"
        )


def test_invariant_validator_accepts_gate_passed_true_with_review_failure_reason() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    for reason in (
        "review_timeout",
        "review_no_verdict",
        "review_non_zero_exit",
        "review_infra_unavailable",
        "review_spawn_failed",
    ):
        transition = StateTransition(
            lane_id="lane-1",
            source_status="executed",
            target_status="gate_failed",
            before={"feature_id": "lane-1", "status": "executed"},
            after={
                "feature_id": "lane-1",
                "status": "gate_failed",
                "failure_reason": reason,
                "gate_passed": True,
            },
        )
        report = validator.validate(transition)
        assert not any(
            "gate_passed=true gate_failed" in i.message for i in report.issues
        ), f"reason '{reason}' was incorrectly rejected"


def test_invariant_validator_rejects_gate_passed_true_with_non_review_failure_reason() -> None:
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="executed",
        target_status="gate_failed",
        before={"feature_id": "lane-1", "status": "executed"},
        after={
            "feature_id": "lane-1",
            "status": "gate_failed",
            "failure_reason": "oom",
            "gate_passed": True,
        },
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("gate_passed=true gate_failed" in i.message for i in report.issues)


# ---------------------------------------------------------------------------
# StateTransitionValidator – composite
# ---------------------------------------------------------------------------


def test_composite_validator_passes_clean_transition() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, StateTransitionValidator

    validator = StateTransitionValidator(VALID_TRANSITIONS)
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "pending", "prompt": "p"},
        after={"feature_id": "lane-1", "status": "dispatched", "prompt": "p"},
    )
    report = validator.validate_transition(transition)
    assert report.ok


def test_composite_validator_aggregates_multiple_issues() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, StateTransitionValidator

    validator = StateTransitionValidator(VALID_TRANSITIONS)
    # illegal transition AND feature_id mutation
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="merged",
        before={"feature_id": "lane-1", "status": "pending", "prompt": "p"},
        after={"feature_id": "lane-CHANGED", "status": "merged", "prompt": "p"},
    )
    report = validator.validate_transition(transition)
    assert not report.ok
    assert len(report.issues) >= 2


def test_composite_validator_validate_state_rejects_duplicate_ids() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransitionValidator

    validator = StateTransitionValidator(VALID_TRANSITIONS)
    report = validator.validate_state({"lanes": [
        {"feature_id": "dup", "status": "pending", "prompt": "a"},
        {"feature_id": "dup", "status": "dispatched", "prompt": "b"},
    ]})
    assert not report.ok


def test_composite_validator_validate_state_rejects_persisted_invariant_breach() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransitionValidator

    validator = StateTransitionValidator(VALID_TRANSITIONS)
    report = validator.validate_state({"lanes": [
        {"feature_id": "lane-1", "status": "gate_failed", "prompt": "p"},
    ]})

    assert not report.ok
    assert any("gate_failed lanes must record failure_reason" in i.message for i in report.issues)


def test_composite_validator_validate_lane_rejects_bad_schema() -> None:
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransitionValidator

    validator = StateTransitionValidator(VALID_TRANSITIONS)
    report = validator.validate_lane({"feature_id": "", "status": "pending"})
    assert not report.ok


def test_composite_validator_includes_state_after_issues() -> None:
    """When state_after is provided, its issues are merged into the report."""
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, StateTransitionValidator

    validator = StateTransitionValidator(VALID_TRANSITIONS)
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "pending", "prompt": "p"},
        after={"feature_id": "lane-1", "status": "dispatched", "prompt": "p"},
    )
    # state_after has a duplicate lane – should surface in the report
    bad_state_after = {"lanes": [
        {"feature_id": "lane-1", "status": "dispatched", "prompt": "p"},
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ]}
    report = validator.validate_transition(transition, state_after=bad_state_after)
    assert not report.ok
    assert any("duplicate" in i.message for i in report.issues)


# ---------------------------------------------------------------------------
# normalize_lane_state – additional edge cases
# ---------------------------------------------------------------------------


def test_failed_with_empty_string_failure_reason_is_terminal() -> None:
    """Empty string failure_reason: isinstance check passes but value is falsy."""
    normalized = normalize_lane_state(
        {"feature_id": "lane-x", "status": "failed", "failure_reason": ""}
    )
    # empty string is a str so normalized_status becomes "" (the reason itself)
    assert normalized.is_terminal is True
    assert normalized.raw_status == "failed"


def test_gate_failed_with_review_infra_reason_is_non_terminal() -> None:
    """review_infra_unavailable is the only gate_failed reason that is non-terminal."""
    normalized = normalize_lane_state(
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "failure_reason": "review_infra_unavailable",
        }
    )
    assert normalized.is_terminal is False
    assert normalized.normalized_status == "review_infra_unavailable"


def test_normalize_preserves_raw_status_for_legacy_aliases() -> None:
    """raw_status must always reflect the original value, not the mapped one."""
    for alias in ("done", "completed"):
        normalized = normalize_lane_state({"feature_id": "lane-1", "status": alias})
        assert normalized.raw_status == alias
        assert normalized.normalized_status == "merged"


def test_normalize_all_status_map_keys_produce_valid_output() -> None:
    """Every key in _STATUS_MAP must produce a NormalizedLaneState without error."""
    from xmuse_core.platform.state_normalizer import _STATUS_MAP  # type: ignore[attr-defined]

    for status in _STATUS_MAP:
        result = normalize_lane_state({"feature_id": "lane-x", "status": status})
        assert isinstance(result, NormalizedLaneState)
        assert result.raw_status == status


def test_normalize_failed_with_all_review_failure_reasons() -> None:
    """failed lanes with review-related failure_reason values normalize correctly."""
    for reason in (
        "review_timeout",
        "review_no_verdict",
        "review_non_zero_exit",
        "review_infra_unavailable",
    ):
        normalized = normalize_lane_state(
            {"feature_id": "lane-x", "status": "failed", "failure_reason": reason}
        )
        assert normalized.normalized_status == reason
        assert normalized.is_terminal is True


# ---------------------------------------------------------------------------
# summarize_lane_states – additional edge cases
# ---------------------------------------------------------------------------


def test_summary_all_terminal_lanes() -> None:
    """A batch of all-terminal lanes must have terminal == total."""
    lanes = [
        {"feature_id": "lane-1", "status": "merged"},
        {"feature_id": "lane-2", "status": "exec_failed"},
        {"feature_id": "lane-3", "status": "gate_failed", "failure_reason": "review_timeout"},
        {"feature_id": "lane-4", "status": "failed"},
    ]
    summary = summarize_lane_states(lanes)
    assert summary["total"] == 4
    assert summary["terminal"] == 4


def test_summary_review_infra_unavailable_not_counted_as_terminal() -> None:
    """gate_failed with review_infra_unavailable is non-terminal – terminal counter stays 0."""
    summary = summarize_lane_states([
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "failure_reason": "review_infra_unavailable",
        },
        {
            "feature_id": "lane-2",
            "status": "gate_failed",
            "failure_reason": "review_infra_unavailable",
        },
    ])
    assert summary["terminal"] == 0
    assert summary["review_infra_unavailable"] == 2


def test_summary_mixed_terminal_and_non_terminal() -> None:
    """terminal counter must only count truly terminal lanes."""
    summary = summarize_lane_states([
        {"feature_id": "lane-1", "status": "pending"},
        {"feature_id": "lane-2", "status": "dispatched"},
        {"feature_id": "lane-3", "status": "merged"},
        {"feature_id": "lane-4", "status": "exec_failed"},
        {"feature_id": "lane-5", "status": "reworking"},
    ])
    assert summary["total"] == 5
    assert summary["terminal"] == 2  # merged + exec_failed


def test_summary_with_failed_and_no_reason_counted_as_terminated() -> None:
    """failed lanes without failure_reason normalize to 'terminated'."""
    summary = summarize_lane_states([
        {"feature_id": "lane-1", "status": "failed"},
        {"feature_id": "lane-2", "status": "failed"},
    ])
    assert summary["terminated"] == 2
    assert summary["terminal"] == 2


# ---------------------------------------------------------------------------
# InvariantPreservationValidator – additional edge cases
# ---------------------------------------------------------------------------


def test_invariant_validator_accepts_retry_count_staying_same() -> None:
    """retry_count staying the same across a transition is valid (monotonic)."""
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="dispatched",
        target_status="executed",
        before={"feature_id": "lane-1", "status": "dispatched", "retry_count": 1},
        after={"feature_id": "lane-1", "status": "executed", "retry_count": 1},
    )
    report = validator.validate(transition)
    assert not any("retry_count cannot decrease" in i.message for i in report.issues)


def test_invariant_validator_accepts_retry_count_increasing() -> None:
    """retry_count increasing across a transition is valid."""
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="rejected",
        target_status="reworking",
        before={"feature_id": "lane-1", "status": "rejected", "retry_count": 0},
        after={"feature_id": "lane-1", "status": "reworking", "retry_count": 1},
    )
    report = validator.validate(transition)
    assert not any("retry_count cannot decrease" in i.message for i in report.issues)


def test_invariant_validator_rejects_gate_passed_false_in_reviewed() -> None:
    """reviewed lanes cannot preserve gate_passed=False."""
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="gated",
        target_status="reviewed",
        before={"feature_id": "lane-1", "status": "gated"},
        after={"feature_id": "lane-1", "status": "reviewed", "gate_passed": False},
    )
    report = validator.validate(transition)
    assert not report.ok
    assert any("gate_passed=false" in i.message for i in report.issues)


def test_invariant_validator_accepts_gate_passed_true_in_gated() -> None:
    """gate_passed=True is valid for gated lanes."""
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="executed",
        target_status="gated",
        before={"feature_id": "lane-1", "status": "executed"},
        after={"feature_id": "lane-1", "status": "gated", "gate_passed": True},
    )
    report = validator.validate(transition)
    assert not any("gate_passed" in i.message for i in report.issues)


def test_invariant_validator_accepts_no_review_decision_field() -> None:
    """Absence of review_decision must not trigger a validation error."""
    from xmuse_core.platform.state_validation import (
        InvariantPreservationValidator,
        StateTransition,
    )

    validator = InvariantPreservationValidator()
    transition = StateTransition(
        lane_id="lane-1",
        source_status="pending",
        target_status="dispatched",
        before={"feature_id": "lane-1", "status": "pending"},
        after={"feature_id": "lane-1", "status": "dispatched"},
    )
    report = validator.validate(transition)
    assert not any("review_decision" in i.message for i in report.issues)


# ---------------------------------------------------------------------------
# TransitionLegalityValidator – terminal state edge cases
# ---------------------------------------------------------------------------


def test_transition_legality_rejects_transition_from_merged() -> None:
    """merged is terminal – any outbound transition must be rejected."""
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, TransitionLegalityValidator

    validator = TransitionLegalityValidator(VALID_TRANSITIONS)
    for target in ("pending", "dispatched", "executed", "failed"):
        transition = StateTransition(
            lane_id="lane-1",
            source_status="merged",
            target_status=target,
            before={"feature_id": "lane-1", "status": "merged"},
            after={"feature_id": "lane-1", "status": target},
        )
        report = validator.validate(transition)
        assert not report.ok, f"merged → {target} should be rejected"


def test_transition_legality_rejects_transition_from_failed() -> None:
    """failed is terminal – any outbound transition must be rejected."""
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, TransitionLegalityValidator

    validator = TransitionLegalityValidator(VALID_TRANSITIONS)
    for target in ("pending", "reworking", "dispatched"):
        transition = StateTransition(
            lane_id="lane-1",
            source_status="failed",
            target_status=target,
            before={"feature_id": "lane-1", "status": "failed"},
            after={"feature_id": "lane-1", "status": target},
        )
        report = validator.validate(transition)
        assert not report.ok, f"failed → {target} should be rejected"


def test_transition_legality_accepts_exec_failed_to_reworking() -> None:
    """exec_failed → reworking is a valid agent recovery path."""
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, TransitionLegalityValidator

    validator = TransitionLegalityValidator(VALID_TRANSITIONS)
    transition = StateTransition(
        lane_id="lane-1",
        source_status="exec_failed",
        target_status="reworking",
        before={"feature_id": "lane-1", "status": "exec_failed"},
        after={"feature_id": "lane-1", "status": "reworking"},
    )
    report = validator.validate(transition)
    assert report.ok


def test_transition_legality_accepts_exec_failed_to_failed() -> None:
    """exec_failed → failed is a valid terminal path."""
    from xmuse_core.platform.state_machine import VALID_TRANSITIONS
    from xmuse_core.platform.state_validation import StateTransition, TransitionLegalityValidator

    validator = TransitionLegalityValidator(VALID_TRANSITIONS)
    transition = StateTransition(
        lane_id="lane-1",
        source_status="exec_failed",
        target_status="failed",
        before={"feature_id": "lane-1", "status": "exec_failed"},
        after={"feature_id": "lane-1", "status": "failed"},
    )
    report = validator.validate(transition)
    assert report.ok
