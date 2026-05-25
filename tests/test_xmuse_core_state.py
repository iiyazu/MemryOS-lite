from __future__ import annotations

import json
from pathlib import Path

from test_xmuse_core_schema import base_master_state


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_controller_path_resolves_project_relative_and_absolute_refs(tmp_path: Path) -> None:
    from xmuse_core.core.paths import (
        controller_display_path,
        controller_path,
        resolve_controller_path,
    )

    loop = tmp_path / "project" / "xmuse"
    absolute = tmp_path / "external.json"

    assert controller_path(loop, "xmuse/work/features/a/ack.json") == (
        tmp_path / "project" / "xmuse" / "work" / "features" / "a" / "ack.json"
    )
    assert controller_path(loop, "state.json") == loop / "state.json"
    assert resolve_controller_path(loop, str(absolute)) == absolute
    assert resolve_controller_path(loop, "") is None
    assert controller_display_path(loop, loop / "work" / "features" / "a" / "ack.json") == (
        "xmuse/work/features/a/ack.json"
    )


def test_load_master_state_reads_and_validates_master_state(tmp_path: Path) -> None:
    from xmuse_core.core.state import load_master_state

    loop = tmp_path / "xmuse"
    write_json(loop / "master_state.json", base_master_state())

    result = load_master_state(loop)

    assert result["valid"] is True
    assert result["state"]["activation_state"] == "master_active"
    assert result["errors"] == []


def test_resolve_active_controller_uses_active_master_state(tmp_path: Path) -> None:
    from xmuse_core.core.state import resolve_active_controller

    loop = tmp_path / "xmuse"
    write_json(loop / "master_state.json", base_master_state())

    result = resolve_active_controller(loop)

    assert result["source"] == "master"
    assert result["execution_allowed"] is True
    assert result["errors"] == []


def test_resolve_active_controller_never_executes_isolated_legacy_without_audit(
    tmp_path: Path,
) -> None:
    from xmuse_core.core.state import resolve_active_controller

    loop = tmp_path / "xmuse"
    write_json(
        loop / "legacy" / "root-loop" / "state.json",
        {"current_state": "DONE", "current_phase_idx": 18},
    )

    result = resolve_active_controller(loop)

    assert result["source"] == "legacy_isolated"
    assert result["execution_allowed"] is False
    assert result["state"] is None
    assert result["errors"] == ["isolated legacy root-loop is audit-only"]
