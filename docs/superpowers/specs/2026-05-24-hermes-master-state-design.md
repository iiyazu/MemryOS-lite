# Hermes Master State Design

> Status: approved design for planning. This document does not implement the
> migration.

## Goal

Replace the current root-state-plus-feature-overlay Hermes control plane with a
single active Master controller state while isolating the old root-loop
architecture as legacy history.

## Context

Current Hermes is a single root state machine with a parallel feature-lane
overlay:

- `.hermes-loop/state.json` is the current root phase state. It is now `DONE`
  after phase 0-18.
- `.hermes-loop/feature_lanes.json` records parallel feature lanes.
- `.hermes-loop/master_slave_status.{json,md}` is derived status.
- `v1-quarantine` is ready for Master review, not ready to merge.
- `archive-rag` is planned.

This has worked as a transition layer, but it keeps root-loop and Master
integration responsibilities split across files. The next architecture should
merge root and Master into one active controller.

## Non-Goals

- Do not change MemoryOS product memory behavior.
- Do not remove the v1 fallback.
- Do not enable the kernel by default.
- Do not claim benchmark improvement or promotion.
- Do not let same-slice repair smoke count as promotion evidence.
- Do not make GitHub mandatory.

## Chosen Approach

Use a new active Master control file:

- `.hermes-loop/master_state.json`

The old root-loop files are moved behind a legacy boundary:

- `.hermes-loop/legacy/root-loop/state.json`
- `.hermes-loop/legacy/root-loop/feature_lanes.json`
- `.hermes-loop/legacy/root-loop/master_slave_status.json`
- `.hermes-loop/legacy/root-loop/master_slave_status.md`
- `.hermes-loop/legacy/root-loop/config.json`
- `.hermes-loop/legacy/root-loop/contracts/god_dispatch_template.json`
- `.hermes-loop/legacy/root-loop/blueprint.md`
- `.hermes-loop/legacy/root-loop/blueprint.zh.md`
- `.hermes-loop/legacy/root-loop/god_loop_prompt.md`

The active control plane is:

- `.hermes-loop/master_blueprint.md`
- `.hermes-loop/master_state.json`
- `.hermes-loop/master_config.json`
- `.hermes-loop/master_status.json`
- `.hermes-loop/master_status.md`
- `.hermes-loop/prompts/master_god_prompt.md`
- `.hermes-loop/prompts/slave_god_prompt.md`
- `.hermes-loop/contracts/master_dispatch_template.json`
- `.hermes-loop/contracts/slave_dispatch_template.json`
- `.hermes-loop/master/features/<feature-id>/...`
- `.hermes-loop/approvals/<feature-id>/...`
- `.hermes-loop/work/features/<feature-id>/...`

Legacy root-loop files remain auditable but no longer drive new control flow.
Old phase-loop blueprints, prompts, config, and dispatch templates must not be
treated as active controller metadata after migration.

## Master State Shape

`master_state.json` should contain:

```json
{
  "version": "1.0",
  "mode": "master_control",
  "activation_state": "master_active",
  "active": true,
  "history_baseline": ".hermes-loop/history/main_loop_phase0_18.json",
  "legacy_root_loop": ".hermes-loop/legacy/root-loop/",
  "master_blueprint": ".hermes-loop/master_blueprint.md",
  "master_config": ".hermes-loop/master_config.json",
  "prompts": {
    "master": ".hermes-loop/prompts/master_god_prompt.md",
    "slave": ".hermes-loop/prompts/slave_god_prompt.md"
  },
  "dispatch_contracts": {
    "master": ".hermes-loop/contracts/master_dispatch_template.json",
    "slave": ".hermes-loop/contracts/slave_dispatch_template.json"
  },
  "master_policy": {},
  "features": [
    {
      "id": "feature-id",
      "name": "Feature Name",
      "state": "ready_for_master_review",
      "branch": "feature/feature-id",
      "target_branch": "main",
      "worktree": "../memoryOS-feature-id",
      "slave_state_path": ".hermes-loop/work/features/feature-id/slave_state.json",
      "slave_god": {
        "owner": "slave-god-feature-id",
        "mode": "feature_local_single_god",
        "last_reported_at": ""
      },
      "blueprint_path": ".hermes-loop/work/features/feature-id/blueprint.md",
      "artifacts": {
        "result": ".hermes-loop/work/features/feature-id/result.md",
        "ack": ".hermes-loop/work/features/feature-id/ack.json",
        "review_verdict": ".hermes-loop/work/features/feature-id/review_verdict.json",
        "integrated_tests": ".hermes-loop/master/features/feature-id/integrated_tests.json",
        "master_review": ".hermes-loop/master/features/feature-id/master_review.json",
        "merge_approval_request": ".hermes-loop/approvals/feature-id/merge_approval_request.json",
        "merge_approval": ".hermes-loop/approvals/feature-id/merge_approval.json",
        "post_merge_verification": ".hermes-loop/approvals/feature-id/post_merge_verification.json",
        "merge_decision": ".hermes-loop/approvals/feature-id/merge_decision.json"
      },
      "merge": {
        "status": "ready_for_master_review",
        "target_branch": "main",
        "strategy": "no_ff_merge_commit",
        "github_pr": null
      },
      "policy_flags": {
        "requires_integrated_tests": true,
        "requires_explicit_merge_approval": true,
        "allows_github_evidence": true
      },
      "risk": {
        "level": "medium",
        "notes": []
      }
    }
  ],
  "queues": {},
  "decisions": [],
  "integration": {},
  "github": {},
  "last_updated": ""
}
```

`activation_state` is the authoritative lifecycle field. Allowed values:

