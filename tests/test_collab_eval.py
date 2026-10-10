"""``eval collab``: scenario loading, scoring, and the deterministic --fake-llm run."""

from __future__ import annotations

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


def test_scenarios_cover_every_expectation():
    scenarios = load_scenarios(DATA)
    assert 6 <= len(scenarios) <= 8
    keys = {key for s in scenarios for key in s["expect"]}
    assert {"proposals", "resolves", "conflicts", "restates", "chatter", "objections"} <= keys
    assert any("supersedes" in p for s in scenarios for p in s["expect"].get("proposals", []))


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
