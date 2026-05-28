"""Peer-chat decomposer backed by a single GOD call (Phase 2).

The decomposer drives one GOD invocation (Codex or Claude) that plays the
role of the *architect GOD* and produces a structured multi-feature plan
as strict JSON. Failure modes always fall back to ``SingleLaneDecomposer``
so the chain remains stable.

Runtime selection (``runtime`` arg or ``XMUSE_PEER_CHAT_RUNTIME`` env):
- ``codex`` (default for non-GOD work) — uses ``codex exec`` with the model
  named in ``XMUSE_NON_GOD_CODEX_MODEL`` (default ``gpt-5.4``).
- ``claude`` — uses ``claude -p --output-format json`` with ``model``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from xmuse_core.self_evolution.decomposer import (
    SingleLaneDecomposer,
    TrackDecomposer,
)
from xmuse_core.self_evolution.models import StructuredEvidenceBundle

logger = logging.getLogger(__name__)


_PROMPT = """\
You are the architect GOD for an autonomous software-delivery system called xmuse.

Your job: decompose the next blueprint-track milestone into 1-3 *features*,
each of which becomes a small set of lanes that one or more execute GODs will
implement.

Guidelines:
- A feature is the smallest user-visible chunk of capability work.
- Features are encouraged to be parallelizable (independent depends_on).
- Inside one feature, lanes may depend on each other (e.g. tests waits for impl).
- Prefer 1 lane per feature unless tests need a dedicated lane.
- Lane prompts must be specific and self-contained (the executing GOD will not
  see the surrounding context — only the lane prompt).
- Reference the evidence bundle id in lane prompts where helpful.

Track: {track}
Evidence bundle: {bundle_id}
Evidence summary:
{summary}

Output ONLY valid JSON of this exact shape, no markdown fence, no commentary:
{{"features": [{{"name": "<feature-slug>", "lanes": [{{"id_suffix": "<short-suffix>", "prompt": "<self-contained instruction>", "capabilities": ["code"], "depends_on": []}}]}}]}}

Constraints on the JSON:
- "features" must be a non-empty list.
- "name" must be a short kebab-case slug.
- "id_suffix" must be a short kebab-case slug unique within the feature.
- "depends_on" entries must reference earlier id_suffix values within the same
  output (cross-feature deps allowed; format: "<other-feature-name>:<id_suffix>").