- `legacy_active`: legacy root-loop is still the active controller.
- `master_pending`: Master files are generated for prepare-phase validation, but
  legacy remains active.
- `master_active`: Master is the active controller.
- `blocked`: activation or active control is blocked.

`active` is a compatibility boolean derived from `activation_state`; it is true
only when `activation_state=master_active`. Implementations must not accept
`active=true` with any non-`master_active` lifecycle state.

`master_state.features[]` is the Master-owned registry. It must contain the
fields Master needs to make review, queue, and merge decisions: branch,
worktree, target branch, blueprint path, artifact paths, merge status, policy
flags, and risk notes. The registry may reference `slave_state.json`, but Master
decisions must not trust slave self-report alone. Master validates referenced
artifacts on disk and derives queue membership from Master-owned registry fields
plus artifact contents.

`slave_state.json` is feature-local. It records the Slave God's internal loop
state, local execution progress, and artifact declarations. It is required for
durability, but it is not an authority for Master queues, Master policy, or
merge state.

`master_state.decisions[]` is an append-only index of Master decision artifacts.
It may summarize decision type, feature id, state transition, artifact path, and
digest. It is not an independent decision source. The authoritative artifacts are
`master_review.json`, `integrated_tests.json`, `merge_approval_request.json`,
`merge_approval.json`, `post_merge_verification.json`, and
`merge_decision.json`; if the index disagrees with an artifact, the feature is
blocked until repaired.

### Master Blueprint And Prompts

`.hermes-loop/blueprint.md`, `.hermes-loop/blueprint.zh.md`, and
`.hermes-loop/god_loop_prompt.md` are legacy root-loop files after migration.
They should move to `.hermes-loop/legacy/root-loop/` with the rest of the
phase0-18 control plane.

Active Master architecture and operating rules live in
`.hermes-loop/master_blueprint.md`. It defines the Master/Slave architecture,
global policy, migration invariants, feature-lane lifecycle, queue semantics,
and integration/merge rules. It must not contain executable phase0-18 ordering.

Active prompts are split by role:

- `.hermes-loop/prompts/master_god_prompt.md` is the Master God prompt. It owns
  integration, audit, status, review, queue, approval-request, and merge
  decision behavior.
- `.hermes-loop/prompts/slave_god_prompt.md` is the Slave God prompt. It owns
  feature-local planning, execution, review, ACK, and readiness reporting.

Master startup must read these files first, in order:

1. `.hermes-loop/master_state.json`
2. `.hermes-loop/master_config.json`
3. `.hermes-loop/master_blueprint.md`
4. `.hermes-loop/prompts/master_god_prompt.md`
5. `.hermes-loop/contracts/master_dispatch_template.json`
6. Feature-local `slave_state.json` and referenced artifacts only for features
   that Master is reviewing, holding, repairing, integrating, or queueing.

Slave startup must read the Master-assigned feature registry entry, then:

1. `.hermes-loop/prompts/slave_god_prompt.md`
2. `.hermes-loop/contracts/slave_dispatch_template.json`
3. `.hermes-loop/work/features/<feature-id>/slave_state.json`
4. `.hermes-loop/work/features/<feature-id>/blueprint.md`

Launchers and prompts must not use legacy `blueprint.md` or
`god_loop_prompt.md` for active execution after migration.

### Master Config And Dispatch Contracts

`.hermes-loop/config.json` is legacy root-loop phase metadata. It should move to
`.hermes-loop/legacy/root-loop/config.json` with the rest of the phase0-18
controller files.

Active Master configuration lives in `.hermes-loop/master_config.json`. It may
hold default worktree roots, allowed target branches, Git/GitHub integration
defaults, status/report settings, approval verification sources, maintainer or
automation allowlists, trusted signing keys, and global policy knobs that are
not per-feature state. It must not contain executable phase-loop ordering.

The old `.hermes-loop/contracts/god_dispatch_template.json` is a legacy
phase-loop dispatch contract because it is populated from `state.json` and phase
metadata. It should move to
`.hermes-loop/legacy/root-loop/contracts/god_dispatch_template.json`.

Active dispatch contracts are split by role:

- `.hermes-loop/contracts/master_dispatch_template.json` describes Master
  decisions, review requests, integration-test requests, merge queue decisions,
  and merge approval requests.
- `.hermes-loop/contracts/slave_dispatch_template.json` describes feature-local
  Slave planning, execution, review, ACK, and readiness reports.

Launcher, reporter, hardening, and prompts must not read the legacy dispatch
template to infer active state after migration.

### Master Policy

The default policy requires:

- usable ACK before Master review acceptance;
- PASS feature review before Master review acceptance;
- result artifact before Master review acceptance;
- clean feature worktree;
- target branch;
- passing integrated tests before merge queue;
- Master review decision before merge queue;
- explicit `merge_approval` artifact before actual merge;
- no benchmark leakage;
- no promotion claim from same-slice repair smoke;
- no LongMemEval-only claim of chain-level improvement;
- v3 default preserved;
- v1 fallback preserved;
- kernel default remains opt-in.

## Master Responsibilities

Master is the only active controller.

Master may autonomously:

- create feature lanes;
- assign or record slave owner, branch, worktree, and blueprint;
- hold a feature;
- reject a feature;
- request repair;
- request Master review;
- write `.hermes-loop/master/features/<feature-id>/master_review.json`;
- run or require integrated tests;
- write `.hermes-loop/master/features/<feature-id>/integrated_tests.json`;
- queue a feature for merge when gates are met;
- write `merge_approval_request.json` when a feature is ready for explicit
  approval;
