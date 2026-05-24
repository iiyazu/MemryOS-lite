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

The active control plane is:

- `.hermes-loop/master_state.json`
- `.hermes-loop/master_config.json`
- `.hermes-loop/master_status.json`
- `.hermes-loop/master_status.md`
- `.hermes-loop/contracts/master_dispatch_template.json`
- `.hermes-loop/contracts/slave_dispatch_template.json`
- `.hermes-loop/work/features/<feature-id>/...`

Legacy root-loop files remain auditable but no longer drive new control flow.
Old phase-loop config and dispatch templates must not be treated as active
controller metadata after migration.

## Master State Shape

`master_state.json` should contain:

```json
{
  "version": "1.0",
  "mode": "master_control",
  "active": true,
  "history_baseline": ".hermes-loop/history/main_loop_phase0_18.json",
  "legacy_root_loop": ".hermes-loop/legacy/root-loop/",
  "master_config": ".hermes-loop/master_config.json",
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
        "integrated_tests": ".hermes-loop/work/features/feature-id/integrated_tests.json",
        "master_review": ".hermes-loop/work/features/feature-id/master_review.json",
        "merge_approval": ".hermes-loop/work/features/feature-id/merge_approval.json"
      },
      "merge": {
        "status": "ready_for_master_review",
        "target_branch": "main",
        "strategy": "no_ff_or_pr",
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

### Master Config And Dispatch Contracts

`.hermes-loop/config.json` is legacy root-loop phase metadata. It should move to
`.hermes-loop/legacy/root-loop/config.json` with the rest of the phase0-18
controller files.

Active Master configuration lives in `.hermes-loop/master_config.json`. It may
hold default worktree roots, allowed target branches, Git/GitHub integration
defaults, status/report settings, and global policy knobs that are not
per-feature state. It must not contain executable phase-loop ordering.

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
- run or require integrated tests;
- queue a feature for merge when gates are met;
- write `merge_approval_request.json` when a feature is ready for explicit
  approval;
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
- `merge.status` must not be ahead of feature state.
- `features[]` and `queues` must be consistent.

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
- explicit `merge_approval` artifact;
- merge execution evidence;
- post-merge verification evidence;
- updated Master decision artifact recording final disposition.

Optional GitHub evidence:

- PR URL or number;
- CI check status;
- review approvals or requested changes;
- conflict or mergeability status;
- CI artifacts.

GitHub evidence can strengthen a decision but cannot replace local gates.

## Merge Approval Contract

`merge_approval.json` is an explicit authorization artifact, not another Master
decision. It cannot be created or modified by a Slave God, and Master may only
create `merge_approval_request.json`. A valid approval must come from a human
maintainer or trusted repository automation outside both the Master and Slave
execution loops.

Required schema:

```json
{
  "version": "1.0",
  "feature_id": "feature-id",
  "decision": "approved",
  "actor": "maintainer-or-automation-id",
  "actor_type": "human|trusted_automation",
  "created_by": "external_to_master_and_slave",
  "approved_commit": "abcdef123456",
  "approved_range": "base..head",
  "target_branch": "main",
  "master_review_ref": ".hermes-loop/work/features/feature-id/master_review.json",
  "integrated_tests_ref": ".hermes-loop/work/features/feature-id/integrated_tests.json",
  "merge_strategy": "no_ff_or_pr",
  "constraints": [],
  "timestamp": "2026-05-24T00:00:00Z"
}
```

Rules:

- `decision` must be `approved` for actual merge. `rejected` or `hold` blocks
  merge.
- `approved_commit` or `approved_range` must match the feature branch head or
  commit range being merged.
- `target_branch`, `master_review_ref`, and `integrated_tests_ref` must match
  the evidence Master used for the merge queue decision.
- A Master-authored approval is invalid. A trusted automation approval is valid
  only when `actor` identifies external repository automation and
  `created_by=external_to_master_and_slave`.
- Missing, stale, mismatched, or Slave-authored approval blocks merge.

## Migration

Migration must be staged so Hermes never has a period where no active state
reader exists. Compatibility readers and launcher support are installed before
old files move into the legacy directory.

Migration steps:

1. Add compatibility readers that resolve the active controller state in this
   order:
   - `.hermes-loop/master_state.json` when present and active;
   - `.hermes-loop/legacy/root-loop/state.json` only as read-only migration
     input;
   - current `.hermes-loop/state.json` only before the isolation move.
   If `.hermes-loop/master_state.json` exists but is invalid, unreadable, or has
   an abnormal `active=false`, the reader must not silently fall back to legacy
   state for active execution. It must return a blocked/report-only status.
   Legacy fallback is allowed only before `master_state.json` exists or for
   explicit migration audit.
2. Update reporter, hardening helpers, launcher, and God prompts to use the
   compatibility reader instead of opening `.hermes-loop/state.json`,
   `.hermes-loop/config.json`, or the legacy God dispatch template directly.
3. Generate `.hermes-loop/master_state.json` from current `.hermes-loop/state.json`
   and `.hermes-loop/feature_lanes.json`.
4. Generate `.hermes-loop/master_config.json` from the active parts of
   `.hermes-loop/config.json`. Phase-loop ordering remains legacy-only.
5. Generate `.hermes-loop/contracts/master_dispatch_template.json` and
   `.hermes-loop/contracts/slave_dispatch_template.json` from the new Master and
   Slave responsibilities.
6. Generate every feature's required
   `.hermes-loop/work/features/<feature-id>/slave_state.json` and record its path
   in `master_state.features[].slave_state_path`.
7. Validate `master_state.json`, `master_config.json`, dispatch contracts, slave
   states, and derived queues before moving legacy files.
8. Move old active root-loop control files to
   `.hermes-loop/legacy/root-loop/`.
9. Leave minimal `.hermes-loop/state.json` and `.hermes-loop/config.json`
   migration stubs only if needed by an
   unreplaced external caller. The stub must say `active=false`, point to
   `.hermes-loop/master_state.json` or `.hermes-loop/master_config.json`, and
   must not contain executable phase lanes or active phase metadata.
10. Generate `.hermes-loop/master_status.{json,md}` from `master_state.json`.
11. Keep legacy readers for audit and migration reports only.
12. Update prompts and blueprint text so old `state.json`, `config.json`, and
   God dispatch template are described as legacy history, not active control.

The implementation plan must treat reporter, hardening, launcher, God prompt,
config migration, and dispatch-contract migration as one migration unit. Moving
root-loop files before those readers and replacement contracts are in place is
invalid.

The migration must preserve phase0-18 evidence and the current feature-lane
status:

- `v1-quarantine`: Master reviewable, not mergeable.
- `archive-rag`: planned.

## Error Handling

- Invalid, unreadable, or unexpectedly inactive `master_state.json`: reporter
  reports blocked/report-only and does not start God. Active execution must not
  fall back to legacy state.
- Missing history baseline: Master control is blocked.
- Missing active-state compatibility reader during migration: migration is
  blocked before moving legacy files.
- Missing or invalid `master_config.json`: Master control is blocked.
- Active code still reading legacy `config.json` or legacy
  `god_dispatch_template.json`: migration is blocked.
- Missing legacy root-loop files: warning unless required migration evidence is
  absent.
- Missing required slave state file: that feature is blocked.
- Missing slave ACK, review, or result: that feature is blocked.
- Dirty slave worktree: feature cannot enter review or merge queue.
- Missing or failed integrated tests: feature cannot enter merge queue.
- Missing, stale, mismatched, self-signed, or Slave-authored `merge_approval`:
  feature cannot be merged.
- GitHub unavailable: degrade to local-only and keep local gates.

## Testing

Add `tests/test_hermes_master_state.py` for:

- migration from old `state.json` and `feature_lanes.json`;
- migration order safety: compatibility readers, reporter, hardening, launcher,
  prompts, config migration, and dispatch contracts are updated before root-loop
  files move;
- legacy root-loop isolation;
- old `config.json` and `god_dispatch_template.json` are legacy-only after
  migration;
- `master_config.json`, `master_dispatch_template.json`, and
  `slave_dispatch_template.json` are the active config and dispatch contracts;
- required `slave_state.json` generation and validation;
- master state schema validation;
- Master-owned feature registry fields are required for review and merge
  decisions;
- queue derivation and queue consistency;
- `ready_for_master_review` not mergeable;
- Master review, merge queue, and actual merge gates require different evidence
  sets;
- `ready_for_merge` requires integrated tests;
- merge requires `merge_approval`;
- `merge_approval.json` rejects missing actor, wrong commit range, wrong target
  branch, stale test/review refs, self-signed Master approval, and Slave-authored
  approval;
- malformed `merge.status` ahead of feature state is blocked;
- invalid or unexpectedly inactive `master_state.json` blocks active execution
  instead of falling back to legacy state;
- GitHub evidence is optional and never replaces local gates.

Update existing tests:

- reporter refreshes `master_status.*` in DONE state;
- hardening reads `master_state.json` as active source;
- hardening reads `master_config.json` instead of active legacy `config.json`;
- launcher does not directly read active `.hermes-loop/state.json` after
  migration;
- launcher and prompts use Master/Slave dispatch contracts, not legacy
  `god_dispatch_template.json`;
- God prompt does not instruct active control through legacy `state.json` or
  `config.json`;
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
- `master_config.json` and Master/Slave dispatch templates replace legacy
  phase-loop config and dispatch contracts.
- Legacy root-loop files are isolated and read-only for audit.
- Slave autonomy is feature-local and cannot mutate Master queues directly.
- Slave state is required and referenced from `master_state.features[]`.
- Migration order installs compatibility readers before moving legacy files.
- Launcher and God prompts are included in the migration scope.
- Master autonomy is audit-driven and cannot merge without external approval.
- GitHub support is optional and cannot replace local gates.
- MemoryOS product behavior is out of scope.
