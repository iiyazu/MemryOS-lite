# Hermes GitHub Read-Only Evidence Design

Date: 2026-05-24

## Summary

Hermes multi-god should keep the current local git/worktree execution model and
add GitHub as a read-only evidence source for Master merge gates. Slave Gods may
continue to work in local branches/worktrees. Master God may verify GitHub PR
metadata, reviews, and check runs, but must not push, create PRs, approve PRs,
or merge through GitHub in this MVP.

This design strengthens provenance for external approval and CI evidence
without making GitHub a required runtime dependency for local development.

## Goals

- Allow Master God to verify GitHub PR, review, and check-run evidence through
  read-only API access.
- Bind GitHub evidence to concrete PR head SHA, base SHA, target branch, and
  feature branch.
- Preserve local integrated tests as a separate Master-owned gate.
- Prevent self-signed local JSON from being treated as external approval.
- Keep local git/worktree collaboration usable when GitHub is disabled.
- Keep MemoryOS constraints intact: v3 default, v1 fallback, opt-in kernel, no
  benchmark score targets, no same-slice repair promotion claims.

## Non-Goals

- Do not push branches from Master.
- Do not open PRs from Master.
- Do not merge PRs automatically.
- Do not replace local integrated tests with GitHub CI.
- Do not require GitHub for all local smoke or feature development.
- Do not treat GitHub checks as benchmark-quality memory improvement evidence.

## Current Context

The active Hermes control plane is Master-based:

- active source: `.hermes-loop/master_state.json`;
- Master prompt: `.hermes-loop/prompts/master_god_prompt.md`;
- Slave prompt: `.hermes-loop/prompts/slave_god_prompt.md`;
- Master contract: `.hermes-loop/contracts/master_dispatch_template.json`;
- Slave contract: `.hermes-loop/contracts/slave_dispatch_template.json`;
- current feature lanes: `v1-quarantine` and `archive-rag`.

Current Master state already has `github.enabled = false` and feature merge
entries have `github_pr = null`. Master gates already require external merge
approval and fresh target evidence, but external provenance is still represented
mostly by local artifacts.

## Architecture

GitHub read-only evidence sits beside local git/worktree evidence.

```text
Slave worktree / branch
  -> local result, ACK, review verdict
  -> optional GitHub PR created outside Master

Master God
  -> reads local feature artifacts
  -> runs local integrated tests
  -> fetches GitHub PR/review/check metadata read-only
  -> records normalized evidence
  -> gates merge readiness
```

Master remains the only active controller. GitHub is an evidence provider, not
an executor.

## Configuration

Extend `.hermes-loop/master_config.json` with a `github` object:

```json
{
  "version": "1.0",
  "allowed_target_branches": ["main"],
  "merge_strategy": "no_ff_merge_commit",
  "github": {
    "enabled": false,
    "repo": "owner/repo",
    "remote": "origin",
    "allowed_target_branches": [
      "main",
      "feat/phase-2.5-3-retrieval-agent"
    ],
    "token_env": "GITHUB_TOKEN",
    "required_review_state": "APPROVED",
    "required_check_conclusions": ["success"],
    "request_timeout_seconds": 20
  }
}
```

When `github.enabled` is false, Master must keep the current local-only gate
behavior. When true, Master may require GitHub evidence for features whose
policy flags allow or require it.

`master_config.allowed_target_branches` remains the local merge target allowlist.
`master_config.github.allowed_target_branches` is the GitHub PR base allowlist.
During the current rollout it must include the active Hermes target branch
`feat/phase-2.5-3-retrieval-agent`; otherwise GitHub evidence for current lanes
must be rejected as branch-policy mismatched. A future production rollout may
shrink both allowlists back to protected branches such as `main`.

## Feature Lane Schema

Extend each feature merge entry with optional GitHub evidence references:

```json
{
  "id": "archive-rag",
  "branch": "feat/archive-rag",
  "target_branch": "feat/phase-2.5-3-retrieval-agent",
  "merge": {
    "status": "ready_for_merge",
    "target_branch": "feat/phase-2.5-3-retrieval-agent",
    "strategy": "no_ff_merge_commit",
    "github_pr": {
      "number": 123,
      "url": "https://github.com/owner/repo/pull/123",
      "head_ref": "feat/archive-rag",
      "base_ref": "feat/phase-2.5-3-retrieval-agent",
      "head_sha": "feature-head-sha",
      "base_sha": "target-base-sha"
    },
    "required_review_ids": [987654321],
    "required_check_runs": [
      {
        "name": "pytest",
        "id": 123456789,
        "head_sha": "feature-head-sha"
      }
    ]
  },
  "policy_flags": {
    "allows_github_evidence": true,
    "requires_github_evidence": false,
    "requires_explicit_merge_approval": true,
    "requires_integrated_tests": true
  }
}
```