- write `post_merge_verification.json` after an approved merge attempt;
- write `merge_decision.json` after merge execution or hold/reject;
- write Master decisions with evidence.

Master may not autonomously:

- execute an actual merge without `merge_approval`;
- create or modify `merge_approval.json`;
- rewrite legacy root-loop history;
- make promotion claims without valid promotion evidence;
- weaken global policy for a feature lane.

## Slave Responsibilities

Each slave owns one feature lane and is feature-local autonomous.

Slave may:

- write `work/features/<feature-id>/blueprint.md`;
- write feature-local brainstorm/spec/plan/execute/review/ACK artifacts;
- maintain required `work/features/<feature-id>/slave_state.json`;
- modify its own branch/worktree;
- run local feature tests;
- report readiness to Master.

Slave may not:

- write Master queues directly;
- change Master policy;
- create, modify, move, or delete Master-owned evidence under
  `.hermes-loop/master/features/<feature-id>/`;
- create or modify `merge_approval.json`;
- change legacy root-loop files;
- change phase0-18 history baseline;
- directly merge into the target branch;
- make promotion or benchmark-quality claims outside its evidence.

## Queue Semantics

`master_state.json.queues` should include:

- `planning_queue`
- `active_lanes`
- `master_review_queue`
- `merge_queue`
- `held`
- `blocked`
- `merged`

Rules:

- `ready_for_master_review` enters `master_review_queue` only.
- `ready_for_master_review` is never mergeable.
- `ready_for_merge` and `merge_requested` may enter `merge_queue` only after
  Master review, integrated tests, clean worktree, policy gates, and required
  artifacts pass.
- `merge_queue` does not mean merged.
- `merged` requires `merge_approval`, merge execution evidence, and
  post-merge verification.
- `held_after_merge` enters `held`, not `merged` or `blocked`.
- For `held_after_merge`, `feature.state` and `merge.status` must both be
  `held_after_merge`.
- `held_after_merge` must not contribute to merged counts or merged summaries
  until a later revert or repair-forward decision closes it.
- `merge.status` must not be ahead of feature state.
- `features[]` and `queues` must be consistent.

## Merge Strategy

The initial Master control plane supports one merge strategy:

- `no_ff_merge_commit`: merge the approved feature head into the target branch
  with a merge commit. The approved feature head must remain an ancestor of the
  post-merge target branch head.

Squash merge, rebase merge, fast-forward-only merge, and any PR-host-specific
strategy are out of scope for this design. They must be rejected unless a later
design adds explicit strategy values, schemas, and verification rules.

## Hybrid Git / GitHub Collaboration

Local Git worktrees are required. GitHub is optional.

Required local evidence is staged by gate.

Master review gate:

- feature branch;
- feature worktree;
- required slave state file at
  `work/features/<feature-id>/slave_state.json`;
- Master-owned registry fields for branch, worktree, target branch, blueprint,
  artifact paths, and merge status;
- blueprint artifact;
- feature ACK;
- PASS feature review;
- result artifact;

Merge queue gate:

- all Master review gate evidence;
- accepted Master review decision artifact;
- clean feature worktree;
- committed feature changes;
- integrated tests artifact;
- target branch and merge strategy;
- policy gates satisfied;
- no merge-status-ahead-of-feature-state mismatch.

Actual merge gate:

- all merge queue gate evidence;
- `merge_approval_request` artifact with a stable digest;
- explicit `merge_approval` artifact;
- approval provenance verification that is not based only on JSON self-claims;
- current master review, integrated test, and policy snapshot digests match the
  digests approved in the request;
- merge execution evidence;
- post-merge verification evidence;
- `merge_decision` artifact recording final disposition.

Optional GitHub evidence:

- PR URL or number;
- CI check status;
- review approvals or requested changes;
- conflict or mergeability status;
- CI artifacts.

GitHub evidence can strengthen a decision but cannot replace local gates.

## Master Gate Evidence

`master_review.json` and `integrated_tests.json` are Master-owned gate evidence.
They live outside feature-local work directories:

- `.hermes-loop/master/features/<feature-id>/master_review.json`
- `.hermes-loop/master/features/<feature-id>/integrated_tests.json`

Slave Gods may read these files, but may not create, edit, move, or delete them.
Master must derive them from Slave artifacts, local git state, and verification
commands, then bind them by digest in the merge approval request.

Required `master_review.json` schema:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "status": "accepted|changes_requested|rejected",
  "recorded_by": "master-god",
  "recorded_at": "2026-05-24T00:00:00Z",
  "branch": "feature/feature-id",
  "base_commit": "123456abcdef",
  "head_commit": "abcdef123456",
  "target_branch": "main",
  "slave_result_ref": ".hermes-loop/work/features/feature-id/result.md",
  "slave_ack_ref": ".hermes-loop/work/features/feature-id/ack.json",
  "slave_review_ref": ".hermes-loop/work/features/feature-id/review_verdict.json",
  "artifact_digests": {
    "result": "sha256:result-digest",
    "ack": "sha256:ack-digest",
    "review_verdict": "sha256:review-verdict-digest"
  },
  "findings": [],
  "policy_checks": {
    "v1_fallback_preserved": true,
    "kernel_opt_in_preserved": true,
    "no_benchmark_leakage": true
  }
}
```

Required `integrated_tests.json` schema:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "status": "passed|failed",
  "recorded_by": "master-god",
  "recorded_at": "2026-05-24T00:00:00Z",
  "branch": "feature/feature-id",
  "base_commit": "123456abcdef",
  "head_commit": "abcdef123456",
  "target_branch": "main",
  "commands": [
    {
      "command": "uv run pytest tests/test_hermes_master_state.py -q",
      "status": "passed",
      "artifact_ref": ".hermes-loop/master/features/feature-id/integrated_pytest.log",
      "artifact_digest": "sha256:test-log-digest"
    }
  ],
  "worktree_clean": true,
  "artifact_digests": {}
}
```

