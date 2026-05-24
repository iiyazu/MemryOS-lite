# Hermes GitHub Read-Only Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add disabled-by-default GitHub read-only PR/review/check evidence to Hermes Master merge gates without replacing local integrated tests or external merge approval artifacts.

**Architecture:** Keep Master as the only active controller. Add pure GitHub evidence schema and validation helpers to `.hermes-loop/hermes_hardening.py`, then wire those helpers into approval validation and Master merge queue derivation. Add a small read-only fetch adapter that can call `gh` or the GitHub REST API, but keep tests fixture-based and network-free.

**Tech Stack:** Python 3.11+, stdlib `json`, `hashlib`, `subprocess`, `urllib.request`, pytest, existing Hermes `.hermes-loop/hermes_hardening.py` control-plane helpers.

---

## Source Spec

Implement against:

- `docs/superpowers/specs/2026-05-24-hermes-github-readonly-evidence-design.md`

Preserve project constraints:

- MemoryOS Lite remains an eval-driven, source-attributed Agent/RAG memory prototype.
- Default memory architecture remains v3.
- `MEMORYOS_MEMORY_ARCH=v1` fallback remains available.
- Kernel remains opt-in via `MEMORYOS_AGENT_KERNEL=v1`.
- No benchmark score targets in Hermes `/goal` or merge evidence.
- Same-slice repair smoke is diagnostic only, not promotion evidence.

## File Structure

- Modify `.hermes-loop/hermes_hardening.py`
  - Add GitHub config defaults.
  - Add pure validation helpers for normalized GitHub evidence.
  - Add optional read-only evidence fetch helpers.
  - Connect required GitHub evidence to `validate_merge_queue_gate()`.
  - Extend `validate_merge_approval()` to verify `github_review` / `github_check` evidence digest and validity.

- Modify `tests/test_hermes_master_state.py`
  - Add fixture builders for GitHub evidence.
  - Test PR lifecycle, SHA binding, review event semantics, check-run validation, approval digest binding, and merge queue blocking.

- Modify `tests/test_hermes_hardening.py`
  - Add legacy summary tests proving local-only features still work when GitHub is disabled or optional.

- Modify `.hermes-loop/master_config.json`
  - Add disabled-by-default `github` config object.
  - Include current rollout target branch in both local and GitHub allowlists.

No product memory modules under `src/memoryos_lite/` should change in this feature.

---

### Task 1: Master Config Defaults

**Files:**
- Modify: `.hermes-loop/hermes_hardening.py`
- Modify: `.hermes-loop/master_config.json`
- Test: `tests/test_hermes_master_state.py`

- [ ] **Step 1: Write failing config tests**

Append these tests to `tests/test_hermes_master_state.py`:

```python
def test_default_master_config_has_disabled_github_rollout_policy(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    loop.mkdir()

    hardening.write_default_master_config(loop)

    config = json.loads((loop / "master_config.json").read_text())
    assert config["allowed_target_branches"] == [
        "main",
        "feat/phase-2.5-3-retrieval-agent",
    ]
    assert config["github"] == {
        "enabled": False,
        "repo": "",
        "remote": "origin",
        "allowed_target_branches": [
            "main",
            "feat/phase-2.5-3-retrieval-agent",
        ],
        "token_env": "GITHUB_TOKEN",
        "required_review_state": "APPROVED",
        "required_check_conclusions": ["success"],
        "request_timeout_seconds": 20,
    }


def test_prepare_master_migration_writes_github_config(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)

    hardening.prepare_master_migration(loop)

    config = json.loads((loop / "master_config.json").read_text())
    assert config["github"]["enabled"] is False
    assert "feat/phase-2.5-3-retrieval-agent" in config["allowed_target_branches"]
    assert "feat/phase-2.5-3-retrieval-agent" in config["github"]["allowed_target_branches"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_default_master_config_has_disabled_github_rollout_policy tests/test_hermes_master_state.py::test_prepare_master_migration_writes_github_config -q
```

Expected: fail because `write_default_master_config()` does not exist and `prepare_master_migration()` writes only the old config.

- [ ] **Step 3: Implement config helper**

In `.hermes-loop/hermes_hardening.py`, add this near the constants:

```python
CURRENT_HERMES_TARGET_BRANCH = "feat/phase-2.5-3-retrieval-agent"


def default_master_config() -> dict[str, Any]:
    return {
        "version": "1.0",
        "allowed_target_branches": ["main", CURRENT_HERMES_TARGET_BRANCH],
        "merge_strategy": "no_ff_merge_commit",
        "github": {
            "enabled": False,
            "repo": "",
            "remote": "origin",
            "allowed_target_branches": ["main", CURRENT_HERMES_TARGET_BRANCH],
            "token_env": "GITHUB_TOKEN",
            "required_review_state": "APPROVED",
            "required_check_conclusions": ["success"],
            "request_timeout_seconds": 20,
        },
    }


def write_default_master_config(loop_root: str | Path) -> dict[str, Any]:
    loop = Path(loop_root)
    config = default_master_config()
    _write_json(loop / "master_config.json", config)
    return config
```

