from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT / "xmuse" / "xmuse_error_knowledge.py"
NOW = "2026-05-25T00:00:00Z"
FEATURE_ID = "xmuse-error-knowledge"


def load_knowledge_module():
    spec = importlib.util.spec_from_file_location("xmuse_error_knowledge", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_contract() -> dict:
    return {
        "role": "knowledge_maintainer",
        "version": "1.0",
        "runner_policy": {
            "command": "codex exec --yolo",
            "approval_policy": "never",
            "skip_human_confirmation": True,
        },
        "allowed_writes": [
            "xmuse/knowledge/**",
            "xmuse/work/features/xmuse-error-knowledge/result.md",
            "xmuse/work/features/xmuse-error-knowledge/review_verdict.json",
            "xmuse/work/features/xmuse-error-knowledge/ack.json",
            "xmuse/work/features/xmuse-error-knowledge/slave_state.json",
        ],
        "bootstrap_failure_writes": [
            "xmuse/work/features/xmuse-error-knowledge/ack.json",
            "xmuse/work/features/xmuse-error-knowledge/result.md",
        ],
        "required_inputs": [
            "xmuse/master_state.json",
            "xmuse/master_status.json",
            "xmuse/contracts/master_dispatch_template.json",
            "xmuse/contracts/slave_dispatch_template.json",
            "xmuse/contracts/knowledge_maintainer_template.json",
        ],
        "forbidden_writes": [
            "xmuse/master_state.json",
            "xmuse/master_status.json",
            "xmuse/master_status.md",
            "xmuse/master/features/**",
            "xmuse/approvals/**",
            "xmuse/prompts/**",
            "src/memoryos_lite/**",
        ],
    }


def write_required_inputs(root: Path, *, contract: bool = True) -> None:
    write_json(root / "xmuse/contracts/master_dispatch_template.json", {"role": "master_god"})
    write_json(root / "xmuse/contracts/slave_dispatch_template.json", {"role": "slave_god"})
    if contract:
        write_json(root / "xmuse/contracts/knowledge_maintainer_template.json", valid_contract())
    write_json(
        root / "xmuse/master_state.json",
        {
            "version": "1.0",
            "activation_state": "master_active",
            "active": True,
            "features": [],
            "queues": {},
            "decisions": [],
        },
    )
    write_json(root / "xmuse/master_status.json", {"version": "1.0", "errors": []})
    (root / "xmuse/work/features/xmuse-error-knowledge").mkdir(parents=True, exist_ok=True)


def add_feature_artifact(
    root: Path,
    feature_id: str,
    artifact_name: str,
    content: str | dict,
) -> Path:
    artifact = root / "xmuse/work/features" / feature_id / artifact_name
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, dict):
        write_json(artifact, content)
    else:
        artifact.write_text(content, encoding="utf-8")
    return artifact


def error_records(root: Path, feature_id: str | None = None) -> list[dict]:
    base = root / "xmuse/knowledge/error_records"
    if not base.exists():
        return []
    paths = (
        sorted((base / feature_id).glob("*.json"))
        if feature_id
        else sorted(base.glob("*/*.json"))
    )
    return [read_json(path) for path in paths]


def clusters(root: Path) -> list[dict]:
    base = root / "xmuse/knowledge/clusters"
    if not base.exists():
        return []
    return [read_json(path) for path in sorted(base.glob("*.json"))]


def relative_digest(root: Path, path: Path) -> str:
    data = path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def test_missing_contract_bootstrap_writes_only_blocked_ack_and_result(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path, contract=False)

    result = knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-bootstrap", now=NOW)

    feature_dir = tmp_path / "xmuse/work/features/xmuse-error-knowledge"
    ack = read_json(feature_dir / "ack.json")
    assert result["status"] == "blocked"
    assert ack["ack_level"] == "blocked"
    assert "knowledge_maintainer_template.json missing" in ack["blockers"]
    assert (feature_dir / "result.md").exists()
    assert not (feature_dir / "review_verdict.json").exists()
    assert not (feature_dir / "slave_state.json").exists()
    assert not (tmp_path / "xmuse/knowledge").exists()


