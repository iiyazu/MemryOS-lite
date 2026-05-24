from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_reporter_module():
    module_path = Path(__file__).resolve().parents[1] / ".hermes-loop" / "hermes_reporter.py"
    spec = importlib.util.spec_from_file_location("hermes_reporter", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
