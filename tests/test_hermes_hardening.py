from __future__ import annotations

import importlib.util
import json
import os
import re
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


def test_review_eval_decision_blocks_missing_decision_for_passing_review(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    write_json(phase_dir / "review_verdict.json", {"verdict": "PASS", "decision": "advance"})

    result = hardening.check_review_eval_decision(loop, "phase-14")

    assert result["ok"] is False
    assert result["blockers"] == ["missing review_eval_decision"]


def test_review_eval_decision_allows_documented_control_plane_skip(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    write_json(
        phase_dir / "review_verdict.json",
        {
            "verdict": "PASS",
            "decision": "advance",
            "review_eval_decision": {
                "scope": "not_applicable",
                "reason": "control-plane hardening only; no MemoryOS answer path changed",
                "longmemeval": {"run": False, "reason": "not applicable"},
                "locomo": {"run": False, "reason": "not applicable"},
                "llm_answer": False,
                "llm_judge": False,
                "promotion_gate": "not_applicable",
            },
        },
    )

    result = hardening.check_review_eval_decision(loop, "phase-14")

    assert result["ok"] is True
    assert result["blockers"] == []


def test_review_eval_decision_blocks_advance_when_promotion_gate_not_satisfied(
    tmp_path: Path,
) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    write_json(
        phase_dir / "review_verdict.json",
        {
            "verdict": "PASS",
            "decision": "advance",
            "review_eval_decision": {
                "scope": "smoke",
                "reason": "quick diagnostic only",
                "longmemeval": {"run": True, "limit": 5},
                "locomo": {"run": True, "limit": 5},
                "llm_answer": False,
                "llm_judge": False,
                "promotion_gate": "not_satisfied",
            },
        },
    )

    result = hardening.check_review_eval_decision(loop, "phase-14")

    assert result["ok"] is False
    assert "advance requires promotion_gate satisfied or not_applicable" in result["blockers"]


def test_review_eval_decision_blocks_milestone_without_both_public_benchmarks(
    tmp_path: Path,
) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    write_json(
        phase_dir / "review_verdict.json",
        {
            "verdict": "PASS",
            "decision": "advance",
            "review_eval_decision": {
                "scope": "milestone",
                "reason": "promotion gate",
                "longmemeval": {"run": True, "limit": 30},
                "locomo": {"run": False, "reason": "skipped"},
                "llm_answer": True,
                "llm_judge": True,
                "promotion_gate": "satisfied",
            },
        },
    )

    result = hardening.check_review_eval_decision(loop, "phase-14")

    assert result["ok"] is False
    assert "milestone scope requires both LongMemEval and LoCoMo" in result["blockers"]


def test_execute_goal_contract_blocks_missing_goal(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    (loop / "work" / "phase-14").mkdir(parents=True)

    result = hardening.check_execute_goal_contract(loop, "phase-14")

    assert result["ok"] is False
    assert result["blockers"] == ["missing execute_goal.md"]


def test_execute_goal_contract_accepts_phase_local_goal(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    (phase_dir / "execute_goal.md").write_text(
        "\n".join(
            [
                "# phase: phase-14",
                "/goal",
                "Implement only the phase-local kernel contract.",
                "Wire changes into the real MemoryOS v3/kernel path.",
                "Required artifacts: result.md, focused tests, execute_review.md.",
                "Demo-only stubs are forbidden.",
                "Benchmark scores are diagnostic evidence only, not goal constraints.",
                "Max repair cycles: 3",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = hardening.check_execute_goal_contract(loop, "phase-14")

    assert result["ok"] is True
    assert result["blockers"] == []


def test_execute_goal_contract_rejects_benchmark_score_targets(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    (phase_dir / "execute_goal.md").write_text(
        "\n".join(
            [
                "# phase: phase-14",
                "/goal",
                "Implement only the phase-local kernel contract.",
                "Wire changes into the real MemoryOS v3/kernel path.",
                "Required artifacts: result.md, focused tests, execute_review.md.",
                "Demo-only stubs are forbidden.",
                "Target score: LongMemEval 50/50.",
                "Max repair cycles: 3",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = hardening.check_execute_goal_contract(loop, "phase-14")

    assert result["ok"] is False
    assert "execute_goal.md contains forbidden benchmark score target" in result["blockers"]


def test_run_phase_hardening_reports_execute_goal_gate(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    (loop / "work" / "phase-14").mkdir(parents=True)

    result = hardening.run_phase_hardening(
        loop,
        tmp_path / ".memoryos" / "evals",
        "phase-14",
    )

    assert result["execute_goal_gate"]["ok"] is False
    assert result["execute_goal_gate"]["blockers"] == ["missing execute_goal.md"]


def test_execute_bootstrap_gate_blocks_execute_without_dispatch_plan(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-12"
    phase_dir.mkdir(parents=True)
    (phase_dir / "context_bundle.md").write_text("# phase: phase-12\n", encoding="utf-8")
    write_json(
        loop / "state.json",
        {
            "current_state": "EXECUTE",
            "execute_lane": {"phase": "phase-12", "state": "EXECUTE"},
        },
    )

    result = hardening.check_execute_bootstrap_gate(loop)

    assert result["ok"] is False
    assert result["phase_id"] == "phase-12"
    assert result["action"] == "bootstrap_dispatch"
    assert "missing god_dispatch.json" in result["blockers"]
    assert "missing plan_final.md" in result["blockers"]


def test_execute_bootstrap_gate_allows_planned_execute(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-12"
    phase_dir.mkdir(parents=True)
    (phase_dir / "context_bundle.md").write_text("# phase: phase-12\n", encoding="utf-8")
    write_json(phase_dir / "god_dispatch.json", {"phase": "phase-12"})
    (phase_dir / "plan_final.md").write_text("# phase: phase-12\n", encoding="utf-8")
    write_json(
        loop / "state.json",
        {
            "current_state": "EXECUTE",
            "execute_lane": {"phase": "phase-12", "state": "EXECUTE"},
        },
    )

    result = hardening.check_execute_bootstrap_gate(loop)

    assert result["ok"] is True
    assert result["blockers"] == []


def test_dispatch_ready_gate_promotes_when_plan_final_exists(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    (phase_dir / "context_bundle.md").write_text("# phase: phase-14\n", encoding="utf-8")
    write_json(phase_dir / "god_dispatch.json", {"phase": "phase-14"})
    (phase_dir / "plan_final.md").write_text("# phase: phase-14\n", encoding="utf-8")
    write_json(
        loop / "state.json",
        {
            "current_state": "GOD_DISPATCH",
            "execute_lane": {"phase": "phase-14", "state": "GOD_DISPATCH"},
        },
    )

    result = hardening.check_execute_bootstrap_gate(loop)

    assert result["ok"] is True
    assert result["phase_id"] == "phase-14"
    assert result["action"] == "promote_execute"
    assert result["blockers"] == []
    assert result["present_files"] == ["context_bundle.md", "god_dispatch.json", "plan_final.md"]


def test_dispatch_ready_gate_stays_in_dispatch_when_plan_final_missing(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    (phase_dir / "context_bundle.md").write_text("# phase: phase-14\n", encoding="utf-8")
    write_json(phase_dir / "god_dispatch.json", {"phase": "phase-14"})
    write_json(
        loop / "state.json",
        {
            "current_state": "GOD_DISPATCH",
            "execute_lane": {"phase": "phase-14", "state": "GOD_DISPATCH"},
        },
    )

    result = hardening.check_execute_bootstrap_gate(loop)

    assert result["ok"] is True
    assert result["action"] == "dispatch_incomplete"
    assert result["missing_files"] == ["plan_final.md"]


def test_promote_dispatch_to_execute_updates_state_and_status_atomically(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    (phase_dir / "context_bundle.md").write_text("# phase: phase-14\n", encoding="utf-8")
    write_json(phase_dir / "god_dispatch.json", {"phase": "phase-14"})
    (phase_dir / "plan_final.md").write_text("# phase: phase-14\n", encoding="utf-8")
    write_json(
        loop / "state.json",
        {
            "current_state": "GOD_DISPATCH",
            "execute_lane": {"phase": "phase-14", "state": "GOD_DISPATCH"},
            "last_updated": "2026-05-23T00:00:00Z",
        },
    )

    result = hardening.promote_dispatch_to_execute(loop, now="2026-05-24T00:00:00Z")

    state = json.loads((loop / "state.json").read_text(encoding="utf-8"))
    status_text = (phase_dir / "phase_status.md").read_text(encoding="utf-8")
    assert result["ok"] is True
    assert result["action"] == "promoted_execute"
    assert state["current_state"] == "EXECUTE"
    assert state["execute_lane"]["state"] == "EXECUTE"
    assert state["last_updated"] == "2026-05-24T00:00:00Z"
    assert "GOD_DISPATCH Auto-Promote To EXECUTE" in status_text
    assert re.search(r"Time: 2026-05-24T00:00:00Z", status_text)


def test_active_job_status_detects_stale_output_for_live_pid(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    log_path = loop / "codex_output.log"
    log_path.write_text("started\n", encoding="utf-8")
    os.utime(log_path, (100.0, 100.0))
    hardening.write_active_job(
        loop,
        pid=12345,
        phase_id="phase-14",
        prompt_file=".hermes-loop/god_loop_prompt.md",
        attempt=1,
        output_path="codex_output.log",
        idle_timeout_seconds=60,
        started_at="2026-05-24T00:00:00Z",
    )

    status = hardening.classify_active_job(
        loop,
        now=200.0,
        pid_alive=lambda pid: pid == 12345,
    )

    assert status["state"] == "stalled"
    assert status["pid"] == 12345
    assert status["output_age_seconds"] == 100
    assert status["reason"] == "output stale beyond idle timeout"


def test_active_job_status_reports_running_when_output_is_fresh(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    log_path = loop / "codex_output.log"
    log_path.write_text("progress\n", encoding="utf-8")
    os.utime(log_path, (190.0, 190.0))
    hardening.write_active_job(
        loop,
        pid=12345,
        phase_id="phase-14",
        prompt_file=".hermes-loop/god_loop_prompt.md",
        attempt=1,
        output_path="codex_output.log",
        idle_timeout_seconds=60,
        started_at="2026-05-24T00:00:00Z",
    )

    status = hardening.classify_active_job(
        loop,
        now=200.0,
        pid_alive=lambda pid: pid == 12345,
    )

    assert status["state"] == "running"
    assert status["output_age_seconds"] == 10


def test_complete_active_job_records_exit_code_without_losing_job_context(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    (loop / "codex_output.log").write_text("done\n", encoding="utf-8")
    hardening.write_active_job(
        loop,
        pid=12345,
        phase_id="phase-14",
        prompt_file=".hermes-loop/god_loop_prompt.md",
        attempt=1,
        output_path="codex_output.log",
        idle_timeout_seconds=60,
        started_at="2026-05-24T00:00:00Z",
    )

    result = hardening.complete_active_job(
        loop,
        exit_code=124,
        status="timeout",
        completed_at="2026-05-24T01:00:00Z",
    )

    job = json.loads((loop / "active_job.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert job["status"] == "timeout"
    assert job["exit_code"] == 124
    assert job["phase_id"] == "phase-14"
    assert job["completed_at"] == "2026-05-24T01:00:00Z"


def test_execute_completion_gate_waits_until_result_exists(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    write_json(
        loop / "state.json",
        {
            "current_state": "EXECUTE",
            "execute_lane": {"phase": "phase-14", "state": "EXECUTE"},
        },
    )

    result = hardening.check_execute_completion_gate(loop)

    assert result["ok"] is True
    assert result["action"] == "wait_execute"
    assert result["missing_files"] == ["result.md"]


def test_promote_execute_to_self_review_when_result_is_phase_bound(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    (phase_dir / "result.md").write_text("# phase: phase-14\n\nImplemented.\n", encoding="utf-8")
    write_json(
        loop / "state.json",
        {
            "current_state": "EXECUTE",
            "execute_lane": {"phase": "phase-14", "state": "EXECUTE"},
            "last_updated": "2026-05-24T00:00:00Z",
        },
    )

    result = hardening.promote_execute_to_self_review(loop, now="2026-05-24T01:00:00Z")

    state = json.loads((loop / "state.json").read_text(encoding="utf-8"))
    status_text = (phase_dir / "phase_status.md").read_text(encoding="utf-8")
    assert result["ok"] is True
    assert result["action"] == "promoted_execute_self_review"
    assert state["current_state"] == "EXECUTE_SELF_REVIEW"
    assert state["execute_lane"]["state"] == "EXECUTE_SELF_REVIEW"
    assert state["last_updated"] == "2026-05-24T01:00:00Z"
    assert "EXECUTE Auto-Promote To EXECUTE_SELF_REVIEW" in status_text


def test_execute_completion_gate_blocks_stale_result_phase_binding(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    (phase_dir / "result.md").write_text("# phase: phase-13\n\nOld result.\n", encoding="utf-8")
    write_json(
        loop / "state.json",
        {
            "current_state": "EXECUTE",
            "execute_lane": {"phase": "phase-14", "state": "EXECUTE"},
        },
    )

    result = hardening.check_execute_completion_gate(loop)

    assert result["ok"] is False
    assert result["action"] == "blocked_stale_result"
    assert result["blockers"] == ["result.md phase binding mismatch"]


def test_run_phase_hardening_write_promotes_completed_execute(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    (phase_dir / "result.md").write_text("# phase: phase-14\n\nImplemented.\n", encoding="utf-8")
    write_json(
        loop / "state.json",
        {
            "current_state": "EXECUTE",
            "execute_lane": {"phase": "phase-14", "state": "EXECUTE"},
            "last_updated": "2026-05-24T00:00:00Z",
        },
    )

    result = hardening.run_phase_hardening(
        loop,
        tmp_path / ".memoryos" / "evals",
        "phase-14",
        write=True,
    )

    state = json.loads((loop / "state.json").read_text(encoding="utf-8"))
    assert result["execute_completion_gate"]["action"] == "promoted_execute_self_review"
    assert state["current_state"] == "EXECUTE_SELF_REVIEW"


def test_launcher_uses_stable_lockfile_without_unlinking() -> None:
    launcher = (Path(__file__).resolve().parents[1] / ".hermes-loop" / "god_launcher.sh").read_text(
        encoding="utf-8"
    )

    assert 'exec 9>>"$LOCKFILE"' in launcher
    assert "rm -f \"$LOCKFILE\"" not in launcher


def test_launcher_records_and_completes_active_codex_job() -> None:
    launcher = (Path(__file__).resolve().parents[1] / ".hermes-loop" / "god_launcher.sh").read_text(
        encoding="utf-8"
    )

    assert "write_active_job" in launcher
    assert "complete_active_job" in launcher
    assert "CODEX_PID=$!" in launcher
    assert 'wait "$CODEX_PID"' in launcher


def test_hermes_gitignore_covers_runtime_control_artifacts() -> None:
    gitignore = (
        Path(__file__).resolve().parents[1] / ".hermes-loop" / ".gitignore"
    ).read_text(encoding="utf-8")

    assert "active_job.json" in gitignore
    assert "work/**/*.log" in gitignore


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


def test_config_blueprint_consistency_reports_missing_phase_heading(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    write_json(
        loop / "config.json",
        {
            "phases": [
                {
                    "id": "phase-15",
                    "blueprint_heading": "Phase 15 - Old Heading",
                }
            ]
        },
    )
    (loop / "blueprint.md").write_text("## Phase 15 - New Heading\n", encoding="utf-8")

    result = hardening.check_config_blueprint_consistency(loop)

    assert result["ok"] is False
    assert result["missing_headings"] == [
        {"phase": "phase-15", "heading": "Phase 15 - Old Heading"}
    ]


def test_state_phase_order_allows_documented_superseded_prior_phase(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    write_json(
        loop / "state.json",
        {
            "current_phase_idx": 14,
            "phases": [
                {"id": "phase-11", "status": "superseded"},
                {"id": "phase-12", "status": "completed"},
                {"id": "phase-13", "status": "completed"},
                {"id": "phase-14", "status": "in_progress"},
            ],
        },
    )
    (loop / "work" / "phase-11").mkdir(parents=True)
    (loop / "work" / "phase-11" / "adjustment.md").write_text(
        "Decision: `repeat_phase`.\nSuperseded by phase-12 and phase-13 ACK evidence.\n",
        encoding="utf-8",
    )

    result = hardening.check_state_phase_order(loop)

    assert result["ok"] is True
    assert result["problems"] == []


def test_state_phase_order_blocks_undocumented_in_progress_prior_phase(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    write_json(
        loop / "state.json",
        {
            "current_phase_idx": 14,
            "phases": [
                {"id": "phase-11", "status": "in_progress"},
                {"id": "phase-12", "status": "completed"},
                {"id": "phase-14", "status": "in_progress"},
            ],
        },
    )

    result = hardening.check_state_phase_order(loop)

    assert result["ok"] is False
    assert result["problems"] == [
        {
            "phase": "phase-11",
            "status": "in_progress",
            "reason": "phase before current_phase_idx is not completed or documented superseded",
        }
    ]


def test_run_phase_hardening_uses_requested_phase_ack_and_stale_checks(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    phase_dir = loop / "work" / "phase-14"
    phase_dir.mkdir(parents=True)
    write_json(
        phase_dir / "ack.json",
        {
            "ack_level": "usable",
            "context_bundle": {"path": "work/phase-14/context_bundle.md"},
        },
    )
    write_json(
        phase_dir / "review_verdict.json",
        {
            "verdict": "PASS",
            "context_bundle": {"path": "work/phase-14/context_bundle.md"},
        },
    )
    (phase_dir / "result.md").write_text("uses work/phase-14/context_bundle.md\n")

    result = hardening.run_phase_hardening(loop, tmp_path / ".memoryos" / "evals", "phase-14")

    assert result["phase_id"] == "phase-14"
    assert result["ack_gate"]["ok"] is True
    assert result["stale_index"]["current_context_bundle"] == "work/phase-14/context_bundle.md"


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


def test_master_slave_summary_allows_missing_registry(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()

    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    assert summary["ok"] is True
    assert summary["state"] == "missing"
    assert summary["counts"] == {
        "features": 0,
        "reviewable": 0,
        "mergeable": 0,
        "blocked": 0,
    }
    assert summary["merge_queue"] == []
    assert summary["master_review_queue"] == []


def test_master_slave_summary_queues_ready_feature_for_master_review_only(
    tmp_path: Path,
) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    feature_dir = loop / "work" / "features" / "archive-rag"
    worktree = tmp_path / "memoryOS-archive-rag"
    feature_dir.mkdir(parents=True)
    worktree.mkdir()
    write_json(feature_dir / "ack.json", {"ack_level": "usable"})
    write_json(feature_dir / "review_verdict.json", {"verdict": "PASS"})
    (feature_dir / "result.md").write_text("# feature: archive-rag\n", encoding="utf-8")
    write_json(
        loop / "feature_lanes.json",
        {
            "features": [
                {
                    "id": "archive-rag",
                    "state": "ready_for_master_review",
                    "branch": "feat/archive-rag",
                    "worktree": str(worktree),
                    "artifacts": {
                        "ack": "work/features/archive-rag/ack.json",
                        "review_verdict": "work/features/archive-rag/review_verdict.json",
                        "result": "work/features/archive-rag/result.md",
                    },
                    "merge": {
                        "status": "ready_for_master_review",
                        "target_branch": "main",
                        "requires_integrated_tests": True,
                    },
                }
            ]
        },
    )

    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    assert summary["ok"] is True
    assert summary["counts"] == {
        "features": 1,
        "reviewable": 1,
        "mergeable": 0,
        "blocked": 0,
    }
    assert summary["master_review_queue"] == [
        {
            "id": "archive-rag",
            "branch": "feat/archive-rag",
            "worktree": str(worktree),
            "target_branch": "main",
            "strategy": "git_worktree",
        }
    ]
    assert summary["merge_queue"] == []
    assert summary["features"][0]["reviewable"] is True
    assert summary["features"][0]["mergeable"] is False


def test_master_slave_summary_blocks_merge_without_integrated_tests(
    tmp_path: Path,
) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    feature_dir = loop / "work" / "features" / "archive-rag"
    worktree = tmp_path / "memoryOS-archive-rag"
    feature_dir.mkdir(parents=True)
    worktree.mkdir()
    write_json(feature_dir / "ack.json", {"ack_level": "usable"})
    write_json(feature_dir / "review_verdict.json", {"verdict": "PASS"})
    (feature_dir / "result.md").write_text("# feature: archive-rag\n", encoding="utf-8")
    write_json(
        loop / "feature_lanes.json",
        {
            "features": [
                {
                    "id": "archive-rag",
                    "state": "ready_for_merge",
                    "branch": "feat/archive-rag",
                    "worktree": str(worktree),
                    "artifacts": {
                        "ack": "work/features/archive-rag/ack.json",
                        "review_verdict": "work/features/archive-rag/review_verdict.json",
                        "result": "work/features/archive-rag/result.md",
                    },
                    "merge": {
                        "status": "ready_for_merge",
                        "target_branch": "main",
                        "requires_integrated_tests": True,
                    },
                }
            ]
        },
    )

    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    assert summary["ok"] is False
    assert summary["counts"] == {
        "features": 1,
        "reviewable": 0,
        "mergeable": 0,
        "blocked": 1,
    }
    assert summary["merge_queue"] == []
    assert "archive-rag: missing integrated_tests artifact path" in summary["blockers"]


def test_master_slave_summary_requires_integrated_tests_for_all_merge_requests(
    tmp_path: Path,
) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    feature_dir = loop / "work" / "features" / "archive-rag"
    worktree = tmp_path / "memoryOS-archive-rag"
    feature_dir.mkdir(parents=True)
    worktree.mkdir()
    write_json(feature_dir / "ack.json", {"ack_level": "usable"})
    write_json(feature_dir / "review_verdict.json", {"verdict": "PASS"})
    (feature_dir / "result.md").write_text("# feature: archive-rag\n", encoding="utf-8")
    write_json(
        loop / "feature_lanes.json",
        {
            "master_god": {
                "merge_policy": "usable_ack_pass_review_clean_worktree_integrated_tests"
            },
            "features": [
                {
                    "id": "archive-rag",
                    "state": "ready_for_merge",
                    "branch": "feat/archive-rag",
                    "worktree": str(worktree),
                    "artifacts": {
                        "ack": "work/features/archive-rag/ack.json",
                        "review_verdict": "work/features/archive-rag/review_verdict.json",
                        "result": "work/features/archive-rag/result.md",
                    },
                    "merge": {
                        "status": "ready_for_merge",
                        "target_branch": "main",
                    },
                }
            ],
        },
    )

    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    assert summary["ok"] is False
    assert summary["merge_queue"] == []
    assert "archive-rag: missing integrated_tests artifact path" in summary["blockers"]


def test_master_slave_summary_blocks_merge_status_ahead_of_feature_state(
    tmp_path: Path,
) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    feature_dir = loop / "work" / "features" / "archive-rag"
    feature_dir.mkdir(parents=True)
    write_json(
        feature_dir / "integrated_tests.json",
        {"status": "passed", "commands": ["uv run pytest -q"]},
    )
    write_json(
        loop / "feature_lanes.json",
        {
            "features": [
                {
                    "id": "archive-rag",
                    "state": "planned",
                    "artifacts": {
                        "integrated_tests": "work/features/archive-rag/integrated_tests.json",
                    },
                    "merge": {
                        "status": "ready_for_merge",
                        "target_branch": "main",
                    },
                }
            ]
        },
    )

    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    assert summary["ok"] is False
    assert summary["merge_queue"] == []
    assert "archive-rag: merge status is ahead of feature state" in summary["blockers"]
    assert "archive-rag: merge-ready feature requires branch" in summary["blockers"]
    assert "archive-rag: merge-ready feature requires worktree" in summary["blockers"]
    assert "archive-rag: missing ack artifact path" in summary["blockers"]


def test_master_slave_summary_queues_ready_feature_for_master_merge(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    feature_dir = loop / "work" / "features" / "archive-rag"
    worktree = tmp_path / "memoryOS-archive-rag"
    feature_dir.mkdir(parents=True)
    worktree.mkdir()
    write_json(feature_dir / "ack.json", {"ack_level": "usable"})
    write_json(feature_dir / "review_verdict.json", {"verdict": "PASS"})
    write_json(
        feature_dir / "integrated_tests.json",
        {"status": "passed", "commands": ["uv run pytest -q"]},
    )
    (feature_dir / "result.md").write_text("# feature: archive-rag\n", encoding="utf-8")
    write_json(
        loop / "feature_lanes.json",
        {
            "master_god": {"role": "integration_owner"},
            "features": [
                {
                    "id": "archive-rag",
                    "name": "Archive RAG Boundary",
                    "state": "ready_for_merge",
                    "branch": "feat/archive-rag",
                    "worktree": str(worktree),
                    "slave_god": {"role": "feature_owner"},
                    "artifacts": {
                        "ack": "work/features/archive-rag/ack.json",
                        "review_verdict": "work/features/archive-rag/review_verdict.json",
                        "result": "work/features/archive-rag/result.md",
                        "integrated_tests": "work/features/archive-rag/integrated_tests.json",
                    },
                    "merge": {
                        "status": "ready_for_merge",
                        "target_branch": "main",
                        "strategy": "git_worktree",
                        "requires_integrated_tests": True,
                    },
                }
            ],
        },
    )

    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    assert summary["ok"] is True
    assert summary["counts"] == {
        "features": 1,
        "reviewable": 0,
        "mergeable": 1,
        "blocked": 0,
    }
    assert summary["merge_queue"] == [
        {
            "id": "archive-rag",
            "branch": "feat/archive-rag",
            "worktree": str(worktree),
            "target_branch": "main",
            "strategy": "git_worktree",
        }
    ]
    assert summary["path"] == ".hermes-loop/feature_lanes.json"
    feature = summary["features"][0]
    assert feature["artifact_gate"]["paths"] == {
        "ack": ".hermes-loop/work/features/archive-rag/ack.json",
        "review_verdict": ".hermes-loop/work/features/archive-rag/review_verdict.json",
        "result": ".hermes-loop/work/features/archive-rag/result.md",
        "integrated_tests": ".hermes-loop/work/features/archive-rag/integrated_tests.json",
    }


def test_master_slave_summary_blocks_ready_feature_without_ack(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    feature_dir = loop / "work" / "features" / "archive-rag"
    worktree = tmp_path / "memoryOS-archive-rag"
    feature_dir.mkdir(parents=True)
    worktree.mkdir()
    write_json(feature_dir / "review_verdict.json", {"verdict": "PASS"})
    (feature_dir / "result.md").write_text("# feature: archive-rag\n", encoding="utf-8")
    write_json(
        loop / "feature_lanes.json",
        {
            "features": [
                {
                    "id": "archive-rag",
                    "state": "ready_for_merge",
                    "branch": "feat/archive-rag",
                    "worktree": str(worktree),
                    "artifacts": {
                        "ack": "work/features/archive-rag/ack.json",
                        "review_verdict": "work/features/archive-rag/review_verdict.json",
                        "result": "work/features/archive-rag/result.md",
                    },
                    "merge": {"status": "ready_for_merge", "target_branch": "main"},
                }
            ]
        },
    )

    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    assert summary["ok"] is False
    assert summary["counts"] == {
        "features": 1,
        "reviewable": 0,
        "mergeable": 0,
        "blocked": 1,
    }
    assert "archive-rag: ack artifact does not exist" in summary["blockers"]


def test_master_slave_status_writer_emits_json_and_markdown(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    paths = hardening.write_master_slave_status(loop, summary)

    assert Path(paths["json"]).exists()
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "Hermes Master/Slave Feature Status" in markdown
    assert "features: `0`" in markdown