def test_invalid_contract_bootstrap_writes_only_blocked_ack_and_result(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path, contract=False)
    contract = tmp_path / "xmuse/contracts/knowledge_maintainer_template.json"
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text("{invalid json", encoding="utf-8")

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-invalid", now=NOW)

    feature_dir = tmp_path / "xmuse/work/features/xmuse-error-knowledge"
    ack = read_json(feature_dir / "ack.json")
    assert ack["ack_level"] == "blocked"
    assert any("invalid JSON" in blocker for blocker in ack["blockers"])
    assert (feature_dir / "result.md").exists()
    assert not (feature_dir / "review_verdict.json").exists()
    assert not (feature_dir / "slave_state.json").exists()
    assert not (tmp_path / "xmuse/knowledge").exists()


def test_semantically_invalid_contract_cannot_enter_normal_write_mode(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path, contract=False)
    bad_contract = valid_contract()
    bad_contract["allowed_writes"] = ["xmuse/knowledge/**"]
    write_json(tmp_path / "xmuse/contracts/knowledge_maintainer_template.json", bad_contract)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})

    result = knowledge.run_knowledge_maintenance(
        tmp_path,
        run_id="krun-bad-contract",
        now=NOW,
    )

    feature_dir = tmp_path / "xmuse/work/features/xmuse-error-knowledge"
    ack = read_json(feature_dir / "ack.json")
    assert result["status"] == "blocked"
    assert ack["ack_level"] == "blocked"
    assert "allowed_writes must exactly match the knowledge maintainer contract" in ack[
        "blockers"
    ]
    assert (feature_dir / "result.md").exists()
    assert not (feature_dir / "review_verdict.json").exists()
    assert not (feature_dir / "slave_state.json").exists()
    assert not (tmp_path / "xmuse/knowledge").exists()


def test_missing_required_input_blocks_without_knowledge_files(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_json(
        tmp_path / "xmuse/contracts/knowledge_maintainer_template.json",
        valid_contract(),
    )
    write_json(tmp_path / "xmuse/contracts/master_dispatch_template.json", {"role": "master"})

    result = knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-required", now=NOW)

    feature_dir = tmp_path / "xmuse/work/features/xmuse-error-knowledge"
    ack = read_json(feature_dir / "ack.json")
    assert result["status"] == "blocked"
    assert ack["ack_level"] == "blocked"
    assert "missing required input: xmuse/master_state.json" in ack["blockers"]
    assert not (tmp_path / "xmuse/knowledge").exists()


def test_write_boundary_and_optional_missing_diagnostics(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    maintainer = knowledge.KnowledgeMaintainer(tmp_path, run_id="krun-boundary", now=NOW)

    maintainer.assert_allowed_write(tmp_path / "xmuse/knowledge/runs/krun-boundary.json")
    with pytest.raises(ValueError, match="write outside knowledge_maintainer boundary"):
        maintainer.assert_allowed_write(tmp_path / "xmuse/master_state.json")

    result = knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-boundary", now=NOW)

    run_summary = read_json(tmp_path / "xmuse/knowledge/runs/krun-boundary.json")
    assert result["status"] == "usable"
    assert "missing optional input: xmuse/reports/latest.json" in run_summary["diagnostics"]
    assert "missing optional input: xmuse/reports/latest.md" in run_summary["diagnostics"]


def test_error_records_include_schema_source_digest_and_run_metadata(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    ack_path = add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "partial"})
    add_feature_artifact(tmp_path, "alpha", "result.md", "Status: blocked\n")
    add_feature_artifact(tmp_path, "alpha", "review_verdict.json", {"verdict": "PASS"})

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-schema", now=NOW)

    records = error_records(tmp_path, "alpha")
    assert len(records) == 1
    record = records[0]
    assert record["schema_version"] == "1.0"
    assert record["knowledge_run_id"] == "krun-schema"
    assert record["extractor_version"]
    assert record["source_ref"]["path"] == "xmuse/work/features/alpha/ack.json"
    assert record["source_ref"]["digest"] == relative_digest(tmp_path, ack_path)
    assert record["source_ref"]["artifact_type"] == "ack"
    assert record["source_ref"]["feature_id"] == "alpha"
    assert record["source_refs"] == [record["source_ref"]]

    cluster = clusters(tmp_path)[0]
    assert cluster["schema_version"] == "1.0"
    assert cluster["knowledge_run_id"] == "krun-schema"
    assert cluster["extractor_version"]
    assert cluster["source_refs"][0]["digest"] == record["source_ref"]["digest"]


def test_digest_idempotency_and_duplicate_failures_do_not_inflate_counts(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(
        tmp_path,
        "alpha",
        "result.md",
        "\n".join(
            [
                "uv run mypy src fails with 82 errors in 11 files",
                "uv run mypy src fails with 82 errors in 11 files",
                "",
            ]
        ),
    )
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "usable"})
    add_feature_artifact(tmp_path, "alpha", "review_verdict.json", {"verdict": "PASS"})

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-idem-1", now=NOW)
    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-idem-2", now=NOW)

    records = error_records(tmp_path, "alpha")
    assert len(records) == 1
    cluster = clusters(tmp_path)[0]
    assert cluster["occurrence_count"] == 1
    assert cluster["feature_count"] == 1
    assert cluster["source_digest_count"] == 1


