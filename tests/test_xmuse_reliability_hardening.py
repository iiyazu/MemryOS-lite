"""Tests for the reliability_hardening track primitives.

Covers:
- RunHeartbeat: record creation, liveness classification, stall detection
- HeartbeatStore: append and list_for_run / latest_for_run
- StaleArtifactRecord: scan, quarantine, promotion_safe
- AckConsistencyGate: consistent / inconsistent / missing cases
- IncidentClassifier: watch / recover / stop decision rules
- IncidentRecord.blocks_auto_followup
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xmuse_core.self_evolution.recovery import (
    CircuitOpenError,
    CircuitState,
    RecoveryConfig,
    RecoveryManager,
)
from xmuse_core.self_evolution.reliability import (
    AckConsistencyGate,
    AckOutcome,
    HeartbeatStatus,
    HeartbeatStore,
    IncidentClassifier,
    IncidentLevel,
    RunHeartbeat,
    StaleArtifactRecord,
    StaleArtifactVerdict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_str(delta_s: int = 0) -> str:
    dt = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=delta_s)
    return dt.isoformat().replace("+00:00", "Z")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# RunHeartbeat
# ---------------------------------------------------------------------------


class TestRunHeartbeat:
    def test_record_creates_alive_heartbeat(self) -> None:
        hb = RunHeartbeat.record(run_id="run-1", heartbeat_interval_s=300)
        assert hb.run_id == "run-1"
        assert hb.status is HeartbeatStatus.ALIVE
        assert hb.heartbeat_id.startswith("hb_")
        assert hb.expected_next_by is not None

    def test_classify_status_alive_before_deadline(self) -> None:
        hb = RunHeartbeat.record(run_id="run-1", heartbeat_interval_s=300)
        # now is before expected_next_by
        status = hb.classify_status(now=_utc_str(0))
        assert status is HeartbeatStatus.ALIVE

    def test_classify_status_stalled_after_deadline(self) -> None:
        hb = RunHeartbeat.record(run_id="run-1", heartbeat_interval_s=60)
        # simulate now = 120 s after expected_next_by
        future = _utc_str(60 + 120)
        status = hb.classify_status(now=future)
        assert status is HeartbeatStatus.STALLED

    def test_classify_status_completed_overrides_deadline(self) -> None:
        hb = RunHeartbeat.record(run_id="run-1", heartbeat_interval_s=60)
        completed_hb = hb.model_copy(update={"status": HeartbeatStatus.COMPLETED})
        # even if deadline has passed, completed wins
        future = _utc_str(60 + 120)
        status = completed_hb.classify_status(now=future)
        assert status is HeartbeatStatus.COMPLETED

    def test_record_includes_lane_counts(self) -> None:
        hb = RunHeartbeat.record(
            run_id="run-2",
            lane_counts={"total": 3, "merged": 2, "dispatched": 1},
        )
        assert hb.lane_counts == {"total": 3, "merged": 2, "dispatched": 1}

    def test_record_includes_worker_id(self) -> None:
        hb = RunHeartbeat.record(run_id="run-3", worker_id="worker-abc")
        assert hb.worker_id == "worker-abc"


# ---------------------------------------------------------------------------
# HeartbeatStore
# ---------------------------------------------------------------------------


class TestHeartbeatStore:
    def test_append_and_list_for_run(self, tmp_path: Path) -> None:
        store = HeartbeatStore(tmp_path / "heartbeats.jsonl")
        hb1 = RunHeartbeat.record(run_id="run-x")
        hb2 = RunHeartbeat.record(run_id="run-x")
        hb3 = RunHeartbeat.record(run_id="run-y")
        store.append(hb1)
        store.append(hb2)
        store.append(hb3)

        records = store.list_for_run("run-x")
        assert len(records) == 2
        assert all(r.run_id == "run-x" for r in records)

    def test_latest_for_run_returns_last(self, tmp_path: Path) -> None:
        store = HeartbeatStore(tmp_path / "heartbeats.jsonl")
        hb1 = RunHeartbeat.record(run_id="run-x")
        hb2 = RunHeartbeat.record(run_id="run-x")
        store.append(hb1)
        store.append(hb2)

        latest = store.latest_for_run("run-x")
        assert latest is not None
        assert latest.heartbeat_id == hb2.heartbeat_id

    def test_latest_for_run_returns_none_when_empty(self, tmp_path: Path) -> None:
        store = HeartbeatStore(tmp_path / "heartbeats.jsonl")
        assert store.latest_for_run("run-missing") is None

    def test_list_for_run_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        store = HeartbeatStore(tmp_path / "no_file.jsonl")
        assert store.list_for_run("run-x") == []

    def test_store_creates_parent_dirs(self, tmp_path: Path) -> None:
        store = HeartbeatStore(tmp_path / "deep" / "nested" / "hb.jsonl")
        hb = RunHeartbeat.record(run_id="run-z")
        store.append(hb)
        assert (tmp_path / "deep" / "nested" / "hb.jsonl").exists()

    def test_store_tolerates_corrupt_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "hb.jsonl"
        hb = RunHeartbeat.record(run_id="run-ok")
        path.write_text("not-json\n" + hb.model_dump_json() + "\n", encoding="utf-8")
        store = HeartbeatStore(path)
        records = store.list_for_run("run-ok")
        assert len(records) == 1


# ---------------------------------------------------------------------------
# StaleArtifactRecord
# ---------------------------------------------------------------------------


class TestStaleArtifactRecord:
    def test_scan_all_active(self, tmp_path: Path) -> None:
        ref_id = "graph-abc"
        p1 = tmp_path / "report.json"
        p2 = tmp_path / "result.md"
        _write(p1, json.dumps({"run_id": ref_id, "passed": True}))
        _write(p2, f"# Result\n\nrun_id: {ref_id}\n")

        record = StaleArtifactRecord.scan(
            run_id="run-1",
            reference_id=ref_id,
            candidate_paths=[p1, p2],
        )
        assert record.verdict is StaleArtifactVerdict.CLEAN
        assert record.stale_paths == []
        assert len(record.active_paths) == 2
        assert record.promotion_safe is True

    def test_scan_detects_stale_artifact(self, tmp_path: Path) -> None:
        ref_id = "graph-new"
        p_active = tmp_path / "active.json"
        p_stale = tmp_path / "stale.json"
        _write(p_active, json.dumps({"run_id": ref_id}))
        _write(p_stale, json.dumps({"run_id": "graph-old"}))

        record = StaleArtifactRecord.scan(
            run_id="run-1",
            reference_id=ref_id,
            candidate_paths=[p_active, p_stale],
        )
        assert record.verdict is StaleArtifactVerdict.STALE
        assert str(p_stale) in record.stale_paths
        assert str(p_active) in record.active_paths
        assert record.promotion_safe is False

    def test_scan_missing_artifact(self, tmp_path: Path) -> None:
        ref_id = "graph-x"
        missing = tmp_path / "missing.json"

        record = StaleArtifactRecord.scan(
            run_id="run-1",
            reference_id=ref_id,
            candidate_paths=[missing],
        )
        assert str(missing) in record.missing_paths
        assert record.verdict is StaleArtifactVerdict.CLEAN  # missing != stale

    def test_quarantine_moves_stale_to_quarantined(self, tmp_path: Path) -> None:
        ref_id = "graph-new"
        p_stale = tmp_path / "stale.json"
        _write(p_stale, json.dumps({"run_id": "graph-old"}))

        record = StaleArtifactRecord.scan(
            run_id="run-1",
            reference_id=ref_id,
            candidate_paths=[p_stale],
        )
        assert record.verdict is StaleArtifactVerdict.STALE

        quarantined = record.quarantine([str(p_stale)])
        assert str(p_stale) in quarantined.quarantined_paths
        assert str(p_stale) not in quarantined.stale_paths
        assert quarantined.verdict is StaleArtifactVerdict.QUARANTINED
        assert quarantined.promotion_safe is True

    def test_quarantine_ignores_non_stale_paths(self, tmp_path: Path) -> None:
        ref_id = "graph-new"
        p_stale = tmp_path / "stale.json"
        _write(p_stale, json.dumps({"run_id": "graph-old"}))

        record = StaleArtifactRecord.scan(
            run_id="run-1",
            reference_id=ref_id,
            candidate_paths=[p_stale],
        )
        # quarantine a path that is not in stale_paths
        quarantined = record.quarantine(["/some/other/path.json"])
        assert quarantined.stale_paths == record.stale_paths
        assert quarantined.quarantined_paths == []

    def test_scan_empty_candidate_list(self) -> None:
        record = StaleArtifactRecord.scan(
            run_id="run-1",
            reference_id="graph-x",
            candidate_paths=[],
        )
        assert record.verdict is StaleArtifactVerdict.CLEAN
        assert record.promotion_safe is True


# ---------------------------------------------------------------------------
# AckConsistencyGate
# ---------------------------------------------------------------------------


class TestAckConsistencyGate:
    def test_consistent_with_valid_artifacts(self, tmp_path: Path) -> None:
        run_id = "run-consistent"
        p = tmp_path / "report.json"
        _write(p, json.dumps({"run_id": run_id, "passed": True}))

        gate = AckConsistencyGate()
        result = gate.check(
            run_id=run_id,
            artifact_paths=[p],
            gate_report={"passed": True},
            lane_status={"normalized_status": "merged", "terminal": True},
        )
        assert result.outcome is AckOutcome.CONSISTENT
        assert result.passed is True
        assert result.blockers == []

    def test_inconsistent_missing_artifact(self, tmp_path: Path) -> None:
        run_id = "run-missing"
        missing = tmp_path / "missing.json"

        gate = AckConsistencyGate()
        result = gate.check(run_id=run_id, artifact_paths=[missing])
        assert result.outcome is AckOutcome.INCONSISTENT
        assert any("missing artifact" in b for b in result.blockers)

    def test_inconsistent_artifact_does_not_reference_run_id(self, tmp_path: Path) -> None:
        run_id = "run-target"
        p = tmp_path / "report.json"
        _write(p, json.dumps({"run_id": "run-other", "passed": True}))

        gate = AckConsistencyGate()
        result = gate.check(run_id=run_id, artifact_paths=[p])
        assert result.outcome is AckOutcome.INCONSISTENT
        assert any("run_id" in b for b in result.blockers)

    def test_inconsistent_gate_report_failed(self) -> None:
        gate = AckConsistencyGate()
        result = gate.check(
            run_id="run-x",
            gate_report={"passed": False},
        )
        assert result.outcome is AckOutcome.INCONSISTENT
        assert any("passed=false" in b for b in result.blockers)

    def test_inconsistent_gate_report_bad_status(self) -> None:
        gate = AckConsistencyGate()
        result = gate.check(
            run_id="run-x",
            gate_report={"status": "failed"},
        )
        assert result.outcome is AckOutcome.INCONSISTENT

    def test_inconsistent_lane_not_terminal(self) -> None:
        gate = AckConsistencyGate()
        result = gate.check(
            run_id="run-x",
            lane_status={"normalized_status": "dispatched", "terminal": False},
        )
        assert result.outcome is AckOutcome.INCONSISTENT
        assert any("not terminal" in b for b in result.blockers)

    def test_missing_when_no_artifacts_provided(self) -> None:
        gate = AckConsistencyGate()
        result = gate.check(run_id="run-x")
        assert result.outcome is AckOutcome.MISSING
        assert result.passed is False

    def test_consistent_gate_report_status_string(self) -> None:
        gate = AckConsistencyGate()
        result = gate.check(
            run_id="run-x",
            gate_report={"status": "passed"},
            lane_status={"normalized_status": "terminated", "terminal": True},
        )
        assert result.outcome is AckOutcome.CONSISTENT

    def test_check_id_is_unique(self) -> None:
        gate = AckConsistencyGate()
        r1 = gate.check(run_id="run-x", gate_report={"passed": True})
        r2 = gate.check(run_id="run-x", gate_report={"passed": True})
        assert r1.check_id != r2.check_id


# ---------------------------------------------------------------------------
# IncidentClassifier
# ---------------------------------------------------------------------------


class TestIncidentClassifier:
    def test_watch_when_no_signals(self) -> None:
        clf = IncidentClassifier()
        record = clf.classify(run_id="run-1")
        assert record.level is IncidentLevel.WATCH
        assert record.blocks_auto_followup is False

    def test_recover_on_stalled_heartbeat(self) -> None:
        clf = IncidentClassifier()
        hb = RunHeartbeat.record(run_id="run-1", heartbeat_interval_s=60)
        future = _utc_str(60 + 120)
        record = clf.classify(run_id="run-1", heartbeat=hb, heartbeat_now=future)
        assert record.level is IncidentLevel.RECOVER
        assert "stalled" in record.reason

    def test_recover_on_stale_artifacts(self, tmp_path: Path) -> None:
        p = tmp_path / "stale.json"
        _write(p, json.dumps({"run_id": "old-run"}))
        stale = StaleArtifactRecord.scan(
            run_id="run-1",
            reference_id="new-run",
            candidate_paths=[p],
        )
        clf = IncidentClassifier()
        record = clf.classify(run_id="run-1", stale_record=stale)
        assert record.level is IncidentLevel.RECOVER
        assert "stale" in record.reason

    def test_recover_on_ack_inconsistency(self) -> None:
        gate = AckConsistencyGate()
        ack = gate.check(run_id="run-1", gate_report={"passed": False})
        clf = IncidentClassifier()
        record = clf.classify(run_id="run-1", ack_check=ack)
        assert record.level is IncidentLevel.RECOVER
        assert "ack" in record.reason

    def test_recover_on_failure_count(self) -> None:
        clf = IncidentClassifier()
        record = clf.classify(run_id="run-1", failure_count=1)
        assert record.level is IncidentLevel.RECOVER

    def test_stop_on_repeated_failures(self) -> None:
        clf = IncidentClassifier(stop_on_repeated_failures=3)
        record = clf.classify(run_id="run-1", repeated_failure_count=3)
        assert record.level is IncidentLevel.STOP
        assert record.blocks_auto_followup is True

    def test_stop_on_budget_exhausted(self) -> None:
        clf = IncidentClassifier()
        record = clf.classify(run_id="run-1", budget_exhausted=True)
        assert record.level is IncidentLevel.STOP

    def test_stop_on_hard_blocker(self) -> None:
        clf = IncidentClassifier()
        record = clf.classify(run_id="run-1", hard_blocker=True)
        assert record.level is IncidentLevel.STOP

    def test_stop_takes_priority_over_recover(self) -> None:
        """budget_exhausted (stop) beats stalled heartbeat (recover)."""
        clf = IncidentClassifier()
        hb = RunHeartbeat.record(run_id="run-1", heartbeat_interval_s=60)
        future = _utc_str(60 + 120)
        record = clf.classify(
            run_id="run-1",
            heartbeat=hb,
            heartbeat_now=future,
            budget_exhausted=True,
        )
        assert record.level is IncidentLevel.STOP

    def test_signals_are_recorded(self) -> None:
        clf = IncidentClassifier()
        record = clf.classify(
            run_id="run-1",
            failure_count=2,
            extra_signals={"custom_key": "custom_value"},
        )
        assert record.signals["failure_count"] == 2
        assert record.signals["custom_key"] == "custom_value"

    def test_incident_id_is_unique(self) -> None:
        clf = IncidentClassifier()
        r1 = clf.classify(run_id="run-1")
        r2 = clf.classify(run_id="run-1")
        assert r1.incident_id != r2.incident_id

    def test_watch_with_alive_heartbeat_and_clean_stale(self, tmp_path: Path) -> None:
        hb = RunHeartbeat.record(run_id="run-1", heartbeat_interval_s=300)
        ref_id = "graph-current"
        p = tmp_path / "report.json"
        _write(p, json.dumps({"run_id": ref_id}))
        stale = StaleArtifactRecord.scan(
            run_id="run-1",
            reference_id=ref_id,
            candidate_paths=[p],
        )
        gate = AckConsistencyGate()
        ack = gate.check(
            run_id="run-1",
            gate_report={"passed": True},
            lane_status={"normalized_status": "merged", "terminal": True},
        )
        clf = IncidentClassifier()
        record = clf.classify(
            run_id="run-1",
            heartbeat=hb,
            heartbeat_now=_utc_str(0),
            stale_record=stale,
            ack_check=ack,
        )
        assert record.level is IncidentLevel.WATCH

    def test_repeated_failure_below_threshold_is_recover(self) -> None:
        clf = IncidentClassifier(stop_on_repeated_failures=3)
        record = clf.classify(run_id="run-1", repeated_failure_count=2)
        # 2 < 3 threshold, but failure_count is 0 and repeated_failure_count
        # is not a recover trigger by itself — only failure_count >= 1 is
        assert record.level is IncidentLevel.WATCH

    def test_custom_stop_threshold(self) -> None:
        clf = IncidentClassifier(stop_on_repeated_failures=1)
        record = clf.classify(run_id="run-1", repeated_failure_count=1)
        assert record.level is IncidentLevel.STOP


# ---------------------------------------------------------------------------
# Integration: full reliability check flow
# ---------------------------------------------------------------------------


class TestReliabilityFlow:
    """End-to-end flow: heartbeat -> stale scan -> ack gate -> incident."""

    def test_healthy_run_produces_watch(self, tmp_path: Path) -> None:
        run_id = "run-healthy"
        # stale scan and ack gate both use run_id as the reference token
        ref_id = run_id

        # Write an artifact that references the current run
        artifact = tmp_path / "gate_report.json"
        _write(artifact, json.dumps({"run_id": run_id, "passed": True}))

        # Heartbeat is alive
        hb = RunHeartbeat.record(run_id=run_id, heartbeat_interval_s=300)

        # Stale scan: clean (artifact contains run_id)
        stale = StaleArtifactRecord.scan(
            run_id=run_id,
            reference_id=ref_id,
            candidate_paths=[artifact],
        )
        assert stale.promotion_safe

        # ACK gate: consistent
        gate = AckConsistencyGate()
        ack = gate.check(
            run_id=run_id,
            artifact_paths=[artifact],
            gate_report={"passed": True},
            lane_status={"normalized_status": "merged", "terminal": True},
        )
        assert ack.passed

        # Incident: watch
        clf = IncidentClassifier()
        incident = clf.classify(
            run_id=run_id,
            heartbeat=hb,
            heartbeat_now=_utc_str(0),
            stale_record=stale,
            ack_check=ack,
        )
        assert incident.level is IncidentLevel.WATCH
        assert not incident.blocks_auto_followup

    def test_stalled_run_with_stale_artifact_produces_recover(self, tmp_path: Path) -> None:
        run_id = "run-stalled"
        ref_id = "graph-new"

        # Stale artifact from old run
        artifact = tmp_path / "old_report.json"
        _write(artifact, json.dumps({"run_id": "graph-old"}))

        # Heartbeat is stalled
        hb = RunHeartbeat.record(run_id=run_id, heartbeat_interval_s=60)
        future = _utc_str(60 + 300)

        stale = StaleArtifactRecord.scan(
            run_id=run_id,
            reference_id=ref_id,
            candidate_paths=[artifact],
        )

        clf = IncidentClassifier()
        incident = clf.classify(
            run_id=run_id,
            heartbeat=hb,
            heartbeat_now=future,
            stale_record=stale,
        )
        assert incident.level is IncidentLevel.RECOVER

    def test_heartbeat_store_roundtrip(self, tmp_path: Path) -> None:
        store = HeartbeatStore(tmp_path / "hb.jsonl")
        run_id = "run-roundtrip"

        for i in range(3):
            hb = RunHeartbeat.record(
                run_id=run_id,
                lane_counts={"total": i + 1},
                notes=f"tick {i}",
            )
            store.append(hb)

        records = store.list_for_run(run_id)
        assert len(records) == 3
        assert records[-1].lane_counts == {"total": 3}

        latest = store.latest_for_run(run_id)
        assert latest is not None
        assert latest.notes == "tick 2"


# ---------------------------------------------------------------------------
# Runtime recovery primitives
# ---------------------------------------------------------------------------


class TestRuntimeRecovery:
    def test_exponential_backoff_retries_transient_failure(self) -> None:
        sleeps: list[float] = []
        events: list[str] = []
        calls = 0
        manager = RecoveryManager(
            RecoveryConfig(max_attempts=3, initial_delay_s=0.5, max_delay_s=5.0),
            observer=lambda event: events.append(event.kind),
            sleep=sleeps.append,
        )

        def flaky() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise TimeoutError("temporary timeout")
            return "ok"

        assert manager.execute("component", "op", flaky) == "ok"
        assert calls == 3
        assert sleeps == [0.5, 1.0]
        assert events.count("retry_scheduled") == 2
        assert "operation_succeeded" in events

    def test_circuit_opens_after_threshold_and_blocks_calls(self) -> None:
        manager = RecoveryManager(
            RecoveryConfig(
                max_attempts=1,
                circuit_failure_threshold=2,
                circuit_recovery_timeout_s=30,
            ),
            sleep=lambda _delay: None,
        )

        for _ in range(2):
            with pytest.raises(TimeoutError):
                manager.execute(
                    "component",
                    "op",
                    lambda: (_ for _ in ()).throw(TimeoutError("temporary timeout")),
                )

        assert manager.circuit("component").state is CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            manager.execute("component", "op", lambda: "blocked")

    def test_non_critical_operation_degrades_to_fallback(self) -> None:
        events = []
        manager = RecoveryManager(
            RecoveryConfig(max_attempts=1, graceful_degradation=True),
            observer=events.append,
            sleep=lambda _delay: None,
        )

        result = manager.execute(
            "component",
            "op",
            lambda: (_ for _ in ()).throw(TimeoutError("temporary timeout")),
            fallback=lambda exc: f"fallback:{type(exc).__name__}",
            critical=False,
        )

        assert result == "fallback:TimeoutError"
        assert events[-1].kind == "degraded"