In `prepare_master_migration()`, replace the inline `_write_json(loop / "master_config.json", ...)` block with:

```python
    write_default_master_config(loop)
```

Update `.hermes-loop/master_config.json` to:

```json
{
  "allowed_target_branches": [
    "main",
    "feat/phase-2.5-3-retrieval-agent"
  ],
  "github": {
    "allowed_target_branches": [
      "main",
      "feat/phase-2.5-3-retrieval-agent"
    ],
    "enabled": false,
    "remote": "origin",
    "repo": "",
    "required_check_conclusions": [
      "success"
    ],
    "required_review_state": "APPROVED",
    "request_timeout_seconds": 20,
    "token_env": "GITHUB_TOKEN"
  },
  "merge_strategy": "no_ff_merge_commit",
  "version": "1.0"
}
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_default_master_config_has_disabled_github_rollout_policy tests/test_hermes_master_state.py::test_prepare_master_migration_writes_github_config -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add .hermes-loop/hermes_hardening.py .hermes-loop/master_config.json tests/test_hermes_master_state.py
git commit -m "feat: add hermes github evidence config"
```

---

### Task 2: Pure GitHub Evidence Validation

**Files:**
- Modify: `.hermes-loop/hermes_hardening.py`
- Test: `tests/test_hermes_master_state.py`

- [ ] **Step 1: Write failing evidence validation tests**

Append these helpers and tests to `tests/test_hermes_master_state.py`:

```python
def github_config() -> dict:
    return {
        "enabled": True,
        "repo": "owner/repo",
        "remote": "origin",
        "allowed_target_branches": ["main", "feat/phase-2.5-3-retrieval-agent"],
        "token_env": "GITHUB_TOKEN",
        "required_review_state": "APPROVED",
        "required_check_conclusions": ["success"],
        "request_timeout_seconds": 20,
    }


def github_feature() -> dict:
    feature = feature_for_gate()["features"][0]
    feature["branch"] = "feat/v1-quarantine"
    feature["target_branch"] = "main"
    feature["merge"]["target_branch"] = "main"
    feature["merge"]["github_pr"] = {
        "number": 123,
        "url": "https://github.com/owner/repo/pull/123",
        "head_ref": "feat/v1-quarantine",
        "base_ref": "main",
        "head_sha": "abcdef123456",
        "base_sha": "123456abcdef",
    }
    feature["merge"]["required_review_ids"] = [987654321]
    feature["merge"]["required_check_runs"] = [
        {"id": 123456789, "name": "pytest", "head_sha": "abcdef123456"}
    ]
    return feature


def github_evidence() -> dict:
    return {
        "version": "1.0",
        "feature_id": "v1-quarantine",
        "recorded_by": "master-god",
        "fetched_at": "2026-05-24T00:00:00Z",
        "repo": "owner/repo",
        "pull_request": {
            "number": 123,
            "url": "https://github.com/owner/repo/pull/123",
            "state": "open",
            "draft": False,
            "merged": False,
            "closed_at": None,
            "merged_at": None,
            "head_ref": "feat/v1-quarantine",
            "base_ref": "main",
            "head_sha": "abcdef123456",
            "base_sha": "123456abcdef",
        },
        "reviews": [
            {
                "id": 987654321,
                "user": "reviewer-login",
                "state": "APPROVED",
                "commit_id": "abcdef123456",
                "submitted_at": "2026-05-24T00:00:00Z",
            }
        ],
        "check_runs": [
            {
                "id": 123456789,
                "name": "pytest",
                "status": "completed",
                "conclusion": "success",
                "head_sha": "abcdef123456",
                "completed_at": "2026-05-24T00:00:00Z",
            }
        ],
    }


def github_local_refs() -> dict:
    return {
        "feature_head": "abcdef123456",
        "target_head": "123456abcdef",
        "integrated_tests_base_commit": "123456abcdef",
    }


def test_github_evidence_validator_accepts_valid_fixture():
    hardening = load_hardening()

    result = hardening.validate_github_pr_evidence(
        github_config(),
        github_feature(),
        github_evidence(),
        github_local_refs(),
    )

    assert result == {"schema_valid": True, "valid": True, "errors": []}


def test_github_evidence_validator_rejects_closed_draft_or_merged_pr():
    hardening = load_hardening()
    evidence = github_evidence()
    evidence["pull_request"]["state"] = "closed"
    evidence["pull_request"]["draft"] = True
    evidence["pull_request"]["merged"] = True

    result = hardening.validate_github_pr_evidence(
        github_config(),
        github_feature(),
        evidence,
        github_local_refs(),
    )

    assert result["valid"] is False
    assert "PR state must be open" in result["errors"]
    assert "PR must not be draft" in result["errors"]
    assert "PR must not already be merged" in result["errors"]


def test_github_evidence_validator_rejects_base_sha_mismatch():
    hardening = load_hardening()
    refs = github_local_refs()
    refs["target_head"] = "newtarget123"

    result = hardening.validate_github_pr_evidence(
        github_config(),
        github_feature(),
        github_evidence(),
        refs,
    )

    assert result["valid"] is False
    assert "PR base SHA does not match current target HEAD" in result["errors"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_github_evidence_validator_accepts_valid_fixture tests/test_hermes_master_state.py::test_github_evidence_validator_rejects_closed_draft_or_merged_pr tests/test_hermes_master_state.py::test_github_evidence_validator_rejects_base_sha_mismatch -q
```

