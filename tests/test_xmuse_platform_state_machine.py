"""Comprehensive tests for LaneStateMachine state validation framework.

Covers:
- Valid and invalid state transitions across the full lifecycle
- Schema violations (missing fields, unknown lanes)
- Invariant breaches (retry limits, terminal state locks)
- Edge cases in agent lifecycle and orchestrator state changes
- Metadata persistence and field cleanup semantics
- Multi-lane orchestrator scenarios
"""

import json

import pytest

from xmuse_core.platform.state_machine import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    LaneStateMachine,
)
from xmuse_core.platform.state_validation import StateValidationError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def lanes_path(tmp_path):
    path = tmp_path / "feature_lanes.json"
    path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "pending", "prompt": "fix bug"},
    ]}))
    return path


@pytest.fixture
def sm(lanes_path):
    return LaneStateMachine(lanes_path)


def _make_sm(tmp_path, lanes: list) -> tuple:
    """Helper: write lanes JSON and return (path, LaneStateMachine)."""
    path = tmp_path / "feature_lanes.json"
    path.write_text(json.dumps({"lanes": lanes}))
    return path, LaneStateMachine(path)


# ---------------------------------------------------------------------------
# Valid transitions – happy path
# ---------------------------------------------------------------------------


def test_valid_transition_pending_to_dispatched(sm):
    sm.transition("lane-1", "dispatched")
    assert sm.get_lane("lane-1")["status"] == "dispatched"


def test_full_happy_path_lifecycle(tmp_path):
    """pending → dispatched → executed → gated → reviewed → merged."""
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "add feature"},
    ])
    for target in ("dispatched", "executed", "gated", "reviewed", "merged"):
        sm.transition("lane-1", target)
    assert sm.get_lane("lane-1")["status"] == "merged"


def test_dispatched_to_exec_failed(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "dispatched", "prompt": "p"},
    ])
    sm.transition("lane-1", "exec_failed")
    assert sm.get_lane("lane-1")["status"] == "exec_failed"


def test_exec_failed_to_failed(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "exec_failed", "prompt": "p"},
    ])
    sm.transition("lane-1", "failed")
    assert sm.get_lane("lane-1")["status"] == "failed"


def test_gated_to_rejected(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "gated", "prompt": "p"},
    ])
    sm.transition("lane-1", "rejected")
    assert sm.get_lane("lane-1")["status"] == "rejected"


def test_reviewed_to_awaiting_final_action(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "p"},
    ])
    sm.transition(
        "lane-1",
        "awaiting_final_action",
        metadata={"final_action_hold_id": "hold-1"},
    )
    assert sm.get_lane("lane-1")["status"] == "awaiting_final_action"


def test_awaiting_final_action_to_merged(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "awaiting_final_action", "prompt": "p"},
    ])
    sm.transition("lane-1", "merged")
    assert sm.get_lane("lane-1")["status"] == "merged"


def test_awaiting_final_action_to_failed(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "awaiting_final_action", "prompt": "p"},
    ])
    sm.transition("lane-1", "failed")
    assert sm.get_lane("lane-1")["status"] == "failed"


def test_gate_failed_to_reworking(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "gate_failed", "prompt": "p"},
    ])
    sm.transition("lane-1", "reworking")
    assert sm.get_lane("lane-1")["status"] == "reworking"


def test_gate_failed_to_failed(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "gate_failed", "prompt": "p"},
    ])
    sm.transition("lane-1", "failed")
    assert sm.get_lane("lane-1")["status"] == "failed"


# ---------------------------------------------------------------------------
# Invalid transitions – schema violations
# ---------------------------------------------------------------------------


def test_invalid_transition_pending_to_merged_raises(sm):
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "merged")


def test_invalid_transition_pending_to_executed_raises(sm):
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "executed")


def test_invalid_transition_pending_to_gated_raises(sm):
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "gated")


def test_invalid_transition_pending_to_failed_raises(sm):
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "failed")