def test_distinct_failed_commands_create_distinct_records(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(
        tmp_path,
        "alpha",
        "result.md",
        "\n".join(
            [
                "uv run mypy src fails with 82 errors in 11 files",
                "uv run pytest -q failed with 3 failures",
                "",
            ]
        ),
    )
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "usable"})
    add_feature_artifact(tmp_path, "alpha", "review_verdict.json", {"verdict": "PASS"})

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-commands", now=NOW)

    fingerprints = {record["fingerprint"] for record in error_records(tmp_path, "alpha")}
    assert fingerprints == {
        "failed_command:uv-run-mypy-src",
        "failed_command:uv-run-pytest-q",
    }


def test_scanner_extracts_missing_artifacts_invalid_json_mypy_and_hard_eval(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    (tmp_path / "xmuse/work/features/alpha").mkdir(parents=True)
    bad_ack = tmp_path / "xmuse/work/features/beta/ack.json"
    bad_ack.parent.mkdir(parents=True)
    bad_ack.write_text("{bad json", encoding="utf-8")
    add_feature_artifact(
        tmp_path,
        "gamma",
        "result.md",
        "\n".join(
            [
                "uv run mypy src fails with 82 errors in 11 files",
                (
                    "hard eval reports accuracy/source_hit 0.56/0.56 "
                    "instead of stated 1.00/1.00 baseline"
                ),
                "",
            ]
        ),
    )

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-extract", now=NOW)

    fingerprints = {record["fingerprint"] for record in error_records(tmp_path)}
    assert {
        "missing_required_artifact:ack",
        "missing_required_artifact:result",
        "missing_required_artifact:review_verdict",
        "invalid_json_artifact:ack",
        "failed_command:uv-run-mypy-src",
        "baseline_drift:hard-eval",
    }.issubset(fingerprints)


def test_scanner_extracts_partially_missing_terminal_artifacts(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "usable"})

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-partial-missing", now=NOW)

    records = error_records(tmp_path, "alpha")
    fingerprints = {record["fingerprint"] for record in records}
    paths = {record["source_ref"]["path"] for record in records}
    assert fingerprints == {
        "missing_required_artifact:result",
        "missing_required_artifact:review_verdict",
    }
    assert paths == {
        "xmuse/work/features/alpha/result.md",
        "xmuse/work/features/alpha/review_verdict.json",
    }