`requires_github_evidence` may be enabled per feature in a separate rollout
after optional validation is stable. The MVP should support validation without
forcing every feature to use GitHub immediately.

## Evidence Artifacts

Master writes normalized GitHub evidence under:

```text
.hermes-loop/master/features/<feature-id>/github_evidence.json
```

Minimum schema:

```json
{
  "version": "1.0",
  "feature_id": "archive-rag",
  "recorded_by": "master-god",
  "fetched_at": "2026-05-24T00:00:00Z",
  "repo": "owner/repo",
  "pull_request": {
    "number": 123,
    "url": "https://github.com/owner/repo/pull/123",
    "state": "open",
    "head_ref": "feat/archive-rag",
    "base_ref": "feat/phase-2.5-3-retrieval-agent",
    "head_sha": "feature-head-sha",
    "base_sha": "target-base-sha"
  },
  "reviews": [
    {
      "id": 987654321,
      "user": "reviewer-login",
      "state": "APPROVED",
      "commit_id": "feature-head-sha",
      "submitted_at": "2026-05-24T00:00:00Z",
      "is_latest_for_reviewer": true
    }
  ],
  "check_runs": [
    {
      "id": 123456789,
      "name": "pytest",
      "status": "completed",
      "conclusion": "success",
      "head_sha": "feature-head-sha",
      "completed_at": "2026-05-24T00:00:00Z"
    }
  ],
  "validation": {
    "schema_valid": true,
    "valid": true,
    "errors": []
  }
}
```

This artifact is Master-owned. Slave Gods must not write it.

## Gate Semantics

GitHub evidence may satisfy external approval provenance only when all of these
conditions hold:

- PR repo matches `master_config.github.repo`.
- PR head ref matches the feature branch.
- PR base ref matches the target branch.
- PR base ref is in `master_config.github.allowed_target_branches`.
- PR head SHA matches the local feature branch HEAD or the declared feature
  head commit.
- PR base SHA matches the Master integrated-test `base_commit`.
- PR base SHA matches the current local target branch HEAD. If it does not,
  Master must hold the feature and refresh integrated tests before merge.
- Review validity is computed from the GitHub review event stream, not by
  selecting any single approved review in isolation.
- Every required review id must exist, have state `APPROVED`, match PR head
  SHA, and remain the latest non-comment review for that reviewer on that head.
- If any later review by the same reviewer on the same head is
  `CHANGES_REQUESTED` or another non-approval state, that reviewer no longer
  contributes approval.
- If project policy requires N approvals, the N approvals must be valid after
  applying latest-review-per-reviewer semantics.
- Required check runs are completed with allowed conclusions.
- Check run head SHA matches PR head SHA.
- Evidence was fetched by Master after the PR reached that head SHA.

GitHub evidence may prove that an external reviewer or CI system exists and
approved the current PR head. It does not by itself prove that the reviewer
authorized the exact Hermes merge request digest. Exact request authorization
remains the job of `merge_approval.json`.

Review selection is explicit. `required_review_ids` are fixed by the feature
merge entry or by `merge_approval_request.json`; Master must not silently pick
any convenient approval from the PR event stream. If `required_review_ids` is
empty and project policy requires approvals, Master may compute candidate
approvals from latest-review-per-reviewer state, but it must write the selected
review ids into the approval request before external approval is granted.

GitHub evidence does not replace:

- local Slave ACK;
- local Slave PASS review;
- Master review;
- `.hermes-loop/approvals/<feature-id>/merge_approval_request.json`;
- `.hermes-loop/approvals/<feature-id>/merge_approval.json`;
- merge approval request digest validation;
- `master_review_digest`, `integrated_tests_digest`, and policy snapshot digest
  checks in the approval contract;
- local integrated tests;
- fresh target-head gate;
- post-merge verification.

## Approval Artifact Binding