def test_invalid_transition_dispatched_to_merged_raises(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "dispatched", "prompt": "p"},
    ])
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "merged")


def test_invalid_transition_executed_to_dispatched_raises(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "executed", "prompt": "p"},
    ])
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "dispatched")


def test_invalid_transition_merged_to_anything_raises(tmp_path):
    """merged is a terminal state – no outbound transitions exist."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "merged", "prompt": "p"},
    ])
    for target in ("pending", "dispatched", "executed", "gated", "reviewed", "failed"):
        with pytest.raises(InvalidTransitionError):
            sm.transition("lane-1", target)


def test_invalid_transition_failed_to_anything_raises(tmp_path):
    """failed is a terminal state – no outbound transitions exist."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "failed", "prompt": "p"},
    ])
    for target in ("pending", "dispatched", "reworking", "merged"):
        with pytest.raises(InvalidTransitionError):
            sm.transition("lane-1", target)


def test_invalid_transition_error_message_contains_lane_and_states(sm):
    with pytest.raises(InvalidTransitionError, match="lane-1"):
        sm.transition("lane-1", "merged")


def test_invalid_transition_to_unknown_status_raises(sm):
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "nonexistent_status")


def test_invalid_transition_reviewed_to_dispatched_raises(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "p"},
    ])
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "dispatched")


# ---------------------------------------------------------------------------
# Invariant breaches – retry / rework depth
# ---------------------------------------------------------------------------


def test_rework_depth_limit(lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "fix",
         "retry_count": 2},
    ]}))
    sm = LaneStateMachine(lanes_path)
    with pytest.raises(InvalidTransitionError, match="max retries"):
        sm.transition("lane-1", "reworking")


def test_rework_depth_limit_at_exact_boundary(tmp_path):
    """retry_count == MAX_RETRIES should be blocked."""
    from xmuse_core.platform.state_machine import MAX_RETRIES
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "p",
         "retry_count": MAX_RETRIES},
    ])
    with pytest.raises(InvalidTransitionError, match="max retries"):
        sm.transition("lane-1", "reworking")


def test_rework_allowed_below_depth_limit(tmp_path):
    """retry_count == MAX_RETRIES - 1 should succeed."""
    from xmuse_core.platform.state_machine import MAX_RETRIES
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "p",
         "retry_count": MAX_RETRIES - 1},
    ])
    lane = sm.transition("lane-1", "reworking")
    assert lane["status"] == "reworking"
    assert lane["retry_count"] == MAX_RETRIES


def test_rework_increments_retry_count(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "p",
         "retry_count": 0},
    ])
    lane = sm.transition("lane-1", "reworking")
    assert lane["retry_count"] == 1


