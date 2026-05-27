"""Tests for xmuse lane-state normalization."""

from xmuse_core.platform.state_normalizer import (
    normalize_lane_state,
    summarize_lane_states,
)


def test_pending_normalizes_to_ready() -> None:
    normalized = normalize_lane_state({"feature_id": "lane-1", "status": "pending"})

    assert normalized.feature_id == "lane-1"
    assert normalized.raw_status == "pending"
    assert normalized.normalized_status == "ready"
    assert normalized.is_terminal is False


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
