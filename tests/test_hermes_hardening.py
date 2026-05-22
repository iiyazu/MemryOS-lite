from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


def load_hardening_module():
    module_path = Path(__file__).resolve().parents[1] / ".hermes-loop" / "hermes_hardening.py"
    spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_summarize_eval_report_counts_llm_judge_and_movements(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    report = tmp_path / "run.partial.json"
    write_json(
        report,
        [
            {
                "case_id": "case-1",
                "verdict": "pass",
                "answer_mode": "llm",
                "judge_status": "pass",
                "movement": "unchanged_pass",
            },
            {
                "case_id": "case-2",
                "verdict": "fail",
                "answer_mode": "llm",
                "judge_status": "fail",
                "movement": "unchanged_fail",
            },
        ],
    )

    summary = hardening.summarize_eval_report(report)

    assert summary["valid"] is True
    assert summary["rows_done"] == 2
    assert summary["last_case_id"] == "case-2"
    assert summary["pass_count"] == 1
    assert summary["fail_count"] == 1
    assert summary["answer_mode_counts"] == {"llm": 2}
    assert summary["judge_status_counts"] == {"pass": 1, "fail": 1}
    assert summary["movement_counts"] == {"unchanged_pass": 1, "unchanged_fail": 1}


def test_summarize_eval_report_counts_real_movement_status_field(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    report = tmp_path / "run.json"
    write_json(
        report,
        [
            {
                "case_id": "case-1",
                "verdict": "pass",
                "answer_mode": "llm",
                "judge_status": "judge_pass",
                "movement_status": "unchanged_pass",
            },
            {
                "case_id": "case-2",
                "verdict": "fail",
                "answer_mode": "llm",
                "judge_status": "judge_fail",
                "movement_status": "new_case_no_baseline",
            },
        ],
    )

    summary = hardening.summarize_eval_report(report)

    assert summary["movement_counts"] == {
        "unchanged_pass": 1,
        "new_case_no_baseline": 1,
    }


def test_projected_partial_is_invalid_for_promotion_when_llm_required(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    partial = tmp_path / "run.partial.json"
    write_json(
        partial,
        [
            {
                "case_id": "case-1",
                "verdict": "pass",
                "answer_mode": "projected",
                "judge_status": "not_run",
            }
        ],
    )

    status = hardening.classify_eval_run(
        run_id="run",
        benchmark="longmemeval",
        partial_path=partial,
        final_path=tmp_path / "run.json",
        previous_snapshot=None,
        now=partial.stat().st_mtime + 1,
        require_llm=True,
    )

    assert status["state"] == "invalid_for_promotion"
    assert "requires llm answer and judge" in status["reason"]


def test_judge_prefixed_statuses_are_valid_llm_judge_outputs(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    final = tmp_path / "run.json"
    write_json(
        final,
        [
            {
                "case_id": "case-1",
                "verdict": "pass",
                "answer_mode": "llm",
                "judge_status": "judge_pass",
            },
            {
                "case_id": "case-2",
                "verdict": "fail",
                "answer_mode": "llm",
                "judge_status": "judge_fail",
            },
        ],
    )

    status = hardening.classify_eval_run(
        run_id="run",
        benchmark="longmemeval",
        partial_path=tmp_path / "run.partial.json",
        final_path=final,
        require_llm=True,
    )

    assert status["state"] == "completed"
    assert status["judge_status_counts"] == {"judge_pass": 1, "judge_fail": 1}


def test_growing_partial_is_running_or_progressing(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    partial = tmp_path / "run.partial.json"
    write_json(partial, [{"case_id": "case-1", "answer_mode": "llm", "judge_status": "pass"}])
    snapshot = {"file_size": partial.stat().st_size - 1, "rows_done": 0, "mtime": 1}

    status = hardening.classify_eval_run(
        run_id="run",
        benchmark="locomo",
        partial_path=partial,
        final_path=tmp_path / "run.json",
        previous_snapshot=snapshot,
        now=partial.stat().st_mtime + 1000,
        stale_after_seconds=10,
    )

    assert status["state"] == "running_or_progressing"
    assert status["rows_done"] == 1
    assert status["reason"] == "partial grew since previous snapshot"


def test_stale_partial_without_final_is_stalled(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    partial = tmp_path / "run.partial.json"
    write_json(partial, [{"case_id": "case-1", "answer_mode": "llm", "judge_status": "pass"}])
    os.utime(partial, (100.0, 100.0))
    snapshot = {"file_size": partial.stat().st_size, "rows_done": 1, "mtime": 100.0}

    status = hardening.classify_eval_run(
        run_id="run",
        benchmark="longmemeval",
        partial_path=partial,
        final_path=tmp_path / "run.json",
        previous_snapshot=snapshot,
        now=1000.0,
        stale_after_seconds=60,
    )

    assert status["state"] == "stalled"
    assert "no final report and partial stale" in status["reason"]


def test_state_ack_gate_blocks_missing_active_phase_artifacts(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-8"
    phase_dir.mkdir(parents=True)
    write_json(loop / "state.json", {"phases": [{"id": "phase-8", "status": "completed"}]})

    result = hardening.check_state_ack_consistency(loop, "phase-8")

    assert result["ok"] is False
    assert "missing ack.json" in result["blockers"]
    assert "missing review_verdict.json" in result["blockers"]
    assert "missing result.md" in result["blockers"]


def test_state_ack_gate_requires_usable_ack_and_passing_review(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-8"
    phase_dir.mkdir(parents=True)
    write_json(loop / "state.json", {"phases": [{"id": "phase-8", "status": "completed"}]})
    write_json(
        phase_dir / "ack.json",
        {"ack_level": "usable", "context_bundle": {"path": "work/phase-8/context_bundle.md"}},
    )
    write_json(
        phase_dir / "review_verdict.json",
        {"verdict": "PASS", "context_bundle": "work/phase-8/context_bundle.md"},
    )
    (phase_dir / "result.md").write_text("uses work/phase-8/context_bundle.md\n", encoding="utf-8")

    result = hardening.check_state_ack_consistency(loop, "phase-8")

    assert result["ok"] is True
    assert result["blockers"] == []


def test_stale_artifact_index_marks_files_without_current_context_bundle(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    phase_dir = tmp_path / "work" / "phase-8"
    phase_dir.mkdir(parents=True)
    (phase_dir / "execute_review.md").write_text("old bundle work/phase-7/context_bundle.md\n")
    write_json(
        phase_dir / "ack.json",
        {"context_bundle": {"path": "work/phase-8/context_bundle.md"}},
    )

    index = hardening.scan_stale_artifacts(
        phase_dir, current_context_bundle="work/phase-8/context_bundle.md"
    )

    assert "execute_review.md" in index["stale_files"]
    assert "ack.json" not in index["stale_files"]


def test_shard_resume_plan_uses_unique_run_ids_and_llm_flags() -> None:
    hardening = load_hardening_module()

    plan = hardening.generate_shard_resume_plan(
        benchmark="locomo",
        data_path="benchmarks/locomo/locomo10.json",
        baseline="memoryos_lite",
        run_id_prefix="phase8_locomo50_retry",
        limit=50,
        shard_size=10,
        comparison_report=".memoryos/evals/phase6_locomo.json",
    )

    assert plan.count("--llm-answer --llm-judge") == 5
    assert "--limit 10" in plan
    assert "phase8_locomo50_retry_s01_001_010" in plan
    assert "phase8_locomo50_retry_s05_041_050" in plan
    assert "--comparison-report .memoryos/evals/phase6_locomo.json" in plan
