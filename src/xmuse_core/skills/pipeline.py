from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from xmuse_core.skills.base import SkillProtocol, SkillResult
from xmuse_core.skills.models import (
    BrainstormInput,
    LaneGraph,
    PipelineInput,
    ReviewInput,
    SpecToLanesInput,
)

logger = logging.getLogger(__name__)


class DesignPipelineSkill(SkillProtocol):
    """Orchestrates: brainstorm → spec_review → decompose → lane_review → emit."""

    async def run(self, input: BaseModel) -> SkillResult:
        assert isinstance(input, PipelineInput)
        sk = self._ctx.skill_registry

        # Phase 1: Brainstorm
        if not input.skip_brainstorm:
            brainstorm = sk.instantiate("brainstorm", self._ctx)
            bs_result = await brainstorm.run(BrainstormInput(
                feature_id=input.feature_id,
                goal=input.goal,
                context_files=input.context_files,
                constraints=input.constraints,
            ))
            if bs_result.status == "failed":
                return bs_result
            spec_path = bs_result.artifacts.get("spec", "")
        else:
            spec_path = str(self._feature_dir(input.feature_id) / "spec.json")

        # Phase 2: Spec Review Gate
        if not input.skip_review:
            review = sk.instantiate("review_gate", self._ctx)
            sr_result = await review.run(ReviewInput(
                feature_id=input.feature_id,
                artifact_path=spec_path,
                review_type="spec_review",
                criteria=input.spec_review_criteria,
            ))
            if sr_result.metadata.get("passed") is False:
                return SkillResult(
                    status="needs_review",
                    artifacts=sr_result.artifacts,
                    metadata={"phase": "spec_review"},
                )

        # Phase 3: Decompose into lanes
        decompose = sk.instantiate("spec_to_lanes", self._ctx)
        dc_result = await decompose.run(SpecToLanesInput(
            feature_id=input.feature_id,
            spec_path=spec_path,
        ))
        if dc_result.status == "failed":
            return dc_result

        # Phase 4: Lane Decomposition Review Gate
        if not input.skip_review:
            review = sk.instantiate("review_gate", self._ctx)
            lr_result = await review.run(ReviewInput(
                feature_id=input.feature_id,
                artifact_path=dc_result.artifacts.get("lane_graph", ""),
                review_type="lane_review",
            ))
            if lr_result.metadata.get("passed") is False:
                return SkillResult(
                    status="needs_review",
                    artifacts=lr_result.artifacts,
                    metadata={"phase": "lane_review"},
                )

        # Phase 5: Emit lanes to feature_lanes.json
        graph_path = dc_result.artifacts.get("lane_graph", "")
        graph = LaneGraph.model_validate_json(Path(graph_path).read_text())
        self._emit_lanes(graph)

        return SkillResult(
            status="success",
            artifacts=dc_result.artifacts,
            metadata={
                "lanes_emitted": len(graph.lanes),
                "concurrency_groups": len(graph.concurrency_groups),
                "critical_path_length": len(graph.critical_path),
            },
        )

    def _emit_lanes(self, graph: LaneGraph) -> None:
        """Atomically append lanes to feature_lanes.json."""
        lanes_path = self._ctx.lanes_path
        data = json.loads(lanes_path.read_text()) if lanes_path.exists() else {"lanes": []}
        existing_ids = {l["feature_id"] for l in data["lanes"]}

        for lane in graph.lanes:
            if lane.feature_id not in existing_ids:
                data["lanes"].append({
                    "feature_id": lane.feature_id,
                    "task_type": lane.task_type,
                    "status": "pending",
                    "prompt": lane.prompt,
                    "branch": lane.branch or f"feat/{lane.feature_id}",
                    "capabilities": lane.capabilities,
                    "depends_on": lane.depends_on,
                    "source": "design_pipeline",
                })

        # Atomic write: temp file then rename
        dir_path = lanes_path.parent
        fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            Path(tmp_path).replace(lanes_path)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise
