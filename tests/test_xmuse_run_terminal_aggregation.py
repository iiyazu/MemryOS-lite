"""Tests for RunTerminalAggregator — authoritative run-level terminal status.

Covers the cases named in the blueprint-anchored self-evolution spec,
section "Run Terminal Aggregation":

- all-merged lineages -> merged
- mixed merged + terminated lineages -> terminated
- open lineages -> in_progress
- blocked-for-input via open clarification objects
- blocked-for-input via pending final-action holds
- requeue / patch-forward descendants (source_lane_id closure)
- authoritative LaneGraph seeding (phantom-lane exclusion)
- mixed-run compatibility bridge for legacy lane states (done/completed)

Source under test: src/xmuse_core/platform/review_plane.py::RunTerminalAggregator
"""
from __future__ import annotations

import json

from xmuse_core.platform.final_action_gate import FinalActionGateStore
from xmuse_core.platform.review_plane import RunTerminalAggregator
from xmuse_core.platform.state_machine import LaneStateMachine
from xmuse_core.structuring.models import (
    LaneGraph,
    LaneNode,
    ReviewDecision,
    ReviewVerdict,
    RunTerminalStatus,
)
from xmuse_core.structuring.verdict_store import ClarificationStore, VerdictStore

_GRAPH = "graph-1"


def _make(tmp_path, lanes: list[dict]):
    """Build a (LaneStateMachine, VerdictStore, holds, clarifications) tuple."""
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(json.dumps({"lanes": lanes}), encoding="utf-8")
    sm = LaneStateMachine(lanes_path)
    verdicts = VerdictStore(tmp_path / "verdicts.json")
    holds = FinalActionGateStore(tmp_path / "final_actions.json")
    clars = ClarificationStore(tmp_path / "clarifications.json")
    return sm, verdicts, holds, clars


def _agg(sm, verdicts, holds=None, clars=None) -> RunTerminalAggregator:
    return RunTerminalAggregator(
        sm=sm,
        verdict_store=verdicts,
        final_action_store=holds,
        clarification_store=clars,
    )


def _lane(fid: str, status: str, **extra) -> dict:
    return {"feature_id": fid, "status": status, "prompt": fid, "graph_id": _GRAPH, **extra}


# ---------------------------------------------------------------------------
# all-merged / mixed / open
# ---------------------------------------------------------------------------


def test_all_merged_lineages_is_merged(tmp_path):
    sm, verdicts, holds, clars = _make(tmp_path, [
        _lane("a", "merged"),
        _lane("b", "done"),
    ])
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH)

    assert result.status is RunTerminalStatus.MERGED
    assert result.open_lane_lineages == []
    assert result.failed_lineages == []


def test_mixed_merged_and_terminated_is_terminated(tmp_path):
    sm, verdicts, holds, clars = _make(tmp_path, [
        _lane("a", "merged"),
        _lane("b", "failed"),
    ])
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH)

    assert result.status is RunTerminalStatus.TERMINATED
    assert "b" in result.failed_lineages
    assert result.open_lane_lineages == []


def test_open_lineage_is_in_progress(tmp_path):
    sm, verdicts, holds, clars = _make(tmp_path, [
        _lane("a", "merged"),
        _lane("b", "dispatched"),
    ])
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH)

    assert result.status is RunTerminalStatus.IN_PROGRESS
    assert "b" in result.open_lane_lineages


def test_unprojected_graph_lane_counts_as_open(tmp_path):
    """A lane named in the LaneGraph but missing from the state machine is open."""
    sm, verdicts, holds, clars = _make(tmp_path, [_lane("a", "merged")])
    graph = LaneGraph(
        id=_GRAPH,
        conversation_id="c",
        resolution_id="r",
        version=1,
        lanes=[LaneNode(feature_id="a", prompt="a"), LaneNode(feature_id="ghost", prompt="ghost")],
    )
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH, lane_graph=graph)

    assert result.status is RunTerminalStatus.IN_PROGRESS
    assert "ghost" in result.open_lane_lineages


