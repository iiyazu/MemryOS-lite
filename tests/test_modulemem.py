"""ModuleMem harness behavior with fake LLMs (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from memoryos_lite.curator.curate import CurateAssignment
from memoryos_lite.modulemem import (
    MODULEMEM_ARMS,
    MODULEMEM_SPLITS,
    FakeModuleCuratorLLM,
    ModuleMemConfig,
    ModuleMemError,
    _write_side,
    accounting_metrics,
    curate_module,
    current_contracts,
    load_modules,
    load_seed,
    load_seed_spec,
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


def _module_with_tasks(tmp_path: Path, tasks: list[dict[str, object]]) -> Path:
    raw = json.loads((DATA / "mm01.json").read_text(encoding="utf-8"))
    raw["tasks"] = tasks
    data = tmp_path / "data"
    data.mkdir()
    (data / "mm01.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return data


def _mm01_task_refs() -> tuple[str, str, str]:
    module = load_modules(DATA, ["mm01"])[0]
    lesson = module.gold.lessons[0].id
    decision = next(d.id for d in module.gold.decisions if d.superseded_by is None)
    contract = f"contract:{module.gold.contracts[0].contract_id}"
    return lesson, decision, contract


def test_owner_tasks_score_memory_against_no_memory(tmp_path):
    lesson, decision, contract = _mm01_task_refs()
    data = _module_with_tasks(
        tmp_path,
        [
            {
                "id": "t1",
                "prompt": "Add a logout endpoint.",
                "requirements": [
                    {"id": "r1", "ref": lesson, "check": "Avoids the known mistake."},
                    {"id": "r2", "ref": decision, "check": "Follows the current decision."},
                    {
                        "id": "r3",
                        "ref": contract,
                        "check": "Matches the current contract.",
                        "violation_patterns": ["NO_MEMORY"],
                    },
                ],
            }
        ],
    )
    summary = run_modulemem(
        load_modules(data),
        out_dir=tmp_path / "out",
        config=ModuleMemConfig(arms=("none", "oracle_pack"), fake_llm=True, tasks=True),
        scratch_root=tmp_path / "scratch",
    )

    behavior = summary["behavior"]
    assert behavior["none"]["all"]["satisfied"] == 0
    assert behavior["none"]["contract"]["pattern_violation"] == 1
    assert behavior["oracle_pack"]["all"]["satisfied"] == 1
    assert behavior["oracle_pack"]["tasks_all_satisfied"] == 1
    assert {behavior["oracle_pack"][c]["n"] for c in ("lesson", "decision", "contract")} == {1}
    rows = (tmp_path / "out" / "tasks.jsonl").read_text().splitlines()
    assert len(rows) == 6
    assert "Behavior: owner tasks" in (tmp_path / "out" / "summary.md").read_text()


FAKE_AGENT = """\
import pathlib, sys
args = sys.argv[1:]
workspace = pathlib.Path(args[args.index("--workspace") + 1])
with open(args[0], "a", encoding="utf-8") as calls:
    calls.write(sys.stdin.read().splitlines()[0] + "\\n")
