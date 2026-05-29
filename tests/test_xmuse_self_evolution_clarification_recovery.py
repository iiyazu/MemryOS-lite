"""Focused tests for the clarification_recovery blueprint track.

Covers:
- ClarificationRequest is created when a run reaches blocked_for_input
- ClarificationRequest captures missing_input, owner, and resume_path
- resolve_clarification accepts provided information and spawns a follow-up run
- The follow-up run re-enters the standard mainline (chat -> proposal -> resolution -> graph)
- ClarificationResolution records spawned conversation/resolution/graph references
- Resolving a non-open request raises ValueError
- TerminalRunWatcher records a ClarificationRequest for blocked_for_input runs
- TerminalRunWatcher skips runs that already have an open clarification request
- Store persists and retrieves ClarificationRequest and ClarificationResolution
- expire_clarification marks an open request as expired
- Expiring a non-open request raises ValueError
- Audit writer materialises clarification read model
- Dashboard /api/self-evolution exposes clarification_requests and clarification_resolutions
- Dashboard /api/self-evolution/clarifications returns joined clarification read model
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xmuse_core.self_evolution import (
    ClarificationRequest,
    ClarificationResolution,
    ClarificationStatus,
    SelfEvolutionController,
)
from xmuse_core.self_evolution.models import RunTerminalStatus
from xmuse_core.self_evolution.watcher import TerminalRunWatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_blueprint(path: Path) -> None:
    path.write_text(
        """
# xmuse Initial Self-Evolution Blueprint

- `blueprint_set_id`: `xmuse-self-evolution-v0`

## Tracks

### graph_authority
### clarification_recovery
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _seed_blocked_graph(
    tmp_path: Path,
    graph_id: str,
    *,
    missing_input: str = "target deployment environment",
    owner: str = "human",
    resume_path: str = "add deployment target and resume graph",
) -> str:
    resolution_id = graph_id.replace("-graph-v1", "")
    lane_id = f"lane-blocked-{graph_id}"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": f"conv-{graph_id}",
            "resolution_id": resolution_id,
            "version": 1,
            "status": "planned",
            "lanes": [{"feature_id": lane_id, "prompt": "needs info", "depends_on": []}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "blocked_for_input",
                    "prompt": "needs info",
                    "graph_id": graph_id,
                    "resolution_id": resolution_id,
                    "missing_input": missing_input,
                    "input_owner": owner,
                    "resume_path": resume_path,
                }
            ]
        },
    )
    return graph_id


def _seed_merged_graph(tmp_path: Path, graph_id: str) -> str:
    resolution_id = graph_id.replace("-graph-v1", "")
    lane_id = f"lane-merged-{graph_id}"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": f"conv-{graph_id}",
            "resolution_id": resolution_id,
            "version": 1,
            "status": "planned",
            "lanes": [{"feature_id": lane_id, "prompt": "go", "depends_on": []}],
        },
    )
    lanes_path = tmp_path / "feature_lanes.json"
    if lanes_path.exists():
        existing = json.loads(lanes_path.read_text())
        lanes = existing.get("lanes", []) if isinstance(existing, dict) else []
    else:
        lanes = []
    lanes.append(
        {
            "feature_id": lane_id,
            "status": "merged",
            "prompt": "go",
            "graph_id": graph_id,
            "resolution_id": resolution_id,
            "review_verdict_id": f"verdict-{graph_id}",
        }
    )
    _write_json(lanes_path, {"lanes": lanes})
    return graph_id


def _make_controller(tmp_path: Path) -> SelfEvolutionController:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    return SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )


# ---------------------------------------------------------------------------
# ClarificationRequest model tests
# ---------------------------------------------------------------------------


def test_clarification_request_has_open_status_by_default(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-model-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)

    request = controller.record_clarification_request(aggregation)

    assert request.status == ClarificationStatus.OPEN
    assert request.source_run_id == graph_id
    assert request.resolved_at is None


