from __future__ import annotations

import importlib.util
import json
import os
from datetime import UTC, datetime
from pathlib import Path


def load_reporter_module():
    module_path = Path(__file__).resolve().parents[1] / ".hermes-loop" / "hermes_reporter.py"
    spec = importlib.util.spec_from_file_location("hermes_reporter", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def base_master_state_for_reporter() -> dict:
    return {
        "version": "1.0",
        "mode": "master_control",
        "activation_state": "master_active",
        "active": True,
        "history_baseline": ".hermes-loop/history/main_loop_phase0_18.json",
        "legacy_root_loop": ".hermes-loop/legacy/root-loop/",
        "master_blueprint": ".hermes-loop/master_blueprint.md",
        "master_config": ".hermes-loop/master_config.json",
        "prompts": {
            "master": ".hermes-loop/prompts/master_god_prompt.md",
            "slave": ".hermes-loop/prompts/slave_god_prompt.md",
        },
        "dispatch_contracts": {
            "master": ".hermes-loop/contracts/master_dispatch_template.json",
            "slave": ".hermes-loop/contracts/slave_dispatch_template.json",
        },
        "master_policy": {},
        "features": [],
        "queues": {
            "planning_queue": [],
            "active_lanes": [],
            "master_review_queue": [],
            "merge_queue": [],
            "held": [],
            "blocked": [],
            "merged": [],
        },
        "decisions": [],
        "integration": {},
        "github": {},
        "last_updated": "2026-05-24T00:00:00Z",
    }


def test_done_state_refreshes_latest_report_without_starting_god(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reporter = load_reporter_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    state_file = loop / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "current_state": "DONE",
                "execute_lane": {"phase": None, "state": "DONE"},
                "plan_lane": {"phase": None, "state": "DONE"},
                "research_lane": {"phases": []},
                "phases": [{"id": "phase-18", "name": "Governance", "status": "completed"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(reporter, "LOOP", loop)
    monkeypatch.setattr(reporter, "PROJECT", tmp_path)
    monkeypatch.setattr(reporter, "LAUNCHER", loop / "god_launcher.sh")
    monkeypatch.setattr(reporter, "STATE_FILE", state_file)
    monkeypatch.setattr(reporter, "LOCK_FILE", loop / "run.lock")

    def fail_start_god() -> bool:
        raise AssertionError("DONE state must not start God")

    monkeypatch.setattr(reporter, "start_god", fail_start_god)

    report = reporter.main()

    latest = json.loads((loop / "reports" / "latest.json").read_text(encoding="utf-8"))
    latest_md = (loop / "reports" / "latest.md").read_text(encoding="utf-8")
    assert report["action"] == "done"
    assert latest["action"] == "done"
    assert latest["execute_lane"] == {"phase": None, "state": "DONE"}
    assert latest["phases"] == [{"id": "phase-18", "name": "Governance", "status": "completed"}]
    assert "Action| done" in latest_md


def test_reporter_refreshes_master_status_when_legacy_done(tmp_path: Path, monkeypatch) -> None:
    reporter = load_reporter_module()
    loop = tmp_path / ".hermes-loop"
    state_file = loop / "state.json"
    write_json(loop / "state.json", {"current_state": "DONE", "current_phase_idx": 18})
    master_state = base_master_state_for_reporter()
    write_json(loop / "master_state.json", master_state)

    monkeypatch.setattr(reporter, "LOOP", loop)
    monkeypatch.setattr(reporter, "PROJECT", tmp_path)
    monkeypatch.setattr(reporter, "LAUNCHER", loop / "god_launcher.sh")
    monkeypatch.setattr(reporter, "STATE_FILE", state_file)
    monkeypatch.setattr(reporter, "LOCK_FILE", loop / "run.lock")

    def fail_start_god() -> bool:
        raise AssertionError("DONE state must not start God")

    monkeypatch.setattr(reporter, "start_god", fail_start_god)

    reporter.main()

    assert (loop / "master_status.json").exists()
    latest = json.loads((loop / "reports" / "latest.json").read_text(encoding="utf-8"))
    assert latest["master"]["counts"]["reviewable"] == 0
    assert latest["master"]["counts"]["mergeable"] == 0


def test_reporter_handles_master_active_without_legacy_state_file(
    tmp_path: Path, monkeypatch
) -> None:
    reporter = load_reporter_module()
    loop = tmp_path / ".hermes-loop"
    state_file = loop / "state.json"
    write_json(loop / "master_state.json", base_master_state_for_reporter())

    monkeypatch.setattr(reporter, "LOOP", loop)
    monkeypatch.setattr(reporter, "PROJECT", tmp_path)
    monkeypatch.setattr(reporter, "LAUNCHER", loop / "god_launcher.sh")
    monkeypatch.setattr(reporter, "STATE_FILE", state_file)
    monkeypatch.setattr(reporter, "LOCK_FILE", loop / "run.lock")
    monkeypatch.setattr(reporter, "start_god", lambda: False)

    report = reporter.main()

    assert report["master"]["activation_state"] == "master_active"
    assert (loop / "master_status.json").exists()
    assert not (loop / "master_slave_status.json").exists()


def test_god_alive_rejects_exited_active_job_even_with_fresh_heartbeat(
    tmp_path: Path, monkeypatch
) -> None:
    reporter = load_reporter_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    lock_file = loop / "run.lock"
    lock_file.write_text(f"pid={os.getpid()} run_id=test\n", encoding="utf-8")
    heartbeat_ts = datetime.now(UTC).isoformat()
    (loop / "heartbeat.log").write_text(f"GOD alive01 {heartbeat_ts}\n")
    write_json(
        loop / "active_job.json",
        {
            "pid": 999999999,
            "phase_id": "master-control",
            "prompt_file": ".hermes-loop/prompts/master_god_prompt.md",
            "attempt": 1,
            "output_path": "codex_output.log",
            "idle_timeout_seconds": 10800,
            "started_at": "2026-05-24T11:48:12Z",
            "status": "running",
        },
    )

    monkeypatch.setattr(reporter, "LOOP", loop)
    monkeypatch.setattr(reporter, "LOCK_FILE", lock_file)
    assert reporter.is_god_alive() is False


def test_active_job_liveness_marks_dead_running_job_failed(tmp_path: Path, monkeypatch) -> None:
    reporter = load_reporter_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    write_json(
        loop / "active_job.json",
        {
            "pid": 999999999,
            "phase_id": "master-control",
            "prompt_file": ".hermes-loop/prompts/master_god_prompt.md",
            "attempt": 1,
            "output_path": "codex_output.log",
            "idle_timeout_seconds": 10800,
            "started_at": "2026-05-24T11:48:12Z",
            "status": "running",
        },
    )

    monkeypatch.setattr(reporter, "LOOP", loop)

    assert reporter.active_job_liveness() == "not_running"
    active_job = json.loads((loop / "active_job.json").read_text(encoding="utf-8"))
    assert active_job["status"] == "failed"
    assert active_job["exit_code"] == 143


def test_reporter_restarts_when_active_job_is_stale_despite_fresh_heartbeat(
    tmp_path: Path, monkeypatch
) -> None:
    reporter = load_reporter_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    state_file = loop / "state.json"
    lock_file = loop / "run.lock"
    lock_file.write_text(f"pid={os.getpid()} run_id=test\n", encoding="utf-8")
    heartbeat_ts = datetime.now(UTC).isoformat()
    (loop / "heartbeat.log").write_text(f"GOD alive01 {heartbeat_ts}\n")
    write_json(loop / "master_state.json", base_master_state_for_reporter())
    write_json(
        loop / "active_job.json",
        {
            "pid": 999999999,
            "phase_id": "master-control",
            "prompt_file": ".hermes-loop/prompts/master_god_prompt.md",
            "attempt": 1,
            "output_path": "codex_output.log",
            "idle_timeout_seconds": 10800,
            "started_at": "2026-05-24T11:48:12Z",
            "status": "running",
        },
    )
    starts = {"count": 0}

    def start_god() -> bool:
        starts["count"] += 1
        return True

    monkeypatch.setattr(reporter, "LOOP", loop)
    monkeypatch.setattr(reporter, "PROJECT", tmp_path)
    monkeypatch.setattr(reporter, "LAUNCHER", loop / "god_launcher.sh")
    monkeypatch.setattr(reporter, "STATE_FILE", state_file)
    monkeypatch.setattr(reporter, "LOCK_FILE", lock_file)
    monkeypatch.setattr(reporter, "start_god", start_god)

    report = reporter.main()

    assert starts["count"] == 1
    assert report["action"] == "started_ok"


def test_latest_markdown_surfaces_master_review_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reporter = load_reporter_module()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()
    state_file = loop / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "current_state": "DONE",
                "execute_lane": {"phase": None, "state": "DONE"},
                "plan_lane": {"phase": None, "state": "DONE"},
                "research_lane": {"phases": []},
                "phases": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(reporter, "LOOP", loop)
    monkeypatch.setattr(reporter, "PROJECT", tmp_path)
    monkeypatch.setattr(reporter, "LAUNCHER", loop / "god_launcher.sh")
    monkeypatch.setattr(reporter, "STATE_FILE", state_file)
    monkeypatch.setattr(reporter, "LOCK_FILE", loop / "run.lock")
    monkeypatch.setattr(
        reporter,
        "master_slave_report",
        lambda: {"counts": {"features": 1, "reviewable": 1, "mergeable": 0, "blocked": 0}},
    )

    reporter.main()

    latest_md = (loop / "reports" / "latest.md").read_text(encoding="utf-8")
    assert "1 reviewable" in latest_md
    assert "0 mergeable" in latest_md