For merge queue and approval request generation, `master_review.status` must be
`accepted`, `integrated_tests.status` must be `passed`, and both artifacts must
match the same branch, base commit, head commit, and target branch that Master
intends to request for merge approval.

## Merge Approval Contract

`merge_approval.json` is an explicit authorization artifact, not another Master
decision. It cannot be created or modified by Master or a Slave God. Master may
create `merge_approval_request.json`, `post_merge_verification.json`, and
`merge_decision.json`. A valid approval must come from a human maintainer or
trusted repository automation outside both the Master and Slave execution loops.

Approval artifacts live outside feature-local work directories:

- `.hermes-loop/approvals/<feature-id>/merge_approval_request.json`
- `.hermes-loop/approvals/<feature-id>/merge_approval.json`
- `.hermes-loop/approvals/<feature-id>/merge_decision.json`
- `.hermes-loop/approvals/<feature-id>/post_merge_verification.json`

The `approvals/` tree is Master/external-owned. Slave Gods may read approval
state if needed, but may not create, edit, move, or delete approval artifacts.
Feature registry entries may reference approval paths, but feature-local
`work/features/<feature-id>/...` artifacts must not be the write authority for
approval.

`merge_approval_request.json` is the request Master creates when a feature is
ready for external approval.

Required request schema:

```json
{
  "version": "1.0",
  "request_id": "feature-id-20260524T000000Z",
  "feature_id": "feature-id",
  "requested_by": "master-god",
  "requested_at": "2026-05-24T00:00:00Z",
  "head_commit": "abcdef123456",
  "base_commit": "123456abcdef",
  "approved_range": "123456abcdef..abcdef123456",
  "target_branch": "main",
  "master_review_ref": ".hermes-loop/master/features/feature-id/master_review.json",
  "master_review_digest": "sha256:master-review-json-canonical-digest",
  "integrated_tests_ref": ".hermes-loop/master/features/feature-id/integrated_tests.json",
  "integrated_tests_digest": "sha256:integrated-tests-json-canonical-digest",
  "merge_strategy": "no_ff_merge_commit",
  "policy_snapshot_ref": ".hermes-loop/master_state.json#features/feature-id",
  "policy_snapshot_digest": "sha256:policy-snapshot-json-canonical-digest",
  "request_digest": "sha256:request-json-canonical-digest"
}
```

`request_digest` is computed from canonical request JSON excluding the
`request_digest` field, including the review, integrated-test, and policy
snapshot digests. External approval must reference `request_id`,
`request_digest`, and the individual evidence digests.

Required approval schema:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "request_id": "feature-id-20260524T000000Z",
  "request_digest": "sha256:request-json-canonical-digest",
  "decision": "approved",
  "actor": "maintainer-or-automation-id",
  "actor_type": "human|trusted_automation",
  "created_by": "external_to_master_and_slave",
  "approved_commit": "abcdef123456",
  "base_commit": "123456abcdef",
  "approved_range": "123456abcdef..abcdef123456",
  "target_branch": "main",
  "master_review_ref": ".hermes-loop/master/features/feature-id/master_review.json",
  "master_review_digest": "sha256:master-review-json-canonical-digest",
  "integrated_tests_ref": ".hermes-loop/master/features/feature-id/integrated_tests.json",
  "integrated_tests_digest": "sha256:integrated-tests-json-canonical-digest",
  "merge_strategy": "no_ff_merge_commit",
  "policy_snapshot_ref": ".hermes-loop/master_state.json#features/feature-id",
  "policy_snapshot_digest": "sha256:policy-snapshot-json-canonical-digest",
  "verification": {
    "method": "signed_approval|git_signature|github_review|github_check|ci_artifact",
    "ref": "https://github.com/org/repo/pull/123#pullrequestreview-456",
    "digest": "sha256:external-evidence-digest",
    "status": "verified"
  },
  "constraints": [],
  "timestamp": "2026-05-24T00:00:00Z"
}
```

Rules:

- `decision` must be `approved` for actual merge. `rejected` or `hold` blocks
  merge.
- `request_id` and `request_digest` must match the current
  `merge_approval_request.json`.
- `approved_commit`, `base_commit`, `approved_range`, and `target_branch` must
  all match the approval request and actual merge input. If any one is stale,
  missing, or mismatched, approval is invalid.
- `master_review_ref` and `integrated_tests_ref` must match the Master-owned
  evidence used for the merge queue decision.
- `master_review_digest`, `integrated_tests_digest`, and
  `policy_snapshot_digest` must match the approval request and current artifact
  contents at actual merge time.
- A Master-authored approval is invalid. A trusted automation approval is valid
  only when `actor` identifies external repository automation and
  `created_by=external_to_master_and_slave`.
- `verification.status` must be `verified`.
- `verification.method` must prove provenance with at least one locally
  checkable or API-checkable source configured in `master_config.json`: signed
  approval body, trusted git signature, GitHub review, GitHub check/run id,
  signed commit/tag, or CI artifact URL with a recorded digest.
- `maintainer_allowlist` is only an authorization filter for actor identity. It
  cannot be the sole provenance verification method.
- Missing, stale, mismatched, or Slave-authored approval blocks merge.

`merge_decision.json` is the final Master disposition after merge execution or
hold/reject.

`post_merge_verification.json` records the merge execution and verification
evidence used by `merge_decision.json`.

Required post-merge verification schema:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "target_branch": "main",
  "pre_merge_head": "123456abcdef",
  "approved_head": "abcdef123456",
  "post_merge_head": "fedcba654321",
  "merge_commit": "fedcba654321",
  "merge_strategy": "no_ff_merge_commit",
  "merge_execution_status": "passed",
  "github_pr": null,
  "approval_ref": ".hermes-loop/approvals/feature-id/merge_approval.json",
  "approval_digest": "sha256:merge-approval-json-canonical-digest",
  "approval_request_ref": ".hermes-loop/approvals/feature-id/merge_approval_request.json",
  "approval_request_digest": "sha256:request-json-canonical-digest",
  "ancestry_check": {
    "command": "git merge-base --is-ancestor abcdef123456 fedcba654321",
    "status": "passed"
  },
  "verification_commands": [
    {
      "command": "uv run pytest tests/test_hermes_master_state.py -q",
      "status": "passed",
      "artifact_ref": ".hermes-loop/approvals/feature-id/post_merge_pytest.log",
      "artifact_digest": "sha256:post-merge-test-log-digest"
    }
  ],
  "status": "passed",
  "recorded_by": "master-god",
  "recorded_at": "2026-05-24T00:00:00Z"
}
```

