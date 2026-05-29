from __future__ import annotations

from pydantic import BaseModel, Field


class Approach(BaseModel):
    name: str
    description: str
    pros: list[str] = []
    cons: list[str] = []
    effort: str = ""


class BrainstormInput(BaseModel):
    feature_id: str
    goal: str
    context_files: list[str] = []
    constraints: list[str] = []


class DesignSpec(BaseModel):
    feature_id: str
    title: str
    summary: str
    approaches: list[Approach] = []
    chosen_approach: str = ""
    architecture_decisions: list[str] = []
    non_goals: list[str] = []
    acceptance_criteria: list[str] = []


class LaneDefinition(BaseModel):
    feature_id: str
    task_type: str = "execute"
    prompt: str
    branch: str = ""
    capabilities: list[str] = Field(default_factory=lambda: ["code"])
    depends_on: list[str] = []
    estimated_complexity: str = "medium"


class LaneGraph(BaseModel):
    source_spec: str
    lanes: list[LaneDefinition]
    concurrency_groups: list[list[str]]
    critical_path: list[str]


class SpecToLanesInput(BaseModel):
    feature_id: str
    spec_path: str


class ReviewInput(BaseModel):
    feature_id: str
    artifact_path: str
    review_type: str  # "spec_review" | "lane_review" | "code_review"
    criteria: list[str] = []


class PipelineInput(BaseModel):
    feature_id: str
    goal: str
    context_files: list[str] = []
    constraints: list[str] = []
    spec_review_criteria: list[str] = []
    skip_brainstorm: bool = False
    skip_review: bool = False