def test_rework_initialises_retry_count_when_absent(tmp_path):
    """A lane with no retry_count field should start at 1 after first rework."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "p"},
    ])
    lane = sm.transition("lane-1", "reworking")
    assert lane["retry_count"] == 1


# ---------------------------------------------------------------------------
# Field cleanup semantics
# ---------------------------------------------------------------------------


def test_reworking_clears_stale_failure_reason(lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "exec_failed",
            "prompt": "fix",
            "failure_reason": "non_zero_exit",
        },
    ]}))
    sm = LaneStateMachine(lanes_path)

    lane = sm.transition("lane-1", "reworking")

    assert lane["status"] == "reworking"
    assert "failure_reason" not in lane


def test_dispatched_clears_stale_failure_reason(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {
            "feature_id": "lane-1",
            "status": "reworking",
            "prompt": "p",
            "failure_reason": "old_reason",
        },
    ])
    lane = sm.transition("lane-1", "dispatched")
    assert "failure_reason" not in lane


def test_gated_clears_stale_failure_reason(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "p",
            "failure_reason": "review_timeout",
        },
    ])
    lane = sm.transition("lane-1", "gated")
    assert "failure_reason" not in lane


def test_failure_reason_preserved_on_non_clearing_transitions(tmp_path):
    """failure_reason should NOT be cleared when transitioning to exec_failed."""
    _, sm = _make_sm(tmp_path, [
        {
            "feature_id": "lane-1",
            "status": "dispatched",
            "prompt": "p",
        },
    ])
    lane = sm.transition("lane-1", "exec_failed", metadata={"failure_reason": "oom"})
    assert lane.get("failure_reason") == "oom"


# ---------------------------------------------------------------------------
# Metadata persistence
# ---------------------------------------------------------------------------


def test_transition_with_metadata(sm):
    sm.transition("lane-1", "dispatched", metadata={"assigned_to": "codex"})
    lane = sm.get_lane("lane-1")
    assert lane["assigned_to"] == "codex"


def test_transition_persists_to_file(sm, lanes_path):
    sm.transition("lane-1", "dispatched")
    data = json.loads(lanes_path.read_text())
    assert data["lanes"][0]["status"] == "dispatched"


def test_metadata_persists_to_file(tmp_path):
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    sm.transition("lane-1", "dispatched", metadata={"agent": "claude-code", "run_id": "r1"})
    data = json.loads(path.read_text())
    lane = data["lanes"][0]
    assert lane["agent"] == "claude-code"
    assert lane["run_id"] == "r1"


def test_metadata_does_not_overwrite_status(sm):
    """Metadata dict must not be able to silently override the status field."""
    sm.transition("lane-1", "dispatched", metadata={"status": "merged"})
    # status is set after metadata merge in the implementation, so it wins
    assert sm.get_lane("lane-1")["status"] == "dispatched"


def test_update_metadata_without_transition(tmp_path):
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    sm.update_metadata("lane-1", {"extra": "value"})
    assert sm.get_lane("lane-1")["extra"] == "value"
    assert sm.get_lane("lane-1")["status"] == "pending"


def test_update_metadata_persists_to_file(tmp_path):
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    sm.update_metadata("lane-1", {"tag": "hotfix"})
    data = json.loads(path.read_text())
    assert data["lanes"][0]["tag"] == "hotfix"


def test_update_metadata_unknown_lane_raises(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    with pytest.raises(KeyError):
        sm.update_metadata("ghost-lane", {"x": 1})


# ---------------------------------------------------------------------------
# Schema / lookup edge cases
# ---------------------------------------------------------------------------


def test_get_lanes_by_status(sm):
    assert len(sm.get_lanes(status="pending")) == 1
    assert len(sm.get_lanes(status="dispatched")) == 0


def test_get_lanes_no_filter_returns_all(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
        {"feature_id": "lane-2", "status": "dispatched", "prompt": "q"},
    ])
    assert len(sm.get_lanes()) == 2


def test_get_lanes_empty_file(tmp_path):
    path = tmp_path / "feature_lanes.json"
    path.write_text(json.dumps({"lanes": []}))
    sm = LaneStateMachine(path)
    assert sm.get_lanes() == []


def test_unknown_lane_raises(sm):
    with pytest.raises(KeyError):
        sm.transition("nonexistent", "dispatched")


def test_get_lane_unknown_raises(sm):
    with pytest.raises(KeyError):
        sm.get_lane("ghost")


def test_lane_with_missing_status_defaults_to_pending(tmp_path):
    """A lane dict without a 'status' key should behave as if status=pending."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "prompt": "p"},
    ])
    lane = sm.transition("lane-1", "dispatched")
    assert lane["status"] == "dispatched"


# ---------------------------------------------------------------------------
# Review / gate recovery edge cases
# ---------------------------------------------------------------------------


def test_review_timeout_can_recover_to_gated(lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "fix",
            "gate_passed": True,
            "failure_reason": "review_timeout",
        },
    ]}))
    sm = LaneStateMachine(lanes_path)

    lane = sm.transition("lane-1", "gated", metadata={"review_retry_count": 1})

    assert lane["status"] == "gated"
    assert lane["review_retry_count"] == 1
    assert "failure_reason" not in lane