def test_json_blocking_findings_stale_gates_and_approval_absence_are_extracted(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "usable"})
    add_feature_artifact(tmp_path, "alpha", "result.md", "Status: blocked\n")
    add_feature_artifact(
        tmp_path,
        "alpha",
        "review_verdict.json",
        {
            "verdict": "FAIL",
            "blocking_findings": [
                "uv run mypy src fails with 82 errors in 11 files",
                "Root cause: review evidence is incomplete.",
            ],
        },
    )
    write_json(
        tmp_path / "xmuse/master/features/beta/integrated_tests.json",
        {
            "feature_id": "beta",
            "status": "failed_stale_target_head",
            "stale_against_current_target_head": True,
            "merge_readiness_blockers": [
                "external merge approval is absent",
            ],
            "commands": [
                {
                    "command": "uv run pytest -q",
                    "status": "failed",
                    "summary": "3 failed, 20 passed",
                },
            ],
        },
    )

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-json-blockers", now=NOW)

    records = error_records(tmp_path)
    by_feature = {}
    for record in records:
        by_feature.setdefault(record["feature_id"], set()).add(record["fingerprint"])
    assert {
        "review_verdict_not_pass",
        "failed_command:uv-run-mypy-src",
        "markdown_diagnosis:free-form-root-cause",
    }.issubset(by_feature["alpha"])
    assert {
        "integrated_tests_not_passed",
        "failed_command:uv-run-pytest-q",
        "stale_target_head",
        "merge_requested_without_approval",
    }.issubset(by_feature["beta"])
    beta_records = [record for record in records if record["feature_id"] == "beta"]
    beta_fingerprints = [record["fingerprint"] for record in beta_records]
    assert beta_fingerprints.count("stale_target_head") == 1
    assert beta_fingerprints.count("merge_requested_without_approval") == 1
    deterministic = {
        record["fingerprint"]: record["deterministic_invariant"]
        for record in beta_records
    }
    assert deterministic["stale_target_head"] == "stale_target_head"
    assert (
        deterministic["merge_requested_without_approval"]
        == "merge_requested_without_approval"
    )


def test_same_feature_retries_do_not_satisfy_cross_feature_promotion(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(
        tmp_path,
        "alpha",
        "result.md",
        "transient network timeout while fetching benchmark data\n",
    )
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "usable"})
    add_feature_artifact(tmp_path, "alpha", "review_verdict.json", {"verdict": "PASS"})
    add_feature_artifact(
        tmp_path,
        "alpha",
        "execute_review.md",
        "transient network timeout while fetching benchmark data\n",
    )

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-same-feature", now=NOW)

    cluster = clusters(tmp_path)[0]
    assert cluster["fingerprint"] == "environment:network-timeout"
    assert cluster["occurrence_count"] == 2
    assert cluster["feature_count"] == 1
    assert cluster["promotion_stage"] == "method_candidate"
    assert cluster["promotion_blockers"] == [
        "same-feature recurrence is not cross-feature evidence"
    ]
    assert not list((tmp_path / "xmuse/knowledge/methods").glob("*/manifest.json"))


def test_same_feature_allowlisted_retries_do_not_promote_to_method_created(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(
        tmp_path,
        "alpha",
        "ack.json",
        {"ack_level": "blocked", "source_run_id": "run-1"},
    )
    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-allow-1", now=NOW)
    add_feature_artifact(
        tmp_path,
        "alpha",
        "ack.json",
        {"ack_level": "partial", "source_run_id": "run-2"},
    )

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-allow-2", now=NOW)

    cluster = next(
        cluster for cluster in clusters(tmp_path) if cluster["fingerprint"] == "ack_non_usable"
    )
    assert cluster["source_run_count"] == 2
    assert cluster["feature_count"] == 1
    assert cluster["promotion_stage"] == "method_candidate"
    assert cluster["promotion_blockers"] == [
        "same-feature recurrence is not cross-feature evidence"
    ]
    assert not list((tmp_path / "xmuse/knowledge/methods").glob("*/manifest.json"))


def test_markdown_only_diagnosis_cannot_confirm_root_cause(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(
        tmp_path,
        "alpha",
        "result.md",
        "Root cause: the prompt probably confused the worker during review.\n",
    )
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "usable"})
    add_feature_artifact(tmp_path, "alpha", "review_verdict.json", {"verdict": "PASS"})

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-markdown", now=NOW)

    records = error_records(tmp_path, "alpha")
    assert len(records) == 1
    assert records[0]["fingerprint"] == "markdown_diagnosis:free-form-root-cause"
    assert records[0]["root_cause_status"] == "suspected"


