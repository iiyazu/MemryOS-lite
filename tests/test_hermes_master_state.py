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