Expected: fail because `validate_github_pr_evidence()` does not exist.

- [ ] **Step 3: Implement pure validator**

In `.hermes-loop/hermes_hardening.py`, add these helpers after `_same_commit_ref()`:

```python
def _github_config(master_config: dict[str, Any] | None) -> dict[str, Any]:
    config = default_master_config()["github"]
    if isinstance(master_config, dict):
        incoming = master_config.get("github", master_config)
        if isinstance(incoming, dict):
            config = {**config, **incoming}
    return config


def _latest_non_comment_reviews_by_user(reviews: list[Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for review in reviews:
        if not isinstance(review, dict):
            continue
        state = str(review.get("state", "")).upper()
        if state == "COMMENTED":
            continue
        user = str(review.get("user") or review.get("user_login") or "").strip()
        submitted_at = str(review.get("submitted_at") or "")
        if not user:
            continue
        current = latest.get(user)
        if current is None or submitted_at >= str(current.get("submitted_at") or ""):
            latest[user] = review
    return latest


def validate_github_pr_evidence(
    config: dict[str, Any],
    feature: dict[str, Any],
    evidence: dict[str, Any],
    local_refs: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return {"schema_valid": False, "valid": False, "errors": ["github evidence root must be an object"]}

    github = _github_config(config)
    merge = feature.get("merge", {}) if isinstance(feature.get("merge"), dict) else {}
    declared_pr = merge.get("github_pr", {}) if isinstance(merge.get("github_pr"), dict) else {}
    pr = evidence.get("pull_request", {}) if isinstance(evidence.get("pull_request"), dict) else {}
    reviews = evidence.get("reviews", []) if isinstance(evidence.get("reviews"), list) else []
    check_runs = evidence.get("check_runs", []) if isinstance(evidence.get("check_runs"), list) else []

    if evidence.get("recorded_by") != "master-god":
        errors.append("github evidence must be recorded_by master-god")
    if evidence.get("repo") != github.get("repo"):
        errors.append("PR repo does not match github config")
    if pr.get("state") != "open":
        errors.append("PR state must be open")
    if pr.get("draft") is True:
        errors.append("PR must not be draft")
    if pr.get("merged") is True or pr.get("merged_at"):
        errors.append("PR must not already be merged")
    if pr.get("closed_at"):
        errors.append("PR must not be closed")
    if pr.get("head_ref") != feature.get("branch"):
        errors.append("PR head ref does not match feature branch")
    if pr.get("base_ref") != feature.get("target_branch"):
        errors.append("PR base ref does not match target branch")
    if pr.get("base_ref") not in github.get("allowed_target_branches", []):
        errors.append("PR base ref is not allowed by github target policy")
    if declared_pr:
        for key in ("number", "head_ref", "base_ref", "head_sha", "base_sha"):
            if declared_pr.get(key) != pr.get(key):
                errors.append(f"PR {key} does not match feature merge github_pr")

    head_sha = pr.get("head_sha")
    base_sha = pr.get("base_sha")
    if not _same_commit_ref(head_sha, local_refs.get("feature_head")):
        errors.append("PR head SHA does not match local feature HEAD")
    if not _same_commit_ref(base_sha, local_refs.get("integrated_tests_base_commit")):
        errors.append("PR base SHA does not match integrated-test base commit")
    if not _same_commit_ref(base_sha, local_refs.get("target_head")):
        errors.append("PR base SHA does not match current target HEAD")

    latest_by_user = _latest_non_comment_reviews_by_user(reviews)
    review_by_id = {review.get("id"): review for review in reviews if isinstance(review, dict)}
    required_review_ids = merge.get("required_review_ids", [])
    for review_id in required_review_ids:
        review = review_by_id.get(review_id)
        if not review:
            errors.append(f"required review id missing: {review_id}")
            continue
        user = str(review.get("user") or review.get("user_login") or "")
        latest = latest_by_user.get(user)
        if latest is not review:
            errors.append(f"required review id is not latest for reviewer: {review_id}")
        if str(review.get("state", "")).upper() != str(github.get("required_review_state")).upper():
            errors.append(f"required review id is not approved: {review_id}")
        if not _same_commit_ref(review.get("commit_id"), head_sha):
            errors.append(f"required review id is not bound to PR head SHA: {review_id}")

    checks_by_id = {run.get("id"): run for run in check_runs if isinstance(run, dict)}
    checks_by_name = {run.get("name"): run for run in check_runs if isinstance(run, dict)}
    for required in merge.get("required_check_runs", []):
        run = checks_by_id.get(required.get("id")) or checks_by_name.get(required.get("name"))
        label = required.get("id") or required.get("name")
        if not run:
            errors.append(f"required check run missing: {label}")
            continue
        if run.get("status") != "completed":
            errors.append(f"required check run not completed: {label}")
        if run.get("conclusion") not in github.get("required_check_conclusions", []):
            errors.append(f"required check run conclusion is not allowed: {label}")
        if not _same_commit_ref(run.get("head_sha"), head_sha):
            errors.append(f"required check run is not bound to PR head SHA: {label}")

    return {"schema_valid": True, "valid": not errors, "errors": errors}
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_github_evidence_validator_accepts_valid_fixture tests/test_hermes_master_state.py::test_github_evidence_validator_rejects_closed_draft_or_merged_pr tests/test_hermes_master_state.py::test_github_evidence_validator_rejects_base_sha_mismatch -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add .hermes-loop/hermes_hardening.py tests/test_hermes_master_state.py
git commit -m "feat: validate github readonly evidence"
```

