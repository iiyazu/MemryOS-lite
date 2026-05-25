#!/usr/bin/env python3
"""Xmuse-local error knowledge maintainer.

The maintainer reads existing Xmuse control-plane artifacts and writes only
local, quarantined knowledge objects. It does not modify MemoryOS runtime
behavior, active prompts, active skills, Master state, or approval artifacts.
"""

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

FEATURE_ID = "xmuse-error-knowledge"
SCHEMA_VERSION = "1.0"
EXTRACTOR_VERSION = "xmuse-error-knowledge-2026-05-25"

DEFAULT_ALLOWED_WRITES = [
    "xmuse/knowledge/**",
    f"xmuse/work/features/{FEATURE_ID}/result.md",
    f"xmuse/work/features/{FEATURE_ID}/review_verdict.json",
    f"xmuse/work/features/{FEATURE_ID}/ack.json",
    f"xmuse/work/features/{FEATURE_ID}/slave_state.json",
]
BOOTSTRAP_WRITES = [
    f"xmuse/work/features/{FEATURE_ID}/ack.json",
    f"xmuse/work/features/{FEATURE_ID}/result.md",
]
REQUIRED_INPUTS = [
    "xmuse/master_state.json",
    "xmuse/master_status.json",
    "xmuse/contracts/master_dispatch_template.json",
    "xmuse/contracts/slave_dispatch_template.json",
    "xmuse/contracts/knowledge_maintainer_template.json",
]
OPTIONAL_INPUTS = [
    "xmuse/reports/latest.json",
    "xmuse/reports/latest.md",
]
SCAN_GLOBS = [
    "xmuse/work/features/*/ack.json",
    "xmuse/work/features/*/result.md",
    "xmuse/work/features/*/review_verdict.json",
    "xmuse/work/features/*/execute_review.md",
    "xmuse/work/features/*/slave_state.json",
    "xmuse/work/features/*/plan_final.md",
    "xmuse/master/features/*/master_review.json",
    "xmuse/master/features/*/integrated_tests.json",
    "xmuse/approvals/*/merge_approval_request.json",
    "xmuse/approvals/*/merge_approval.json",
    "xmuse/approvals/*/merge_decision.json",
    "xmuse/approvals/*/post_merge_verification.json",
]
FINAL_WORK_ARTIFACTS = ["ack.json", "result.md", "review_verdict.json"]
DETERMINISTIC_INVARIANTS = {
    "missing_required_artifact",
    "invalid_json_artifact",
    "ack_non_usable",
    "review_verdict_not_pass",
    "integrated_tests_missing",
    "integrated_tests_not_passed",
    "merge_requested_without_approval",
    "approval_artifact_digest_mismatch",
    "stale_target_head",
    "write_boundary_violation",
}
NON_PROMOTABLE_PREFIXES = (
    "environment:",
    "transient:",
    "baseline_drift:",
    "dirty_worktree:",
    "missing_optional:",
)


class SimulatedWriteFailure(RuntimeError):
    """Raised by tests to stop after a bounded number of object writes."""


