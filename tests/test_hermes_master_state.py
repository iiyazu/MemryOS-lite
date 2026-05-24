import importlib.util
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
HARDENING_PATH = PROJECT / ".hermes-loop" / "hermes_hardening.py"


def load_hardening():
    spec = importlib.util.spec_from_file_location("hermes_hardening", HARDENING_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def base_master_state() -> dict:
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
        "master_policy": {
            "v1_fallback_preserved": True,
            "kernel_opt_in_preserved": True,
            "no_benchmark_score_targets": True,
        },
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


def test_canonical_json_digest_ignores_key_order():
    hardening = load_hardening()

    left = {"b": 2, "a": {"z": 3, "y": [1, 2]}}
    right = {"a": {"y": [1, 2], "z": 3}, "b": 2}

    assert hardening.canonical_json_digest(left) == hardening.canonical_json_digest(right)
    assert hardening.canonical_json_digest(left).startswith("sha256:")


def test_master_state_rejects_active_flag_mismatch():
    hardening = load_hardening()
    state = base_master_state()
    state["activation_state"] = "master_pending"
    state["active"] = True

    result = hardening.validate_master_state(state)

    assert result["valid"] is False
    assert "active must be false unless activation_state is master_active" in result["errors"]


def test_master_state_accepts_pending_inactive_state():
    hardening = load_hardening()
    state = base_master_state()
    state["activation_state"] = "master_pending"
    state["active"] = False

    result = hardening.validate_master_state(state)

    assert result["valid"] is True
    assert result["errors"] == []


def test_active_controller_uses_master_state_when_active(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    state = base_master_state()
    write_json(loop / "master_state.json", state)

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "master"
    assert result["execution_allowed"] is True
    assert result["state"]["activation_state"] == "master_active"


def test_active_controller_blocks_invalid_master_without_legacy_fallback(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    bad = base_master_state()
    bad["activation_state"] = "master_pending"
    bad["active"] = True
    write_json(loop / "master_state.json", bad)
    write_json(loop / "state.json", {"current_state": "DONE"})

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "blocked"
    assert result["execution_allowed"] is False
    assert "active must be false unless activation_state is master_active" in result["errors"]


def test_active_controller_allows_legacy_before_master_exists(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_json(loop / "state.json", {"current_state": "DONE", "current_phase_idx": 18})

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "legacy_root"
    assert result["execution_allowed"] is True
    assert result["state"]["current_state"] == "DONE"


def test_active_controller_never_executes_isolated_legacy_without_audit(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_json(
        loop / "legacy" / "root-loop" / "state.json",
        {"current_state": "DONE", "current_phase_idx": 18},
    )

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "legacy_isolated"
    assert result["execution_allowed"] is False
    assert result["errors"] == ["isolated legacy root-loop is audit-only"]


def test_active_controller_can_read_isolated_legacy_for_explicit_audit(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_json(
        loop / "legacy" / "root-loop" / "state.json",
        {"current_state": "DONE", "current_phase_idx": 18},
    )

    result = hardening.resolve_active_controller(loop, audit=True)

    assert result["source"] == "legacy_isolated"
    assert result["execution_allowed"] is False
    assert result["state"]["current_state"] == "DONE"


def test_active_controller_reports_pending_master_as_prepare(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    pending = base_master_state()
    pending["activation_state"] = "master_pending"
    pending["active"] = False
    write_json(loop / "master_state.json", pending)
    write_json(loop / "state.json", {"current_state": "DONE", "current_phase_idx": 18})

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "master_pending"
    assert result["execution_allowed"] is False
    assert result["legacy_source"] == str(loop / "state.json")


def write_legacy_inputs(loop: Path) -> None:
    write_json(loop / "state.json", {"current_state": "DONE", "current_phase_idx": 18})
    write_json(
        loop / "feature_lanes.json",
        {
            "version": "1.0",
            "features": [
                {
                    "id": "v1-quarantine",
                    "name": "v1 Quarantine",
                    "state": "ready_for_master_review",
                    "branch": "feature/v1-quarantine",
                    "target_branch": "main",
                    "worktree": "../memoryOS-v1-quarantine",
                    "artifacts": {
                        "result": ".hermes-loop/work/features/v1-quarantine/result.md",
                        "ack": ".hermes-loop/work/features/v1-quarantine/ack.json",
                        "review_verdict": ".hermes-loop/work/features/v1-quarantine/review_verdict.json",
                    },
                    "merge": {"status": "ready_for_master_review", "target_branch": "main"},
                },
                {
                    "id": "archive-rag",
                    "name": "Archive RAG",
                    "state": "planned",
                    "branch": "feature/archive-rag",
                    "target_branch": "main",
                    "worktree": "../memoryOS-archive-rag",
                    "artifacts": {},
                    "merge": {"status": "planned", "target_branch": "main"},
                },
            ],
        },
    )
    write_json(loop / "config.json", {"phases": [], "reporter": {"enabled": True}})
    (loop / "blueprint.md").write_text("# Legacy Blueprint\n")
    (loop / "blueprint.zh.md").write_text("# Legacy Blueprint ZH\n")
    (loop / "god_loop_prompt.md").write_text("legacy prompt reads state.json\n")
    write_json(loop / "contracts" / "god_dispatch_template.json", {"legacy": True})


def test_prepare_master_migration_generates_pending_master_files(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)

    result = hardening.prepare_master_migration(loop)

    assert result["status"] == "prepared"
    master_state = json.loads((loop / "master_state.json").read_text())
    assert master_state["activation_state"] == "master_pending"
    assert master_state["active"] is False
    assert [feature["id"] for feature in master_state["features"]] == ["v1-quarantine", "archive-rag"]
    assert (
        master_state["features"][0]["slave_state_path"]
        == ".hermes-loop/work/features/v1-quarantine/slave_state.json"
    )
    assert (loop / "master_blueprint.md").exists()
    assert (loop / "master_config.json").exists()
    assert (loop / "prompts" / "master_god_prompt.md").exists()
    assert (loop / "prompts" / "slave_god_prompt.md").exists()
    assert (loop / "contracts" / "master_dispatch_template.json").exists()
    assert (loop / "contracts" / "slave_dispatch_template.json").exists()
    assert (loop / "work" / "features" / "v1-quarantine" / "slave_state.json").exists()
    assert (loop / "approvals").is_dir()
    assert (loop / "state.json").exists()


def test_prepare_master_migration_does_not_synthesize_merge_approval(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)

    hardening.prepare_master_migration(loop)

    assert not (loop / "approvals" / "v1-quarantine" / "merge_approval.json").exists()