`status` may be `passed` or `failed`. `merge_execution_status` must be `passed`
for every post-merge verification artifact: `post_merge_head` must be on
`target_branch`, `merge_commit` must identify the merge commit on that branch,
and `approved_head` must be an ancestor of `post_merge_head`. For
`status=passed`, each required verification command must have `status=passed`
plus an artifact digest. For `status=failed`, merge execution evidence must
still pass; only one or more verification commands may fail. Failed or missing
post-merge verification prevents `merge_decision.decision=merged`.
`approval_ref`, `approval_digest`, `approval_request_ref`,
`approval_request_digest`, and `merge_strategy=no_ff_merge_commit` are required
for every post-merge verification artifact.
These ancestry rules apply to `merge_strategy=no_ff_merge_commit`; squash,
rebase, fast-forward-only, and host-specific PR merge strategies are invalid for
this design.

Required final decision schema for `decision=merged`:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "decision": "merged",
  "final_state": "merged",
  "approved_head": "abcdef123456",
  "target_branch": "main",
  "merge_strategy": "no_ff_merge_commit",
  "merge_commit": "fedcba654321",
  "github_pr": null,
  "approval_ref": ".hermes-loop/approvals/feature-id/merge_approval.json",
  "approval_digest": "sha256:merge-approval-json-canonical-digest",
  "approval_request_ref": ".hermes-loop/approvals/feature-id/merge_approval_request.json",
  "approval_request_digest": "sha256:request-json-canonical-digest",
  "integrated_tests_ref": ".hermes-loop/master/features/feature-id/integrated_tests.json",
  "post_merge_verification_refs": [
    ".hermes-loop/approvals/feature-id/post_merge_verification.json"
  ],
  "post_merge_verification_digests": [
    "sha256:post-merge-verification-json-canonical-digest"
  ],
  "recorded_by": "master-god",
  "recorded_at": "2026-05-24T00:00:00Z"
}
```

For `decision=merged`, `merge_commit` is required. `github_pr` is optional
supporting metadata and cannot replace `merge_commit`. Approval request,
approval, and post-merge verification digests must match the current artifact
contents when Master records the final decision.

Required final decision schema for `decision=held` or `decision=rejected`:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "decision": "held|rejected",
  "final_state": "held|rejected",
  "blocked_gate": "master_review|integrated_tests|approval|merge_execution|policy",
  "reasons": [
    "Human-readable reason tied to evidence."
  ],
  "target_branch": "main",
  "approved_head": null,
  "merge_strategy": "no_ff_merge_commit",
  "existing_evidence_refs": [
    ".hermes-loop/master/features/feature-id/master_review.json"
  ],
  "existing_evidence_digests": [
    "sha256:existing-evidence-digest"
  ],
  "recorded_by": "master-god",
  "recorded_at": "2026-05-24T00:00:00Z"
}
```

For `decision=held` or `decision=rejected`, `reasons[]` and `blocked_gate` are
required, evidence refs/digests are optional but must match if present, and
`final_state=merged`, `merge_commit`, and post-merge verification refs are
forbidden. These decisions cover pre-merge blocks and merge execution failures
where no merge commit reached the target branch.

If the hold/reject occurs after approval but before merge execution,
`approved_head`, `approval_ref`, `approval_digest`, `approval_request_ref`, and
`approval_request_digest` are required. Before approval, those fields may be
absent or null.