---

### Task 3: Review Event Stream And Check-Run Edge Cases

**Files:**
- Modify: `.hermes-loop/hermes_hardening.py`
- Test: `tests/test_hermes_master_state.py`

- [ ] **Step 1: Write failing review/check tests**

Append these tests to `tests/test_hermes_master_state.py`:

```python
def test_github_evidence_rejects_superseded_approval():
    hardening = load_hardening()
    evidence = github_evidence()
    evidence["reviews"].append(
        {
            "id": 987654322,
            "user": "reviewer-login",
            "state": "CHANGES_REQUESTED",
            "commit_id": "abcdef123456",
            "submitted_at": "2026-05-24T00:10:00Z",
        }
    )

    result = hardening.validate_github_pr_evidence(
        github_config(),
        github_feature(),
        evidence,
        github_local_refs(),
    )

    assert result["valid"] is False
    assert "required review id is not latest for reviewer: 987654321" in result["errors"]


def test_github_evidence_rejects_review_on_old_head():
    hardening = load_hardening()
    evidence = github_evidence()
    evidence["reviews"][0]["commit_id"] = "oldhead123"

    result = hardening.validate_github_pr_evidence(
        github_config(),
        github_feature(),
        evidence,
        github_local_refs(),
    )

    assert result["valid"] is False
    assert "required review id is not bound to PR head SHA: 987654321" in result["errors"]


def test_github_evidence_rejects_missing_failed_or_stale_check_run():
    hardening = load_hardening()
    evidence = github_evidence()
    evidence["check_runs"][0]["conclusion"] = "failure"
    evidence["check_runs"][0]["head_sha"] = "oldhead123"

    result = hardening.validate_github_pr_evidence(
        github_config(),
        github_feature(),
        evidence,
        github_local_refs(),
    )

    assert result["valid"] is False
    assert "required check run conclusion is not allowed: 123456789" in result["errors"]
    assert "required check run is not bound to PR head SHA: 123456789" in result["errors"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_github_evidence_rejects_superseded_approval tests/test_hermes_master_state.py::test_github_evidence_rejects_review_on_old_head tests/test_hermes_master_state.py::test_github_evidence_rejects_missing_failed_or_stale_check_run -q
```

Expected: fail if Task 2 validator missed event-stream or check-run details.

- [ ] **Step 3: Fix validator details**

If any test fails, update only the corresponding block in `validate_github_pr_evidence()`:

```python
    latest_by_user = _latest_non_comment_reviews_by_user(reviews)
    review_by_id = {review.get("id"): review for review in reviews if isinstance(review, dict)}
    required_review_ids = merge.get("required_review_ids", [])
    for review_id in required_review_ids:
        review = review_by_id.get(review_id)
        if not review:
            errors.append(f"required review id missing: {review_id}")
            continue
        user = str(review.get("user") or review.get("user_login") or "")
        latest = latest_by_user.get(user)
        if latest is not review:
            errors.append(f"required review id is not latest for reviewer: {review_id}")
        if str(review.get("state", "")).upper() != str(github.get("required_review_state")).upper():
            errors.append(f"required review id is not approved: {review_id}")
        if not _same_commit_ref(review.get("commit_id"), head_sha):
            errors.append(f"required review id is not bound to PR head SHA: {review_id}")
```

and:

```python
    checks_by_id = {run.get("id"): run for run in check_runs if isinstance(run, dict)}
    checks_by_name = {run.get("name"): run for run in check_runs if isinstance(run, dict)}
    for required in merge.get("required_check_runs", []):
        run = checks_by_id.get(required.get("id")) or checks_by_name.get(required.get("name"))
        label = required.get("id") or required.get("name")
        if not run:
            errors.append(f"required check run missing: {label}")
            continue
        if run.get("status") != "completed":
            errors.append(f"required check run not completed: {label}")
        if run.get("conclusion") not in github.get("required_check_conclusions", []):
            errors.append(f"required check run conclusion is not allowed: {label}")
        if not _same_commit_ref(run.get("head_sha"), head_sha):
            errors.append(f"required check run is not bound to PR head SHA: {label}")
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_github_evidence_rejects_superseded_approval tests/test_hermes_master_state.py::test_github_evidence_rejects_review_on_old_head tests/test_hermes_master_state.py::test_github_evidence_rejects_missing_failed_or_stale_check_run -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add .hermes-loop/hermes_hardening.py tests/test_hermes_master_state.py
git commit -m "test: cover github review and check evidence gates"
```