def test_validate_rejects_duplicate_lane_ids(lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "pending", "prompt": "fix"},
        {"feature_id": "lane-1", "status": "pending", "prompt": "fix again"},
    ]}))
    sm = LaneStateMachine(lanes_path)

    with pytest.raises(StateValidationError, match="duplicate feature_id"):
        sm.validate()


def test_transition_rejects_malformed_lane_schema(lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "pending",
            "prompt": "fix",
            "retry_count": -1,
        },
    ]}))
    sm = LaneStateMachine(lanes_path)

    with pytest.raises(StateValidationError, match="retry_count"):
        sm.transition("lane-1", "dispatched")

    assert json.loads(lanes_path.read_text())["lanes"][0]["status"] == "pending"


def test_transition_rejects_gate_failed_without_failure_reason(lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "executed", "prompt": "fix"},
    ]}))
    sm = LaneStateMachine(lanes_path)

    with pytest.raises(StateValidationError, match="failure_reason"):
        sm.transition("lane-1", "gate_failed")

    assert json.loads(lanes_path.read_text())["lanes"][0]["status"] == "executed"


def test_transition_rejects_broken_gate_invariant(lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {
            "feature_id": "lane-1",
            "status": "executed",
            "prompt": "fix",
            "gate_passed": False,
        },
    ]}))
    sm = LaneStateMachine(lanes_path)

    with pytest.raises(StateValidationError, match="gate_passed=false"):
        sm.transition("lane-1", "gated")


def test_gate_failed_cannot_go_directly_to_reviewed(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "gate_failed", "prompt": "p"},
    ])
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "reviewed")


def test_gate_failed_cannot_go_directly_to_merged(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "gate_failed", "prompt": "p"},
    ])
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "merged")


def test_reviewed_to_failed_is_valid(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "p"},
    ])
    lane = sm.transition("lane-1", "failed")
    assert lane["status"] == "failed"


def test_exec_failed_to_reworking_is_valid(tmp_path):
    """exec_failed → reworking is a valid agent-lifecycle recovery path."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "exec_failed", "prompt": "p"},
    ])
    lane = sm.transition("lane-1", "reworking")
    assert lane["status"] == "reworking"


def test_rejected_to_failed_is_valid(tmp_path):
    """rejected → failed is a valid terminal path when retries are exhausted."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "p"},
    ])
    lane = sm.transition("lane-1", "failed")
    assert lane["status"] == "failed"