Required final decision schema for `decision=held_after_merge`:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "decision": "held_after_merge",
  "final_state": "held_after_merge",
  "blocked_gate": "post_merge_verification",
  "reasons": [
    "Post-merge verification failed after merge commit reached target branch."
  ],
  "target_branch": "main",
  "approved_head": "abcdef123456",
  "merge_strategy": "no_ff_merge_commit",
  "merge_commit": "fedcba654321",
  "github_pr": null,
  "approval_ref": ".hermes-loop/approvals/feature-id/merge_approval.json",
  "approval_digest": "sha256:merge-approval-json-canonical-digest",
  "approval_request_ref": ".hermes-loop/approvals/feature-id/merge_approval_request.json",
  "approval_request_digest": "sha256:request-json-canonical-digest",
  "failed_post_merge_verification_ref": ".hermes-loop/approvals/feature-id/post_merge_verification.json",
  "failed_post_merge_verification_digest": "sha256:failed-post-merge-verification-json-canonical-digest",
  "next_action": "revert|repair_forward|manual_hold",
  "next_action_ref": ".hermes-loop/approvals/feature-id/next_action.json",
  "recorded_by": "master-god",
  "recorded_at": "2026-05-24T00:00:00Z"
}
```

`held_after_merge` is required when a merge commit has reached the target branch
but post-merge verification failed or is incomplete. It must record the
`merge_commit`, failed post-merge verification ref/digest, approval
ref/digest, approval request ref/digest, and a `next_action` of `revert`,
`repair_forward`, or `manual_hold`. It must not be reported as `merged`.

`next_action` has closure requirements:

- `revert` requires a revert artifact with revert commit, target branch,
  reverted merge commit, verification command refs/digests, and `status=passed`.
- `repair_forward` requires a new repair feature lane or worktree ref, target
  branch, starting commit, and a Master decision linking the repair lane back to
  the failed merge.
- `manual_hold` requires external hold approval or maintainer reason, actor,
  timestamp, and provenance ref/digest.

Until the required next-action artifact exists and passes its own verification,
the feature remains in `held` with `feature.state=held_after_merge` and
`merge.status=held_after_merge`.

Required next-action artifact schema:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "action": "revert|repair_forward|manual_hold",
  "status": "passed|accepted",
  "held_after_merge_ref": ".hermes-loop/approvals/feature-id/merge_decision.json",
  "held_after_merge_digest": "sha256:held-after-merge-decision-digest",
  "target_branch": "main",
  "reverted_merge_commit": "fedcba654321",
  "revert_commit": "012345abcdef",
  "repair_feature_id": null,
  "repair_lane_ref": null,
  "manual_hold_ref": null,
  "verification_refs": [
    ".hermes-loop/approvals/feature-id/revert_verification.json"
  ],
  "verification_digests": [
    "sha256:next-action-verification-digest"
  ],
  "recorded_by": "master-god|external_maintainer",
  "recorded_at": "2026-05-24T00:00:00Z"
}
```

Fields that do not apply to the selected `action` may be null. The closure rules
below define which fields are required for each action.

Closure rules:

- `revert` closes `held_after_merge` only when `revert_commit` is present,
  verifies cleanly, and records `feature.state=reverted_after_merge` and
  `merge.status=reverted_after_merge`. It must not count as merged.
- `repair_forward` closes the original feature's `held_after_merge` only by
  opening a linked repair lane; the original feature remains non-merged with
  `feature.state=repair_forward_open` and `merge.status=repair_forward_open`
  until the repair lane completes its own Master review and merge gates.
- `manual_hold` closes only the emergency post-merge failure state; it records
  `feature.state=manual_hold` and `merge.status=manual_hold`, remains in `held`,
  and requires external maintainer provenance.

## Migration

Migration must be staged so Hermes never has a period where no active state
reader exists. Compatibility readers and launcher support are installed before
old files move into the legacy directory.

Migration has two phases: prepare and activate. The prepare phase adds readers
and generates all new Master files while legacy remains active. The activate
phase atomically switches active control to Master files only after validation.

Prepare phase:

1. Add compatibility readers that resolve the active controller state in this
   order:
   - `.hermes-loop/master_state.json` when present and active;
   - `.hermes-loop/legacy/root-loop/state.json` only as read-only migration
     input;
   - current `.hermes-loop/state.json` only before the isolation move.
   If `.hermes-loop/master_state.json` exists but is invalid, unreadable, or has
   an abnormal activation state, the reader must not silently fall back to legacy
   state for active execution. It must return a blocked/report-only status.
   The only allowed inactive Master state is
   `activation_state=master_pending` during prepare phase, where legacy remains
   the active source. Legacy fallback is allowed only before `master_state.json`
   exists, during explicit prepare-phase activation staging, or for explicit
   migration audit.
2. Wire reporter, hardening helpers, launcher, and prompts with compatibility
   read capability, but keep legacy root-loop files as the active source until
   generated Master files pass validation. This step must not require missing
   Master prompts, config, contracts, or state.
3. Generate `.hermes-loop/master_state.json` from current `.hermes-loop/state.json`
   and `.hermes-loop/feature_lanes.json` with
   `activation_state=master_pending` and `active=false`.
4. Generate `.hermes-loop/master_blueprint.md` from the active Master/Slave
   architecture decisions. Phase0-18 execution ordering remains legacy-only.
5. Generate `.hermes-loop/prompts/master_god_prompt.md` and
   `.hermes-loop/prompts/slave_god_prompt.md` from the new role boundaries.
6. Generate `.hermes-loop/master_config.json` from the active parts of
   `.hermes-loop/config.json`. Phase-loop ordering remains legacy-only.
7. Generate `.hermes-loop/contracts/master_dispatch_template.json` and
   `.hermes-loop/contracts/slave_dispatch_template.json` from the new Master and
   Slave responsibilities.
8. Generate `.hermes-loop/master/features/` and migrate any existing
   Master-review or integrated-test evidence as read-only historical evidence.
   Do not trust feature-local copies as active Master gate evidence.
9. Generate every feature's required
   `.hermes-loop/work/features/<feature-id>/slave_state.json` and record its path
   in `master_state.features[].slave_state_path`.
10. Create `.hermes-loop/approvals/` and migrate any existing approval-like
   evidence as read-only historical evidence. Do not synthesize
   `merge_approval.json`.
11. Validate `master_state.json`, `master_blueprint.md`, prompts,
   `master_config.json`, dispatch contracts, approval paths, slave states, and
   derived queues before moving legacy files.

Activate phase:

