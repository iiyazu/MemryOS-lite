"""Tests for evidence bundle assembly.

Evidence bundle: evbundle_e72fecb39ee8439c8338891e9f4fd373

Covers:
1. Bundles correctly curate verdicts, gate reports, and lineage refs.
2. Primary references retained for all summarized items.
3. Selection policy versioning tracked.
4. Bundle assembly works for merged / terminated / blocked_for_input outcomes.
5. Evidence curation maintains auditability for dashboard review.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from xmuse_core.platform.final_action_gate import FinalActionGateStore
from xmuse_core.platform.review_plane import ReviewPlaneController
from xmuse_core.structuring.models import (
    ReviewDecision,
    ReviewTask,
    ReviewTaskStatus,
    ReviewVerdict,
    RunTerminalStatus,
    StructuredEvidenceBundle,
)
from xmuse_core.structuring.verdict_store import EvidenceBundleStore, VerdictStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _make_lanes_file(tmp_path: Path, lanes: list[dict[str, Any]]) -> Path:
    p = tmp_path / "feature_lanes.json"
    p.write_text(json.dumps({"lanes": lanes}), encoding="utf-8")
    return p


def _make_controller(tmp_path: Path, lanes: list[dict[str, Any]]) -> ReviewPlaneController:
    lanes_path = _make_lanes_file(tmp_path, lanes)
    return ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=tmp_path / "review_plane.json",
        final_actions_path=tmp_path / "final_actions.json",
    )


def _seed_verdict(
    store: VerdictStore,
    *,
    verdict_id: str,
    lane_id: str,
    task_id: str,
    decision: ReviewDecision = ReviewDecision.MERGE,
    gate_report_ref: str | None = None,
) -> tuple[ReviewTask, ReviewVerdict]:
    task = ReviewTask(
        task_id=task_id,
        lane_id=lane_id,
        graph_id="graph-1",
        lane_prompt="fix bug",
        gate_report_ref=gate_report_ref,
        status=ReviewTaskStatus.PENDING,
        created_at=_utc_now(),
    )
    verdict = ReviewVerdict(
        id=verdict_id,
        lane_id=lane_id,
        decision=decision,
        summary=f"verdict for {lane_id}",
        task_id=task_id,
        created_at=_utc_now(),
    )
    return store.save_task_and_verdict(task, verdict)


# ---------------------------------------------------------------------------
# Fixture: single merged lane
# ---------------------------------------------------------------------------

@pytest.fixture()
def merged_run(tmp_path: Path):
    """A run with one lane that merged cleanly."""
    lanes = [
        {
            "feature_id": "lane-a",
            "graph_id": "graph-1",
            "status": "merged",
            "prompt": "implement feature A",
        }
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _seed_verdict(
        ctrl.store,
        verdict_id="v-a",
        lane_id="lane-a",
        task_id="task-a",
        decision=ReviewDecision.MERGE,
        gate_report_ref="logs/gates/lane-a/report.json",
    )
    return ctrl, tmp_path


# ---------------------------------------------------------------------------
# Fixture: terminated run (one lane failed)
# ---------------------------------------------------------------------------

@pytest.fixture()
def terminated_run(tmp_path: Path):
    """A run with one lane that failed without a merge verdict."""
    lanes = [
        {
            "feature_id": "lane-b",
            "graph_id": "graph-2",
            "status": "failed",
            "prompt": "implement feature B",
            "failure_reason": "gate_failed",
        }
    ]
    ctrl = _make_controller(tmp_path, lanes)
    # No merge verdict — lane terminated without one.
    return ctrl, tmp_path


# ---------------------------------------------------------------------------
# Fixture: blocked_for_input run (pending final-action hold)
# ---------------------------------------------------------------------------

@pytest.fixture()
def blocked_run(tmp_path: Path):
    """A run where all lanes are closed but a final-action hold is pending."""
    lanes = [
        {
            "feature_id": "lane-c",
            "graph_id": "graph-3",
            "status": "merged",
            "prompt": "implement feature C",
        }
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _seed_verdict(
        ctrl.store,
        verdict_id="v-c",
        lane_id="lane-c",
        task_id="task-c",
        decision=ReviewDecision.MERGE,
    )
    # Create a pending final-action hold to trigger blocked_for_input.
    fa_store = FinalActionGateStore(tmp_path / "final_actions.json")
    fa_store.create_hold(
        lane_id="lane-c",
        verdict_id="v-c",
        action="deploy",
        target_status="deployed",
        summary="awaiting deploy approval",
    )
    return ctrl, tmp_path, fa_store


# ---------------------------------------------------------------------------
# Fixture: multi-lane run with patch-forward lineage
# ---------------------------------------------------------------------------

@pytest.fixture()
def lineage_run(tmp_path: Path):
    """A run with a patch-forward descendant lane."""
    lanes = [
        {
            "feature_id": "lane-orig",
            "graph_id": "graph-4",
            "status": "merged",
            "prompt": "original lane",
        },
        {
            "feature_id": "lane-patch",
            "graph_id": "graph-4",
            "source_lane_id": "lane-orig",
            "status": "merged",
            "prompt": "patch-forward lane",
        },
    ]
    ctrl = _make_controller(tmp_path, lanes)
    _seed_verdict(
        ctrl.store,
        verdict_id="v-orig",
        lane_id="lane-orig",
        task_id="task-orig",
        decision=ReviewDecision.MERGE,
        gate_report_ref="logs/gates/lane-orig/report.json",
    )
    _seed_verdict(
        ctrl.store,
        verdict_id="v-patch",
        lane_id="lane-patch",
        task_id="task-patch",
        decision=ReviewDecision.MERGE,
        gate_report_ref="logs/gates/lane-patch/report.json",
    )
    return ctrl, tmp_path


# ===========================================================================
# 1. Bundles correctly curate verdicts, gate reports, and lineage refs
# ===========================================================================

class TestBundleCuration:
    def test_verdict_refs_populated(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert "v-a" in bundle.verdict_refs

    def test_gate_report_refs_populated(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert "logs/gates/lane-a/report.json" in bundle.gate_report_refs

    def test_lineage_refs_populated_for_patch_forward(self, lineage_run):
        ctrl, _ = lineage_run
        bundle = ctrl.assemble_evidence_bundle("graph-4")
        # Expect a lineage ref linking lane-patch back to lane-orig.
        assert any("lane-patch" in ref and "lane-orig" in ref for ref in bundle.lineage_refs)

    def test_no_spurious_verdict_refs_for_other_graphs(self, tmp_path: Path):
        """Verdicts from a different graph must not bleed into this bundle."""
        lanes_g1 = [
            {
                "feature_id": "lane-x",
                "graph_id": "graph-x",
                "status": "merged",
                "prompt": "x",
            }
        ]
        lanes_g2 = [
            {
                "feature_id": "lane-y",
                "graph_id": "graph-y",
                "status": "merged",
                "prompt": "y",
            }
        ]
        all_lanes = lanes_g1 + lanes_g2
        ctrl = _make_controller(tmp_path, all_lanes)
        _seed_verdict(ctrl.store, verdict_id="v-x", lane_id="lane-x", task_id="task-x")
        _seed_verdict(ctrl.store, verdict_id="v-y", lane_id="lane-y", task_id="task-y")

        bundle = ctrl.assemble_evidence_bundle("graph-x")
        assert "v-x" in bundle.verdict_refs
        assert "v-y" not in bundle.verdict_refs

    def test_gate_report_refs_deduplicated(self, lineage_run):
        ctrl, _ = lineage_run
        bundle = ctrl.assemble_evidence_bundle("graph-4")
        assert len(bundle.gate_report_refs) == len(set(bundle.gate_report_refs))

    def test_verdict_refs_deduplicated(self, lineage_run):
        ctrl, _ = lineage_run
        bundle = ctrl.assemble_evidence_bundle("graph-4")
        assert len(bundle.verdict_refs) == len(set(bundle.verdict_refs))

    def test_bundle_source_run_id_matches_graph(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert bundle.source_run_id == "graph-1"

    def test_bundle_summary_contains_terminal_status(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert "merged" in bundle.summary.lower()

    def test_bundle_summary_contains_verdict_count(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert "Verdicts: 1" in bundle.summary

    def test_bundle_summary_contains_gate_report_count(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert "Gate reports: 1" in bundle.summary


# ===========================================================================
# 2. Primary references retained for all summarized items
# ===========================================================================

class TestPrimaryRefs:
    def test_primary_refs_include_review_task(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        task_refs = [r for r in bundle.primary_refs if r.get("type") == "review_task"]
        assert len(task_refs) >= 1
        assert task_refs[0]["lane_id"] == "lane-a"

    def test_primary_refs_include_review_verdict(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        verdict_refs = [r for r in bundle.primary_refs if r.get("type") == "review_verdict"]
        assert len(verdict_refs) >= 1
        assert verdict_refs[0]["id"] == "v-a"
        assert verdict_refs[0]["decision"] == ReviewDecision.MERGE

    def test_primary_refs_include_gate_report_ref_on_task(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        task_refs = [r for r in bundle.primary_refs if r.get("type") == "review_task"]
        assert task_refs[0]["gate_report_ref"] == "logs/gates/lane-a/report.json"

    def test_primary_refs_include_lane_lineage_for_patch_forward(self, lineage_run):
        ctrl, _ = lineage_run
        bundle = ctrl.assemble_evidence_bundle("graph-4")
        lineage_refs = [r for r in bundle.primary_refs if r.get("type") == "lane_lineage"]
        assert any(r["lane_id"] == "lane-patch" and r["source_lane_id"] == "lane-orig"
                   for r in lineage_refs)

    def test_primary_refs_include_negative_signal_for_failed_lane(self, terminated_run):
        ctrl, _ = terminated_run
        bundle = ctrl.assemble_evidence_bundle("graph-2")
        neg_refs = [r for r in bundle.primary_refs if r.get("type") == "negative_signal"]
        assert len(neg_refs) >= 1
        assert neg_refs[0]["lane_id"] == "lane-b"

    def test_primary_refs_include_incomplete_termination_for_failed_lane(self, terminated_run):
        ctrl, _ = terminated_run
        bundle = ctrl.assemble_evidence_bundle("graph-2")
        inc_refs = [r for r in bundle.primary_refs if r.get("type") == "incomplete_termination"]
        assert len(inc_refs) >= 1
        assert inc_refs[0]["lane_id"] == "lane-b"
        assert "evidence_bundle_ref" in inc_refs[0]

    def test_every_verdict_ref_has_primary_ref(self, lineage_run):
        ctrl, _ = lineage_run
        bundle = ctrl.assemble_evidence_bundle("graph-4")
        verdict_primary_ids = {
            r["id"] for r in bundle.primary_refs if r.get("type") == "review_verdict"
        }
        for vref in bundle.verdict_refs:
            assert vref in verdict_primary_ids, (
                f"verdict_ref {vref!r} has no corresponding primary_ref"
            )

    def test_every_gate_report_ref_has_primary_ref_task(self, lineage_run):
        ctrl, _ = lineage_run
        bundle = ctrl.assemble_evidence_bundle("graph-4")
        task_gate_refs = {
            r["gate_report_ref"]
            for r in bundle.primary_refs
            if r.get("type") == "review_task" and r.get("gate_report_ref")
        }
        for gref in bundle.gate_report_refs:
            assert gref in task_gate_refs, (
                f"gate_report_ref {gref!r} has no corresponding primary_ref task"
            )

    def test_primary_refs_verdict_contains_summary(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        verdict_refs = [r for r in bundle.primary_refs if r.get("type") == "review_verdict"]
        assert verdict_refs[0]["summary"] == "verdict for lane-a"

    def test_primary_refs_verdict_links_task_id(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        verdict_refs = [r for r in bundle.primary_refs if r.get("type") == "review_verdict"]
        assert verdict_refs[0]["task_id"] == "task-a"


# ===========================================================================
# 3. Selection policy versioning tracked
# ===========================================================================

class TestSelectionPolicyVersioning:
    def test_default_policy_id_present(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert bundle.selection_policy_id == "default-v1"

    def test_default_policy_version_present(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert bundle.selection_policy_version == "1"

    def test_custom_policy_id_tracked(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle(
            "graph-1",
            selection_policy_id="strict-v2",
            selection_policy_version="2",
        )
        assert bundle.selection_policy_id == "strict-v2"

    def test_custom_policy_version_tracked(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle(
            "graph-1",
            selection_policy_id="strict-v2",
            selection_policy_version="2",
        )
        assert bundle.selection_policy_version == "2"

    def test_policy_primary_ref_records_curation_contract(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle(
            "graph-1",
            selection_policy_id="strict-v2",
            selection_policy_version="2",
        )

        policy_refs = [
            r for r in bundle.primary_refs if r.get("type") == "selection_policy"
        ]
        assert policy_refs == [
            {
                "type": "selection_policy",
                "lane_id": None,
                "graph_id": "graph-1",
                "policy_id": "strict-v2",
                "policy_version": "2",
                "curation_contract": (
                    "cluster_by_evidence_class; summarize_counts_and_previews; "
                    "retain_full_primary_refs_for_all_cited_or_summarized_items"
                ),
            }
        ]

    def test_policy_fields_persisted_in_store(self, merged_run):
        ctrl, tmp_path = merged_run
        ev_store = EvidenceBundleStore(tmp_path / "evidence_bundles.json")
        bundle = ctrl.assemble_evidence_bundle(
            "graph-1",
            evidence_store=ev_store,
            selection_policy_id="audit-v3",
            selection_policy_version="3",
        )
        loaded = ev_store.get(bundle.bundle_id)
        assert loaded.selection_policy_id == "audit-v3"
        assert loaded.selection_policy_version == "3"

    def test_two_bundles_same_run_different_policies_both_stored(self, merged_run):
        ctrl, tmp_path = merged_run
        ev_store = EvidenceBundleStore(tmp_path / "evidence_bundles.json")
        b1 = ctrl.assemble_evidence_bundle(
            "graph-1", evidence_store=ev_store,
            selection_policy_id="policy-a", selection_policy_version="1",
        )
        b2 = ctrl.assemble_evidence_bundle(
            "graph-1", evidence_store=ev_store,
            selection_policy_id="policy-b", selection_policy_version="2",
        )
        assert b1.bundle_id != b2.bundle_id
        bundles = ev_store.list_for_run("graph-1")
        policy_ids = {b.selection_policy_id for b in bundles}
        assert "policy-a" in policy_ids
        assert "policy-b" in policy_ids


# ===========================================================================
# 4. Bundle assembly for merged / terminated / blocked_for_input outcomes
# ===========================================================================

class TestTerminalOutcomes:
    def test_merged_outcome(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert bundle.run_terminal_status == RunTerminalStatus.MERGED

    def test_terminated_outcome(self, terminated_run):
        ctrl, _ = terminated_run
        bundle = ctrl.assemble_evidence_bundle("graph-2")
        assert bundle.run_terminal_status == RunTerminalStatus.TERMINATED

    def test_blocked_for_input_outcome(self, blocked_run):
        ctrl, tmp_path, fa_store = blocked_run
        bundle = ctrl.assemble_evidence_bundle("graph-3", final_action_store=fa_store)
        assert bundle.run_terminal_status == RunTerminalStatus.BLOCKED_FOR_INPUT

    def test_in_progress_outcome_is_rejected(self, tmp_path: Path):
        lanes = [
            {
                "feature_id": "lane-ip",
                "graph_id": "graph-5",
                "status": "dispatched",
                "prompt": "wip",
            }
        ]
        ctrl = _make_controller(tmp_path, lanes)
        with pytest.raises(RuntimeError, match="source run is not terminal: in_progress"):
            ctrl.assemble_evidence_bundle("graph-5")

    def test_terminated_bundle_has_signal_refs(self, terminated_run):
        ctrl, _ = terminated_run
        bundle = ctrl.assemble_evidence_bundle("graph-2")
        assert len(bundle.signal_refs) >= 1

    def test_terminated_bundle_signal_ref_contains_lane_id(self, terminated_run):
        ctrl, _ = terminated_run
        bundle = ctrl.assemble_evidence_bundle("graph-2")
        assert any("lane-b" in ref for ref in bundle.signal_refs)

    def test_merged_bundle_has_no_signal_refs(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert bundle.signal_refs == []

    def test_terminated_bundle_records_incomplete_termination_verdict(self, terminated_run):
        ctrl, _ = terminated_run
        ctrl.assemble_evidence_bundle("graph-2")
        # The incomplete-termination verdict should now be in the store.
        verdicts = ctrl.store.list_verdicts_for_lane("lane-b")
        incomplete = [v for v in verdicts if v.status == "incomplete_termination"]
        assert len(incomplete) == 1

    def test_terminated_bundle_incomplete_termination_idempotent(self, terminated_run):
        ctrl, _ = terminated_run
        ctrl.assemble_evidence_bundle("graph-2")
        ctrl.assemble_evidence_bundle("graph-2")
        verdicts = ctrl.store.list_verdicts_for_lane("lane-b")
        incomplete = [v for v in verdicts if v.status == "incomplete_termination"]
        assert len(incomplete) == 1

    def test_blocked_bundle_has_no_signal_refs(self, blocked_run):
        ctrl, tmp_path, fa_store = blocked_run
        bundle = ctrl.assemble_evidence_bundle("graph-3", final_action_store=fa_store)
        # No failed lineages — signal_refs should be empty.
        assert bundle.signal_refs == []

    def test_multi_lane_partial_failure(self, tmp_path: Path):
        """One lane merged, one failed → terminated overall."""
        lanes = [
            {"feature_id": "lane-ok", "graph_id": "graph-6", "status": "merged", "prompt": "ok"},
            {"feature_id": "lane-fail", "graph_id": "graph-6", "status": "failed",
             "prompt": "fail", "failure_reason": "exec_failed"},
        ]
        ctrl = _make_controller(tmp_path, lanes)
        _seed_verdict(ctrl.store, verdict_id="v-ok", lane_id="lane-ok", task_id="task-ok")
        bundle = ctrl.assemble_evidence_bundle("graph-6")
        assert bundle.run_terminal_status == RunTerminalStatus.TERMINATED
        assert "v-ok" in bundle.verdict_refs
        assert any("lane-fail" in ref for ref in bundle.signal_refs)


# ===========================================================================
# 5. Evidence curation maintains auditability for dashboard review
# ===========================================================================

class TestAuditability:
    def test_bundle_id_is_unique_per_assembly(self, merged_run):
        ctrl, _ = merged_run
        b1 = ctrl.assemble_evidence_bundle("graph-1")
        b2 = ctrl.assemble_evidence_bundle("graph-1")
        assert b1.bundle_id != b2.bundle_id

    def test_bundle_persisted_in_evidence_store(self, merged_run):
        ctrl, tmp_path = merged_run
        ev_store = EvidenceBundleStore(tmp_path / "evidence_bundles.json")
        bundle = ctrl.assemble_evidence_bundle("graph-1", evidence_store=ev_store)
        loaded = ev_store.get(bundle.bundle_id)
        assert loaded.bundle_id == bundle.bundle_id

    def test_bundle_retrievable_by_run_id(self, merged_run):
        ctrl, tmp_path = merged_run
        ev_store = EvidenceBundleStore(tmp_path / "evidence_bundles.json")
        bundle = ctrl.assemble_evidence_bundle("graph-1", evidence_store=ev_store)
        run_bundles = ev_store.list_for_run("graph-1")
        assert any(b.bundle_id == bundle.bundle_id for b in run_bundles)

    def test_bundle_created_at_is_set(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert bundle.created_at
        assert "Z" in bundle.created_at or "+" in bundle.created_at

    def test_bundle_primary_refs_non_empty_for_reviewed_run(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert len(bundle.primary_refs) >= 2  # at least task + verdict

    def test_bundle_primary_refs_non_empty_for_terminated_run(self, terminated_run):
        ctrl, _ = terminated_run
        bundle = ctrl.assemble_evidence_bundle("graph-2")
        assert len(bundle.primary_refs) >= 1

    def test_bundle_is_structured_evidence_bundle_instance(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        assert isinstance(bundle, StructuredEvidenceBundle)

    def test_bundle_serializable_to_json(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        raw = bundle.model_dump(mode="json")
        assert json.dumps(raw)  # must not raise

    def test_bundle_primary_refs_each_have_type_field(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        for ref in bundle.primary_refs:
            assert "type" in ref, f"primary_ref missing 'type': {ref}"

    def test_bundle_primary_refs_each_have_lane_id(self, merged_run):
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        for ref in bundle.primary_refs:
            assert "lane_id" in ref, f"primary_ref missing 'lane_id': {ref}"

    def test_verdict_lineage_preserved_in_store_after_assembly(self, merged_run):
        ctrl, _ = merged_run
        ctrl.assemble_evidence_bundle("graph-1")
        lineage = ctrl.verdict_lineage_for_lane("lane-a")
        assert len(lineage) == 1
        assert lineage[0]["verdict"]["id"] == "v-a"

    def test_incomplete_termination_verdict_has_evidence_bundle_ref(self, terminated_run):
        ctrl, _ = terminated_run
        ctrl.assemble_evidence_bundle("graph-2")
        verdicts = ctrl.store.list_verdicts_for_lane("lane-b")
        incomplete = [v for v in verdicts if v.status == "incomplete_termination"]
        assert "evbundle_6259476d67dd414a8be293d1025ccb8c" in incomplete[0].summary

    def test_bundle_without_evidence_store_not_persisted(self, merged_run):
        ctrl, tmp_path = merged_run
        ev_store = EvidenceBundleStore(tmp_path / "evidence_bundles.json")
        # Assemble without passing evidence_store.
        ctrl.assemble_evidence_bundle("graph-1")
        # Nothing should be in the store.
        assert ev_store.list_all() == []

    def test_multiple_bundles_for_same_run_all_listed(self, merged_run):
        ctrl, tmp_path = merged_run
        ev_store = EvidenceBundleStore(tmp_path / "evidence_bundles.json")
        b1 = ctrl.assemble_evidence_bundle("graph-1", evidence_store=ev_store)
        b2 = ctrl.assemble_evidence_bundle("graph-1", evidence_store=ev_store)
        bundles = ev_store.list_for_run("graph-1")
        ids = {b.bundle_id for b in bundles}
        assert b1.bundle_id in ids
        assert b2.bundle_id in ids

    def test_dashboard_can_reconstruct_verdict_from_primary_refs(self, merged_run):
        """Simulate a dashboard read: reconstruct verdict details from primary_refs."""
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        verdict_primaries = [r for r in bundle.primary_refs if r.get("type") == "review_verdict"]
        assert verdict_primaries[0]["decision"] == ReviewDecision.MERGE
        assert verdict_primaries[0]["summary"] == "verdict for lane-a"
        assert verdict_primaries[0]["task_id"] == "task-a"

    def test_dashboard_can_reconstruct_gate_report_path_from_primary_refs(self, merged_run):
        """Simulate a dashboard read: reconstruct gate report path from primary_refs."""
        ctrl, _ = merged_run
        bundle = ctrl.assemble_evidence_bundle("graph-1")
        task_primaries = [r for r in bundle.primary_refs if r.get("type") == "review_task"]
        assert task_primaries[0]["gate_report_ref"] == "logs/gates/lane-a/report.json"
