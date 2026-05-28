"""Snapshot tests for platform/prompts/builders.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from xmuse_core.platform.prompts.builders import (
    build_execution_prompt,
    build_review_prompt,
    build_review_verdict,
)
from xmuse_core.structuring.models import ReviewDecision


@pytest.fixture
def xmuse_root(tmp_path: Path) -> Path:
    prompts_dir = tmp_path / "xmuse" / "god_prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "execution_god.md").write_text("You are the execution god.")
    (prompts_dir / "review_god.md").write_text("You are the review god.")
    return tmp_path


def test_build_execution_prompt_includes_skill_and_task(xmuse_root: Path):
    lane = {"feature_id": "lane-42", "prompt": "implement caching"}
    result = build_execution_prompt(
        lane,
        xmuse_root=xmuse_root,
        skill_prompt_path="xmuse/god_prompts/execution_god.md",
    )
    assert "You are the execution god." in result
    assert "Lane ID: lane-42" in result
    assert "implement caching" in result


def test_build_execution_prompt_missing_skill_file(tmp_path: Path):
    lane = {"feature_id": "lane-1", "prompt": "do stuff"}
    result = build_execution_prompt(
        lane,
        xmuse_root=tmp_path,
        skill_prompt_path="nonexistent/path.md",
    )
    assert "Lane ID: lane-1" in result
    assert "do stuff" in result


def test_build_review_prompt_includes_skill_and_lane_id(xmuse_root: Path):
    lane = {"feature_id": "lane-review-7"}
    result = build_review_prompt(
        lane,
        xmuse_root=xmuse_root,
        skill_prompt_path="xmuse/god_prompts/review_god.md",
    )
    assert "You are the review god." in result
    assert "Review lane: lane-review-7" in result


def test_build_review_verdict_defaults_to_merge():
    lane = {"feature_id": "lane-x"}
    verdict = build_review_verdict(lane)
    assert verdict.decision == ReviewDecision.MERGE
    assert verdict.lane_id == "lane-x"
    assert verdict.id == "verdict-lane-x"
    assert verdict.summary == "reviewed"


def test_build_review_verdict_with_rework_decision():
    lane = {
        "feature_id": "lane-y",
        "review_decision": "rework",
        "review_summary": "needs fixes",
        "review_verdict_id": "v-123",
        "review_evidence_refs": ["ref-a", "ref-b"],
        "patch_instructions": "fix the tests",
    }
    verdict = build_review_verdict(lane)
    assert verdict.decision == ReviewDecision.REWORK
    assert verdict.id == "v-123"
    assert verdict.summary == "needs fixes"
    assert verdict.evidence_refs == ["ref-a", "ref-b"]
    assert verdict.patch_instructions == "fix the tests"
    assert verdict.terminate_reason is None