12. Apply a single migration transaction, preferably one git commit, that
   simultaneously:
   - writes `.hermes-loop/master_state.json` as
     `activation_state=master_active` and `active=true`;
   - enables reporter, hardening, launcher, and prompts to reject legacy active
     execution;
   - moves old active root-loop control files to
     `.hermes-loop/legacy/root-loop/`;
   - writes required legacy stubs and `master_status.{json,md}`.
   Any failure before the transaction is complete must leave legacy as the active
   source with `activation_state=master_pending` or no active Master state.
13. Keep legacy readers for audit and migration reports only.
14. Update prompts and blueprint text so old `state.json`, `config.json`,
   `blueprint.md`, `god_loop_prompt.md`, and God dispatch template are described
   as legacy history, not active control.

The implementation plan must treat reporter, hardening, launcher, Master/Slave
prompts, Master blueprint migration, config migration, approval path setup, and
dispatch-contract migration as one migration unit. Moving root-loop files before
those readers and replacement contracts are in place is invalid.
Switching launcher/prompts to require Master files before those files exist and
pass validation is also invalid.

The migration must preserve phase0-18 evidence and the current feature-lane
status:

- `v1-quarantine`: Master reviewable, not mergeable.
- `archive-rag`: planned.

## Error Handling

- Invalid, unreadable, internally inconsistent, or unexpectedly inactive
  `master_state.json`: reporter reports blocked/report-only and does not start
  God. Active execution must not fall back to legacy state.
- Missing history baseline: Master control is blocked.
- Missing active-state compatibility reader during migration: migration is
  blocked before moving legacy files.
- Missing or invalid `master_blueprint.md`, `master_god_prompt.md`, or
  `slave_god_prompt.md`: Master control is blocked.
- Missing or invalid `master_config.json`: Master control is blocked.
- Active code still reading legacy `blueprint.md`, `god_loop_prompt.md`,
  `config.json`, or legacy `god_dispatch_template.json`: migration is blocked.
- Missing legacy root-loop files: warning unless required migration evidence is
  absent.
- Missing required slave state file: that feature is blocked.
- Missing slave ACK, review, or result: that feature is blocked.
- Dirty slave worktree: feature cannot enter review or merge queue.
- Missing, malformed, Slave-authored, or non-accepted `master_review`: feature
  cannot enter merge queue.
- Missing, malformed, Slave-authored, or failed `integrated_tests`: feature
  cannot enter merge queue.
- Master review and integrated-test evidence with branch, base commit, head
  commit, or target branch mismatches cannot enter merge queue.
- Unsupported merge strategy, including squash, rebase, fast-forward-only, or
  host-specific PR strategy, cannot enter merge queue.
- Missing, malformed, or digest-mismatched `merge_approval_request`: feature
  cannot be merged.
- Changed master review, integrated-test, or policy snapshot contents after
  approval request digest generation invalidate the approval and block merge.
- Missing, stale, mismatched, unverifiable, self-signed, Master-authored, or
  Slave-authored `merge_approval`: feature cannot be merged.
- Approval that uses maintainer allowlist without a signed/API/external artifact
  provenance check is unverifiable and cannot be merged.
- Missing, malformed, or failed `post_merge_verification`: feature cannot be
  marked merged.
- Failed or incomplete post-merge verification after a merge commit reaches the
  target branch must produce `merge_decision.decision=held_after_merge`, not
  `merged` or plain `held`.
- `held_after_merge` belongs to the `held` queue and must not be counted as
  merged.
- Failed post-merge verification with `merge_execution_status` other than
  `passed` is invalid; use a plain held/rejected merge execution failure before
  a merge commit reaches the target branch.
- Plain `held` or `rejected` with `blocked_gate=post_merge_verification` is
  invalid; use `held_after_merge` once a merge commit reaches the target branch.
- Missing or failed next-action closure artifact keeps `held_after_merge` open.
- Missing, malformed, digest-mismatched, conditionally invalid, or inconsistent
  `merge_decision`: feature cannot be marked merged.
- GitHub unavailable: degrade to local-only and keep local gates.

## Testing

Add `tests/test_hermes_master_state.py` for:

- migration from old `state.json` and `feature_lanes.json`;
- migration order safety: compatibility readers, reporter, hardening, launcher,
  prompts, Master blueprint, config migration, approval path setup, and dispatch
  contracts are updated before root-loop files move;
- prepare phase keeps legacy active until all Master files exist and validate;
- activate phase atomically switches to active Master control only after
  validation;
- activate phase is applied as one migration transaction/commit; simulated
  mid-activation failure leaves legacy active;
- legacy root-loop isolation;
- old `blueprint.md`, `blueprint.zh.md`, `god_loop_prompt.md`, `config.json`,
  and `god_dispatch_template.json` are legacy-only after migration;
- `master_blueprint.md`, `master_god_prompt.md`, and `slave_god_prompt.md` are
  the active blueprint and prompts;
- `master_config.json`, `master_dispatch_template.json`, and
  `slave_dispatch_template.json` are the active config and dispatch contracts;
- Master startup read-first order uses Master files, not legacy root-loop files;
- Slave startup read-first order uses assigned feature registry plus Slave
  prompt/contract/state/blueprint;
- required `slave_state.json` generation and validation;
- master state schema validation;
- activation state validation, including rejection of inconsistent
  `activation_state` and `active` combinations;
- Master-owned feature registry fields are required for review and merge
  decisions;
- `master_review.json` and `integrated_tests.json` live under
  `.hermes-loop/master/features/<feature-id>/`, are Master-owned, and reject
  Slave-authored or feature-local copies as active gate evidence;