memory = (workspace / "AGENTS.md").read_text(encoding="utf-8")
_, _, body = memory.partition("## Module memory from the host")
body = body.strip() or "NO_MEMORY\\nrows = fetch_legacy(order)"
body += "\\n# fetch_legacy(order) is not used here"
(workspace / "app").mkdir(exist_ok=True)
(workspace / "app" / "change.py").write_text(body + "\\n", encoding="utf-8")
print("done")
"""


def test_agent_coder_edits_the_seed_repo_and_the_judge_grades_its_diff(tmp_path):
    lesson, _, contract = _mm01_task_refs()
    data = _module_with_tasks(
        tmp_path,
        [
            {
                "id": "t1",
                "prompt": "Add a logout endpoint.",
                "requirements": [
                    {
                        "id": "r1",
                        "ref": contract,
                        "check": "Matches the current contract.",
                        "violation_patterns": ["NO_MEMORY"],
                    }
                ],
            },
            {
                "id": "t2",
                "prompt": "Move sessions to the new store.",
                "requirements": [{"id": "r1", "ref": contract, "check": "Matches the contract."}],
            },
        ],
    )
    module = load_modules(data)[0]
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    # The seed itself contains the patterns: only lines the agent adds may count.
    seed = {
        "files": {"app/main.py": "MODE = 'NO_MEMORY'\nrows = fetch_legacy(order)\n"},
        "debt": [{"id": "legacy_fetch", "ref": lesson, "patterns": [r"\bfetch_legacy\("]}],
        "exclude_tasks": {"t2": "the seed already uses the new store"},
    }
    (seeds / f"{module.module_id}.json").write_text(json.dumps(seed), encoding="utf-8")
    script = tmp_path / "agent.py"
    script.write_text(FAKE_AGENT, encoding="utf-8")
    calls = tmp_path / "calls.txt"
    config = ModuleMemConfig(
        arms=("none", "oracle_pack"),
        fake_llm=True,
        probes=False,
        tasks=True,
        coder_command=(sys.executable, str(script), str(calls)),
        seeds_dir=str(seeds),
    )

    summary = run_modulemem([module], out_dir=tmp_path / "out", config=config)

    behavior = summary["behavior"]
    assert behavior["none"]["all"]["satisfied"] == 0
    assert behavior["none"]["all"]["pattern_violation"] == 1
    assert behavior["oracle_pack"]["all"]["satisfied"] == 1
    assert behavior["oracle_pack"]["all"]["pattern_violation"] == 0
    assert behavior["none"]["tasks_with_violation"] == 1
    assert behavior["oracle_pack"]["tasks_with_violation"] == 0
    assert behavior["none"]["all"]["addressed"] == 0
    assert behavior["oracle_pack"]["all"]["addressed"] == 1
    assert behavior["oracle_pack"]["all"]["violated_of_addressed"] == 0
    assert behavior["none"]["tasks_reusing_debt"] == 1
    assert behavior["none"]["debt_reuse_by_id"] == {"legacy_fetch": 1}
    assert behavior["oracle_pack"]["tasks_reusing_debt"] == 0
    rows = [
        json.loads(line) for line in (tmp_path / "out" / "tasks.jsonl").read_text().splitlines()
    ]
    assert all(row["code"].startswith("diff --git a/app/change.py") for row in rows)
    assert all(row["code"].endswith("Notes:\ndone") for row in rows)
    assert calls.read_text().splitlines() == ["Add a logout endpoint."] * 2
    workspaces = sorted((tmp_path / "out" / "agent_work").iterdir())
    memories = [(w / "AGENTS.md").read_text(encoding="utf-8") for w in workspaces]
    assert sorted("Module memory from the host" in m for m in memories) == [False, True]

    # A rerun is served from the agent cache.
    run_modulemem([module], out_dir=tmp_path / "out", config=config)
    assert len(calls.read_text().splitlines()) == 2


def test_agent_coder_needs_tasks_and_safe_seeds(tmp_path):
    module = load_modules(DATA, ["mm01"])[0]
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "mm01.json").write_text(json.dumps({"files": {"../escape.py": ""}}), encoding="utf-8")
    config = ModuleMemConfig(arms=("none",), fake_llm=True, coder_command=("agent",))
    with pytest.raises(ModuleMemError, match="--tasks"):
        run_modulemem([module], out_dir=tmp_path / "out", config=config)
    with pytest.raises(ModuleMemError, match="bad seed path"):
        load_seed(seeds, "mm01")
    (seeds / f"{module.module_id}.json").write_text(
        json.dumps(
            {"files": {"a.py": ""}, "debt": [{"id": "x", "ref": "d999", "patterns": ["y"]}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModuleMemError, match="gold ref"):
        load_seed_spec(seeds, module)


def test_task_refs_and_patterns_are_validated(tmp_path):
    _, _, contract = _mm01_task_refs()
    data = _module_with_tasks(
        tmp_path,
        [
            {
                "id": "t1",
                "prompt": "Do something.",
                "requirements": [
                    {"id": "r1", "ref": "d999", "check": "Unknown gold."},
                    {
                        "id": "r2",
                        "ref": contract,
                        "check": "Bad regex.",
                        "violation_patterns": ["("],
                    },
                ],
            }
        ],
    )
    try:
        load_modules(data)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("invalid tasks must not load")
    assert "d999" in message and "bad pattern" in message


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