def test_confirmed_root_cause_requires_verification_or_allowlisted_invariant(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})
    add_feature_artifact(tmp_path, "alpha", "result.md", "Status: blocked\n")
    add_feature_artifact(tmp_path, "alpha", "review_verdict.json", {"verdict": "PASS"})
    add_feature_artifact(
        tmp_path,
        "beta",
        "result.md",
        "verification evidence: uv run pytest tests/test_x.py -q failed\n",
    )
    add_feature_artifact(tmp_path, "beta", "ack.json", {"ack_level": "usable"})
    add_feature_artifact(tmp_path, "beta", "review_verdict.json", {"verdict": "PASS"})

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-confirmed", now=NOW)

    by_feature = {record["source_ref"]["feature_id"]: record for record in error_records(tmp_path)}
    assert by_feature["alpha"]["root_cause_status"] == "confirmed"
    assert by_feature["alpha"]["deterministic_invariant"] == "ack_non_usable"
    assert by_feature["beta"]["root_cause_status"] == "confirmed"
    assert by_feature["beta"]["verification_evidence"] is True


def test_partial_write_failure_does_not_leave_indexes_pointing_to_missing_objects(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})
    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-index-1", now=NOW)
    add_feature_artifact(tmp_path, "beta", "ack.json", {"ack_level": "blocked"})

    result = knowledge.run_knowledge_maintenance(
        tmp_path,
        run_id="krun-index-2",
        now=NOW,
        fail_after_object_writes=1,
    )

    assert result["status"] == "failed"
    for index_path in sorted((tmp_path / "xmuse/knowledge/indexes").glob("*.json")):
        index = read_json(index_path)
        for rel_path in index["paths"].values():
            assert (tmp_path / rel_path).exists(), rel_path


def test_rerun_prunes_cluster_occurrences_for_missing_record_files(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})
    add_feature_artifact(tmp_path, "beta", "ack.json", {"ack_level": "partial"})
    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-prune-1", now=NOW)

    cluster_path = next(
        path
        for path in (tmp_path / "xmuse/knowledge/clusters").glob("*.json")
        if read_json(path)["fingerprint"] == "ack_non_usable"
    )
    cluster = read_json(cluster_path)
    cluster["occurrences"].append(
        {
            "record_id": "error-missing",
            "feature_id": "alpha",
            "source_digest": "sha256:missing",
            "source_path": "xmuse/work/features/alpha/ack.json",
            "root_cause_status": "confirmed",
            "deterministic_invariant": "ack_non_usable",
        }
    )
    write_json(cluster_path, cluster)

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-prune-2", now=NOW)

    repaired = read_json(cluster_path)
    assert repaired["occurrence_count"] == 2
    assert {item["record_id"] for item in repaired["occurrences"]} != {"error-missing"}
    for occurrence in repaired["occurrences"]:
        record_path = (
            tmp_path
            / "xmuse/knowledge/error_records"
            / occurrence["feature_id"]
            / f"{occurrence['record_id']}.json"
        )
        assert record_path.exists()


def test_generated_methods_and_skill_proposals_are_local_quarantined_drafts(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})
    add_feature_artifact(tmp_path, "beta", "ack.json", {"ack_level": "partial"})

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-drafts", now=NOW)

    method_manifests = sorted((tmp_path / "xmuse/knowledge/methods").glob("*/manifest.json"))
    proposal_manifests = sorted(
        (tmp_path / "xmuse/knowledge/skill_proposals").glob("*/manifest.json")
    )
    assert method_manifests
    assert proposal_manifests
    method = read_json(method_manifests[0])
    proposal = read_json(proposal_manifests[0])
    assert method["status"] == "draft"
    assert method["quarantined"] is True
    assert method["activation_status"] == "not_active"
    assert proposal["status"] == "draft"
    assert proposal["quarantined"] is True
    assert proposal["activation_status"] == "not_installed"
    assert "Draft" in method_manifests[0].with_name("current.md").read_text(encoding="utf-8")


def test_human_edited_current_method_is_not_overwritten(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})
    add_feature_artifact(tmp_path, "beta", "ack.json", {"ack_level": "partial"})
    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-human-1", now=NOW)
    current = next((tmp_path / "xmuse/knowledge/methods").glob("*/current.md"))
    current.write_text("Human edited method text\n", encoding="utf-8")

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-human-2", now=NOW)

    assert current.read_text(encoding="utf-8") == "Human edited method text\n"
    revisions = list((current.parent / "revisions").glob("*.md"))
    assert revisions
    assert "Draft" in revisions[0].read_text(encoding="utf-8")