def test_gated_to_gate_failed_is_valid(tmp_path):
    """gated → gate_failed is a valid path when the review gate rejects."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "gated", "prompt": "p"},
    ])
    lane = sm.transition(
        "lane-1", "gate_failed",
        metadata={"failure_reason": "review_timeout"},
    )
    assert lane["status"] == "gate_failed"
    assert lane["failure_reason"] == "review_timeout"


# ---------------------------------------------------------------------------
# Multi-lane orchestrator scenarios
# ---------------------------------------------------------------------------


def test_multiple_lanes_independent_transitions(tmp_path):
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-A", "status": "pending", "prompt": "a"},
        {"feature_id": "lane-B", "status": "pending", "prompt": "b"},
    ])
    sm.transition("lane-A", "dispatched")
    # lane-B must remain unaffected
    assert sm.get_lane("lane-B")["status"] == "pending"
    assert sm.get_lane("lane-A")["status"] == "dispatched"


def test_multiple_lanes_different_lifecycle_stages(tmp_path):
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-A", "status": "pending", "prompt": "a"},
        {"feature_id": "lane-B", "status": "dispatched", "prompt": "b"},
        {"feature_id": "lane-C", "status": "merged", "prompt": "c"},
    ])
    sm.transition("lane-A", "dispatched")
    sm.transition("lane-B", "executed")

    assert sm.get_lane("lane-A")["status"] == "dispatched"
    assert sm.get_lane("lane-B")["status"] == "executed"
    assert sm.get_lane("lane-C")["status"] == "merged"


def test_get_lanes_by_status_multi_lane(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-A", "status": "pending", "prompt": "a"},
        {"feature_id": "lane-B", "status": "pending", "prompt": "b"},
        {"feature_id": "lane-C", "status": "dispatched", "prompt": "c"},
    ])
    pending = sm.get_lanes(status="pending")
    assert len(pending) == 2
    assert all(lane["status"] == "pending" for lane in pending)


def test_transition_only_mutates_target_lane_in_file(tmp_path):
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-A", "status": "pending", "prompt": "a"},
        {"feature_id": "lane-B", "status": "pending", "prompt": "b"},
    ])
    sm.transition("lane-A", "dispatched")
    data = json.loads(path.read_text())
    lane_b = next(lane for lane in data["lanes"] if lane["feature_id"] == "lane-B")
    assert lane_b["status"] == "pending"


# ---------------------------------------------------------------------------
# VALID_TRANSITIONS graph invariants
# ---------------------------------------------------------------------------


def test_valid_transitions_map_has_no_self_loops():
    """A state should never list itself as a valid target."""
    for source, targets in VALID_TRANSITIONS.items():
        assert source not in targets, f"{source} has a self-loop"


def test_terminal_states_have_no_outbound_transitions():
    """merged and failed must not appear as keys in VALID_TRANSITIONS."""
    terminal = {"merged", "failed"}
    for state in terminal:
        assert state not in VALID_TRANSITIONS, (
            f"terminal state '{state}' has outbound transitions"
        )


def test_all_transition_targets_are_known_states():
    """Every target in VALID_TRANSITIONS must itself be a known source or terminal."""
    all_states = set(VALID_TRANSITIONS) | {"merged", "failed"}
    for source, targets in VALID_TRANSITIONS.items():
        for target in targets:
            assert target in all_states, (
                f"transition target '{target}' from '{source}' is not a known state"
            )


# ---------------------------------------------------------------------------
# append_lane
# ---------------------------------------------------------------------------


def test_append_lane_adds_new_lane(tmp_path):
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    sm.append_lane({"feature_id": "lane-2", "status": "pending", "prompt": "q"})
    assert len(sm.get_lanes()) == 2
    assert sm.get_lane("lane-2")["status"] == "pending"


def test_append_lane_is_idempotent_for_duplicate_feature_id(tmp_path):
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    sm.append_lane({"feature_id": "lane-1", "status": "dispatched", "prompt": "dup"})
    # original lane must be unchanged; no duplicate added
    assert len(sm.get_lanes()) == 1
    assert sm.get_lane("lane-1")["status"] == "pending"


def test_append_lane_persists_to_file(tmp_path):
    path, sm = _make_sm(tmp_path, [])
    sm.append_lane({"feature_id": "lane-new", "status": "pending", "prompt": "x"})
    data = json.loads(path.read_text())
    assert len(data["lanes"]) == 1
    assert data["lanes"][0]["feature_id"] == "lane-new"


# ---------------------------------------------------------------------------
# validate() – whole-document validation
# ---------------------------------------------------------------------------


def test_validate_passes_on_clean_document(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    # must not raise
    sm.validate()


def test_validate_raises_on_duplicate_feature_ids(tmp_path):
    from xmuse_core.platform.state_validation import StateValidationError
    path = tmp_path / "feature_lanes.json"
    path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-dup", "status": "pending", "prompt": "a"},
        {"feature_id": "lane-dup", "status": "dispatched", "prompt": "b"},
    ]}))
    sm = LaneStateMachine(path)
    with pytest.raises(StateValidationError, match="duplicate"):
        sm.validate()


def test_validate_raises_on_missing_lanes_key(tmp_path):
    from xmuse_core.platform.state_validation import StateValidationError
    path = tmp_path / "feature_lanes.json"
    path.write_text(json.dumps({"not_lanes": []}))
    sm = LaneStateMachine(path)
    with pytest.raises(StateValidationError):
        sm.validate()


def test_validate_raises_on_unknown_status(tmp_path):
    from xmuse_core.platform.state_validation import StateValidationError
    path = tmp_path / "feature_lanes.json"
    path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "totally_unknown", "prompt": "p"},
    ]}))
    sm = LaneStateMachine(path)
    with pytest.raises(StateValidationError, match="unknown status"):
        sm.validate()


# ---------------------------------------------------------------------------
# Invariant breaches surfaced through transition()
# ---------------------------------------------------------------------------


def test_transition_to_gate_failed_without_failure_reason_raises(tmp_path):
    """gate_failed lanes must record failure_reason – invariant enforced post-transition."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "executed", "prompt": "p"},
    ])
    with pytest.raises((StateValidationError, InvalidTransitionError)):
        sm.transition("lane-1", "gate_failed")