---

### Task 4: Approval Digest Binding For GitHub Evidence

**Files:**
- Modify: `.hermes-loop/hermes_hardening.py`
- Test: `tests/test_hermes_master_state.py`

- [ ] **Step 1: Write failing approval binding tests**

Append these tests to `tests/test_hermes_master_state.py`:

```python
def valid_github_approval_bundle(loop: Path) -> dict:
    bundle = valid_approval_bundle(loop)
    feature_id = "v1-quarantine"
    evidence = github_evidence()
    evidence_path = loop / "master" / "features" / feature_id / "github_evidence.json"
    write_json(evidence_path, evidence)
    evidence_digest = load_hardening().file_json_digest(evidence_path)

    approval_path = loop / "approvals" / feature_id / "merge_approval.json"
    approval = json.loads(approval_path.read_text())
    approval["verification"] = {
        "method": "github_review",
        "status": "verified",
        "ref": f".hermes-loop/master/features/{feature_id}/github_evidence.json",
        "digest": evidence_digest,
    }
    write_json(approval_path, approval)
    return {**bundle, "github_evidence": evidence, "github_evidence_digest": evidence_digest}


def test_github_approval_schema_accepts_bound_evidence_digest(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    bundle = valid_github_approval_bundle(loop)

    result = hardening.validate_merge_approval(
        loop,
        ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["schema_valid"] is True
    assert result["errors"] == []
    assert result["provenance_scope"] == "schema_level_only"


def test_github_approval_rejects_changed_evidence_after_approval(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    bundle = valid_github_approval_bundle(loop)
    evidence_path = loop / "master" / "features" / "v1-quarantine" / "github_evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["pull_request"]["head_sha"] = "changedhead"
    write_json(evidence_path, evidence)

    result = hardening.validate_merge_approval(
        loop,
        ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["schema_valid"] is False
    assert "approval verification digest does not match current ref" in result["errors"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_github_approval_schema_accepts_bound_evidence_digest tests/test_hermes_master_state.py::test_github_approval_rejects_changed_evidence_after_approval -q
```

Expected: second test fails because `validate_merge_approval()` currently checks presence of `ref` and `digest`, but not current digest content.

- [ ] **Step 3: Implement digest check**

In `.hermes-loop/hermes_hardening.py`, add this helper near `file_json_digest()`:

```python
def file_digest_for_ref(loop: Path, ref: str) -> str:
    path = _controller_path(loop, ref)
    return file_json_digest(path)
```

In `validate_merge_approval()`, after the existing `verification.ref` and `verification.digest` required checks, add:

```python
    if isinstance(verification, dict) and verification.get("ref") and verification.get("digest"):
        try:
            verification_digest = file_digest_for_ref(loop, verification["ref"])
        except Exception:
            verification_digest = None
            errors.append("approval verification ref cannot be read")
        if verification_digest != verification.get("digest"):
            errors.append("approval verification digest does not match current ref")

        if method in {"github_review", "github_check"}:
            if not str(verification["ref"]).startswith(".hermes-loop/master/features/"):
                errors.append("github approval verification ref must be Master-owned")
```

Keep the final return unchanged:

```python
    schema_valid = not errors
    return {
        "schema_valid": schema_valid,
        "valid": False,
        "errors": errors,
        "provenance_scope": "schema_level_only",
        "provenance_verified": False,
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_github_approval_schema_accepts_bound_evidence_digest tests/test_hermes_master_state.py::test_github_approval_rejects_changed_evidence_after_approval -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add .hermes-loop/hermes_hardening.py tests/test_hermes_master_state.py
git commit -m "fix: bind github approval evidence digest"
```

---

### Task 5: Merge Queue Gate Requires GitHub Evidence When Policy Requires It

**Files:**
- Modify: `.hermes-loop/hermes_hardening.py`
- Test: `tests/test_hermes_master_state.py`

- [ ] **Step 1: Write failing merge queue tests**

Append these tests to `tests/test_hermes_master_state.py`:

```python
def test_merge_queue_gate_blocks_missing_required_github_evidence(tmp_path, monkeypatch):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    state = feature_for_gate()
    feature = state["features"][0]
    feature["policy_flags"]["requires_github_evidence"] = True
    feature["branch"] = "feat/v1-quarantine"
    feature["target_branch"] = "main"
    feature["merge"]["target_branch"] = "main"
    write_gate_artifacts(loop)
    monkeypatch.setattr(hardening, "_current_target_head", lambda _loop, _branch: "123456abcdef")

    result = hardening.validate_merge_queue_gate(loop, feature)

    assert result["valid"] is False
    assert "missing required github_evidence artifact" in result["errors"]


def test_merge_queue_gate_accepts_required_github_evidence(tmp_path, monkeypatch):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    state = feature_for_gate()
    feature = state["features"][0]
    feature.update(github_feature())
    feature["policy_flags"]["requires_github_evidence"] = True
    feature["artifacts"]["github_evidence"] = ".hermes-loop/master/features/v1-quarantine/github_evidence.json"
    write_gate_artifacts(loop)
    write_json(loop / "master" / "features" / "v1-quarantine" / "github_evidence.json", github_evidence())
    monkeypatch.setattr(hardening, "_current_target_head", lambda _loop, _branch: "123456abcdef")

    result = hardening.validate_merge_queue_gate(loop, feature)

    assert result["valid"] is True
    assert result["errors"] == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_merge_queue_gate_blocks_missing_required_github_evidence tests/test_hermes_master_state.py::test_merge_queue_gate_accepts_required_github_evidence -q
```