- Do not use markdown. Do not wrap in code fences. Do not add comments.
"""  # noqa: E501


@dataclass(frozen=True)
class PeerChatResult:
    raw_output: str
    features: list[dict]


class PeerChatDecomposer:
    """Single-GOD-call decomposer producing a multi-feature plan.

    The decomposer shells out to ``codex exec`` (default) or ``claude -p``
    directly so it does not depend on the platform's MCP server. The fallback
    decomposer is used whenever the call fails or produces unparseable JSON.
    """

    def __init__(
        self,
        *,
        fallback: TrackDecomposer,
        runtime: str | None = None,
        model: str | None = None,
        timeout_s: float = 300.0,
        codex_binary: str | None = None,
        claude_binary: str | None = None,
    ) -> None:
        self._fallback = fallback
        self._runtime = (
            runtime
            or os.environ.get("XMUSE_PEER_CHAT_RUNTIME")
            or "codex"
        ).lower()
        if self._runtime not in {"codex", "claude"}:
            raise ValueError(f"PeerChatDecomposer runtime must be codex|claude, got {self._runtime!r}")
        if model is not None:
            self._model = model
        elif self._runtime == "codex":
            self._model = os.environ.get("XMUSE_NON_GOD_CODEX_MODEL", "gpt-5.4")
        else:
            self._model = os.environ.get("XMUSE_PEER_CHAT_CLAUDE_MODEL", "haiku")
        self._timeout_s = timeout_s
        self._codex_binary = codex_binary or shutil.which("codex") or "codex"
        self._claude_binary = claude_binary or shutil.which("claude") or "claude"

    def decompose(
        self,
        target_track: str,
        evidence: StructuredEvidenceBundle,
    ) -> list[dict]:
        try:
            result = self._call_god(target_track, evidence)
        except Exception as exc:
            logger.warning(
                "peer-chat: %s invocation failed (%s); falling back",
                self._runtime,
                exc,
            )
            return self._fallback.decompose(target_track, evidence)

        try:
            features = self._parse_features(result.raw_output)
        except ValueError as exc:
            logger.warning("peer-chat: parse failed (%s); falling back", exc)
            return self._fallback.decompose(target_track, evidence)

        if not features:
            logger.info("peer-chat: empty plan; falling back")
            return self._fallback.decompose(target_track, evidence)

        return self._materialize(features, target_track, evidence)

    def _call_god(
        self,
        target_track: str,
        evidence: StructuredEvidenceBundle,
    ) -> PeerChatResult:
        if self._runtime == "codex":
            return self._call_codex(target_track, evidence)
        return self._call_claude(target_track, evidence)

    def _call_codex(
        self,
        target_track: str,
        evidence: StructuredEvidenceBundle,
    ) -> PeerChatResult:
        prompt = _PROMPT.format(
            track=target_track,
            bundle_id=evidence.bundle_id,
            summary=evidence.summary[:800],
        )
        cmd = [
            self._codex_binary,
            "exec",
            "-m",
            self._model,
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"codex exit {proc.returncode}: {proc.stderr.strip()[:400]}")
        return PeerChatResult(raw_output=proc.stdout, features=[])

    def _call_claude(
        self,
        target_track: str,
        evidence: StructuredEvidenceBundle,
    ) -> PeerChatResult:
        prompt = _PROMPT.format(
            track=target_track,
            bundle_id=evidence.bundle_id,
            summary=evidence.summary[:800],
        )
        cmd = [
            self._claude_binary,
            "-p",
            "--bare",
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--model",
            self._model,
        ]
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude exit {proc.returncode}: {proc.stderr.strip()[:400]}")
        return PeerChatResult(raw_output=proc.stdout, features=[])

    def _parse_features(self, stdout: str) -> list[dict]:
        # Codex emits raw text; Claude --output-format json wraps under "result".
        # Try the Claude envelope first; fall back to raw text for codex.
        result_text = stdout
        try:
            envelope = json.loads(stdout)
            if isinstance(envelope, dict) and isinstance(envelope.get("result"), str):
                result_text = envelope["result"]
        except json.JSONDecodeError:
            pass
        json_blob = self._extract_json_blob(result_text)
        try:
            payload = json.loads(json_blob)
        except json.JSONDecodeError as exc:
            raise ValueError(f"inner JSON invalid: {exc}") from exc
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError("'features' must be a list")
        cleaned: list[dict] = []
        for entry in features:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            lanes = entry.get("lanes")
            if not isinstance(name, str) or not isinstance(lanes, list):
                continue
            valid_lanes: list[dict] = []
            for lane in lanes:
                if not isinstance(lane, dict):
                    continue
                if not isinstance(lane.get("id_suffix"), str):
                    continue
                if not isinstance(lane.get("prompt"), str):
                    continue
                valid_lanes.append(lane)
            if valid_lanes:
                cleaned.append({"name": name, "lanes": valid_lanes})
        return cleaned

    def _extract_json_blob(self, text: str) -> str:
        # Strip ``` fences if Claude added them despite the instructions.
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fence:
            return fence.group(1)
        # Otherwise expect raw JSON.
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise ValueError("no JSON object found in peer-chat output")
        return text[first : last + 1]

    def _materialize(
        self,
        features: list[dict],
        target_track: str,
        evidence: StructuredEvidenceBundle,
    ) -> list[dict]:
        base = f"self-evolution-{target_track}-{evidence.source_run_id}"
        suffix_to_feature_id: dict[str, str] = {}
        for feature in features:
            for lane in feature["lanes"]:
                key = f"{feature['name']}:{lane['id_suffix']}"
                suffix_to_feature_id[key] = self._lane_id(base, feature["name"], lane["id_suffix"])

        priority = 100
        materialized: list[dict] = []
        for feature in features:
            for lane in feature["lanes"]:
                lane_id = suffix_to_feature_id[f"{feature['name']}:{lane['id_suffix']}"]
                deps_raw = lane.get("depends_on", [])
                deps = [
                    suffix_to_feature_id[d]
                    for d in deps_raw
                    if isinstance(d, str) and d in suffix_to_feature_id
                ]
                capabilities_raw = lane.get("capabilities") or ["code"]
                capabilities = (
                    [str(c) for c in capabilities_raw if isinstance(c, str)]
                    if isinstance(capabilities_raw, list)
                    else ["code"]
                )
                materialized.append(
                    {
                        "feature_id": lane_id,
                        "title": f"{target_track}/{feature['name']}/{lane['id_suffix']}",
                        "prompt": (
                            lane["prompt"]
                            + f"\n\nEvidence bundle: {evidence.bundle_id}."
                        ),
                        "task_type": "execute",
                        "priority": priority,
                        "capabilities": capabilities or ["code"],
                        "depends_on": deps,
                        "gate_profiles": ["xmuse-core"],
                        "feature_group": f"{target_track}/{feature['name']}",
                    }
                )
                priority -= 1
        return materialized

    def _lane_id(self, base: str, feature_name: str, id_suffix: str) -> str:
        raw = f"{base}-{feature_name}-{id_suffix}"
        slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw).strip("-").lower()
        return slug[:120]


def build_default_peer_chat_decomposer(
    *,
    lane_id_factory,
    prompt_factory,
) -> PeerChatDecomposer:
    """Convenience: peer-chat backed by a SingleLaneDecomposer fallback."""
    return PeerChatDecomposer(
        fallback=SingleLaneDecomposer(
            lane_id_factory=lane_id_factory,
            prompt_factory=prompt_factory,
        )
    )
