"""xmuse skill system — composable agent orchestration skills."""

from xmuse_core.skills.base import SkillContext, SkillMeta, SkillProtocol, SkillResult
from xmuse_core.skills.registry import SkillRegistry

__all__ = [
    "SkillContext",
    "SkillMeta",
    "SkillProtocol",
    "SkillResult",
    "SkillRegistry",
    "create_default_registry",
]


def create_default_registry() -> SkillRegistry:
    """Create registry with all built-in skills registered."""
    from xmuse_core.skills.brainstorm import BrainstormSkill
    from xmuse_core.skills.pipeline import DesignPipelineSkill
    from xmuse_core.skills.review_gate import ReviewGateSkill
    from xmuse_core.skills.spec_to_lanes import SpecToLanesSkill

    reg = SkillRegistry()
    reg.register("brainstorm", BrainstormSkill, tags=["design", "planning"])
    reg.register("spec_to_lanes", SpecToLanesSkill, tags=["decomposition", "planning"])
    reg.register("review_gate", ReviewGateSkill, tags=["review", "quality"])
    reg.register("design_pipeline", DesignPipelineSkill, tags=["orchestration"])
    return reg
