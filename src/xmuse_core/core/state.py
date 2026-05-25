from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xmuse_core.core.schema import validate_master_state

MASTER_STATE_FILE = "master_state.json"
LEGACY_ROOT_LOOP_DIR = "legacy/root-loop"


def _load_json_path(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"missing file: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON in {path}: {exc}"]
    if not isinstance(payload, dict):
        return None, [f"JSON root must be an object: {path}"]
    return payload, []


def load_master_state(loop_root: str | Path) -> dict[str, Any]:
    loop = Path(loop_root)
    master_path = loop / MASTER_STATE_FILE
    master_state, load_errors = _load_json_path(master_path)
    if master_state is None:
        return {
            "valid": False,
            "path": str(master_path),
            "state": None,
            "errors": load_errors,
        }
    validation = validate_master_state(master_state)
    return {
        "valid": validation["valid"],
        "path": str(master_path),
        "state": master_state,
        "errors": validation["errors"],
    }


def resolve_active_controller(loop_root: str | Path, *, audit: bool = False) -> dict[str, Any]:
    loop = Path(loop_root)
    master_path = loop / MASTER_STATE_FILE
    legacy_isolated = loop / LEGACY_ROOT_LOOP_DIR / "state.json"
    legacy_current = loop / "state.json"

    if master_path.exists():
        master_state, load_errors = _load_json_path(master_path)
        if master_state is None:
            return {
                "source": "blocked",
                "path": str(master_path),
                "state": None,
                "execution_allowed": False,
                "errors": load_errors,
            }
        validation = validate_master_state(master_state)
        if not validation["valid"]:
            return {
                "source": "blocked",
                "path": str(master_path),
                "state": master_state,
                "execution_allowed": False,
                "errors": validation["errors"],
            }
        if master_state["activation_state"] == "master_active":
            return {
                "source": "master",
                "path": str(master_path),
                "state": master_state,
                "execution_allowed": True,
                "errors": [],
            }
        if master_state["activation_state"] == "master_pending":
            legacy_source = legacy_isolated if legacy_isolated.exists() else legacy_current
            return {
                "source": "master_pending",
                "path": str(master_path),
                "legacy_source": str(legacy_source),
                "state": master_state,
                "execution_allowed": False,
                "errors": [],
            }
        return {
            "source": "blocked",
            "path": str(master_path),
            "state": master_state,
            "execution_allowed": False,
            "errors": [
                f"activation_state does not allow execution: {master_state['activation_state']}"
            ],
        }

    if legacy_isolated.exists():
        legacy_state, load_errors = _load_json_path(legacy_isolated)
        errors = load_errors if load_errors else ["isolated legacy root-loop is audit-only"]
        return {
            "source": "legacy_isolated",
            "path": str(legacy_isolated),
            "state": legacy_state if audit else None,
            "execution_allowed": False,
            "errors": load_errors if audit else errors,
        }

    legacy_state, load_errors = _load_json_path(legacy_current)
    return {
        "source": "legacy_root",
        "path": str(legacy_current),
        "state": legacy_state,
        "execution_allowed": legacy_state is not None,
        "errors": load_errors,
    }
