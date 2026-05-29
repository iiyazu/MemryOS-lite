"""Decomposers turn a target blueprint track + evidence into a multi-lane plan.

Three backends are planned:

* ``SingleLaneDecomposer`` — backward-compatible default; one rich-prompt lane
  per chain step. This is what the live chain has used since bootstrap, and is
  what the existing self-evolution test suite asserts on.
* ``DeterministicMultiLaneDecomposer`` — a 3-lane design/impl/tests breakdown
  for tracks where the work decomposes naturally; useful for benchmarks and
  for exercising the dependency-aware projection path under deterministic
  conditions.
* ``PeerChatDecomposer`` — Phase 2: drives a short architect/critic Claude
  conversation and emits a real multi-feature graph (each feature can have its
  own internal lane chain).

The interface is a Protocol so the controller does not depend on any concrete
backend.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from xmuse_core.self_evolution.models import StructuredEvidenceBundle


class TrackDecomposer(Protocol):
    def decompose(
        self,
        target_track: str,
        evidence: StructuredEvidenceBundle,
    ) -> list[dict]: ...


class SingleLaneDecomposer:
    """Backward-compatible default: one rich-prompt lane per chain step.

    The lane prompt is produced by the caller-supplied callable so that the
    controller stays the source of truth for "what evidence to emit" while the
    decomposer stays the source of truth for "how many lanes to emit".
    """

    def __init__(
        self,
        *,
        lane_id_factory: Callable[[StructuredEvidenceBundle, str], str],
        prompt_factory: Callable[[StructuredEvidenceBundle, str], str],
    ) -> None:
        self._lane_id_factory = lane_id_factory
        self._prompt_factory = prompt_factory

    def decompose(
        self,
        target_track: str,
        evidence: StructuredEvidenceBundle,
    ) -> list[dict]:
        return [
            {
                "feature_id": self._lane_id_factory(evidence, target_track),
                "title": "Bootstrap the next xmuse self-evolution improvement",
                "prompt": self._prompt_factory(evidence, target_track),
                "priority": 100,
                "capabilities": ["code", "test"],
                "depends_on": [],
                "task_type": "execute",
                "gate_profiles": ["xmuse-core"],
                "feature_group": target_track,
            }
        ]


class DeterministicMultiLaneDecomposer:
    """Produces a 3-lane chain (design → impl → tests) per target track.

    Useful for stress-testing dependency-aware projection. Not the default
    because the live chain still expects single-lane evidence-rich prompts.
    """

    PHASES: tuple[tuple[str, str, list[str]], ...] = (
        (
            "design",
            "Draft a focused design note that names the smallest concrete "
            "milestone for blueprint track {track}, lists the files that will "
            "change, and calls out one acceptance signal that the change must "
            "produce. Reference the evidence bundle for context.",
            ["code"],
        ),
        (
            "impl",
            "Implement the milestone described by the design lane for "
            "blueprint track {track}. Touch only the files listed in the "
            "design note and follow existing project conventions.",
            ["code"],
        ),
        (
            "tests",
            "Add or update focused pytest tests that exercise the "
            "implementation for blueprint track {track}. Run "
            "`uv run pytest -q` for the affected modules and report the "
            "result. Do not modify production code.",
            ["test"],
        ),
    )

    def decompose(
        self,
        target_track: str,
        evidence: StructuredEvidenceBundle,
    ) -> list[dict]:
        base_id = f"self-evolution-{target_track}-{evidence.source_run_id}"
        prev_id: str | None = None
        lanes: list[dict] = []
        for index, (phase, prompt_template, capabilities) in enumerate(self.PHASES):
            feature_id = f"{base_id}-{phase}"
            prompt = (
                prompt_template.format(track=target_track)
                + f" Evidence bundle: {evidence.bundle_id}."
            )
            lanes.append(
                {
                    "feature_id": feature_id,
                    "title": f"{target_track} {phase}",
                    "prompt": prompt,
                    "task_type": "execute",
                    "priority": 100 - index,
                    "capabilities": capabilities,
                    "depends_on": [prev_id] if prev_id else [],
                    "gate_profiles": ["xmuse-core"],
                    "feature_group": target_track,
                }
            )
            prev_id = feature_id
        return lanes
