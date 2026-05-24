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

The active control plane is:

- `.hermes-loop/master_state.json`
- `.hermes-loop/master_status.json`
- `.hermes-loop/master_status.md`
- `.hermes-loop/work/features/<feature-id>/...`

Legacy root-loop files remain auditable but no longer drive new control flow.

## Master State Shape

`master_state.json` should contain:

```json
{
  "version": "1.0",
  "mode": "master_control",
  "active": true,
  "history_baseline": ".hermes-loop/history/main_loop_phase0_18.json",
  "legacy_root_loop": ".hermes-loop/legacy/root-loop/",
  "master_policy": {},
  "features": [],
  "queues": {},
  "decisions": [],
  "integration": {},
  "github": {},
  "last_updated": ""
}
```

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
- write Master decisions with evidence.

Master may not autonomously:

- execute an actual merge without `merge_approval`;
- rewrite legacy root-loop history;
- make promotion claims without valid promotion evidence;
- weaken global policy for a feature lane.

## Slave Responsibilities

Each slave owns one feature lane and is feature-local autonomous.

Slave may:

- write `work/features/<feature-id>/blueprint.md`;
- write feature-local brainstorm/spec/plan/execute/review/ACK artifacts;
- maintain optional `work/features/<feature-id>/slave_state.json`;
- modify its own branch/worktree;
- run local feature tests;
- report readiness to Master.

Slave may not:

- write Master queues directly;
- change Master policy;
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

Required local evidence:

- feature branch;
- feature worktree;
- clean feature worktree;
- committed feature changes;
- feature ACK;
- PASS feature review;
- result artifact;
- integrated tests artifact;
- Master decision artifact.

Optional GitHub evidence:

- PR URL or number;
- CI check status;
- review approvals or requested changes;
- conflict or mergeability status;
- CI artifacts.

GitHub evidence can strengthen a decision but cannot replace local gates.

## Migration

Migration steps:

1. Read current `.hermes-loop/state.json`.
2. Read current `.hermes-loop/feature_lanes.json`.
3. Generate `.hermes-loop/master_state.json`.
4. Move old active root-loop control files to
   `.hermes-loop/legacy/root-loop/`.
5. Generate `.hermes-loop/master_status.{json,md}` from `master_state.json`.
6. Update reporter and hardening helpers to use `master_state.json` as the
   active source.
7. Keep legacy readers for audit and migration reports only.
8. Update prompts and blueprint text so old `state.json` is described as
   legacy history, not active control.

The migration must preserve phase0-18 evidence and the current feature-lane
status:

- `v1-quarantine`: Master reviewable, not mergeable.
- `archive-rag`: planned.

## Error Handling

- Invalid `master_state.json`: reporter reports blocked and does not start God.
- Missing history baseline: Master control is blocked.
- Missing legacy root-loop files: warning unless required migration evidence is
  absent.
- Missing slave ACK, review, or result: that feature is blocked.
- Dirty slave worktree: feature cannot enter review or merge queue.
- Missing or failed integrated tests: feature cannot enter merge queue.
- Missing `merge_approval`: feature cannot be merged.
- GitHub unavailable: degrade to local-only and keep local gates.

## Testing

Add `tests/test_hermes_master_state.py` for:

- migration from old `state.json` and `feature_lanes.json`;
- legacy root-loop isolation;
- master state schema validation;
- queue derivation and queue consistency;
- `ready_for_master_review` not mergeable;
- `ready_for_merge` requires integrated tests;
- merge requires `merge_approval`;
- malformed `merge.status` ahead of feature state is blocked;
- GitHub evidence is optional and never replaces local gates.

Update existing tests:

- reporter refreshes `master_status.*` in DONE state;
- hardening reads `master_state.json` as active source;
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
- Legacy root-loop files are isolated and read-only for audit.
- Slave autonomy is feature-local and cannot mutate Master queues directly.
- Master autonomy is audit-driven and cannot merge without approval.
- GitHub support is optional and cannot replace local gates.
- MemoryOS product behavior is out of scope.