- `master_state.features[].artifacts` includes `post_merge_verification`;
- `master_review.json` records feature id, branch/base/head/target, status,
  recorded_by, source artifact refs, artifact digests, findings, and policy
  checks;
- `integrated_tests.json` records feature id, branch/base/head/target, status,
  recorded_by, command results, artifact refs/digests, and clean-worktree state;
- queue derivation and queue consistency;
- `held_after_merge` maps to the `held` queue, sets feature state and
  `merge.status` to `held_after_merge`, and does not affect merged counts;
- `ready_for_master_review` not mergeable;
- Master review, merge queue, and actual merge gates require different evidence
  sets;
- `ready_for_merge` requires integrated tests;
- merge requires `merge_approval`;
- `merge_approval_request.json` includes request id, commit/range, target,
  review/test refs and digests, merge strategy, policy snapshot and digest, and
  canonical request digest;
- `merge_approval.json` must match request id and request digest;
- `merge_approval.json` must match master review, integrated-test, and policy
  snapshot digests from the approval request;
- `approved_commit`, `base_commit`, `approved_range`, and `target_branch` must
  all match the approval request and actual merge input;
- only `merge_strategy=no_ff_merge_commit` is accepted; squash, rebase,
  fast-forward-only, and host-specific PR strategies are rejected;
- `merge_approval.json` rejects missing actor, wrong commit range, wrong target
  branch, stale test/review refs, self-signed Master approval, and Slave-authored
  approval;
- maintainer allowlist alone is rejected as provenance verification;
- `merge_approval.json` must live under `.hermes-loop/approvals/<feature-id>/`
  and must include verified signed approval, trusted git signature, GitHub
  review/check, signed commit/tag, or CI artifact evidence;
- `merge_decision.json` for `decision=merged` requires `merge_commit` plus
  approval refs/digests, approval request refs/digests, and post-merge
  verification refs/digests; `github_pr` is optional metadata only;
- `merge_decision.json` for `decision=held|rejected` requires `blocked_gate`
  and `reasons[]`, allows existing evidence refs/digests, conditionally requires
  approval refs after approval, and forbids `final_state=merged`, `merge_commit`,
  and post-merge verification refs;
- `merge_decision.json` for `decision=held_after_merge` requires merge commit,
  failed post-merge verification ref/digest, approval refs/digests, approval
  request refs/digests, `next_action`, and `next_action_ref`;
- `post_merge_verification.json` records target branch, pre/post HEAD, merge
  commit, merge strategy, merge execution status, approval refs/digests,
  approval request refs/digests, ancestry check, verification commands, result
  artifact digests, and status;
- failed `post_merge_verification.json` after a merge commit reaches the target
  branch produces `held_after_merge`, not plain `held` or `rejected`;
- failed `post_merge_verification.json` must still have
  `merge_execution_status=passed`, valid target/head/ancestor evidence, and a
  valid merge commit;
- `held_after_merge.next_action=revert` requires revert commit plus verification;
  `repair_forward` requires a new repair lane/ref; `manual_hold` requires
  external hold approval or reason with provenance;
- next-action closure updates `feature.state` and `merge.status` to
  `reverted_after_merge`, `repair_forward_open`, or `manual_hold` according to
  the action, and none of those closure states count as merged;
- malformed `merge.status` ahead of feature state is blocked;
- invalid or unexpectedly inactive `master_state.json` blocks active execution
  instead of falling back to legacy state;
- `master_state.decisions[]` is an append-only artifact index and not an
  independent decision source;
- GitHub evidence is optional and never replaces local gates.

Update existing tests:

- reporter refreshes `master_status.*` in DONE state;
- hardening reads `master_state.json` as active source;
- hardening reads `master_config.json` instead of active legacy `config.json`;
- launcher does not directly read active `.hermes-loop/state.json` after
  migration;
- launcher and prompts use Master/Slave dispatch contracts, not legacy
  `god_dispatch_template.json`;
- launcher and prompts use active Master/Slave prompts, not legacy
  `god_loop_prompt.md`;
- God prompt does not instruct active control through legacy `state.json`,
  `blueprint.md`, or `config.json`;
- old `feature_lanes.json` is not treated as active source after migration;
- compatibility status clearly reports legacy inputs as inactive.

Expected verification:

```bash
uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py -q
uv run ruff check .hermes-loop/hermes_hardening.py .hermes-loop/hermes_reporter.py tests/test_hermes_*.py
python3 -m py_compile .hermes-loop/hermes_hardening.py .hermes-loop/hermes_reporter.py && bash -n .hermes-loop/god_launcher.sh
```

## Spec Self-Review

- No placeholders remain.
- `master_state.json` is the only active control-plane truth source.
- `master_blueprint.md` and Master/Slave prompts replace legacy root-loop
  blueprint and prompt files.
- `master_config.json` and Master/Slave dispatch templates replace legacy
  phase-loop config and dispatch contracts.
- Legacy root-loop files are isolated and read-only for audit.
- Master review and integrated-test gate evidence live under
  `.hermes-loop/master/features/`, not feature-local work directories.
- Approval artifacts live under `.hermes-loop/approvals/` and require
  externally verifiable authority.
- Slave autonomy is feature-local and cannot mutate Master queues directly.
- Slave state is required and referenced from `master_state.features[]`.
- Migration order installs compatibility readers before moving legacy files.
- Migration activation is two-phase: prepare with
  `activation_state=master_pending` while legacy remains active, then atomically
  activate Master after validation in a single migration transaction.
- Launcher and God prompts are included in the migration scope.
- Master autonomy is audit-driven and cannot merge without external approval.
- GitHub support is optional and cannot replace local gates.
- MemoryOS product behavior is out of scope.