Expected: first test fails because no GitHub evidence gate exists.

- [ ] **Step 3: Implement merge queue wiring**

In `.hermes-loop/hermes_hardening.py`, add this helper near `validate_merge_queue_gate()`:

```python
def _load_master_config(loop: Path) -> dict[str, Any]:
    path = loop / "master_config.json"
    if not path.exists():
        return default_master_config()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return default_master_config()
    config = default_master_config()
    config.update(payload)
    if isinstance(payload.get("github"), dict):
        config["github"] = {**default_master_config()["github"], **payload["github"]}
    return config


def _github_evidence_gate(
    loop: Path,
    feature: dict[str, Any],
    integrated_tests: dict[str, Any] | None,
) -> list[str]:
    policy = feature.get("policy_flags", {}) if isinstance(feature.get("policy_flags"), dict) else {}
    if not policy.get("requires_github_evidence"):
        return []
    artifacts = feature.get("artifacts", {}) if isinstance(feature.get("artifacts"), dict) else {}
    evidence_ref = artifacts.get("github_evidence")
    if not evidence_ref:
        return ["missing required github_evidence artifact"]
    evidence = _load_required_json(loop, evidence_ref, [], "github_evidence")
    if not evidence:
        return [f"missing github_evidence: {evidence_ref}"]
    target_head = _current_target_head(loop, feature.get("target_branch"))
    local_refs = {
        "feature_head": feature.get("merge", {}).get("github_pr", {}).get("head_sha"),
        "target_head": target_head,
        "integrated_tests_base_commit": integrated_tests.get("base_commit") if integrated_tests else None,
    }
    result = validate_github_pr_evidence(_load_master_config(loop), feature, evidence, local_refs)
    return result["errors"]
```

In `validate_merge_queue_gate()`, after the existing `if master_review and integrated_tests:` block, add:

```python
    github_errors = _github_evidence_gate(loop, feature, integrated_tests)
    errors.extend(github_errors)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_merge_queue_gate_blocks_missing_required_github_evidence tests/test_hermes_master_state.py::test_merge_queue_gate_accepts_required_github_evidence -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add .hermes-loop/hermes_hardening.py tests/test_hermes_master_state.py
git commit -m "feat: gate merges on required github evidence"
```

---

### Task 6: Read-Only Fetch Adapter

**Files:**
- Modify: `.hermes-loop/hermes_hardening.py`
- Test: `tests/test_hermes_master_state.py`

- [ ] **Step 1: Write failing fetch normalization tests**

Append these tests to `tests/test_hermes_master_state.py`:

```python
def test_normalize_github_api_payloads_to_evidence():
    hardening = load_hardening()
    pr = {
        "number": 123,
        "html_url": "https://github.com/owner/repo/pull/123",
        "state": "open",
        "draft": False,
        "merged": False,
        "closed_at": None,
        "merged_at": None,
        "head": {"ref": "feat/v1-quarantine", "sha": "abcdef123456"},
        "base": {"ref": "main", "sha": "123456abcdef"},
    }
    reviews = [
        {
            "id": 987654321,
            "user": {"login": "reviewer-login"},
            "state": "APPROVED",
            "commit_id": "abcdef123456",
            "submitted_at": "2026-05-24T00:00:00Z",
        }
    ]
    checks = {
        "check_runs": [
            {
                "id": 123456789,
                "name": "pytest",
                "status": "completed",
                "conclusion": "success",
                "head_sha": "abcdef123456",
                "completed_at": "2026-05-24T00:00:00Z",
            }
        ]
    }

    evidence = hardening.normalize_github_api_payloads(
        repo="owner/repo",
        feature_id="v1-quarantine",
        pr=pr,
        reviews=reviews,
        checks=checks,
        fetched_at="2026-05-24T00:00:00Z",
    )

    assert evidence["recorded_by"] == "master-god"
    assert evidence["pull_request"]["head_sha"] == "abcdef123456"
    assert evidence["reviews"][0]["user"] == "reviewer-login"
    assert evidence["check_runs"][0]["conclusion"] == "success"


def test_write_github_evidence_writes_master_owned_artifact(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    evidence = github_evidence()

    result = hardening.write_github_evidence(loop, "v1-quarantine", evidence)

    path = loop / "master" / "features" / "v1-quarantine" / "github_evidence.json"
    assert path.exists()
    assert result["ref"] == ".hermes-loop/master/features/v1-quarantine/github_evidence.json"
    assert result["digest"] == hardening.file_json_digest(path)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_normalize_github_api_payloads_to_evidence tests/test_hermes_master_state.py::test_write_github_evidence_writes_master_owned_artifact -q
```