def test_clarification_request_captures_missing_input(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(
        tmp_path,
        "res-blocked-missing-graph-v1",
        missing_input="API key for external service",
        owner="ops-team",
        resume_path="set API_KEY env var and reproject",
    )
    aggregation = controller.aggregate_run_terminal(graph_id)

    request = controller.record_clarification_request(aggregation)

    assert "API key for external service" in request.missing_input_summary
    assert request.owner == "ops-team"
    assert "set API_KEY env var" in request.resume_path


def test_clarification_request_captures_blocked_objects(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(
        tmp_path,
        "res-blocked-objects-graph-v1",
        missing_input="database connection string",
    )
    aggregation = controller.aggregate_run_terminal(graph_id)

    request = controller.record_clarification_request(aggregation)

    assert len(request.blocked_objects) == 1
    assert request.blocked_objects[0]["missing_input"] == "database connection string"


def test_record_clarification_request_raises_for_non_blocked_run(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_merged_graph(tmp_path, "res-merged-not-blocked-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)

    with pytest.raises(ValueError, match="cannot record clarification request"):
        controller.record_clarification_request(aggregation)


def test_clarification_request_is_persisted_in_store(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-persist-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)

    request = controller.record_clarification_request(aggregation)

    stored = controller.store.list_clarification_requests()
    assert any(r.request_id == request.request_id for r in stored)


# ---------------------------------------------------------------------------
# resolve_clarification tests
# ---------------------------------------------------------------------------


def test_resolve_clarification_spawns_follow_up_run(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-resolve-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    resolution = controller.resolve_clarification(
        request,
        provided_information="The deployment target is production-us-east-1.",
    )

    assert resolution.source_run_id == graph_id
    assert resolution.request_id == request.request_id
    assert resolution.spawned_graph_id is not None
    assert resolution.spawned_conversation_id is not None
    assert resolution.spawned_resolution_id is not None


def test_resolve_clarification_marks_request_as_resolved(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-mark-resolved-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    controller.resolve_clarification(
        request,
        provided_information="Deployment target: staging.",
    )

    # The request object is mutated in place and re-persisted
    assert request.status == ClarificationStatus.RESOLVED
    assert request.resolved_at is not None

    # Verify the store reflects the resolved status
    stored = controller.store.list_clarification_requests()
    stored_request = next(r for r in stored if r.request_id == request.request_id)
    assert stored_request.status == ClarificationStatus.RESOLVED


def test_resolve_clarification_raises_for_already_resolved_request(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-double-resolve-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    controller.resolve_clarification(
        request,
        provided_information="First answer.",
    )

    with pytest.raises(ValueError, match="cannot resolve clarification request"):
        controller.resolve_clarification(
            request,
            provided_information="Second answer.",
        )


def test_resolve_clarification_spawned_graph_contains_provided_information(
    tmp_path: Path,
) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(
        tmp_path,
        "res-blocked-prompt-graph-v1",
        missing_input="target region",
        resume_path="set region and reproject",
    )
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    resolution = controller.resolve_clarification(
        request,
        provided_information="Region is eu-west-2.",
    )

    # The spawned graph should exist and contain the provided information in the lane prompt
    from xmuse_core.structuring.graph_store import LaneGraphStore

    graph_store = LaneGraphStore(tmp_path / "lane_graphs")
    spawned_graph = graph_store.get(resolution.spawned_graph_id)
    assert len(spawned_graph.lanes) == 1
    lane = spawned_graph.lanes[0]
    assert "Region is eu-west-2." in lane.prompt
    assert "target region" in lane.prompt
    assert lane.feature_group == "clarification_recovery"


def test_resolve_clarification_persists_resolution_in_store(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-store-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    resolution = controller.resolve_clarification(
        request,
        provided_information="Answer: use staging.",
        provided_by="ops-bot",
    )

    stored = controller.store.list_clarification_resolutions()
    assert any(r.resolution_id == resolution.resolution_id for r in stored)
    stored_res = next(r for r in stored if r.resolution_id == resolution.resolution_id)
    assert stored_res.provided_by == "ops-bot"
    assert stored_res.provided_information == "Answer: use staging."


def test_resolve_clarification_accepts_provided_context(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-context-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    resolution = controller.resolve_clarification(
        request,
        provided_information="Use the staging cluster.",
        provided_context={"region": "us-east-1", "cluster": "staging-k8s"},
    )

    stored = controller.store.list_clarification_resolutions()
    stored_res = next(r for r in stored if r.resolution_id == resolution.resolution_id)
    assert stored_res.provided_context == {"region": "us-east-1", "cluster": "staging-k8s"}


# ---------------------------------------------------------------------------
# TerminalRunWatcher clarification_recovery integration tests
# ---------------------------------------------------------------------------


def test_watcher_records_clarification_request_for_blocked_run(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(
        tmp_path,
        "res-watcher-blocked-graph-v1",
        missing_input="API credentials",
    )
    watcher = TerminalRunWatcher(controller)

    outcomes = watcher.tick()

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.source_run_id == graph_id
    assert outcome.spawned is None
    assert outcome.skip_reason == "clarification_pending"
    assert outcome.clarification_request is not None
    assert outcome.clarification_request.status == ClarificationStatus.OPEN
    assert "API credentials" in outcome.clarification_request.missing_input_summary


def test_watcher_skips_run_with_existing_open_clarification_request(
    tmp_path: Path,
) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-watcher-skip-clarif-graph-v1")
    watcher = TerminalRunWatcher(controller)

    # First tick records the clarification request
    first_outcomes = watcher.tick()
    assert len(first_outcomes) == 1
    assert first_outcomes[0].skip_reason == "clarification_pending"

    # Second tick should skip the same run (already has an open request)
    second_outcomes = watcher.tick()
    sources = [o.source_run_id for o in second_outcomes]
    assert graph_id not in sources


def test_watcher_processes_merged_run_alongside_blocked_run(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    _seed_blocked_graph(tmp_path, "res-watcher-mixed-blocked-graph-v1")
    _seed_merged_graph(tmp_path, "res-watcher-mixed-merged-graph-v1")
    watcher = TerminalRunWatcher(controller)

    outcomes = watcher.tick()

    skip_outcomes = [o for o in outcomes if o.skip_reason == "clarification_pending"]
    spawn_outcomes = [o for o in outcomes if o.spawned is not None]
    assert len(skip_outcomes) == 1
    assert len(spawn_outcomes) == 1


def test_watcher_outcome_clarification_request_field_is_none_for_merged_run(
    tmp_path: Path,
) -> None:
    controller = _make_controller(tmp_path)
    _seed_merged_graph(tmp_path, "res-watcher-merged-no-clarif-graph-v1")
    watcher = TerminalRunWatcher(controller)

    outcomes = watcher.tick()

    assert len(outcomes) == 1
    assert outcomes[0].clarification_request is None


# ---------------------------------------------------------------------------
# Store round-trip tests
# ---------------------------------------------------------------------------


def test_store_clarification_request_round_trip(tmp_path: Path) -> None:
    from xmuse_core.self_evolution.store import SelfEvolutionStore

    store = SelfEvolutionStore(tmp_path / "se_store")
    request = ClarificationRequest(
        request_id="clarreq_test001",
        source_run_id="run-test-001",
        aggregation_id="runagg_test001",
        blocked_objects=[{"lane_id": "lane-1", "missing_input": "env var"}],
        missing_input_summary="env var for deployment",
        owner="human",
        resume_path="set env var and retry",
        status=ClarificationStatus.OPEN,
        created_at="2026-05-28T10:00:00Z",
    )

    store.save_clarification_request(request)
    retrieved = store.list_clarification_requests()

    assert len(retrieved) == 1
    assert retrieved[0].request_id == "clarreq_test001"
    assert retrieved[0].status == ClarificationStatus.OPEN
    assert retrieved[0].missing_input_summary == "env var for deployment"


def test_store_clarification_resolution_round_trip(tmp_path: Path) -> None:
    from xmuse_core.self_evolution.store import SelfEvolutionStore

    store = SelfEvolutionStore(tmp_path / "se_store")
    resolution = ClarificationResolution(
        resolution_id="clarres_test001",
        request_id="clarreq_test001",
        source_run_id="run-test-001",
        provided_information="The env var is DEPLOY_TARGET=staging.",
        provided_context={"target": "staging"},
        provided_by="ops-bot",
        spawned_conversation_id="conv-spawned-001",
        spawned_resolution_id="res-spawned-001",
        spawned_graph_id="res-spawned-001-graph-v1",
        created_at="2026-05-28T10:05:00Z",
    )

    store.save_clarification_resolution(resolution)
    retrieved = store.list_clarification_resolutions()

    assert len(retrieved) == 1
    assert retrieved[0].resolution_id == "clarres_test001"
    assert retrieved[0].provided_by == "ops-bot"
    assert retrieved[0].spawned_graph_id == "res-spawned-001-graph-v1"


def test_store_upserts_clarification_request_on_status_change(tmp_path: Path) -> None:
    from xmuse_core.self_evolution.store import SelfEvolutionStore

    store = SelfEvolutionStore(tmp_path / "se_store")
    request = ClarificationRequest(
        request_id="clarreq_upsert001",
        source_run_id="run-upsert-001",
        aggregation_id="runagg_upsert001",
        blocked_objects=[],
        missing_input_summary="something",
        owner="human",
        resume_path="retry",
        status=ClarificationStatus.OPEN,
        created_at="2026-05-28T10:00:00Z",
    )
    store.save_clarification_request(request)

    # Update status to resolved
    request.status = ClarificationStatus.RESOLVED
    request.resolved_at = "2026-05-28T10:10:00Z"
    store.save_clarification_request(request)

    retrieved = store.list_clarification_requests()
    # Should still be one record (upserted, not duplicated)
    assert len(retrieved) == 1
    assert retrieved[0].status == ClarificationStatus.RESOLVED
    assert retrieved[0].resolved_at == "2026-05-28T10:10:00Z"


# ---------------------------------------------------------------------------
# Clarification request with clarification_request lane field
# ---------------------------------------------------------------------------


def test_record_clarification_request_from_clarification_request_lane_field(
    tmp_path: Path,
) -> None:
    """Lanes may carry a structured clarification_request dict instead of
    top-level blocked_for_input status.  The controller should handle both."""
    controller = _make_controller(tmp_path)
    graph_id = "res-clarif-field-graph-v1"
    resolution_id = "res-clarif-field"
    lane_id = "lane-clarif-field"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-clarif-field",
            "resolution_id": resolution_id,
            "version": 1,
            "status": "planned",
            "lanes": [{"feature_id": lane_id, "prompt": "needs info", "depends_on": []}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "blocked_for_input",
                    "prompt": "needs info",
                    "graph_id": graph_id,
                    "resolution_id": resolution_id,
                    "clarification_request": {
                        "missing_input": "OAuth client secret",
                        "owner": "security-team",
                        "resume_path": "inject secret via vault and reproject",
                    },
                }
            ]
        },
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    assert aggregation.status == RunTerminalStatus.BLOCKED_FOR_INPUT

    request = controller.record_clarification_request(aggregation)

    assert request.status == ClarificationStatus.OPEN
    assert "OAuth client secret" in request.missing_input_summary


# ---------------------------------------------------------------------------
# expire_clarification tests
# ---------------------------------------------------------------------------


def test_expire_clarification_marks_request_as_expired(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-expire-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    controller.expire_clarification(request)

    assert request.status == ClarificationStatus.EXPIRED
    assert request.resolved_at is not None


def test_expire_clarification_persists_in_store(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-expire-persist-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    controller.expire_clarification(request)

    stored = controller.store.list_clarification_requests()
    stored_req = next(r for r in stored if r.request_id == request.request_id)
    assert stored_req.status == ClarificationStatus.EXPIRED
    assert stored_req.resolved_at is not None


def test_expire_clarification_raises_for_already_resolved_request(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-expire-resolved-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    controller.resolve_clarification(request, provided_information="Answer: staging.")

    with pytest.raises(ValueError, match="cannot expire clarification request"):
        controller.expire_clarification(request)


def test_expire_clarification_raises_for_already_expired_request(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-expire-twice-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    controller.expire_clarification(request)

    with pytest.raises(ValueError, match="cannot expire clarification request"):
        controller.expire_clarification(request)


def test_expire_clarification_does_not_spawn_follow_up_run(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    graph_id = _seed_blocked_graph(tmp_path, "res-blocked-expire-no-spawn-graph-v1")
    aggregation = controller.aggregate_run_terminal(graph_id)
    request = controller.record_clarification_request(aggregation)

    controller.expire_clarification(request)

    # No resolution should be created
    resolutions = controller.store.list_clarification_resolutions()
    assert not any(r.request_id == request.request_id for r in resolutions)


# ---------------------------------------------------------------------------
# Audit writer clarification read model tests
# ---------------------------------------------------------------------------


def test_audit_writer_materialises_clarification_read_model(tmp_path: Path) -> None:
    from xmuse_core.self_evolution.audit_writer import SelfEvolutionAuditWriter
    from xmuse_core.self_evolution.store import SelfEvolutionStore

    se_dir = tmp_path / "self_evolution"
    read_models_dir = tmp_path / "read_models"
    store = SelfEvolutionStore(se_dir)

    request = ClarificationRequest(
        request_id="clarreq_audit001",
        source_run_id="run-audit-001",
        aggregation_id="runagg_audit001",
        blocked_objects=[{"lane_id": "lane-1", "missing_input": "API key"}],
        missing_input_summary="API key for external service",
        owner="ops-team",
        resume_path="set API_KEY and retry",
        status=ClarificationStatus.OPEN,
        created_at="2026-05-28T10:00:00Z",
    )
    store.save_clarification_request(request)

    writer = SelfEvolutionAuditWriter(
        store_root=se_dir,
        read_models_root=read_models_dir,
    )
    writer.write()

    assert writer.clarification_path.exists()
    import json as _json
    data = _json.loads(writer.clarification_path.read_text())
    assert data["schema_version"] == "1"
    assert len(data["clarification_requests"]) == 1
    entry = data["clarification_requests"][0]
    assert entry["request_id"] == "clarreq_audit001"
    assert entry["status"] == "open"
    assert entry["missing_input_summary"] == "API key for external service"
    assert entry["owner"] == "ops-team"


def test_audit_writer_clarification_entry_joins_resolution(tmp_path: Path) -> None:
    from xmuse_core.self_evolution.audit_writer import SelfEvolutionAuditWriter
    from xmuse_core.self_evolution.store import SelfEvolutionStore

    se_dir = tmp_path / "self_evolution"
    read_models_dir = tmp_path / "read_models"
    store = SelfEvolutionStore(se_dir)

    request = ClarificationRequest(
        request_id="clarreq_join001",
        source_run_id="run-join-001",
        aggregation_id="runagg_join001",
        blocked_objects=[],
        missing_input_summary="deployment target",
        owner="human",
        resume_path="set target and retry",
        status=ClarificationStatus.RESOLVED,
        created_at="2026-05-28T10:00:00Z",
        resolved_at="2026-05-28T10:05:00Z",
    )
    resolution = ClarificationResolution(
        resolution_id="clarres_join001",
        request_id="clarreq_join001",
        source_run_id="run-join-001",
        provided_information="Target is production-us-east-1.",
        provided_by="ops-bot",
        spawned_conversation_id="conv-join-001",
        spawned_resolution_id="res-join-001",
        spawned_graph_id="res-join-001-graph-v1",
        created_at="2026-05-28T10:05:00Z",
    )
    store.save_clarification_request(request)
    store.save_clarification_resolution(resolution)

    writer = SelfEvolutionAuditWriter(
        store_root=se_dir,
        read_models_root=read_models_dir,
    )
    writer.write()

    import json as _json
    data = _json.loads(writer.clarification_path.read_text())
    req_entry = data["clarification_requests"][0]
    assert req_entry["status"] == "resolved"
    assert req_entry["resolution_id"] == "clarres_join001"
    assert req_entry["provided_by"] == "ops-bot"
    assert req_entry["spawned_graph_id"] == "res-join-001-graph-v1"

    assert len(data["clarification_resolutions"]) == 1
    res_entry = data["clarification_resolutions"][0]
    assert res_entry["resolution_id"] == "clarres_join001"
    assert res_entry["provided_information"] == "Target is production-us-east-1."


def test_audit_writer_clarification_entries_sorted_most_recent_first(
    tmp_path: Path,
) -> None:
    from xmuse_core.self_evolution.audit_writer import SelfEvolutionAuditWriter
    from xmuse_core.self_evolution.store import SelfEvolutionStore

    se_dir = tmp_path / "self_evolution"
    read_models_dir = tmp_path / "read_models"
    store = SelfEvolutionStore(se_dir)

    for i, ts in enumerate(["2026-05-28T08:00:00Z", "2026-05-28T10:00:00Z"], start=1):
        store.save_clarification_request(
            ClarificationRequest(
                request_id=f"clarreq_sort{i:03d}",
                source_run_id=f"run-sort-{i:03d}",
                aggregation_id=f"runagg_sort{i:03d}",
                blocked_objects=[],
                missing_input_summary="something",
                owner="human",
                resume_path="retry",
                status=ClarificationStatus.OPEN,
                created_at=ts,
            )
        )

    writer = SelfEvolutionAuditWriter(
        store_root=se_dir,
        read_models_root=read_models_dir,
    )
    writer.write()

    import json as _json
    data = _json.loads(writer.clarification_path.read_text())
    entries = data["clarification_requests"]
    assert len(entries) == 2
    # Most recent first
    assert entries[0]["created_at"] > entries[1]["created_at"]


def test_audit_writer_clarification_tolerates_empty_store(tmp_path: Path) -> None:
    from xmuse_core.self_evolution.audit_writer import SelfEvolutionAuditWriter

    se_dir = tmp_path / "self_evolution"
    read_models_dir = tmp_path / "read_models"

    writer = SelfEvolutionAuditWriter(
        store_root=se_dir,
        read_models_root=read_models_dir,
    )
    writer.write()

    import json as _json
    data = _json.loads(writer.clarification_path.read_text())
    assert data["clarification_requests"] == []
    assert data["clarification_resolutions"] == []


# ---------------------------------------------------------------------------
# Dashboard API clarification tests
# ---------------------------------------------------------------------------


def _dashboard_client(tmp_path: Path):
    """Create a TestClient for the dashboard API rooted at tmp_path."""
    import importlib.util
    import sqlite3
    from pathlib import Path as _Path

    from fastapi.testclient import TestClient

    from xmuse_core.self_evolution.store import SelfEvolutionStore

    # Seed a minimal feature_lanes.json so the app doesn't error on /api/lanes
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text('{"lanes": []}\n', encoding="utf-8")

    # Seed a minimal chat.db so ChatStore doesn't fail
    db_path = tmp_path / "chat.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()

    # Load dashboard_api via importlib so the xmuse/ directory does not need
    # to be on sys.path (mirrors the pattern used in test_xmuse_dashboard_api.py).
    _project_root = _Path(__file__).resolve().parents[1]
    _module_path = _project_root / "xmuse" / "dashboard_api.py"
    spec = importlib.util.spec_from_file_location("xmuse_dashboard_api", _module_path)
    assert spec is not None and spec.loader is not None
    _mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_mod)
    create_app = _mod.create_app

    return TestClient(create_app(base_dir=tmp_path)), SelfEvolutionStore(
        tmp_path / "self_evolution"
    )


def test_list_self_evolution_includes_clarification_keys(tmp_path: Path) -> None:
    client, _ = _dashboard_client(tmp_path)

    response = client.get("/api/self-evolution")

    assert response.status_code == 200
    data = response.json()
    assert "clarification_requests" in data
    assert "clarification_resolutions" in data
    assert isinstance(data["clarification_requests"], list)
    assert isinstance(data["clarification_resolutions"], list)


def test_list_self_evolution_returns_persisted_clarification_requests(
    tmp_path: Path,
) -> None:
    client, store = _dashboard_client(tmp_path)

    store.save_clarification_request(
        ClarificationRequest(
            request_id="clarreq_dash001",
            source_run_id="run-dash-001",
            aggregation_id="runagg_dash001",
            blocked_objects=[],
            missing_input_summary="DB connection string",
            owner="human",
            resume_path="set DB_URL and retry",
            status=ClarificationStatus.OPEN,
            created_at="2026-05-28T10:00:00Z",
        )
    )

    response = client.get("/api/self-evolution")

    assert response.status_code == 200
    requests = response.json()["clarification_requests"]
    assert len(requests) == 1
    assert requests[0]["request_id"] == "clarreq_dash001"
    assert requests[0]["status"] == "open"


def test_clarifications_endpoint_returns_read_model(tmp_path: Path) -> None:
    client, store = _dashboard_client(tmp_path)

    store.save_clarification_request(
        ClarificationRequest(
            request_id="clarreq_ep001",
            source_run_id="run-ep-001",
            aggregation_id="runagg_ep001",
            blocked_objects=[{"lane_id": "lane-ep", "missing_input": "OAuth secret"}],
            missing_input_summary="OAuth secret for auth service",
            owner="security-team",
            resume_path="inject secret via vault",
            status=ClarificationStatus.OPEN,
            created_at="2026-05-28T10:00:00Z",
        )
    )

    response = client.get("/api/self-evolution/clarifications")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "1"
    assert len(data["clarification_requests"]) == 1
    entry = data["clarification_requests"][0]
    assert entry["request_id"] == "clarreq_ep001"
    assert entry["missing_input_summary"] == "OAuth secret for auth service"
    assert entry["owner"] == "security-team"
    assert entry["status"] == "open"


def test_clarifications_endpoint_tolerates_empty_store(tmp_path: Path) -> None:
    client, _ = _dashboard_client(tmp_path)

    response = client.get("/api/self-evolution/clarifications")

    assert response.status_code == 200
    data = response.json()
    assert data["clarification_requests"] == []
    assert data["clarification_resolutions"] == []


def test_clarifications_endpoint_joins_resolution_to_request(tmp_path: Path) -> None:
    client, store = _dashboard_client(tmp_path)

    store.save_clarification_request(
        ClarificationRequest(
            request_id="clarreq_join_ep001",
            source_run_id="run-join-ep-001",
            aggregation_id="runagg_join_ep001",
            blocked_objects=[],
            missing_input_summary="deployment region",
            owner="human",
            resume_path="set region and retry",
            status=ClarificationStatus.RESOLVED,
            created_at="2026-05-28T10:00:00Z",
            resolved_at="2026-05-28T10:10:00Z",
        )
    )
    store.save_clarification_resolution(
        ClarificationResolution(
            resolution_id="clarres_join_ep001",
            request_id="clarreq_join_ep001",
            source_run_id="run-join-ep-001",
            provided_information="Region is eu-west-2.",
            provided_by="ops-bot",
            spawned_conversation_id="conv-join-ep-001",
            spawned_resolution_id="res-join-ep-001",
            spawned_graph_id="res-join-ep-001-graph-v1",
            created_at="2026-05-28T10:10:00Z",
        )
    )

    response = client.get("/api/self-evolution/clarifications")

    assert response.status_code == 200
    data = response.json()
    req_entry = data["clarification_requests"][0]
    assert req_entry["status"] == "resolved"
    assert req_entry["resolution_id"] == "clarres_join_ep001"
    assert req_entry["spawned_graph_id"] == "res-join-ep-001-graph-v1"

    assert len(data["clarification_resolutions"]) == 1
    res_entry = data["clarification_resolutions"][0]
    assert res_entry["provided_information"] == "Region is eu-west-2."
    assert res_entry["provided_by"] == "ops-bot"
