"""Tests for skill registry and base protocol."""

from __future__ import annotations

import pytest

from xmuse_core.skills import SkillContext, SkillResult, create_default_registry
from xmuse_core.skills.base import SkillMeta, SkillProtocol
from xmuse_core.skills.registry import SkillRegistry


def test_registry_register_and_list():
    reg = SkillRegistry()
    assert reg.list_skills() == []

    from xmuse_core.skills.review_gate import ReviewGateSkill

    reg.register("test_review", ReviewGateSkill, tags=["test"])
    skills = reg.list_skills()
    assert len(skills) == 1
    assert skills[0].name == "test_review"
    assert skills[0].tags == ["test"]


def test_registry_get():
    reg = SkillRegistry()
    from xmuse_core.skills.brainstorm import BrainstormSkill

    reg.register("bs", BrainstormSkill)
    assert reg.get("bs") is BrainstormSkill
    assert reg.get("nonexistent") is None


def test_registry_instantiate():
    reg = SkillRegistry()
    from xmuse_core.skills.brainstorm import BrainstormSkill

    reg.register("bs", BrainstormSkill)
    ctx = SkillContext(
        registry=None,
        session_manager=None,
        skill_registry=reg,
    )
    instance = reg.instantiate("bs", ctx)
    assert isinstance(instance, BrainstormSkill)
    assert instance.name == "bs"


def test_registry_instantiate_unknown_raises():
    reg = SkillRegistry()
    ctx = SkillContext(registry=None, session_manager=None, skill_registry=reg)
    with pytest.raises(KeyError, match="not registered"):
        reg.instantiate("unknown", ctx)


def test_create_default_registry():
    reg = create_default_registry()
    names = [s.name for s in reg.list_skills()]
    assert "brainstorm" in names
    assert "spec_to_lanes" in names
    assert "review_gate" in names
    assert "design_pipeline" in names