Expected: fail because normalization and write helpers do not exist.

- [ ] **Step 3: Implement normalization and writer**

In `.hermes-loop/hermes_hardening.py`, add:

```python
def normalize_github_api_payloads(
    *,
    repo: str,
    feature_id: str,
    pr: dict[str, Any],
    reviews: list[dict[str, Any]],
    checks: dict[str, Any],
    fetched_at: str,
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "feature_id": feature_id,
        "recorded_by": "master-god",
        "fetched_at": fetched_at,
        "repo": repo,
        "pull_request": {
            "number": pr.get("number"),
            "url": pr.get("html_url"),
            "state": pr.get("state"),
            "draft": pr.get("draft", False),
            "merged": pr.get("merged", False),
            "closed_at": pr.get("closed_at"),
            "merged_at": pr.get("merged_at"),
            "head_ref": pr.get("head", {}).get("ref"),
            "base_ref": pr.get("base", {}).get("ref"),
            "head_sha": pr.get("head", {}).get("sha"),
            "base_sha": pr.get("base", {}).get("sha"),
        },
        "reviews": [
            {
                "id": review.get("id"),
                "user": review.get("user", {}).get("login") if isinstance(review.get("user"), dict) else review.get("user"),
                "state": review.get("state"),
                "commit_id": review.get("commit_id"),
                "submitted_at": review.get("submitted_at"),
            }
            for review in reviews
        ],
        "check_runs": [
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "head_sha": run.get("head_sha"),
                "completed_at": run.get("completed_at"),
            }
            for run in checks.get("check_runs", [])
        ],
    }


def write_github_evidence(
    loop_root: str | Path,
    feature_id: str,
    evidence: dict[str, Any],
) -> dict[str, str]:
    loop = Path(loop_root)
    ref = f".hermes-loop/master/features/{feature_id}/github_evidence.json"
    path = _controller_path(loop, ref)
    _write_json(path, evidence)
    return {"ref": ref, "digest": file_json_digest(path)}
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_hermes_master_state.py::test_normalize_github_api_payloads_to_evidence tests/test_hermes_master_state.py::test_write_github_evidence_writes_master_owned_artifact -q
```

Expected: `2 passed`.

- [ ] **Step 5: Add read-only fetch shell/API helpers**

In `.hermes-loop/hermes_hardening.py`, add:

```python
def _run_gh_json(args: list[str], *, timeout: int) -> Any:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gh command failed")
    return json.loads(result.stdout)


def fetch_github_pr_evidence(
    config: dict[str, Any],
    feature: dict[str, Any],
    *,
    now: str,
) -> dict[str, Any]:
    github = _github_config(config)
    merge = feature.get("merge", {}) if isinstance(feature.get("merge"), dict) else {}
    pr_number = merge.get("github_pr", {}).get("number")
    if not pr_number:
        raise ValueError("feature merge.github_pr.number is required")
    if not github.get("enabled"):
        raise ValueError("github evidence fetch requires github.enabled=true")
    repo = github.get("repo")
    timeout = int(github.get("request_timeout_seconds", 20))
    pr = _run_gh_json(
        [
            "api",
            f"repos/{repo}/pulls/{pr_number}",
        ],
        timeout=timeout,
    )
    reviews = _run_gh_json(
        [
            "api",
            f"repos/{repo}/pulls/{pr_number}/reviews",
        ],
        timeout=timeout,
    )
    checks = _run_gh_json(
        [
            "api",
            f"repos/{repo}/commits/{pr['head']['sha']}/check-runs",
        ],
        timeout=timeout,
    )
    return normalize_github_api_payloads(
        repo=repo,
        feature_id=feature["id"],
        pr=pr,
        reviews=reviews,
        checks=checks,
        fetched_at=now,
    )
```

This helper uses only `gh api` read calls. It does not push, approve, create PRs, or merge.

- [ ] **Step 6: Commit**

```bash
git add .hermes-loop/hermes_hardening.py tests/test_hermes_master_state.py
git commit -m "feat: add readonly github evidence fetch helpers"
```

---

### Task 7: Legacy Summary Compatibility

**Files:**
- Modify: `.hermes-loop/hermes_hardening.py`
- Test: `tests/test_hermes_hardening.py`

- [ ] **Step 1: Write compatibility tests**

Append these tests to `tests/test_hermes_hardening.py`:

