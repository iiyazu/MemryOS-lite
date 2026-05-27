import json
import pytest
from pathlib import Path
from xmuse_core.platform.state_machine import LaneStateMachine, InvalidTransitionError


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


def test_valid_transition_pending_to_dispatched(sm):
    sm.transition("lane-1", "dispatched")
    assert sm.get_lane("lane-1")["status"] == "dispatched"


def test_invalid_transition_pending_to_merged_raises(sm):
    with pytest.raises(InvalidTransitionError):
        sm.transition("lane-1", "merged")


def test_transition_persists_to_file(sm, lanes_path):
    sm.transition("lane-1", "dispatched")
    data = json.loads(lanes_path.read_text())
    assert data["lanes"][0]["status"] == "dispatched"


def test_transition_with_metadata(sm):
    sm.transition("lane-1", "dispatched", metadata={"assigned_to": "codex"})
    lane = sm.get_lane("lane-1")
    assert lane["assigned_to"] == "codex"


def test_get_lanes_by_status(sm):
    assert len(sm.get_lanes(status="pending")) == 1
    assert len(sm.get_lanes(status="dispatched")) == 0


def test_unknown_lane_raises(sm):
    with pytest.raises(KeyError):
        sm.transition("nonexistent", "dispatched")


def test_rework_depth_limit(lanes_path):
    lanes_path.write_text(json.dumps({"lanes": [
        {"feature_id": "lane-1", "status": "rejected", "prompt": "fix",
         "retry_count": 2},
    ]}))
    sm = LaneStateMachine(lanes_path)
    with pytest.raises(InvalidTransitionError, match="max retries"):
        sm.transition("lane-1", "reworking")