# ---------------------------------------------------------------------------
# blocked-for-input: holds + clarifications
# ---------------------------------------------------------------------------


def test_pending_final_action_hold_is_blocked_for_input(tmp_path):
    sm, verdicts, holds, clars = _make(tmp_path, [_lane("a", "merged")])
    holds.create_hold(
        lane_id="a",
        verdict_id="v1",
        action="merge",
        target_status="merged",
        summary="awaiting human approval",
    )
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH)

    assert result.status is RunTerminalStatus.BLOCKED_FOR_INPUT
    assert len(result.open_final_action_holds) == 1


def test_open_clarification_is_blocked_for_input(tmp_path):
    sm, verdicts, holds, clars = _make(tmp_path, [_lane("a", "merged")])
    clars.open_clarification(
        clarification_id="clr-1",
        lane_id="a",
        question="which API version?",
        graph_id=_GRAPH,
        created_at="2026-05-29T00:00:00Z",
    )
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH)

    assert result.status is RunTerminalStatus.BLOCKED_FOR_INPUT
    assert "clr-1" in result.open_clarification_ids


def test_open_lineage_outranks_pending_hold(tmp_path):
    """in_progress takes priority over blocked_for_input when a lane is open."""
    sm, verdicts, holds, clars = _make(tmp_path, [
        _lane("a", "merged"),
        _lane("b", "dispatched"),
    ])
    holds.create_hold(
        lane_id="a", verdict_id="v1", action="merge",
        target_status="merged", summary="hold",
    )
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH)

    assert result.status is RunTerminalStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# verdict-based merge + patch-forward closure + authoritative graph
# ---------------------------------------------------------------------------


def test_failed_lane_with_merge_verdict_counts_as_merged(tmp_path):
    """A lane in a failed state but with a finalized MERGE verdict is merged."""
    sm, verdicts, holds, clars = _make(tmp_path, [_lane("a", "failed")])
    verdicts.save_verdict(
        ReviewVerdict(
            id="v-a",
            lane_id="a",
            decision=ReviewDecision.MERGE,
            status="finalized",
            summary="merged via override",
        )
    )
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH)

    assert result.status is RunTerminalStatus.MERGED
    assert result.failed_lineages == []


def test_source_lane_id_descendant_keeps_run_open(tmp_path):
    """A patch-forward descendant (source_lane_id) is pulled into the closure."""
    sm, verdicts, holds, clars = _make(tmp_path, [
        _lane("a", "failed"),
        _lane("a-patch", "dispatched", source_lane_id="a"),
    ])
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH)

    assert result.status is RunTerminalStatus.IN_PROGRESS
    assert "a-patch" in result.open_lane_lineages


def test_authoritative_graph_excludes_phantom_lane(tmp_path):
    """Lanes whose graph_id matches but are absent from the authoritative
    LaneGraph are excluded, so a stale phantom lane cannot keep a run open."""
    sm, verdicts, holds, clars = _make(tmp_path, [
        _lane("a", "merged"),
        _lane("phantom", "dispatched"),
    ])
    graph = LaneGraph(
        id=_GRAPH,
        conversation_id="c",
        resolution_id="r",
        version=1,
        lanes=[LaneNode(feature_id="a", prompt="a")],
    )
    result = _agg(sm, verdicts, holds, clars).compute(_GRAPH, lane_graph=graph)

    assert result.status is RunTerminalStatus.MERGED
    assert "phantom" not in result.open_lane_lineages


def test_no_optional_stores_still_aggregates(tmp_path):
    """Aggregator works when final-action and clarification stores are absent."""
    sm, verdicts, _, _ = _make(tmp_path, [_lane("a", "merged"), _lane("b", "done")])
    result = _agg(sm, verdicts).compute(_GRAPH)

    assert result.status is RunTerminalStatus.MERGED