```python
def test_master_slave_summary_ignores_optional_github_evidence_when_disabled(tmp_path: Path) -> None:
    hardening = load_hardening_module()
    loop = tmp_path / ".hermes-loop"
    feature_dir = loop / "work" / "features" / "archive-rag"
    worktree = tmp_path / "memoryOS-archive-rag"
    feature_dir.mkdir(parents=True)
    worktree.mkdir()
    write_json(feature_dir / "ack.json", {"ack_level": "usable"})
    write_json(feature_dir / "review_verdict.json", {"verdict": "PASS"})
    write_json(feature_dir / "integrated_tests.json", {"status": "passed", "commands": ["uv run pytest -q"]})
    (feature_dir / "result.md").write_text("# feature: archive-rag\n", encoding="utf-8")
    write_json(loop / "master_config.json", hardening.default_master_config())
    write_json(
        loop / "feature_lanes.json",
        {
            "features": [
                {
                    "id": "archive-rag",
                    "state": "ready_for_merge",
                    "branch": "feat/archive-rag",
                    "worktree": str(worktree),
                    "artifacts": {
                        "ack": "work/features/archive-rag/ack.json",
                        "review_verdict": "work/features/archive-rag/review_verdict.json",
                        "result": "work/features/archive-rag/result.md",
                        "integrated_tests": "work/features/archive-rag/integrated_tests.json",
                    },
                    "merge": {
                        "status": "ready_for_merge",
                        "target_branch": "main",
                        "strategy": "git_worktree",
                    },
                    "policy_flags": {
                        "allows_github_evidence": True,
                        "requires_github_evidence": False,
                    },
                }
            ]
        },
    )

    summary = hardening.summarize_master_slave_control(loop, project_root=tmp_path)

    assert summary["ok"] is True
    assert summary["counts"]["mergeable"] == 1
    assert summary["blockers"] == []
```

- [ ] **Step 2: Run test**

Run:

```bash
uv run pytest tests/test_hermes_hardening.py::test_master_slave_summary_ignores_optional_github_evidence_when_disabled -q
```

Expected: pass after Tasks 1-6. If it fails, fix only the legacy summary path so optional GitHub evidence remains non-blocking.

- [ ] **Step 3: Commit if code changed**

If Step 2 required a code change:

```bash
git add .hermes-loop/hermes_hardening.py tests/test_hermes_hardening.py
git commit -m "fix: keep optional github evidence non-blocking"
```

If only the test was added and passed:

```bash
git add tests/test_hermes_hardening.py
git commit -m "test: cover optional github evidence compatibility"
```

---

### Task 8: Full Verification And Status Refresh

**Files:**
- Modify only if a verification failure points to this feature:
  - `.hermes-loop/hermes_hardening.py`
  - `.hermes-loop/hermes_reporter.py`
  - `tests/test_hermes_master_state.py`
  - `tests/test_hermes_hardening.py`

- [ ] **Step 1: Run focused Hermes test suite**

Run:

```bash
uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run lint**

Run:

```bash
uv run ruff check .hermes-loop/hermes_hardening.py .hermes-loop/hermes_reporter.py tests/test_hermes_*.py
```

Expected: no ruff errors.

- [ ] **Step 3: Run syntax checks**

Run:

```bash
python3 -m py_compile .hermes-loop/hermes_hardening.py .hermes-loop/hermes_reporter.py && bash -n .hermes-loop/god_launcher.sh
```

Expected: command exits 0.

- [ ] **Step 4: Run status generation without committing runtime artifacts**

Run:

```bash
python3 .hermes-loop/hermes_reporter.py
git status --porcelain
```

Expected:

- Reporter exits 0.
- `git status --porcelain` may show active runtime files from parallel agents.
- Do not commit `.hermes-loop/master_state.json`, `.hermes-loop/master_status.json`, feature work artifacts, or consensus files unless they are intentionally part of this feature.

- [ ] **Step 5: Commit verification-only fixes**

If Step 1-3 required fixes:

```bash
git add .hermes-loop/hermes_hardening.py .hermes-loop/hermes_reporter.py tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py
git commit -m "fix: stabilize github evidence gates"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- GitHub disabled by default: Task 1 and Task 7.
- PR head/base/branch binding: Task 2.
- PR lifecycle gate: Task 2.
- Review event-stream semantics: Task 3.
- Check-run validation: Task 3.
- GitHub evidence remains approval verification, not approval replacement: Task 4.
- Existing `verification.method/ref/digest` contract preserved: Task 4.
- Required GitHub evidence can block merge readiness: Task 5.
- Optional GitHub evidence does not block local-only flows: Task 7.
- Read-only fetch adapter exists and does not push/approve/merge: Task 6.
- Local integrated tests remain separate: Tasks 4, 5, and 8.

Red-flag scan:

- The plan uses concrete file paths, functions, commands, and expected results.
- The plan does not defer schema, validator, or test details to a future worker.
- No undefined helper is used before a task defines it, except existing helpers already present in the repo: `load_hardening()`, `write_json()`, `feature_for_gate()`, `write_gate_artifacts()`, `valid_approval_bundle()`, and `load_hardening_module()`.

Type consistency:

- GitHub evidence validator signature is consistently `validate_github_pr_evidence(config, feature, evidence, local_refs)`.
- GitHub evidence writer signature is consistently `write_github_evidence(loop_root, feature_id, evidence)`.
- Approval binding uses existing `verification.method`, `verification.status`, `verification.ref`, and `verification.digest`.
- `github_review` and `github_check` remain existing provenance methods from `PROVENANCE_METHODS`.