def test_human_edit_below_generated_digest_marker_is_not_overwritten(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})
    add_feature_artifact(tmp_path, "beta", "ack.json", {"ack_level": "partial"})
    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-marker-1", now=NOW)
    current = next((tmp_path / "xmuse/knowledge/methods").glob("*/current.md"))
    current.write_text(
        current.read_text(encoding="utf-8") + "\nHuman edited below marker\n",
        encoding="utf-8",
    )

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-marker-2", now=NOW)

    assert current.read_text(encoding="utf-8").endswith("\nHuman edited below marker\n")
    revisions = list((current.parent / "revisions").glob("*.md"))
    assert revisions
    assert "Draft" in revisions[0].read_text(encoding="utf-8")


def test_existing_skill_proposal_tombstones_are_preserved(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})
    add_feature_artifact(tmp_path, "beta", "ack.json", {"ack_level": "partial"})
    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-proposal-1", now=NOW)
    manifest_path = next(
        (tmp_path / "xmuse/knowledge/skill_proposals").glob("*/manifest.json")
    )
    manifest = read_json(manifest_path)
    assert isinstance(manifest, dict)
    original_created_at = manifest["created_at"]
    tombstone = {
        "recorded_at": NOW,
        "reason": "human archived an earlier proposal revision",
    }
    manifest["tombstones"] = [tombstone]
    write_json(manifest_path, manifest)

    knowledge.run_knowledge_maintenance(
        tmp_path,
        run_id="krun-proposal-2",
        now="2026-05-25T01:00:00Z",
    )

    updated = read_json(manifest_path)
    assert isinstance(updated, dict)
    assert updated["created_at"] == original_created_at
    assert updated["updated_at"] == "2026-05-25T01:00:00Z"
    assert updated["tombstones"] == [tombstone]


def test_run_and_index_objects_include_source_refs_and_digest_metadata(
    tmp_path: Path,
) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    add_feature_artifact(tmp_path, "alpha", "ack.json", {"ack_level": "blocked"})

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-object-metadata", now=NOW)

    object_paths = [
        tmp_path / "xmuse/knowledge/runs/krun-object-metadata.json",
        *sorted((tmp_path / "xmuse/knowledge/indexes").glob("*.json")),
    ]
    for object_path in object_paths:
        payload = read_json(object_path)
        assert payload["schema_version"] == "1.0"
        assert payload["knowledge_run_id"] == "krun-object-metadata"
        assert payload["extractor_version"]
        assert payload["source_digest"].startswith("sha256:")
        assert payload["source_refs"]
        for ref in payload["source_refs"]:
            assert ref["path"]
            assert ref["digest"].startswith("sha256:")
            assert ref["artifact_type"]
            assert ref["feature_id"]


def test_run_does_not_modify_master_prompts_skills_or_memoryos_files(tmp_path: Path) -> None:
    knowledge = load_knowledge_module()
    write_required_inputs(tmp_path)
    write_json(tmp_path / "xmuse/master_state.json", {"features": []})
    (tmp_path / "xmuse/prompts").mkdir(parents=True)
    prompt = tmp_path / "xmuse/prompts/slave_god_prompt.md"
    skill = tmp_path / ".codex/skills/example/SKILL.md"
    memoryos = tmp_path / "src/memoryos_lite/config.py"
    prompt.write_text("active prompt\n", encoding="utf-8")
    skill.parent.mkdir(parents=True)
    skill.write_text("active skill\n", encoding="utf-8")
    memoryos.parent.mkdir(parents=True)
    memoryos.write_text("MEMORYOS_RUNTIME = True\n", encoding="utf-8")
    before = {
        "master_state": (tmp_path / "xmuse/master_state.json").read_text(encoding="utf-8"),
        "prompt": prompt.read_text(encoding="utf-8"),
        "skill": skill.read_text(encoding="utf-8"),
        "memoryos": memoryos.read_text(encoding="utf-8"),
    }

    knowledge.run_knowledge_maintenance(tmp_path, run_id="krun-forbidden", now=NOW)

    after = {
        "master_state": (tmp_path / "xmuse/master_state.json").read_text(encoding="utf-8"),
        "prompt": prompt.read_text(encoding="utf-8"),
        "skill": skill.read_text(encoding="utf-8"),
        "memoryos": memoryos.read_text(encoding="utf-8"),
    }
    assert after == before