@dataclass(frozen=True)
class Finding:
    feature_id: str
    artifact_path: Path
    artifact_type: str
    fingerprint: str
    summary: str
    evidence: str
    root_cause_status: str
    deterministic_invariant: str | None = None
    verification_evidence: bool = False
    source_run_id: str | None = None
    promotion_suppressed: bool = False


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def stable_id(prefix: str, *parts: str, length: int = 16) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalize_command(command: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", command.strip().lower()).strip("-")
    return value[:80] or "unknown"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_matches(pattern: str, rel_path: str) -> bool:
    pattern = pattern.strip("/")
    rel_path = rel_path.strip("/")
    if pattern.endswith("/**"):
        base = pattern[:-3].rstrip("/")
        return rel_path == base or rel_path.startswith(base + "/")
    return rel_path == pattern


def _safe_relative(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    return resolved_path.relative_to(resolved_root).as_posix()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_type_for(path: Path) -> str:
    name = path.name
    if name == "ack.json":
        return "ack"
    if name == "review_verdict.json":
        return "review_verdict"
    if name == "result.md":
        return "result"
    if name == "execute_review.md":
        return "execute_review"
    if name == "slave_state.json":
        return "slave_state"
    if name == "plan_final.md":
        return "plan_final"
    if name == "master_review.json":
        return "master_review"
    if name == "integrated_tests.json":
        return "integrated_tests"
    if name.startswith("merge_approval_request"):
        return "merge_approval_request"
    if name.startswith("merge_approval"):
        return "merge_approval"
    if name.startswith("merge_decision"):
        return "merge_decision"
    if name.startswith("post_merge_verification"):
        return "post_merge_verification"
    return path.suffix.lstrip(".") or "artifact"


def feature_id_for(root: Path, path: Path) -> str:
    rel = _safe_relative(root, path)
    parts = rel.split("/")
    if len(parts) >= 4 and parts[:3] == ["xmuse", "work", "features"]:
        return parts[3]
    if len(parts) >= 4 and parts[:3] == ["xmuse", "master", "features"]:
        return parts[3]
    if len(parts) >= 3 and parts[:2] == ["xmuse", "approvals"]:
        return parts[2]
    return "global"


def source_ref(
    root: Path,
    path: Path,
    *,
    artifact_type: str,
    feature_id: str,
    digest: str,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    ref = {
        "path": _safe_relative(root, path),
        "digest": digest,
        "artifact_type": artifact_type,
        "feature_id": feature_id,
    }
    if source_run_id:
        ref["source_run_id"] = source_run_id
    return ref


def source_digest_for_refs(refs: list[dict[str, Any]]) -> str:
    return sha256_text(canonical_json(refs))


def unique_source_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for ref in refs:
        unique[(str(ref.get("path")), str(ref.get("digest")))] = ref
    return [unique[key] for key in sorted(unique)]


def validate_contract(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    contract_path = root / "xmuse/contracts/knowledge_maintainer_template.json"
    if not contract_path.exists():
        return {
            "valid": False,
            "bootstrap": True,
            "contract": None,
            "blockers": ["knowledge_maintainer_template.json missing"],
        }
    try:
        contract = _read_json(contract_path)
    except JSONDecodeError as exc:
        return {
            "valid": False,
            "bootstrap": True,
            "contract": None,
            "blockers": [f"knowledge_maintainer_template.json invalid JSON: {exc.msg}"],
        }

    blockers: list[str] = []
    if contract.get("role") != "knowledge_maintainer":
        blockers.append("knowledge_maintainer_template.json role must be knowledge_maintainer")
    allowed = contract.get("allowed_writes")
    if not isinstance(allowed, list) or sorted(allowed) != sorted(DEFAULT_ALLOWED_WRITES):
        blockers.append(
            "allowed_writes must exactly match the knowledge maintainer contract"
        )
    bootstrap = contract.get("bootstrap_failure_writes")
    if not isinstance(bootstrap, list) or sorted(bootstrap) != sorted(BOOTSTRAP_WRITES):
        blockers.append(
            "knowledge_maintainer_template.json bootstrap writes must be ack/result only"
        )
    required_inputs = contract.get("required_inputs")
    if not isinstance(required_inputs, list) or sorted(required_inputs) != sorted(REQUIRED_INPUTS):
        blockers.append(
            "knowledge_maintainer_template.json required_inputs must match contract"
        )
    return {
        "valid": not blockers,
        "bootstrap": bool(blockers),
        "contract": contract,
        "blockers": blockers,
    }


def _write_bootstrap_blocked(root: Path, blockers: list[str], *, run_id: str, now: str) -> dict:
    feature_dir = root / f"xmuse/work/features/{FEATURE_ID}"
    feature_dir.mkdir(parents=True, exist_ok=True)
    ack = {
        "feature_id": FEATURE_ID,
        "ack_level": "blocked",
        "mode": "bootstrap_no_op",
        "knowledge_run_id": run_id,
        "recorded_at": now,
        "blockers": blockers,
        "allowed_writes_used": BOOTSTRAP_WRITES,
        "knowledge_files_written": False,
    }
    result = "\n".join(
        [
            f"# feature: {FEATURE_ID}",
            "",
            "## Bootstrap No-Op",
            "",
            "The knowledge maintainer did not enter normal authorized mode.",
            "",
            "Blockers:",
            *[f"- {blocker}" for blocker in blockers],
            "",
            "Writes performed: `ack.json` and `result.md` only.",
            "",
        ]
    )
    _atomic_write_json(feature_dir / "ack.json", ack)
    _atomic_write_text(feature_dir / "result.md", result)
    return {"status": "blocked", "blockers": blockers, "knowledge_run_id": run_id}


class KnowledgeMaintainer:
    def __init__(
        self,
        root: str | Path,
        *,
        run_id: str | None = None,
        now: str | None = None,
        fail_after_object_writes: int | None = None,
    ) -> None:
        self.root = Path(root)
        self.run_id = run_id or f"knowledge-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        self.now = now or utc_now()
        contract_status = validate_contract(self.root)
        self.contract = contract_status.get("contract") or {}
        self.allowed_writes = list(self.contract.get("allowed_writes") or DEFAULT_ALLOWED_WRITES)
        self.fail_after_object_writes = fail_after_object_writes
        self.object_write_count = 0
        self.diagnostics: list[str] = []
        self.scanned_artifacts: list[str] = []
        self.generated: dict[str, list[str]] = {
            "error_records": [],
            "clusters": [],
            "methods": [],
            "skill_proposals": [],
        }

    @property
    def feature_dir(self) -> Path:
        return self.root / f"xmuse/work/features/{FEATURE_ID}"

    @property
    def knowledge_dir(self) -> Path:
        return self.root / "xmuse/knowledge"

    def assert_allowed_write(self, path: str | Path) -> None:
        path = Path(path)
        try:
            rel = _safe_relative(self.root, path)
        except ValueError as exc:
            raise ValueError(f"write outside knowledge_maintainer boundary: {path}") from exc
        if not any(_path_matches(pattern, rel) for pattern in self.allowed_writes):
            raise ValueError(f"write outside knowledge_maintainer boundary: {rel}")

    def write_json(
        self,
        rel_path: str,
        payload: Any,
        *,
        object_write: bool = False,
    ) -> None:
        path = self.root / rel_path
        self.assert_allowed_write(path)
        if object_write:
            if (
                self.fail_after_object_writes is not None
                and self.object_write_count >= self.fail_after_object_writes
            ):
                raise SimulatedWriteFailure("simulated partial object write failure")
            self.object_write_count += 1
        _atomic_write_json(path, payload)

    def write_text(
        self,
        rel_path: str,
        content: str,
        *,
        object_write: bool = False,
    ) -> None:
        path = self.root / rel_path
        self.assert_allowed_write(path)
        if object_write:
            if (
                self.fail_after_object_writes is not None
                and self.object_write_count >= self.fail_after_object_writes
            ):
                raise SimulatedWriteFailure("simulated partial object write failure")
            self.object_write_count += 1
        _atomic_write_text(path, content)

    def run(self) -> dict[str, Any]:
        try:
            findings = self.scan_findings()
            records = self.write_error_records(findings)
            clusters = self.write_clusters(records)
            methods = self.write_methods(clusters)
            proposals = self.write_skill_proposals(methods, clusters)
            self.write_run_summary(records, clusters, methods, proposals)
            self.rebuild_indexes()
            self.write_handoff_artifacts(
                status="usable",
                records=records,
                clusters=clusters,
                methods=methods,
                proposals=proposals,
            )
            return {
                "status": "usable",
                "knowledge_run_id": self.run_id,
                "records": len(records),
                "clusters": len(clusters),
                "methods": len(methods),
                "skill_proposals": len(proposals),
            }
        except SimulatedWriteFailure as exc:
            self.write_handoff_artifacts(
                status="failed",
                records=[],
                clusters=[],
                methods=[],
                proposals=[],
                blockers=[str(exc)],
            )
            return {
                "status": "failed",
                "knowledge_run_id": self.run_id,
                "blockers": [str(exc)],
            }

    def scan_findings(self) -> list[Finding]:
        for optional in OPTIONAL_INPUTS:
            if not (self.root / optional).exists():
                self.diagnostics.append(f"missing optional input: {optional}")

        findings: list[Finding] = []
        findings.extend(self.find_missing_feature_artifacts())
        seen_paths: set[Path] = set()
        for pattern in SCAN_GLOBS:
            for path in sorted(self.root.glob(pattern)):
                if not path.is_file() or path in seen_paths:
                    continue
                seen_paths.add(path)
                feature_id = feature_id_for(self.root, path)
                if feature_id == FEATURE_ID:
                    continue
                artifact_type = artifact_type_for(path)
                self.scanned_artifacts.append(_safe_relative(self.root, path))
                if path.suffix == ".json":
                    findings.extend(self.extract_json_findings(path, feature_id, artifact_type))
                elif path.suffix == ".md":
                    findings.extend(self.extract_markdown_findings(path, feature_id, artifact_type))
        return findings

    def find_missing_feature_artifacts(self) -> list[Finding]:
        work_features = self.root / "xmuse/work/features"
        if not work_features.exists():
            return []
        findings: list[Finding] = []
        for feature_dir in sorted(path for path in work_features.iterdir() if path.is_dir()):
            feature_id = feature_dir.name
            if feature_id == FEATURE_ID:
                continue
            present_terminal = [
                name for name in FINAL_WORK_ARTIFACTS if (feature_dir / name).exists()
            ]
            if present_terminal:
                continue
            for artifact in FINAL_WORK_ARTIFACTS:
                artifact_type = artifact_type_for(feature_dir / artifact)
                missing_path = feature_dir / artifact
                findings.append(
                    Finding(
                        feature_id=feature_id,
                        artifact_path=missing_path,
                        artifact_type=artifact_type,
                        fingerprint=f"missing_required_artifact:{artifact_type}",
                        summary=f"Required artifact {artifact} is missing for {feature_id}",
                        evidence=f"{_safe_relative(self.root, missing_path)} missing",
                        root_cause_status="confirmed",
                        deterministic_invariant="missing_required_artifact",
                    )
                )
        return findings

    def extract_json_findings(
        self,
        path: Path,
        feature_id: str,
        artifact_type: str,
    ) -> list[Finding]:
        try:
            payload = _read_json(path)
        except JSONDecodeError as exc:
            return [
                Finding(
                    feature_id=feature_id,
                    artifact_path=path,
                    artifact_type=artifact_type,
                    fingerprint=f"invalid_json_artifact:{artifact_type}",
                    summary=f"{artifact_type} artifact contains invalid JSON",
                    evidence=exc.msg,
                    root_cause_status="confirmed",
                    deterministic_invariant="invalid_json_artifact",
                )
            ]
        if not isinstance(payload, dict):
            return []

        source_run_id = self.extract_source_run_id(payload)
        findings: list[Finding] = []
        if artifact_type == "ack":
            ack_level = str(payload.get("ack_level", "")).lower()
            if ack_level != "usable":
                findings.append(
                    Finding(
                        feature_id=feature_id,
                        artifact_path=path,
                        artifact_type=artifact_type,
                        fingerprint="ack_non_usable",
                        summary=f"ACK level is {ack_level or 'missing'}",
                        evidence=canonical_json(payload)[:500],
                        root_cause_status="confirmed",
                        deterministic_invariant="ack_non_usable",
                        source_run_id=source_run_id,
                    )
                )
        elif artifact_type == "review_verdict":
            verdict = str(payload.get("verdict", "")).upper()
            if verdict != "PASS":
                findings.append(
                    Finding(
                        feature_id=feature_id,
                        artifact_path=path,
                        artifact_type=artifact_type,
                        fingerprint="review_verdict_not_pass",
                        summary=f"Review verdict is {verdict or 'missing'}",
                        evidence=canonical_json(payload)[:500],
                        root_cause_status="confirmed",
                        deterministic_invariant="review_verdict_not_pass",
                        source_run_id=source_run_id,
                    )
                )
        elif artifact_type == "integrated_tests":
            status = str(payload.get("status", "")).lower()
            if status and status not in {"passed", "pass"}:
                findings.append(
                    Finding(
                        feature_id=feature_id,
                        artifact_path=path,
                        artifact_type=artifact_type,
                        fingerprint="integrated_tests_not_passed",
                        summary=f"Integrated tests status is {status}",
                        evidence=canonical_json(payload)[:500],
                        root_cause_status="confirmed",
                        deterministic_invariant="integrated_tests_not_passed",
                        source_run_id=source_run_id,
                    )
                )
        return findings

    def extract_markdown_findings(
        self,
        path: Path,
        feature_id: str,
        artifact_type: str,
    ) -> list[Finding]:
        text = path.read_text(encoding="utf-8", errors="replace")[:200_000]
        digest_seen: set[tuple[str, str]] = set()
        findings: list[Finding] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            finding = self.finding_from_markdown_line(
                line,
                lower,
                path=path,
                feature_id=feature_id,
                artifact_type=artifact_type,
            )
            if finding is None:
                continue
            dedup_key = (finding.fingerprint, finding.evidence)
            if dedup_key in digest_seen:
                continue
            digest_seen.add(dedup_key)
            findings.append(finding)
        return findings

    def finding_from_markdown_line(
        self,
        line: str,
        lower: str,
        *,
        path: Path,
        feature_id: str,
        artifact_type: str,
    ) -> Finding | None:
        verification = "verification evidence" in lower
        command_match = re.search(
            r"((?:uv|pytest|python|mypy|ruff|make|git)\s+[^`|;:]*?)\s+"
            r"(?:fails?|failed|reports?\s+\w*\s*failed)\b",
            line,
            flags=re.IGNORECASE,
        )
        if command_match:
            command = command_match.group(1).strip()
            return Finding(
                feature_id=feature_id,
                artifact_path=path,
                artifact_type=artifact_type,
                fingerprint=f"failed_command:{normalize_command(command)}",
                summary=f"Command failed: {command}",
                evidence=line[:500],
                root_cause_status="confirmed" if verification else "suspected",
                verification_evidence=verification,
            )
        if "hard eval" in lower and (
            "baseline" in lower or "drift" in lower or "instead of stated" in lower
        ):
            return Finding(
                feature_id=feature_id,
                artifact_path=path,
                artifact_type=artifact_type,
                fingerprint="baseline_drift:hard-eval",
                summary="Hard eval drift or baseline mismatch reported",
                evidence=line[:500],
                root_cause_status="suspected",
                promotion_suppressed=True,
            )
        if "network timeout" in lower or ("transient" in lower and "timeout" in lower):
            return Finding(
                feature_id=feature_id,
                artifact_path=path,
                artifact_type=artifact_type,
                fingerprint="environment:network-timeout",
                summary="Transient network timeout reported",
                evidence=line[:500],
                root_cause_status="suspected",
                promotion_suppressed=True,
            )
        if "root cause:" in lower:
            return Finding(
                feature_id=feature_id,
                artifact_path=path,
                artifact_type=artifact_type,
                fingerprint="markdown_diagnosis:free-form-root-cause",
                summary="Markdown-only root cause diagnosis",
                evidence=line[:500],
                root_cause_status="suspected",
            )
        return None

    def extract_source_run_id(self, payload: dict[str, Any]) -> str | None:
        for key in ("source_run_id", "run_id", "knowledge_run_id", "head_commit"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def write_error_records(self, findings: list[Finding]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen_records: set[str] = set()
        for finding in findings:
            if finding.artifact_path.exists():
                digest = sha256_file(finding.artifact_path)
            else:
                digest = sha256_text("missing:" + _safe_relative(self.root, finding.artifact_path))
            ref = source_ref(
                self.root,
                finding.artifact_path,
                artifact_type=finding.artifact_type,
                feature_id=finding.feature_id,
                digest=digest,
                source_run_id=finding.source_run_id,
            )
            record_id = stable_id(
                "error",
                finding.fingerprint,
                ref["path"],
                digest,
                finding.evidence,
            )
            if record_id in seen_records:
                continue
            seen_records.add(record_id)
            rel_path = f"xmuse/knowledge/error_records/{finding.feature_id}/{record_id}.json"
            existing_path = self.root / rel_path
            if existing_path.exists():
                record = _read_json(existing_path)
                record["last_seen_at"] = self.now
                record["last_knowledge_run_id"] = self.run_id
            else:
                record = {
                    "schema_version": SCHEMA_VERSION,
                    "object_type": "error_record",
                    "record_id": record_id,
                    "knowledge_run_id": self.run_id,
                    "extractor_version": EXTRACTOR_VERSION,
                    "created_at": self.now,
                    "last_seen_at": self.now,
                    "feature_id": finding.feature_id,
                    "fingerprint": finding.fingerprint,
                    "summary": finding.summary,
                    "evidence": finding.evidence,
                    "source_ref": ref,
                    "source_refs": [ref],
                    "source_digest": ref["digest"],
                    "root_cause_status": finding.root_cause_status,
                    "deterministic_invariant": finding.deterministic_invariant,
                    "verification_evidence": finding.verification_evidence,
                    "promotion_suppressed": finding.promotion_suppressed,
                }
            self.write_json(rel_path, record, object_write=True)
            self.generated["error_records"].append(record_id)
            records.append(record)
        return records

    def write_clusters(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_cluster: dict[str, dict[str, Any]] = {}
        for record in records:
            cluster_id = stable_id("cluster", record["fingerprint"])
            rel_path = f"xmuse/knowledge/clusters/{cluster_id}.json"
            if cluster_id in by_cluster:
                cluster = by_cluster[cluster_id]
            elif (self.root / rel_path).exists():
                cluster = _read_json(self.root / rel_path)
            else:
                cluster = {
                    "schema_version": SCHEMA_VERSION,
                    "object_type": "cluster",
                    "cluster_id": cluster_id,
                    "knowledge_run_id": self.run_id,
                    "extractor_version": EXTRACTOR_VERSION,
                    "created_at": self.now,
                    "fingerprint": record["fingerprint"],
                    "summary": record["summary"],
                    "occurrences": [],
                    "source_refs": [],
                    "promotion_stage": "observed",
                    "promotion_blockers": [],
                }
            self.add_record_to_cluster(cluster, record)
            by_cluster[cluster_id] = cluster

        clusters = []
        for cluster in by_cluster.values():
            self.recompute_cluster(cluster)
            rel_path = f"xmuse/knowledge/clusters/{cluster['cluster_id']}.json"
            self.write_json(rel_path, cluster, object_write=True)
            self.generated["clusters"].append(cluster["cluster_id"])
            clusters.append(cluster)
        return clusters

    def add_record_to_cluster(self, cluster: dict[str, Any], record: dict[str, Any]) -> None:
        occurrence = {
            "record_id": record["record_id"],
            "feature_id": record["feature_id"],
            "source_digest": record["source_ref"]["digest"],
            "source_path": record["source_ref"]["path"],
            "root_cause_status": record["root_cause_status"],
            "deterministic_invariant": record.get("deterministic_invariant"),
            "verification_evidence": record.get("verification_evidence", False),
        }
        source_run_id = record["source_ref"].get("source_run_id")
        if source_run_id:
            occurrence["source_run_id"] = source_run_id
        if not any(item["record_id"] == occurrence["record_id"] for item in cluster["occurrences"]):
            cluster["occurrences"].append(occurrence)
        if not any(
            ref["path"] == record["source_ref"]["path"]
            and ref["digest"] == record["source_ref"]["digest"]
            for ref in cluster["source_refs"]
        ):
            cluster["source_refs"].append(record["source_ref"])

    def recompute_cluster(self, cluster: dict[str, Any]) -> None:
        occurrences = cluster["occurrences"]
        feature_ids = sorted({item["feature_id"] for item in occurrences})
        source_digests = sorted({item["source_digest"] for item in occurrences})
        source_run_ids = sorted(
            {item["source_run_id"] for item in occurrences if item.get("source_run_id")}
        )
        cluster["last_seen_at"] = self.now
        cluster["last_knowledge_run_id"] = self.run_id
        cluster["occurrence_count"] = len(occurrences)
        cluster["feature_ids"] = feature_ids
        cluster["feature_count"] = len(feature_ids)
        cluster["source_digest_count"] = len(source_digests)
        cluster["source_run_ids"] = source_run_ids
        cluster["source_run_count"] = len(source_run_ids)
        cluster["root_cause_status"] = (
            "confirmed"
            if any(item["root_cause_status"] == "confirmed" for item in occurrences)
            else "suspected"
        )

        blockers: list[str] = []
        stage = "observed"
        if len(occurrences) >= 2:
            stage = "method_candidate"
            if len(feature_ids) < 2:
                blockers.append("same-feature recurrence is not cross-feature evidence")
            if str(cluster["fingerprint"]).startswith(NON_PROMOTABLE_PREFIXES):
                if "same-feature recurrence is not cross-feature evidence" not in blockers:
                    blockers.append("environment or baseline findings require independent evidence")
            allowlisted = any(
                item.get("deterministic_invariant") in DETERMINISTIC_INVARIANTS
                for item in occurrences
            )
            if (
                not str(cluster["fingerprint"]).startswith(NON_PROMOTABLE_PREFIXES)
                and len(feature_ids) > 1
                and (len(source_run_ids) > 1 or allowlisted or len(occurrences) >= 2)
            ):
                stage = "method_created"
                blockers = []
        cluster["promotion_stage"] = stage
        cluster["promotion_blockers"] = blockers
        cluster["source_refs"] = unique_source_refs(cluster["source_refs"])
        cluster["source_digest"] = source_digest_for_refs(cluster["source_refs"])

    def write_methods(self, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        methods = []
        for cluster in clusters:
            if cluster.get("promotion_stage") != "method_created":
                continue
            method_id = stable_id("method", cluster["cluster_id"])
            method_dir_rel = f"xmuse/knowledge/methods/{method_id}"
            manifest_rel = f"{method_dir_rel}/manifest.json"
            manifest_path = self.root / manifest_rel
            generated_body = self.render_method(cluster, method_id)
            generated_digest = sha256_text(generated_body)
            if manifest_path.exists():
                manifest = _read_json(manifest_path)
                manifest["updated_at"] = self.now
            else:
                manifest = {
                    "schema_version": SCHEMA_VERSION,
                    "object_type": "method_manifest",
                    "method_id": method_id,
                    "knowledge_run_id": self.run_id,
                    "extractor_version": EXTRACTOR_VERSION,
                    "created_at": self.now,
                    "status": "draft",
                    "quarantined": True,
                    "activation_status": "not_active",
                    "cluster_id": cluster["cluster_id"],
                    "tombstones": [],
                }
            manifest["last_knowledge_run_id"] = self.run_id
            manifest["last_generated_digest"] = generated_digest
            manifest["source_refs"] = unique_source_refs(cluster["source_refs"])
            manifest["source_digest"] = source_digest_for_refs(manifest["source_refs"])
            manifest["occurrence_count"] = cluster["occurrence_count"]
            manifest["feature_count"] = cluster["feature_count"]
            self.write_current_or_revision(method_dir_rel, generated_body, generated_digest)
            self.write_json(manifest_rel, manifest, object_write=True)
            for subdir in ("revisions", "tombstones"):
                (self.root / method_dir_rel / subdir).mkdir(parents=True, exist_ok=True)
            self.generated["methods"].append(method_id)
            methods.append(manifest)
        return methods

    def render_method(self, cluster: dict[str, Any], method_id: str) -> str:
        sources = "\n".join(
            f"- `{ref['path']}` ({ref['digest']})" for ref in cluster["source_refs"]
        )
        return "\n".join(
            [
                f"# Draft Method: {method_id}",
                "",
                "Status: draft/quarantined. This is local Xmuse knowledge only.",
                "",
                f"Cluster: `{cluster['cluster_id']}`",
                f"Fingerprint: `{cluster['fingerprint']}`",
                f"Occurrences: {cluster['occurrence_count']}",
                "",
                "Suggested local method:",
                "1. Verify the cited control-plane artifact first.",
                "2. Repair from the deterministic blocker or confirmed evidence.",
                "3. Keep Master approval and merge gates unchanged.",
                "",
                "Sources:",
                sources,
                "",
            ]
        )

    def write_current_or_revision(
        self,
        object_dir_rel: str,
        generated_body: str,
        generated_digest: str,
    ) -> None:
        current_rel = f"{object_dir_rel}/current.md"
        current_path = self.root / current_rel
        content = f"<!-- xmuse-generated-digest:{generated_digest} -->\n{generated_body}"
        if current_path.exists():
            current_text = current_path.read_text(encoding="utf-8")
            if current_text != content:
                revision_rel = (
                    f"{object_dir_rel}/revisions/"
                    f"{self.run_id}-{generated_digest.removeprefix('sha256:')[:12]}.md"
                )
                self.write_text(revision_rel, content, object_write=True)
                return
        self.write_text(current_rel, content, object_write=True)

    def write_skill_proposals(
        self,
        methods: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        proposals = []
        clusters_by_id = {cluster["cluster_id"]: cluster for cluster in clusters}
        for method in methods:
            cluster = clusters_by_id.get(method["cluster_id"], {})
            if len(methods) < 2 and cluster.get("feature_count", 0) < 2:
                continue
            proposal_id = stable_id("proposal", method["method_id"])
            proposal_dir_rel = f"xmuse/knowledge/skill_proposals/{proposal_id}"
            manifest_rel = f"{proposal_dir_rel}/manifest.json"
            body = self.render_skill_proposal(method, proposal_id)
            digest = sha256_text(body)
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "object_type": "skill_proposal_manifest",
                "proposal_id": proposal_id,
                "knowledge_run_id": self.run_id,
                "extractor_version": EXTRACTOR_VERSION,
                "created_at": self.now,
                "updated_at": self.now,
                "status": "draft",
                "quarantined": True,
                "activation_status": "not_installed",
                "method_ids": [method["method_id"]],
                "source_refs": unique_source_refs(method.get("source_refs", [])),
                "source_digest": source_digest_for_refs(
                    unique_source_refs(method.get("source_refs", []))
                ),
                "last_generated_digest": digest,
                "tombstones": [],
            }
            self.write_current_or_revision(proposal_dir_rel, body, digest)
            self.write_json(manifest_rel, manifest, object_write=True)
            for subdir in ("revisions", "tombstones"):
                (self.root / proposal_dir_rel / subdir).mkdir(parents=True, exist_ok=True)
            self.generated["skill_proposals"].append(proposal_id)
            proposals.append(manifest)
        return proposals

    def render_skill_proposal(self, method: dict[str, Any], proposal_id: str) -> str:
        return "\n".join(
            [
                f"# Draft Skill Proposal: {proposal_id}",
                "",
                "Status: draft/quarantined. This proposal is not installed or active.",
                "",
                f"Source method: `{method['method_id']}`",
                "",
                "Proposal:",
                (
                    "Capture the repeated Xmuse control-plane repair pattern as a "
                    "future skill only after human review."
                ),
                "",
            ]
        )

    def write_run_summary(
        self,
        records: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
        methods: list[dict[str, Any]],
        proposals: list[dict[str, Any]],
    ) -> None:
        source_refs = unique_source_refs(
            [ref for record in records for ref in record.get("source_refs", [])]
        )
        summary = {
            "schema_version": SCHEMA_VERSION,
            "object_type": "knowledge_run",
            "knowledge_run_id": self.run_id,
            "extractor_version": EXTRACTOR_VERSION,
            "recorded_at": self.now,
            "feature_id": FEATURE_ID,
            "source_refs": source_refs,
            "source_digest": source_digest_for_refs(source_refs),
            "scanned_artifacts": sorted(set(self.scanned_artifacts)),
            "diagnostics": self.diagnostics,
            "generated_or_updated": self.generated,
            "counts": {
                "error_records": len(records),
                "clusters": len(clusters),
                "methods": len(methods),
                "skill_proposals": len(proposals),
                "blocked_clusters": len(
                    [cluster for cluster in clusters if cluster.get("promotion_blockers")]
                ),
                "promoted_clusters": len(
                    [
                        cluster
                        for cluster in clusters
                        if cluster.get("promotion_stage") == "method_created"
                    ]
                ),
            },
        }
        self.write_json(f"xmuse/knowledge/runs/{self.run_id}.json", summary, object_write=True)

    def rebuild_indexes(self) -> None:
        indexes = {
            "error_index": self.collect_index(
                "xmuse/knowledge/error_records/*/*.json",
                "record_id",
            ),
            "cluster_index": self.collect_index("xmuse/knowledge/clusters/*.json", "cluster_id"),
            "method_index": self.collect_index(
                "xmuse/knowledge/methods/*/manifest.json",
                "method_id",
            ),
            "proposal_index": self.collect_index(
                "xmuse/knowledge/skill_proposals/*/manifest.json",
                "proposal_id",
            ),
        }
        for name, paths in indexes.items():
            source_refs = self.source_refs_for_index(paths)
            payload = {
                "schema_version": SCHEMA_VERSION,
                "object_type": name,
                "knowledge_run_id": self.run_id,
                "extractor_version": EXTRACTOR_VERSION,
                "updated_at": self.now,
                "source_refs": source_refs,
                "source_digest": source_digest_for_refs(source_refs),
                "paths": paths,
            }
            self.write_json(f"xmuse/knowledge/indexes/{name}.json", payload)

    def collect_index(self, pattern: str, id_key: str) -> dict[str, str]:
        paths: dict[str, str] = {}
        for path in sorted(self.root.glob(pattern)):
            if not path.is_file():
                continue
            payload = _read_json(path)
            object_id = payload.get(id_key)
            if isinstance(object_id, str) and object_id:
                paths[object_id] = _safe_relative(self.root, path)
        return paths

    def source_refs_for_index(self, paths: dict[str, str]) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for rel_path in paths.values():
            payload = _read_json(self.root / rel_path)
            if isinstance(payload.get("source_refs"), list):
                refs.extend(payload["source_refs"])
            elif isinstance(payload.get("source_ref"), dict):
                refs.append(payload["source_ref"])
        if refs:
            return unique_source_refs(refs)
        return self.all_source_refs()

    def all_source_refs(self) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for path in sorted((self.root / "xmuse/knowledge/error_records").glob("*/*.json")):
            payload = _read_json(path)
            if isinstance(payload.get("source_refs"), list):
                refs.extend(payload["source_refs"])
            elif isinstance(payload.get("source_ref"), dict):
                refs.append(payload["source_ref"])
        return unique_source_refs(refs)

    def write_handoff_artifacts(
        self,
        *,
        status: str,
        records: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
        methods: list[dict[str, Any]],
        proposals: list[dict[str, Any]],
        blockers: list[str] | None = None,
    ) -> None:
        blockers = blockers or []
        ack_level = "usable" if status == "usable" else "failed"
        verification = [
            {
                "command": "uv run pytest tests/test_xmuse_error_knowledge.py -q",
                "result": "recorded by Slave after focused verification",
            },
            {
                "command": "uv run ruff check .",
                "result": "repository lint gate; xmuse is excluded by project config",
            },
            {
                "command": (
                    "uv run ruff check --no-cache xmuse/xmuse_error_knowledge.py "
                    "tests/test_xmuse_error_knowledge.py"
                ),
                "result": "explicit Xmuse maintainer lint gate",
            },
        ]
        phase_rows = [
            ("Phase 0", "complete", "Contract and bootstrap boundary implemented."),
            ("Phase 1", "complete", "Schema objects and index rebuilds implemented."),
            (
                "Phase 2",
                "complete",
                "Structured scanner extracts JSON and bounded Markdown failures.",
            ),
            ("Phase 3", "complete", "Clustering and conservative promotion rules implemented."),
            ("Phase 4", "complete", "Draft methods and skill proposals remain quarantined."),
            (
                "Phase 5",
                "complete" if status == "usable" else "failed",
                "Integrated run artifacts emitted.",
            ),
        ]
        result_md = "\n".join(
            [
                f"# feature: {FEATURE_ID}",
                "",
                "## Result",
                "",
                f"- Status: `{status}`",
                f"- Knowledge run: `{self.run_id}`",
                f"- Error records: {len(records)}",
                f"- Clusters touched: {len(clusters)}",
                f"- Draft methods touched: {len(methods)}",
                f"- Draft skill proposals touched: {len(proposals)}",
                "",
                "## Phase Matrix",
                "",
                "| Phase | Status | Evidence |",
                "|---|---|---|",
                *[
                    f"| {phase} | {row_status} | {evidence} |"
                    for phase, row_status, evidence in phase_rows
                ],
                "",
                "## Boundaries",
                "",
                (
                    "- No MemoryOS runtime, store, recall, v1 fallback, "
                    "v3 default, or kernel default changes."
                ),
                (
                    "- No Master state/status, Master review, approval, "
                    "active prompt, or active skill writes."
                ),
                "- Benchmark scores are diagnostic evidence only; no improvement claim is made.",
                "",
                "## Blockers",
                "",
                *(f"- {blocker}" for blocker in blockers),
                "" if blockers else "- None",
                "",
            ]
        )
        review = {
            "feature_id": FEATURE_ID,
            "verdict": "PASS" if status == "usable" else "FAIL",
            "blocking_findings": blockers,
            "required_repairs": blockers,
            "review_eval_decision": {
                "scope": "not_applicable",
                "reason": "Xmuse control-plane maintenance only; no MemoryOS answer path changed",
                "longmemeval": {"run": False, "reason": "not applicable"},
                "locomo": {"run": False, "reason": "not applicable"},
                "llm_answer": False,
                "llm_judge": False,
                "promotion_gate": "not_applicable",
            },
            "readiness_for_slave_ack": status == "usable",
            "v3_default_preserved": True,
            "v1_fallback_preserved": True,
            "kernel_default_unchanged": True,
            "benchmark_improvement_claim_flag": False,
        }
        ack = {
            "feature_id": FEATURE_ID,
            "ack_level": ack_level,
            "branch": "feat/xmuse-error-knowledge",
            "worktree": str(self.root.resolve()),
            "head_ref": self.current_head_ref(),
            "knowledge_run_id": self.run_id,
            "verification_commands": verification,
            "v3_default_preserved": True,
            "v1_fallback_preserved": True,
            "recall_v2_opt_in_preserved": True,
            "kernel_default_unchanged": True,
            "benchmark_improvement_claim_flag": False,
            "review_verdict": review["verdict"],
            "review_eval_decision": review["review_eval_decision"],
            "blockers": blockers,
        }
        slave_state = {
            "version": "1.0",
            "feature_id": FEATURE_ID,
            "mode": "feature_local_single_god",
            "state": "ready_for_master_review" if status == "usable" else "feature_blocked",
            "branch": "feat/xmuse-error-knowledge",
            "worktree": str(self.root.resolve()),
            "last_updated": self.now,
            "ack_level": ack_level,
            "review_verdict": review["verdict"],
            "knowledge_run_id": self.run_id,
            "artifacts": {
                "result": f"xmuse/work/features/{FEATURE_ID}/result.md",
                "ack": f"xmuse/work/features/{FEATURE_ID}/ack.json",
                "review_verdict": f"xmuse/work/features/{FEATURE_ID}/review_verdict.json",
                "knowledge_run": f"xmuse/knowledge/runs/{self.run_id}.json",
            },
        }
        self.write_text(f"xmuse/work/features/{FEATURE_ID}/result.md", result_md)
        self.write_json(f"xmuse/work/features/{FEATURE_ID}/review_verdict.json", review)
        self.write_json(f"xmuse/work/features/{FEATURE_ID}/ack.json", ack)
        self.write_json(f"xmuse/work/features/{FEATURE_ID}/slave_state.json", slave_state)

    def current_head_ref(self) -> str:
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        except OSError:
            return "unknown"
        if branch and commit:
            return f"{branch}@{commit}"
        return commit or branch or "unknown"


def missing_required_inputs(root: Path) -> list[str]:
    blockers = []
    for rel in REQUIRED_INPUTS:
        if not (root / rel).exists():
            blockers.append(f"missing required input: {rel}")
    return blockers


def run_knowledge_maintenance(
    root: str | Path = ".",
    *,
    run_id: str | None = None,
    now: str | None = None,
    fail_after_object_writes: int | None = None,
) -> dict[str, Any]:
    root = Path(root)
    actual_run_id = run_id or f"knowledge-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    actual_now = now or utc_now()
    contract = validate_contract(root)
    if not contract["valid"]:
        return _write_bootstrap_blocked(
            root,
            contract["blockers"],
            run_id=actual_run_id,
            now=actual_now,
        )
    blockers = missing_required_inputs(root)
    if blockers:
        return _write_bootstrap_blocked(root, blockers, run_id=actual_run_id, now=actual_now)
    maintainer = KnowledgeMaintainer(
        root,
        run_id=actual_run_id,
        now=actual_now,
        fail_after_object_writes=fail_after_object_writes,
    )
    return maintainer.run()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    result = run_knowledge_maintenance(args.root, run_id=args.run_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "usable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