def test_transition_to_gate_failed_with_failure_reason_succeeds(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "executed", "prompt": "p"},
    ])
    lane = sm.transition(
        "lane-1", "gate_failed",
        metadata={"failure_reason": "review_timeout"},
    )
    assert lane["status"] == "gate_failed"
    assert lane["failure_reason"] == "review_timeout"


def test_transition_to_awaiting_final_action_without_hold_id_raises(tmp_path):
    """awaiting_final_action requires final_action_hold_id – invariant enforced."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "p"},
    ])
    with pytest.raises((StateValidationError, InvalidTransitionError)):
        sm.transition("lane-1", "awaiting_final_action")


def test_transition_to_awaiting_final_action_with_hold_id_succeeds(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "p"},
    ])
    lane = sm.transition(
        "lane-1", "awaiting_final_action",
        metadata={"final_action_hold_id": "hold-abc"},
    )
    assert lane["status"] == "awaiting_final_action"
    assert lane["final_action_hold_id"] == "hold-abc"


def test_transition_preserves_gate_passed_false_raises_for_gated(tmp_path):
    """A lane with gate_passed=False must not reach gated status."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {
            "feature_id": "lane-1",
            "status": "gate_failed",
            "prompt": "p",
            "failure_reason": "review_timeout",
            "gate_passed": False,
        },
    ])
    with pytest.raises((StateValidationError, InvalidTransitionError)):
        sm.transition("lane-1", "gated")


def test_transition_with_invalid_review_decision_raises(tmp_path):
    """An unknown review_decision value must be rejected by the invariant validator."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "p"},
    ])
    with pytest.raises((StateValidationError, InvalidTransitionError)):
        sm.transition(
            "lane-1", "merged",
            metadata={"review_decision": "invalid_decision"},
        )


def test_transition_with_valid_review_decision_succeeds(tmp_path):
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "reviewed", "prompt": "p"},
    ])
    lane = sm.transition(
        "lane-1", "merged",
        metadata={"review_decision": "merge"},
    )
    assert lane["status"] == "merged"
    assert lane["review_decision"] == "merge"


# ---------------------------------------------------------------------------
# Schema violations surfaced through transition() metadata
# ---------------------------------------------------------------------------


def test_transition_metadata_with_non_string_failure_reason_raises(tmp_path):
    """failure_reason must be a string – schema validator rejects integers."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "executed", "prompt": "p"},
    ])
    with pytest.raises((StateValidationError, InvalidTransitionError)):
        sm.transition("lane-1", "gate_failed", metadata={"failure_reason": 99})


def test_transition_metadata_with_negative_retry_count_raises(tmp_path):
    """retry_count must be a non-negative integer."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "p", "retry_count": 0},
    ])
    with pytest.raises((StateValidationError, InvalidTransitionError)):
        sm.transition("lane-1", "reworking", metadata={"retry_count": -1})


def test_transition_metadata_with_non_list_capabilities_raises(tmp_path):
    """capabilities must be a list when present."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    with pytest.raises((StateValidationError, InvalidTransitionError)):
        sm.transition("lane-1", "dispatched", metadata={"capabilities": "not-a-list"})


