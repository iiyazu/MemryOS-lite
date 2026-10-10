"""``eval collab``: scenario loading, scoring, and the deterministic --fake-llm run."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from memoryos_eval.cli import app
from memoryos_eval.collab import load_scenarios, run_collab, score
from memoryos_lite.curator.curate import CurateResponse

DATA = Path(__file__).resolve().parents[1] / "benchmarks" / "collab"


def _memory(key: str, statement: str, source: str, **extra: object) -> dict[str, object]:
    return {
        "id": f"mem_{key}",
        "kind": "decision",
        "topic_key": key,
        "statement": statement,
        "version": 1,
        "sources": [{"activity_id": source, "quote": statement}],
        **extra,
    }


EXPECT_KEYS = {"proposals", "resolves", "conflicts", "restates", "chatter", "objections"}


def test_scenarios_cover_every_expectation():
    scenarios = load_scenarios(DATA)
    assert 10 <= len(scenarios) <= 14
    keys = {key for s in scenarios for key in s["expect"]}
    assert EXPECT_KEYS <= keys
    assert any("supersedes" in p for s in scenarios for p in s["expect"].get("proposals", []))
    for scenario in scenarios:
        window = {a["id"] for a in scenario["window"]}
        active = {e["id"] for e in scenario["active"]}
        expect = scenario["expect"]
        cited = {a for p in expect.get("proposals", []) for a in p["sources"]}
        cited |= set(expect.get("restates", {})) | set(expect.get("chatter", []))
        assert cited | set(expect.get("objections", [])) <= window, scenario["scenario_id"]
        named = set(expect.get("resolves", [])) | set(expect.get("conflicts", []))
        named |= {p["supersedes"] for p in expect.get("proposals", []) if "supersedes" in p}
        assert named | set(expect.get("restates", {}).values()) <= active, scenario["scenario_id"]


def test_hub_id_variants_change_only_ids_and_keys():
    """``c<nn>e`` is ``c<nn>`` with the hub's ids: ``E<n>`` ids and ``e<n>`` topic keys."""

    scenarios = {s["scenario_id"]: s for s in load_scenarios(DATA)}
    variants = [s for s in scenarios.values() if "variant_of" in s]
    assert len(variants) >= 2
    for variant in variants:
        base = scenarios[variant["variant_of"]]
        pairs = list(zip(base["active"], variant["active"], strict=True))
        ids = {old["id"]: new["id"] for old, new in pairs}
        for old, new in pairs:
            assert re.fullmatch(r"E\d+", new["id"]) and new["topic_key"] == new["id"].lower()
            assert {**old, "id": new["id"], "topic_key": new["topic_key"]} == new
        assert variant["window"] == base["window"]
        expect = json.loads(json.dumps(base["expect"]))
        for proposal in expect.get("proposals", []):
            if "supersedes" in proposal:
                proposal["supersedes"] = ids[proposal["supersedes"]]
        for key in ("resolves", "not_resolved", "conflicts"):
            if key in expect:
                expect[key] = [ids[i] for i in expect[key]]
        if "restates" in expect:
            expect["restates"] = {a: ids[i] for a, i in expect["restates"].items()}
        assert variant["expect"] == expect


def test_long_windows_mix_every_case():
    long = [s for s in load_scenarios(DATA) if len(s["window"]) >= 16]
    assert len(long) >= 2
    for scenario in long:
        assert len(scenario["window"]) <= 32
        expect = scenario["expect"]
        assert EXPECT_KEYS <= set(expect), scenario["scenario_id"]
        assert any("supersedes" in p for p in expect["proposals"])
        assert any(len(p.get("qualifiers", [])) >= 2 for p in expect["proposals"])
    assert any(e["topic_key"] == e["id"].lower() for s in long for e in s["active"])


def test_score_counts_every_metric():
    scenario = {
        "active": [
            {"id": "Q1", "kind": "question"},
            {"id": "Q2", "kind": "question"},
            {"id": "C1", "kind": "convention"},
        ],
        "expect": {
            "proposals": [
                {
                    "sources": ["m1"],
                    "qualifiers": [["only"], ["ledger", "cents"]],
                    "supersedes": "D1",
                },
                {"sources": ["m9"]},
            ],
            "resolves": ["Q1"],
            "conflicts": ["C1", "C2"],
            "restates": {"m2": "A1"},
            "chatter": ["m3", "m4"],
            "objections": ["m5"],
        },
    }
    response = CurateResponse.model_validate(
        {
            "scope_id": "t",
            "memories": [
                _memory(
                    "a", "Decimal only in the API, cents in the ledger", "m1", supersedes_id="D1"
                ),
                _memory("b", "restated", "m2", resolves_ids=["Q1", "Q2"]),
                _memory("c", "chatter", "m3", supersedes_id="X9"),
            ],
            "conflicts": [
                {"a_id": "C1", "b_id": "mem_a", "reason": "r"},
                {"a_id": "Q2", "b_id": "mem_b", "reason": "r"},
            ],
            "assignments": [{"activity_id": "m5", "dismiss": "not a lesson"}],
        }
    )

    scored = score(scenario, response)

    assert scored["proposal_recall"] == [1, 2]
    assert scored["qualifier_retention"] == [1, 1]
    assert scored["supersedes_accuracy"] == [1, 1]
    assert scored["resolves_precision"] == [1, 2]
    assert scored["resolves_recall"] == [1, 1]
    assert scored["conflict_recall"] == [1, 2]
    assert scored["conflict_extra"] == [1]
    assert scored["duplicate_rate"] == [1, 1]
    assert scored["chatter_stored_rate"] == [1, 2]
    assert scored["objection_lesson_rate"] == [0, 1]
    assert scored["supersedes_wrong"] == [1]
    assert scored["clean_first_reply"] == [1, 1]
    assert score(scenario, None)["errors"] == [1]
    assert score(scenario, None)["clean_first_reply"] == [0, 1]


def test_fake_llm_run_is_deterministic(tmp_path):
    scenarios = load_scenarios(DATA)
    first = run_collab(scenarios, out_dir=tmp_path / "a", repeats=2, fake_llm=True)
    run_collab(scenarios, out_dir=tmp_path / "b", repeats=2, fake_llm=True, workers=3)

    for name in ("runs.jsonl", "summary.json", "summary.md"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    metrics = first["metrics"]
    assert metrics["errors"]["mean"] == 0
    assert metrics["objection_lesson_rate"]["mean"] == 1.0
    assert metrics["resolves_recall"]["mean"] == 0.0
    assert metrics["qualifier_retention"]["std"] == 0.0
    assert first["usage"]["attempts"] == 0


def test_cli_runs_one_scenario(tmp_path):
    result = CliRunner().invoke(
        app, ["collab", "--fake-llm", "--scenarios", "c01", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "proposal_recall" in (tmp_path / "summary.md").read_text(encoding="utf-8")
