"""Tests for platform/verdicts/writer.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from xmuse_core.platform.verdicts.writer import (
    gate_report_ref_for_lane,
    ingest_merge_verdict,
    ingest_rework_verdict,
    stable_verdict_id_for_lane,
)
from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict


class FakeReviewPlane:
    """Minimal fake implementing ReviewPlaneProtocol."""

    def __init__(self) -> None:
        self.ingested: list[tuple[str, ReviewVerdict]] = []

    def ingest_verdict(
        self,
        task_id: str,
        verdict: ReviewVerdict,
        *,
        require_final_action_approval: bool | None = None,
    ) -> None:
        self.ingested.append((task_id, verdict))


def test_stable_verdict_id_uses_review_task_id():
    lane: dict[str, Any] = {"review_task_id": "task-abc"}
    result = stable_verdict_id_for_lane("lane-1", lane=lane)
    assert result == "verdict-merge-task-abc"


def test_stable_verdict_id_falls_back_to_lane_id():
    lane: dict[str, Any] = {}
    result = stable_verdict_id_for_lane("lane-1", lane=lane)
    assert result == "verdict-merge-lane-1"


def test_ingest_merge_verdict_round_trip():
    plane = FakeReviewPlane()
    lane: dict[str, Any] = {
        "review_task_id": "task-99",
        "review_verdict_id": "v-merge-99",
    }
    ingest_merge_verdict("lane-1", "looks good", lane=lane, review_plane=plane)
    assert len(plane.ingested) == 1
    task_id, verdict = plane.ingested[0]
    assert task_id == "task-99"
    assert verdict.id == "v-merge-99"
    assert verdict.decision == ReviewDecision.MERGE
    assert verdict.summary == "looks good"


def test_ingest_rework_verdict_round_trip():
    plane = FakeReviewPlane()
    lane: dict[str, Any] = {
        "review_task_id": "task-77",
        "review_verdict_id": "v-rework-77",
    }
    ingest_rework_verdict("lane-2", "needs work", lane=lane, review_plane=plane)
    assert len(plane.ingested) == 1
    task_id, verdict = plane.ingested[0]
    assert task_id == "task-77"
    assert verdict.id == "v-rework-77"
    assert verdict.decision == ReviewDecision.REWORK
    assert verdict.summary == "needs work"


def test_ingest_merge_verdict_no_task_id_is_noop():
    plane = FakeReviewPlane()
    lane: dict[str, Any] = {}
    ingest_merge_verdict("lane-x", "summary", lane=lane, review_plane=plane)
    assert len(plane.ingested) == 0


def test_gate_report_ref_for_lane_returns_relative_path(tmp_path: Path):
    gates_dir = tmp_path / "logs" / "gates" / "lane-1"
    gates_dir.mkdir(parents=True)
    (gates_dir / "report.json").write_text("{}")
    result = gate_report_ref_for_lane("lane-1", xmuse_root=tmp_path)
    assert result == "logs/gates/lane-1/report.json"


def test_gate_report_ref_for_lane_returns_none_when_missing(tmp_path: Path):
    result = gate_report_ref_for_lane("lane-missing", xmuse_root=tmp_path)
    assert result is None
