"""Reliability hardening primitives for xmuse self-evolution.

Implements the ``reliability_hardening`` blueprint track milestones:

- ``RunHeartbeat`` records for long-running runs or workers
- ``StaleArtifactRecord`` / quarantine gate before promotion
- ``AckConsistencyGate`` that checks artifact consistency
- ``IncidentClassifier`` that classifies a run as ``watch``, ``recover``, or
  ``stop``

These objects are intentionally narrow: they record evidence and emit
structured decisions. They do not mutate source code, move files, or trigger
automatic retries.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IncidentLevel(StrEnum):
    WATCH = "watch"
    RECOVER = "recover"
    STOP = "stop"


class HeartbeatStatus(StrEnum):
    ALIVE = "alive"
    STALLED = "stalled"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class AckOutcome(StrEnum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    MISSING = "missing"


class StaleArtifactVerdict(StrEnum):
    CLEAN = "clean"
    STALE = "stale"
    QUARANTINED = "quarantined"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RunHeartbeat(BaseModel):
    """A single heartbeat record for a long-running xmuse run or worker.

    The heartbeat writer calls ``record()`` periodically.  The monitor reads
    the latest record and calls ``classify_status()`` to decide whether the
    run is alive, stalled, or completed.
    """

    heartbeat_id: str
    run_id: str
    worker_id: str | None = None
    status: HeartbeatStatus
    recorded_at: str
    expected_next_by: str | None = None
    lane_counts: dict[str, int] = Field(default_factory=dict)
    notes: str = ""

    @classmethod
    def record(
        cls,
        *,
        run_id: str,
        worker_id: str | None = None,
        lane_counts: dict[str, int] | None = None,
        notes: str = "",
        heartbeat_interval_s: int = 300,
    ) -> "RunHeartbeat":
        now = _utc_now()
        expected = (
            datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=heartbeat_interval_s)
        ).isoformat().replace("+00:00", "Z")
        return cls(
            heartbeat_id=_new_id("hb"),
            run_id=run_id,
            worker_id=worker_id,
            status=HeartbeatStatus.ALIVE,
            recorded_at=now,
            expected_next_by=expected,
            lane_counts=lane_counts or {},
            notes=notes,
        )

    def classify_status(self, *, now: str | None = None) -> HeartbeatStatus:
        """Return the current liveness status relative to *now*.

        - ``COMPLETED`` if the heartbeat itself carries that status.
        - ``STALLED`` if ``expected_next_by`` has passed without a newer
          heartbeat (caller is responsible for checking newer records).
        - ``ALIVE`` otherwise.
        """
        if self.status is HeartbeatStatus.COMPLETED:
            return HeartbeatStatus.COMPLETED
        if self.expected_next_by is None:
            return self.status
        reference = _parse_utc(now) if now is not None else datetime.now(UTC)
        if reference > _parse_utc(self.expected_next_by):
            return HeartbeatStatus.STALLED
        return HeartbeatStatus.ALIVE


class StaleArtifactRecord(BaseModel):
    """Records which artifacts are stale relative to a reference run/bundle.

    A stale artifact is one that exists on disk but does not reference the
    current ``reference_id`` (e.g. a graph_id or evidence_bundle_id).  Stale
    artifacts must be quarantined before they can be used as promotion
    evidence.
    """

    record_id: str
    run_id: str
    reference_id: str
    checked_at: str
    stale_paths: list[str] = Field(default_factory=list)
    active_paths: list[str] = Field(default_factory=list)
    missing_paths: list[str] = Field(default_factory=list)
    quarantined_paths: list[str] = Field(default_factory=list)
    verdict: StaleArtifactVerdict

    @property
    def promotion_safe(self) -> bool:
        """True when no stale artifacts remain un-quarantined."""
        return not self.stale_paths

    @classmethod
    def scan(
        cls,
        *,
        run_id: str,
        reference_id: str,
        candidate_paths: list[Path],
    ) -> "StaleArtifactRecord":
        """Scan *candidate_paths* and classify each as stale, active, or missing."""
        stale: list[str] = []
        active: list[str] = []
        missing: list[str] = []

        for path in candidate_paths:
            if not path.exists():
                missing.append(str(path))
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                missing.append(str(path))
                continue
            if reference_id in text:
                active.append(str(path))
            else:
                stale.append(str(path))

        verdict = (
            StaleArtifactVerdict.CLEAN
            if not stale
            else StaleArtifactVerdict.STALE
        )
        return cls(
            record_id=_new_id("stale"),
            run_id=run_id,
            reference_id=reference_id,
            checked_at=_utc_now(),
            stale_paths=stale,
            active_paths=active,
            missing_paths=missing,
            quarantined_paths=[],
            verdict=verdict,
        )

    def quarantine(self, paths: list[str]) -> "StaleArtifactRecord":
        """Return a new record with *paths* moved from stale to quarantined."""
        remaining_stale = [p for p in self.stale_paths if p not in paths]
        newly_quarantined = [p for p in paths if p in self.stale_paths]
        new_quarantined = list(self.quarantined_paths) + newly_quarantined
        new_verdict = (
            StaleArtifactVerdict.QUARANTINED
            if new_quarantined
            else (
                StaleArtifactVerdict.CLEAN
                if not remaining_stale
                else StaleArtifactVerdict.STALE
            )
        )
        return self.model_copy(
            update={
                "stale_paths": remaining_stale,
                "quarantined_paths": new_quarantined,
                "verdict": new_verdict,
            }
        )


class AckConsistencyCheck(BaseModel):
    """Result of an ACK-style consistency gate for a single artifact set.

    The gate verifies that key artifacts (gate report, lane status, evidence
    bundle) are mutually consistent: they reference the same run/graph and
    agree on the terminal outcome.
    """

    check_id: str
    run_id: str
    checked_at: str
    outcome: AckOutcome
    blockers: list[str] = Field(default_factory=list)
    checked_refs: list[str] = Field(default_factory=list)
    notes: str = ""

    @property
    def passed(self) -> bool:
        return self.outcome is AckOutcome.CONSISTENT


class IncidentRecord(BaseModel):
    """Structured incident classification for a self-evolution run.

    Classifies the current state of a run as ``watch``, ``recover``, or
    ``stop`` based on evidence signals.

    - ``watch``: run is progressing normally; no action required
    - ``recover``: run is stalled or has recoverable failures; operator
      should inspect and may need to intervene
    - ``stop``: run has repeated failures, budget exhausted, or a hard
      blocker; automatic follow-up must not be triggered
    """

    incident_id: str
    run_id: str
    level: IncidentLevel
    reason: str
    signals: dict[str, Any] = Field(default_factory=dict)
    created_at: str

    @property
    def blocks_auto_followup(self) -> bool:
        """True when the incident level prevents automatic follow-up."""
        return self.level is IncidentLevel.STOP


# ---------------------------------------------------------------------------
# ACK consistency gate
# ---------------------------------------------------------------------------


class AckConsistencyGate:
    """Checks that a set of artifacts are mutually consistent for a run.

    Consistency rules:
    1. Every provided artifact path must exist.
    2. Every artifact must reference ``run_id`` somewhere in its content.
    3. If a gate report JSON is provided it must have ``passed=true`` or
       ``status`` in {``passed``, ``pass``, ``success``}.
    4. If a lane status dict is provided its ``normalized_status`` must be
       ``merged`` or ``terminated`` (i.e. terminal).
    """

    _GATE_PASS_STATUSES = {"passed", "pass", "success", "succeeded"}

    def check(
        self,
        *,
        run_id: str,
        artifact_paths: list[Path] | None = None,
        gate_report: dict[str, Any] | None = None,
        lane_status: dict[str, Any] | None = None,
        notes: str = "",
    ) -> AckConsistencyCheck:
        blockers: list[str] = []
        checked_refs: list[str] = []

        # 1 + 2: artifact existence and run_id reference
        for path in artifact_paths or []:
            checked_refs.append(str(path))
            if not path.exists():
                blockers.append(f"missing artifact: {path}")
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                blockers.append(f"unreadable artifact {path}: {exc}")
                continue
            if run_id not in text:
                blockers.append(f"artifact does not reference run_id {run_id}: {path}")

        # 3: gate report outcome
        if gate_report is not None:
            checked_refs.append("gate_report")
            passed = gate_report.get("passed")
            status = str(gate_report.get("status") or "").strip().lower()
            if isinstance(passed, bool):
                if not passed:
                    blockers.append("gate report: passed=false")
            elif status not in self._GATE_PASS_STATUSES:
                blockers.append(f"gate report: status={status!r} is not passing")

        # 4: lane terminal status
        if lane_status is not None:
            checked_refs.append("lane_status")
            normalized = str(lane_status.get("normalized_status") or "").strip()
            terminal = bool(lane_status.get("terminal", False))
            if not terminal and normalized not in {"merged", "terminated"}:
                blockers.append(
                    f"lane status is not terminal: normalized_status={normalized!r}"
                )

        if not checked_refs:
            outcome = AckOutcome.MISSING
            blockers.append("no artifacts provided for consistency check")
        elif blockers:
            outcome = AckOutcome.INCONSISTENT
        else:
            outcome = AckOutcome.CONSISTENT

        return AckConsistencyCheck(
            check_id=_new_id("ack"),
            run_id=run_id,
            checked_at=_utc_now(),
            outcome=outcome,
            blockers=blockers,
            checked_refs=checked_refs,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Incident classifier
# ---------------------------------------------------------------------------


class IncidentClassifier:
    """Classifies a self-evolution run into an incident level.

    Decision logic (first matching rule wins):

    ``stop``
      - ``repeated_failure_count`` >= ``stop_on_repeated_failures`` (default 3)
      - ``budget_exhausted`` is True
      - ``hard_blocker`` is True

    ``recover``
      - Latest heartbeat is ``stalled``
      - ``stale_artifact_record`` has un-quarantined stale paths
      - ``ack_check`` is inconsistent or missing
      - ``failure_count`` >= 1

    ``watch``
      - Everything else
    """

    def __init__(
        self,
        *,
        stop_on_repeated_failures: int = 3,
    ) -> None:
        self._stop_threshold = stop_on_repeated_failures

    def classify(
        self,
        *,
        run_id: str,
        heartbeat: RunHeartbeat | None = None,
        heartbeat_now: str | None = None,
        stale_record: StaleArtifactRecord | None = None,
        ack_check: AckConsistencyCheck | None = None,
        failure_count: int = 0,
        repeated_failure_count: int = 0,
        budget_exhausted: bool = False,
        hard_blocker: bool = False,
        extra_signals: dict[str, Any] | None = None,
    ) -> IncidentRecord:
        signals: dict[str, Any] = {
            "failure_count": failure_count,
            "repeated_failure_count": repeated_failure_count,
            "budget_exhausted": budget_exhausted,
            "hard_blocker": hard_blocker,
        }
        if heartbeat is not None:
            hb_status = heartbeat.classify_status(now=heartbeat_now)
            signals["heartbeat_status"] = hb_status.value
        else:
            hb_status = HeartbeatStatus.UNKNOWN
            signals["heartbeat_status"] = hb_status.value

        if stale_record is not None:
            signals["stale_paths_count"] = len(stale_record.stale_paths)
            signals["stale_verdict"] = stale_record.verdict.value
        if ack_check is not None:
            signals["ack_outcome"] = ack_check.outcome.value
            signals["ack_blockers"] = ack_check.blockers
        if extra_signals:
            signals.update(extra_signals)

        level, reason = self._decide(
            heartbeat_status=hb_status,
            stale_record=stale_record,
            ack_check=ack_check,
            failure_count=failure_count,
            repeated_failure_count=repeated_failure_count,
            budget_exhausted=budget_exhausted,
            hard_blocker=hard_blocker,
        )

        return IncidentRecord(
            incident_id=_new_id("incident"),
            run_id=run_id,
            level=level,
            reason=reason,
            signals=signals,
            created_at=_utc_now(),
        )

    def _decide(
        self,
        *,
        heartbeat_status: HeartbeatStatus,
        stale_record: StaleArtifactRecord | None,
        ack_check: AckConsistencyCheck | None,
        failure_count: int,
        repeated_failure_count: int,
        budget_exhausted: bool,
        hard_blocker: bool,
    ) -> tuple[IncidentLevel, str]:
        # --- stop rules ---
        if hard_blocker:
            return IncidentLevel.STOP, "hard_blocker set"
        if budget_exhausted:
            return IncidentLevel.STOP, "budget_exhausted"
        if repeated_failure_count >= self._stop_threshold:
            return (
                IncidentLevel.STOP,
                f"repeated_failure_count={repeated_failure_count} >= {self._stop_threshold}",
            )

        # --- recover rules ---
        if heartbeat_status is HeartbeatStatus.STALLED:
            return IncidentLevel.RECOVER, "heartbeat stalled"
        if stale_record is not None and stale_record.stale_paths:
            return (
                IncidentLevel.RECOVER,
                f"stale artifacts present: {len(stale_record.stale_paths)} path(s)",
            )
        if ack_check is not None and not ack_check.passed:
            return (
                IncidentLevel.RECOVER,
                f"ack consistency check failed: {'; '.join(ack_check.blockers[:2])}",
            )
        if failure_count >= 1:
            return IncidentLevel.RECOVER, f"failure_count={failure_count}"

        return IncidentLevel.WATCH, "no incident signals"


# ---------------------------------------------------------------------------
# Heartbeat store (append-only JSONL)
# ---------------------------------------------------------------------------


class HeartbeatStore:
    """Append-only JSONL store for ``RunHeartbeat`` records.

    Each line is a JSON-serialised ``RunHeartbeat``.  The store is intentionally
    simple: it appends on write and scans on read.  For the xmuse self-evolution
    use-case the volume is low enough that a full scan is acceptable.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def append(self, heartbeat: RunHeartbeat) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(heartbeat.model_dump_json() + "\n")

    def list_for_run(self, run_id: str) -> list[RunHeartbeat]:
        if not self._path.exists():
            return []
        records: list[RunHeartbeat] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("run_id") == run_id:
                try:
                    records.append(RunHeartbeat.model_validate(data))
                except Exception:
                    continue
        return records

    def latest_for_run(self, run_id: str) -> RunHeartbeat | None:
        records = self.list_for_run(run_id)
        return records[-1] if records else None
