from __future__ import annotations

from test_xmuse_core_schema import base_master_state, master_feature


def test_core_status_blocks_merge_requested_features_without_validator() -> None:
    from xmuse_core.core.status import derive_master_queues

    state = base_master_state()
    feature = master_feature("v1-quarantine")
    feature["state"] = "ready_for_merge"
    feature["merge"]["status"] = "ready_for_merge"
    state["features"] = [feature]

    result = derive_master_queues(state)

    assert result["queues"]["merge_queue"] == []
    assert result["queues"]["blocked"] == ["v1-quarantine"]
    assert result["counts"]["mergeable"] == 0
    assert result["errors"] == [
        "merge gate failed for v1-quarantine: merge_gate_validator is required"
    ]


def test_core_status_uses_injected_merge_gate_validator() -> None:
    from xmuse_core.core.status import derive_master_queues

    state = base_master_state()
    feature = master_feature("v1-quarantine")
    state["features"] = [feature]
    seen: list[str] = []

    def fake_gate(candidate: dict) -> dict:
        seen.append(candidate["id"])
        return {"valid": True, "errors": []}

    result = derive_master_queues(state, merge_gate_validator=fake_gate)

    assert seen == ["v1-quarantine"]
    assert result["queues"]["merge_queue"] == ["v1-quarantine"]
    assert result["queues"]["blocked"] == []
    assert result["counts"]["mergeable"] == 1
    assert result["errors"] == []


def test_core_status_reports_injected_merge_gate_errors() -> None:
    from xmuse_core.core.status import derive_master_queues

    state = base_master_state()
    feature = master_feature("v1-quarantine")
    state["features"] = [feature]

    def fake_gate(_candidate: dict) -> dict:
        return {"valid": False, "errors": ["missing approval"]}

    result = derive_master_queues(state, merge_gate_validator=fake_gate)

    assert result["queues"]["merge_queue"] == []
    assert result["queues"]["blocked"] == ["v1-quarantine"]
    assert result["errors"] == ["merge gate failed for v1-quarantine: missing approval"]


def test_core_master_status_markdown_matches_status_payload() -> None:
    from xmuse_core.core.status import build_master_status, master_status_markdown

    status = build_master_status(base_master_state())
    markdown = master_status_markdown(status)

    assert status["source"] == "xmuse/master_state.json"
    assert status["counts"]["total"] == 0
    assert "# Hermes Master Status" in markdown
    assert "- activation_state: master_active" in markdown
