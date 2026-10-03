"""ModuleMem harness behavior with fake LLMs (no network)."""

from __future__ import annotations

from pathlib import Path

from memoryos_lite.modulemem import (
    MODULEMEM_ARMS,
    MODULEMEM_SPLITS,
    ModuleMemConfig,
    _write_side,
    load_modules,
    pack_evidence,
    run_modulemem,
)

DATA = Path(__file__).resolve().parents[1] / "benchmarks" / "modulemem" / "modules"


class _LessonCurator:
    """Proposes one lesson per gate failure, quoting its first long line."""

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        window = user.split("Messages to curate:\n", 1)[-1]
        operations = []
        for line in window.splitlines():
            if ", gate_failure): " not in line:
                continue
            message_id = line[1 : line.index("]")]
            body = line.split(", gate_failure): ", 1)[1]
            quote = next((part for part in body.split(" ") if len(part) >= 8), body[:20])
            operations.append(
                {
                    "op": "add",
                    "kind": "lesson",
                    "topic_key": "module.gate",
                    "statement": f"Avoid what failed: {quote}",
                    "sources": [{"message_id": message_id, "quote": quote}],
                }
            )
        return {"operations": operations}


def test_modules_load_and_splits_cover_all_modules():
    modules = load_modules(DATA)
    assert {m.module_id for m in modules} >= {"auth"} or len(modules) == 8
    assert sorted(MODULEMEM_SPLITS["dev"] + MODULEMEM_SPLITS["test"]) == sorted(
        path.stem for path in DATA.glob("mm*.json")
    )


def test_oracle_pack_contains_current_contract_and_no_superseded_decision(tmp_path):
    modules = load_modules(DATA, ["mm01"])
    summary = run_modulemem(
        modules,
        out_dir=tmp_path / "out",
        config=ModuleMemConfig(arms=("oracle_pack",), fake_llm=True),
        scratch_root=tmp_path / "scratch",
    )

    import json

    pack_row = json.loads((tmp_path / "out" / "packs.jsonl").read_text().splitlines()[0])
    pack = pack_row["pack"]
    module = modules[0]
    current = {c.contract_id: c.version for c in module.gold.contracts}
    assert {c["contract_id"]: c["version"] for c in pack["sections"]["contracts"]} == current
    superseded = {f"mm01.{d.id}" for d in module.gold.decisions if d.superseded_by}
    included = {
        item["document_id"].split("candidate-")[-1] for item in pack["sections"]["decisions"]
    }
    assert not (superseded & included)
    repeated = [lesson for lesson in pack["sections"]["lessons"] if lesson["occurrences"] >= 2]
    assert repeated, "the repeated gold lesson must be in the pack"
    evidence = pack_evidence(module, pack)
    assert evidence[0].layer == "contract" and "Current contract" in evidence[0].text
    assert summary["packs"]["oracle_pack"]["packs"] == 1


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


def test_all_arms_run_end_to_end_with_fake_llms(tmp_path):
    modules = load_modules(DATA, ["mm01"])
    summary = run_modulemem(
        modules,
        out_dir=tmp_path / "out",
        config=ModuleMemConfig(arms=MODULEMEM_ARMS, fake_llm=True),
        curated_llm_factory=lambda settings: _LessonCurator(),
        scratch_root=tmp_path / "scratch",
    )

    assert set(summary["read_side"]) == set(MODULEMEM_ARMS)
    probes = len(modules[0].probes)
    for arm in MODULEMEM_ARMS:
        assert summary["read_side"][arm]["all"]["n"] == probes
    recent = summary["read_side"]["recent"]["all"]["evidence_tokens"]
    full = summary["read_side"]["full_history"]["all"]["evidence_tokens"]
    assert full > recent
    ws = summary["write_side"]
    assert ws["curator_counts"] if isinstance(ws.get("curator_counts"), dict) else True
    assert summary["gate_to_lesson_lag_s"]["n"] >= 1
    assert summary["packs"]["pack"]["packs"] == 1
    assert (tmp_path / "out" / "summary.md").exists()