def test_transition_metadata_with_non_bool_gate_passed_raises(tmp_path):
    """gate_passed must be a boolean when present."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    with pytest.raises((StateValidationError, InvalidTransitionError)):
        sm.transition("lane-1", "dispatched", metadata={"gate_passed": "yes"})


# ---------------------------------------------------------------------------
# update_metadata invariant enforcement
# ---------------------------------------------------------------------------


def test_update_metadata_cannot_change_feature_id(tmp_path):
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    with pytest.raises((StateValidationError, KeyError)):
        sm.update_metadata("lane-1", {"feature_id": "lane-hijacked"})


def test_update_metadata_rejects_invalid_schema_field(tmp_path):
    """Setting retry_count to a negative value via update_metadata must fail."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    with pytest.raises((StateValidationError, ValueError)):
        sm.update_metadata("lane-1", {"retry_count": -5})


def test_update_metadata_cannot_change_status(tmp_path):
    """Metadata-only updates must not bypass transition legality checks."""
    from xmuse_core.platform.state_validation import StateValidationError

    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])

    with pytest.raises(StateValidationError, match="status cannot change"):
        sm.update_metadata("lane-1", {"status": "merged"})

    assert sm.get_lane("lane-1")["status"] == "pending"


# ---------------------------------------------------------------------------
# Monotonic counter invariant
# ---------------------------------------------------------------------------


def test_retry_count_cannot_decrease_via_metadata(tmp_path):
    """retry_count is monotonic – decreasing it must be rejected."""
    from xmuse_core.platform.state_validation import StateValidationError
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "reworking", "prompt": "p", "retry_count": 2},
    ])
    with pytest.raises((StateValidationError, ValueError)):
        sm.update_metadata("lane-1", {"retry_count": 1})


# ---------------------------------------------------------------------------
# Agent lifecycle edge cases
# ---------------------------------------------------------------------------


def test_full_rework_cycle_increments_retry_count_correctly(tmp_path):
    """Simulate a full rework cycle: dispatched → exec_failed → reworking → dispatched."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "dispatched", "prompt": "p"},
    ])
    sm.transition("lane-1", "exec_failed")
    lane = sm.transition("lane-1", "reworking")
    assert lane["retry_count"] == 1
    lane = sm.transition("lane-1", "dispatched")
    assert lane["status"] == "dispatched"
    assert lane["retry_count"] == 1  # count preserved after re-dispatch


def test_rework_cycle_via_rejected_increments_retry_count(tmp_path):
    """Simulate a review-rejection rework cycle: gated → rejected → reworking."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "gated", "prompt": "p"},
    ])
    sm.transition("lane-1", "rejected")
    lane = sm.transition("lane-1", "reworking")
    assert lane["retry_count"] == 1
    assert lane["status"] == "reworking"


def test_exec_failed_reworking_clears_failure_reason(tmp_path):
    """failure_reason set during exec_failed must be cleared when reworking."""
    _, sm = _make_sm(tmp_path, [
        {
            "feature_id": "lane-1",
            "status": "exec_failed",
            "prompt": "p",
            "failure_reason": "non_zero_exit",
        },
    ])
    lane = sm.transition("lane-1", "reworking")
    assert "failure_reason" not in lane


