"""ModuleMem harness behavior with fake LLMs (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from memoryos_lite.curator.curate import CurateAssignment
from memoryos_lite.modulemem import (
    MODULEMEM_ARMS,
    MODULEMEM_SPLITS,
    FakeModuleCuratorLLM,
    ModuleMemConfig,
    _write_side,
    accounting_metrics,
    curate_module,
    current_contracts,
    load_modules,
    render_module_memory,
    run_modulemem,
)

DATA = Path(__file__).resolve().parents[1] / "benchmarks" / "modulemem" / "modules"


def test_modules_load_and_splits_cover_all_modules():
    modules = load_modules(DATA)
    assert {m.module_id for m in modules} >= {"auth"} or len(modules) == 8
    assert sorted(MODULEMEM_SPLITS["dev"] + MODULEMEM_SPLITS["test"]) == sorted(
        path.stem for path in DATA.glob("mm*.json")
    )


def test_oracle_file_has_current_contracts_and_no_superseded_decision(tmp_path):
    modules = load_modules(DATA, ["mm01"])
    summary = run_modulemem(
        modules,
        out_dir=tmp_path / "out",
        config=ModuleMemConfig(arms=("oracle_pack",), fake_llm=True),
        scratch_root=tmp_path / "scratch",
    )

    row = json.loads((tmp_path / "out" / "packs.jsonl").read_text().splitlines()[0])
    module = modules[0]
    current = {c.contract_id: c.version for c in module.gold.contracts}
    assert {a.contract_id: a.contract_version for a in current_contracts(module)} == current
    evidence = row["evidence"]
    assert evidence[0].startswith("Current contract")
    superseded = {d.statement for d in module.gold.decisions if d.superseded_by}
    assert not any(statement in text for text in evidence for statement in superseded)
    assert any("(failed" in text for text in evidence), "the repeated gold lesson must be shown"
    assert summary["files"]["oracle_pack"]["files"] == 1


def test_render_orders_lessons_by_occurrences_and_respects_the_budget():
    module = load_modules(DATA, ["mm01"])[0]
    memories = [
        {"id": "m1", "kind": "lesson", "statement": "rare lesson", "occurrences": 1, "version": 9},
        {
            "id": "m2",
            "kind": "lesson",
            "statement": "common lesson",
            "occurrences": 3,
            "version": 2,
        },
        {"id": "m3", "kind": "decision", "statement": "a decision", "version": 5},
        {"id": "m4", "kind": "decision", "statement": "old", "version": 1, "status": "superseded"},
    ]
    items, stats = render_module_memory(module, memories, budget=1000)
    texts = [item.text for item in items if item.layer != "contract"]
    assert texts == [
        "Lesson (failed 3 times): common lesson",
        "Lesson: rare lesson",
        "Decision: a decision",
    ]
    _, tight = render_module_memory(module, memories, budget=8)
    assert tight["omitted"] >= 1 and tight["memory_tokens"] <= 8


def test_write_side_reports_overcounted_lesson_occurrences():
    module = load_modules(DATA, ["mm01"])[0]
    lesson = next(lesson for lesson in module.gold.lessons if lesson.occurrences >= 2)

    def memories(occurrences: int) -> list[dict[str, object]]:
        return [
            {
                "id": "cmem_1",
                "kind": "lesson",
                "topic_key": lesson.topic_key,
                "statement": lesson.statement,
                "occurrences": occurrences,
                "status": "active",
                "sources": [
                    {"activity_id": s.activity_id, "quote": s.quote} for s in lesson.sources
                ],
            }
        ]

    exact = _write_side(module, memories(lesson.occurrences))
    over = _write_side(module, memories(lesson.occurrences + 1))

    assert exact["lesson_occurrences_exact"] == 1 and exact["lesson_occurrences_over"] == 0
    assert over["lesson_occurrences_exact"] == 0 and over["lesson_occurrences_over"] == 1
    assert over["repeated_lessons_recognized"] == 1


def test_accounting_matches_gold_clusters():
    module = load_modules(DATA, ["mm01"])[0]
    gold_assignments = [
        CurateAssignment(activity_id=src.activity_id, lesson=lesson.id, quote=src.quote)
        for lesson in module.gold.lessons
        for src in lesson.sources
    ]
    cited = {a.activity_id for a in gold_assignments}
    dismissals = [
        CurateAssignment(activity_id=a.id, dismiss="not a mistake")
        for a in module.activities
        if a.type in {"gate_failure", "review_objection"} and a.id not in cited
    ]
    perfect = accounting_metrics(module, [*gold_assignments, *dismissals], [])
    assert perfect["pair_fp"] == 0 and perfect["pair_fn"] == 0
    assert perfect["dismissed_gold_lesson"] == 0 and perfect["unaccounted"] == 0

    # One lesson per failure (the fake curator) never groups repeats.
    split = curate_module(module, FakeModuleCuratorLLM())
    metrics = accounting_metrics(module, split.assignments, split.unaccounted)
    assert metrics["pair_tp"] == 0
    assert metrics["pair_fn"] == perfect["pair_tp"] > 0
    assert metrics["unaccounted"] == 0


def test_all_arms_run_end_to_end_with_fake_llms(tmp_path):
    modules = load_modules(DATA, ["mm01"])
    summary = run_modulemem(
        modules,
        out_dir=tmp_path / "out",
        config=ModuleMemConfig(arms=MODULEMEM_ARMS, fake_llm=True),
        scratch_root=tmp_path / "scratch",
    )

    assert set(summary["read_side"]) == set(MODULEMEM_ARMS)
    probes = len(modules[0].probes)
    for arm in MODULEMEM_ARMS:
        assert summary["read_side"][arm]["all"]["n"] == probes
    recent = summary["read_side"]["recent"]["all"]["evidence_tokens"]
    full = summary["read_side"]["full_history"]["all"]["evidence_tokens"]
    assert full > recent
    assert summary["read_side"]["raw_log"]["all"]["evidence_tokens"] <= 1500
    ws = summary["write_side"]
    assert ws["calls"] >= 1 and ws["unaccounted"] == 0
    assert summary["gate_to_lesson_lag_s"]["n"] >= 1
    assert summary["files"]["pack"]["files"] == 1
    assert (tmp_path / "out" / "summary.md").exists()
