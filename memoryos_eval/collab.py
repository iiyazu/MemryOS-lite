"""``eval collab``: quality of the ``collab`` profile of ``/curate``.

Each scenario (``benchmarks/collab/c*.json``) is one xmuse topic: the hub's
``active`` entries, a ``window`` of new messages, and what a good curator does
with them (``expect``). Every scenario runs ``repeats`` times through the same
graph as ``POST /curate``; each metric is a ratio over all scenarios of one
repeat, reported as the mean and sample standard deviation over repeats.

Metrics (numerator / denominator, summed over the scenarios of one repeat):

- ``proposal_recall``: expected proposals matched by a memory citing one of
  their source activities / expected proposals.
- ``qualifier_retention``: matched proposals whose statement keeps every
  qualifier group (any alternative, case-insensitive) / matched proposals.
- ``resolves_precision`` and ``resolves_recall``: question ids the response
  resolves (``resolves_ids``, or ``supersedes_id`` naming a question) against
  ``expect.resolves``.
- ``conflict_recall``: expected active ids that appear in a reported conflict /
  expected; ``conflict_extra`` counts conflicts touching none of them.
- ``duplicate_rate``: restating activities that ground a memory citing only
  restating activities / restating activities.
- ``chatter_stored_rate``: the same for chit-chat activities.
- ``objection_lesson_rate``: review objections assigned to a lesson / objections.
- ``supersedes_accuracy``: expected replacements whose matched memory names the
  expected ``supersedes_id`` / expected replacements; ``supersedes_wrong``
  counts memories superseding anything else.
- ``clean_first_reply``: runs whose first LLM reply broke no rule (no repair
  needed) / runs.

Usage comes from ``diagnostics.usage`` (every provider attempt); a fake LLM
makes none, and ``--fake-llm`` output carries no wall times so it is
byte-identical across runs.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from memoryos_eval.roommem import settings_for_llm_spec
from memoryos_lite.config import get_settings
from memoryos_lite.curator import CuratorLLM, build_curator_llm
from memoryos_lite.curator.curate import CurateMemoryVersion, CurateRequest, CurateResponse
from memoryos_lite.curator.graph import run_curate
from memoryos_lite.curator.llm import CuratorLLMError

METRICS = (
    "proposal_recall",
    "qualifier_retention",
    "resolves_precision",
    "resolves_recall",
    "conflict_recall",
    "duplicate_rate",
    "chatter_stored_rate",
    "objection_lesson_rate",
    "supersedes_accuracy",
    "clean_first_reply",
)
COUNTS = ("conflict_extra", "supersedes_wrong", "errors")


class CollabEvalError(RuntimeError):
    pass


class FakeCollabLLM:
    """Deterministic replies for ``--fake-llm``: one entry per decision, assumption,
    question or handoff message (its first sentence), one lesson per review
    objection, and no resolves or conflicts. It checks the pipeline, not quality."""

    KINDS = {"decision": "decision", "handoff": "decision", "assumption": "assumption"}

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        window = user.split("Messages to curate:\n", 1)[-1].split("\n\nFailures", 1)[0]
        memories: list[dict[str, Any]] = []
        assignments: list[dict[str, Any]] = []
        lessons: list[dict[str, Any]] = []
        for line in window.splitlines():
            match = re.match(r"\[([^\]]+)\] \S+ \(([a-z_]+)\): (.*)$", line)
            if match is None:
                continue
            activity_id, label, text = match.groups()
            sentence = re.split(r"(?<=[。！？.!?；;])", text, maxsplit=1)[0][:200]
            if label == "review_objection":
                key = f"lesson.{activity_id}"
                lessons.append({"topic_key": key, "statement": sentence})
                assignments.append({"activity_id": activity_id, "lesson": key, "quote": sentence})
            elif label in self.KINDS or label == "question":
                memories.append(
                    {
                        "kind": self.KINDS.get(label, "question"),
                        "topic_key": f"fake.{activity_id}",
                        "statement": sentence,
                        "sources": [{"activity_id": activity_id, "quote": sentence}],
                    }
                )
        return {"memories": memories, "assignments": assignments, "lessons": lessons}


def load_scenarios(data: Path, ids: list[str] | None = None) -> list[dict[str, Any]]:
    scenarios = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(data.glob("c*.json"))]
    if ids is not None:
        scenarios = [s for s in scenarios if s["scenario_id"] in ids]
    if not scenarios:
        raise CollabEvalError(f"no collab scenarios in {data}")
    return scenarios


def _has(statement: str, group: list[str]) -> bool:
    return any(option.lower() in statement.lower() for option in group)


def score(scenario: dict[str, Any], response: CurateResponse | None) -> dict[str, list[int]]:
    """``{metric: [numerator, denominator]}`` plus the plain counts, for one run."""

    expect = scenario["expect"]
    memories: list[CurateMemoryVersion] = response.memories if response else []
    sources = [{s.activity_id for s in m.sources} for m in memories]
    expected = expect.get("proposals", [])
    out: dict[str, list[int]] = {name: [0, 0] for name in METRICS}
    for proposal in expected:
        out["proposal_recall"][1] += 1
        groups = proposal.get("qualifiers", [])
        matches = [
            m for m, s in zip(memories, sources, strict=True) if s & set(proposal["sources"])
        ]
        if "supersedes" in proposal:
            out["supersedes_accuracy"][1] += 1
        if not matches:
            continue
        best = max(matches, key=lambda m: sum(_has(m.statement, g) for g in groups))
        out["proposal_recall"][0] += 1
        out["qualifier_retention"][1] += 1
        out["qualifier_retention"][0] += all(_has(best.statement, g) for g in groups)
        if "supersedes" in proposal:
            out["supersedes_accuracy"][0] += any(
                m.supersedes_id == proposal["supersedes"] for m in matches
            )
    questions = {e["id"] for e in scenario["active"] if e["kind"] == "question"}
    resolved = {q for m in memories for q in m.resolves_ids or []}
    # Contract v1.1: superseding a question also resolves it.
    resolved |= questions & {m.supersedes_id or "" for m in memories}
    wanted = set(expect.get("resolves", []))
    out["resolves_precision"] = [len(resolved & wanted), len(resolved)]
    out["resolves_recall"] = [len(resolved & wanted), len(wanted)]
    conflicts = (response.conflicts or []) if response else []
    involved = {side for c in conflicts for side in (c.a_id, c.b_id)}
    expected_conflicts = set(expect.get("conflicts", []))
    out["conflict_recall"] = [len(expected_conflicts & involved), len(expected_conflicts)]
    for metric, listed in (
        ("duplicate_rate", expect.get("restates", {})),
        ("chatter_stored_rate", expect.get("chatter", [])),
    ):
        group = set(listed)
        stored = {a for s in sources if s and s <= group for a in s}
        out[metric] = [len(stored), len(group)]
    objections = set(expect.get("objections", []))
    lessons = {a.activity_id for a in (response.assignments if response else []) if a.lesson}
    out["objection_lesson_rate"] = [len(objections & lessons), len(objections)]
    allowed = {p["supersedes"] for p in expected if "supersedes" in p} | wanted
    out["conflict_extra"] = [sum(not ({c.a_id, c.b_id} & expected_conflicts) for c in conflicts)]
    out["supersedes_wrong"] = [
        sum(m.supersedes_id is not None and m.supersedes_id not in allowed for m in memories)
    ]
    out["errors"] = [int(response is None)]
    clean = response is not None and not response.diagnostics.initial_violations
    out["clean_first_reply"] = [int(clean), 1]
    return out


def _run_one(
    scenario: dict[str, Any], repeat: int, llm: CuratorLLM, fake: bool, max_repairs: int
) -> dict[str, Any]:
    request = CurateRequest.model_validate(
        {
            "scope_id": f"collab-{scenario['scenario_id']}",
            "profile": "collab",
            "active": scenario["active"],
            "window": scenario["window"],
            "max_repairs": max_repairs,
        }
    )
    started = time.perf_counter()
    try:
        response: CurateResponse | None = run_curate(request, llm)
        error = None
    except CuratorLLMError as exc:
        response, error = None, str(exc)
    wall = None if fake else round(time.perf_counter() - started, 1)
    diagnostics = response.diagnostics if response else None
    usage = diagnostics.usage.model_dump() if diagnostics and diagnostics.usage else None
    return {
        "scenario_id": scenario["scenario_id"],
        "repeat": repeat,
        "error": error,
        "wall_s": wall,
        "usage": usage,
        "llm_calls": diagnostics.llm_calls if diagnostics else None,
        "repairs": diagnostics.repairs if diagnostics else None,
        "initial_violations": diagnostics.initial_violations if diagnostics else None,
        "final_violations": diagnostics.final_violations if diagnostics else None,
        "memories": [m.model_dump(mode="json") for m in response.memories] if response else [],
        "conflicts": [c.model_dump(mode="json") for c in response.conflicts or []]
        if response
        else [],
        "assignments": [a.model_dump(mode="json") for a in response.assignments]
        if response
        else [],
        "score": score(scenario, response),
    }


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "std": None}
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": round(statistics.fmean(values), 4), "std": round(std, 4)}


def summarize(runs: list[dict[str, Any]], repeats: int) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for name in (*METRICS, *COUNTS):
        per_repeat: list[float] = []
        for repeat in range(repeats):
            totals = [r["score"][name] for r in runs if r["repeat"] == repeat]
            if name in COUNTS:
                per_repeat.append(sum(t[0] for t in totals))
            elif sum(t[1] for t in totals):
                per_repeat.append(sum(t[0] for t in totals) / sum(t[1] for t in totals))
        metrics[name] = {**_stats(per_repeat), "per_repeat": [round(v, 4) for v in per_repeat]}
    scenarios: dict[str, Any] = {}
    for scenario_id in sorted({r["scenario_id"] for r in runs}):
        rows = [r for r in runs if r["scenario_id"] == scenario_id]
        usage = [r["usage"] or {} for r in rows]
        scenarios[scenario_id] = {
            "memories": _stats([len(r["memories"]) for r in rows]),
            "conflicts": _stats([len(r["conflicts"]) for r in rows]),
            "total_tokens": _stats([u.get("total_tokens", 0) for u in usage]),
            "completion_tokens": _stats([u.get("completion_tokens", 0) for u in usage]),
            "llm_calls": sum(r["llm_calls"] or 0 for r in rows),
            "attempts": sum(u.get("attempts", 0) for u in usage),
            "unmetered_attempts": sum(u.get("unmetered_attempts", 0) for u in usage),
            "wall_s": _stats([r["wall_s"] for r in rows if r["wall_s"] is not None]),
            "errors": sum(r["error"] is not None for r in rows),
        }
    usage_rows = [r["usage"] or {} for r in runs]
    total = {
        key: sum(u.get(key, 0) for u in usage_rows)
        for key in (
            "attempts",
            "unmetered_attempts",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        )
    }
    return {"repeats": repeats, "metrics": metrics, "scenarios": scenarios, "usage": total}


def _fmt(stat: dict[str, Any]) -> str:
    return "n/a" if stat["mean"] is None else f"{stat['mean']:.3f} ± {stat['std']:.3f}"


def render_markdown(summary: dict[str, Any], label: str) -> str:
    lines = [
        f"# eval collab ({label}, {summary['repeats']} repeat(s))",
        "",
        "| metric | mean ± std | per repeat |",
        "|---|---|---|",
    ]
    for name, stat in summary["metrics"].items():
        lines.append(f"| {name} | {_fmt(stat)} | {stat['per_repeat']} |")
    lines += [
        "",
        "| scenario | memories | conflicts | total tokens | completion tokens | "
        "LLM calls | attempts | wall s | errors |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for scenario_id, row in summary["scenarios"].items():
        lines.append(
            f"| {scenario_id} | {_fmt(row['memories'])} | {_fmt(row['conflicts'])} | "
            f"{_fmt(row['total_tokens'])} | {_fmt(row['completion_tokens'])} | "
            f"{row['llm_calls']} | {row['attempts']} ({row['unmetered_attempts']} unmetered) | "
            f"{_fmt(row['wall_s'])} | {row['errors']} |"
        )
    usage = summary["usage"]
    lines += [
        "",
        f"Usage over every attempt: {usage['attempts']} attempts "
        f"({usage['unmetered_attempts']} unmetered), {usage['prompt_tokens']} prompt + "
        f"{usage['completion_tokens']} completion = {usage['total_tokens']} tokens.",
        "",
    ]
    return "\n".join(lines)


def run_collab(
    scenarios: list[dict[str, Any]],
    *,
    out_dir: Path,
    repeats: int = 1,
    fake_llm: bool = False,
    curator_llm: str | None = None,
    workers: int = 1,
    max_repairs: int = 2,
) -> dict[str, Any]:
    if fake_llm:
        llm: CuratorLLM = FakeCollabLLM()
        label = "fake LLM"
    else:
        settings = settings_for_llm_spec(get_settings(), curator_llm)
        built = build_curator_llm(settings)
        if built is None:
            raise CollabEvalError(f"{settings.chat_api_key_name} is required without --fake-llm")
        llm, label = built, f"{settings.resolved_llm_provider}:{settings.chat_model}"
    jobs = [(s, r) for r in range(repeats) for s in scenarios]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        runs = list(
            pool.map(lambda job: _run_one(job[0], job[1], llm, fake_llm, max_repairs), jobs)
        )
    summary = {"label": label, **summarize(runs, repeats)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "runs.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in runs),
        encoding="utf-8",
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "summary.md").write_text(render_markdown(summary, label), encoding="utf-8")
    return summary


__all__ = ["CollabEvalError", "FakeCollabLLM", "load_scenarios", "run_collab", "score"]
