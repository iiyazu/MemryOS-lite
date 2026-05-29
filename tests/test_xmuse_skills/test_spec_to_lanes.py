"""Tests for SpecToLanesSkill graph algorithms."""

from __future__ import annotations

import pytest

from xmuse_core.skills.models import LaneDefinition
from xmuse_core.skills.spec_to_lanes import SpecToLanesSkill


def _make_lane(fid: str, depends: list[str] | None = None) -> LaneDefinition:
    return LaneDefinition(
        feature_id=fid,
        prompt=f"implement {fid}",
        depends_on=depends or [],
    )


class TestValidateGraph:
    def test_valid_dag(self):
        lanes = [_make_lane("a"), _make_lane("b", ["a"]), _make_lane("c", ["a"])]
        errors = SpecToLanesSkill._validate_graph(lanes)
        assert errors == []

    def test_duplicate_feature_id(self):
        lanes = [_make_lane("a"), _make_lane("a")]
        errors = SpecToLanesSkill._validate_graph(lanes)
        assert any("Duplicate" in e for e in errors)

    def test_unknown_dependency(self):
        lanes = [_make_lane("a", ["nonexistent"])]
        errors = SpecToLanesSkill._validate_graph(lanes)
        assert any("unknown" in e for e in errors)

    def test_self_dependency(self):
        lanes = [_make_lane("a", ["a"])]
        errors = SpecToLanesSkill._validate_graph(lanes)
        assert any("itself" in e for e in errors)

    def test_cycle_detection(self):
        lanes = [_make_lane("a", ["b"]), _make_lane("b", ["a"])]
        errors = SpecToLanesSkill._validate_graph(lanes)
        assert any("Cycle" in e for e in errors)


class TestConcurrencyGroups:
    def test_no_deps_single_group(self):
        lanes = [_make_lane("a"), _make_lane("b"), _make_lane("c")]
        groups = SpecToLanesSkill._compute_concurrency_groups(lanes)
        assert groups == [["a", "b", "c"]]

    def test_linear_chain(self):
        lanes = [_make_lane("a"), _make_lane("b", ["a"]), _make_lane("c", ["b"])]
        groups = SpecToLanesSkill._compute_concurrency_groups(lanes)
        assert groups == [["a"], ["b"], ["c"]]

    def test_diamond(self):
        lanes = [
            _make_lane("a"),
            _make_lane("b", ["a"]),
            _make_lane("c", ["a"]),
            _make_lane("d", ["b", "c"]),
        ]
        groups = SpecToLanesSkill._compute_concurrency_groups(lanes)
        assert groups == [["a"], ["b", "c"], ["d"]]