def test_agent_lifecycle_exec_failed_to_failed_terminal(tmp_path):
    """exec_failed → failed is a valid terminal path for unrecoverable agent errors."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "exec_failed", "prompt": "p"},
    ])
    lane = sm.transition("lane-1", "failed")
    assert lane["status"] == "failed"
    # terminal – no further transitions allowed
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "reworking")


def test_agent_lifecycle_max_retries_across_exec_failed_path(tmp_path):
    """An agent that hits exec_failed twice and reworks twice must be blocked on the third."""
    from xmuse_core.platform.state_machine import MAX_RETRIES
    _, sm = _make_sm(tmp_path, [
        {
            "feature_id": "lane-1",
            "status": "exec_failed",
            "prompt": "p",
            "retry_count": MAX_RETRIES,
        },
    ])
    with pytest.raises(InvalidTransitionError, match="max retries"):
        sm.transition("lane-1", "reworking")


def test_dispatched_to_executed_to_gated_agent_path(tmp_path):
    """Core agent execution path: dispatched → executed → gated."""
    _, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "dispatched", "prompt": "p"},
    ])
    sm.transition("lane-1", "executed")
    lane = sm.transition("lane-1", "gated")
    assert lane["status"] == "gated"


def test_agent_metadata_assigned_to_persists_through_lifecycle(tmp_path):
    """Agent assignment metadata must survive state transitions."""
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "pending", "prompt": "p"},
    ])
    sm.transition("lane-1", "dispatched", metadata={"assigned_to": "codex", "run_id": "r42"})
    sm.transition("lane-1", "executed")
    lane = sm.get_lane("lane-1")
    assert lane["assigned_to"] == "codex"
    assert lane["run_id"] == "r42"


# ---------------------------------------------------------------------------
# Orchestrator state change edge cases
# ---------------------------------------------------------------------------


def test_orchestrator_append_then_transition_new_lane(tmp_path):
    """Orchestrator appends a lane then immediately transitions it."""
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-existing", "status": "merged", "prompt": "old"},
    ])
    sm.append_lane({"feature_id": "lane-new", "status": "pending", "prompt": "new"})
    lane = sm.transition("lane-new", "dispatched")
    assert lane["status"] == "dispatched"
    # existing lane must be untouched
    assert sm.get_lane("lane-existing")["status"] == "merged"


def test_orchestrator_append_lane_missing_feature_id_uses_unknown(tmp_path):
    """append_lane rejects invalid lane schema before writing."""
    from xmuse_core.platform.state_validation import StateValidationError

    path, sm = _make_sm(tmp_path, [])
    with pytest.raises(StateValidationError, match="feature_id"):
        sm.append_lane({"status": "pending", "prompt": "no id"})
    assert json.loads(path.read_text())["lanes"] == []


def test_orchestrator_validate_after_bulk_append(tmp_path):
    """validate() must pass after appending multiple valid lanes."""
    path, sm = _make_sm(tmp_path, [])
    for i in range(5):
        sm.append_lane(
            {"feature_id": f"lane-{i}", "status": "pending", "prompt": f"p{i}"}
        )
    sm.validate()  # must not raise


def test_orchestrator_transition_does_not_corrupt_sibling_metadata(tmp_path):
    """Transitioning one lane must not alter metadata of sibling lanes."""
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-A", "status": "pending", "prompt": "a", "tag": "alpha"},
        {"feature_id": "lane-B", "status": "pending", "prompt": "b", "tag": "beta"},
    ])
    sm.transition("lane-A", "dispatched", metadata={"assigned_to": "codex"})
    lane_b = sm.get_lane("lane-B")
    assert lane_b["tag"] == "beta"
    assert "assigned_to" not in lane_b


def test_orchestrator_update_metadata_on_terminal_lane(tmp_path):
    """update_metadata on a terminal lane must succeed (metadata-only, no transition)."""
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-1", "status": "merged", "prompt": "p"},
    ])
    sm.update_metadata("lane-1", {"merge_sha": "abc123"})
    assert sm.get_lane("lane-1")["merge_sha"] == "abc123"
    assert sm.get_lane("lane-1")["status"] == "merged"


def test_orchestrator_get_lanes_after_mixed_transitions(tmp_path):
    """get_lanes(status=...) reflects live state after multiple transitions."""
    path, sm = _make_sm(tmp_path, [
        {"feature_id": "lane-A", "status": "pending", "prompt": "a"},
        {"feature_id": "lane-B", "status": "pending", "prompt": "b"},
        {"feature_id": "lane-C", "status": "pending", "prompt": "c"},
    ])
    sm.transition("lane-A", "dispatched")
    sm.transition("lane-B", "dispatched")

    assert len(sm.get_lanes(status="pending")) == 1
    assert len(sm.get_lanes(status="dispatched")) == 2
    assert sm.get_lanes(status="pending")[0]["feature_id"] == "lane-C"