GitHub read-only evidence is verification evidence for the existing Hermes
approval artifact. It must not directly replace `merge_approval.json`.

The approved shape is:

```text
merge_approval_request.json
  -> binds feature id, target branch, head/base commits, master review digest,
     integrated tests digest, and policy snapshot digest

github_evidence.json
  -> proves GitHub PR/review/check provenance for the same feature head and
     target base

merge_approval.json
  -> references both the request digest and github_evidence digest
```

`merge_approval.json` must include a verification reference like:

```json
{
  "verification": {
    "method": "github_readonly_evidence",
    "github_evidence_ref": ".hermes-loop/master/features/archive-rag/github_evidence.json",
    "github_evidence_digest": "sha256:evidence-digest",
    "request_digest": "sha256:request-digest"
  }
}
```

Master must validate that the current file digest of `github_evidence_ref`
matches `github_evidence_digest`, and that the current request digest matches
`request_digest`. If any referenced artifact has changed since approval, the
feature returns to hold.

## API Boundary

Create a small read-only GitHub evidence adapter. The implementation can use
one of two providers:

- `gh` CLI if available and authenticated;
- direct GitHub REST API using `token_env`.

The adapter returns normalized Python dictionaries. Gate validation must be
separate from fetching, so tests can validate evidence without network access.

Recommended internal functions:

```text
fetch_github_pr_evidence(config, feature) -> dict
validate_github_pr_evidence(config, feature, evidence, local_refs) -> dict
write_github_evidence(loop_root, feature_id, evidence) -> dict
```

Implementation tests should use local JSON fixtures and monkeypatch fetching.
No test should require live GitHub network access.

## Error Handling

- Missing token when GitHub evidence is required: block the feature with a clear
  error.
- Missing token when GitHub evidence is optional: keep local-only behavior and
  report a warning.
- API timeout: block only if GitHub evidence is required.
- PR head SHA mismatch: block.
- Review not bound to current head SHA: block.
- Required review id missing, stale, or superseded by a later non-approval
  review from the same reviewer: block.
- Check run incomplete or failed: block.
- PR base SHA does not match integrated-test base commit or current target HEAD:
  hold and refresh integrated tests.

## Security And Authority

The GitHub token must be read-only for this MVP. The system should not require
write or admin scopes. Master must never use this feature to push, approve,
or merge.

GitHub review evidence is treated as external provenance only if fetched from
GitHub, not if copied by a Slave into local JSON. Local approval JSON may
reference GitHub evidence, but cannot replace it.

## Testing Strategy

Tests should cover:

- config parsing with GitHub disabled;
- config parsing with GitHub enabled;
- valid PR evidence;
- PR head SHA mismatch;
- PR base SHA mismatch against integrated-test base commit;
- review approval tied to an old commit;
- approved review superseded by later changes-requested review;
- required review id missing from the fetched review stream;
- missing or failed check run;
- optional GitHub evidence not blocking local-only features;
- required GitHub evidence blocking when unavailable;
- Master queue integration with local gates still enforced.

Existing Hermes control-plane verification should continue to pass:

```bash
uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py -q
uv run ruff check .hermes-loop/hermes_hardening.py .hermes-loop/hermes_reporter.py tests/test_hermes_*.py
python3 -m py_compile .hermes-loop/hermes_hardening.py .hermes-loop/hermes_reporter.py && bash -n .hermes-loop/god_launcher.sh
```

## Rollout Plan

1. Add schema and validation helpers with tests.
2. Add read-only fetch adapter behind a disabled-by-default config.
3. Add `github_evidence.json` as an optional Master-owned artifact.
4. Connect `requires_github_evidence` to merge gate validation.
5. Keep all existing local-only features working.
6. Later, add GitHub PR automation only as a separate design.

## Acceptance Criteria

- Local-only multi-god flow still works with `github.enabled = false`.
- With GitHub evidence enabled and supplied through fixtures, Master can
  validate PR review/check provenance.
- Stale PR, stale review, failed check, and SHA mismatch all block merge
  readiness.
- No code path pushes, approves, or merges through GitHub.
- The design preserves current MemoryOS constraints and does not make benchmark
  claims.

## Self-Review Notes

- No implementation requires live GitHub in tests.
- GitHub is read-only and evidence-only.
- Local integrated tests remain required.
- External approval cannot be self-signed by Master or Slave.
- Scope is one implementation plan, not a full GitHub automation system.
