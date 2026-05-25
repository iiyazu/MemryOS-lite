# xmuse-core-state-extraction API Dependency Map

Feature: `xmuse-core-state-extraction`
Recorded: 2026-05-25

## Public Functions Migrated In This Slice

| Function | Current source | New owner | Reads FS | Writes FS | Git/subprocess | Gate logic | Runtime jobs |
|---|---|---|---:|---:|---:|---:|---:|
| `validate_master_state(state)` | `xmuse/hermes_hardening.py` | `xmuse_core.core.schema` | no | no | no | schema only | no |
| `resolve_active_controller(loop_root, audit=False)` | `xmuse/hermes_hardening.py` | `xmuse_core.core.state` | yes | no | no | schema only | no |
| `derive_master_queues(master_state, loop_root=None)` | `xmuse/hermes_hardening.py` | `xmuse_core.core.status` with shim injection | no in core | no | no | injected only | no |
| `build_master_status(loop_root, master_state)` | `xmuse/hermes_hardening.py` | `xmuse_core.core.status` with shim wrapper | no in core | no | no | injected only | no |

## Constants Migrated In This Slice

| Constant/helper group | New owner | Notes |
|---|---|---|
| `MASTER_ACTIVATION_STATES` | `xmuse_core.core.schema` | Required by `validate_master_state()`. |
| `MASTER_QUEUE_NAMES` | `xmuse_core.core.schema` | Required by validation and status queue creation. |
| `REQUIRED_MASTER_STATE_KEYS` | `xmuse_core.core.schema` | Required by validation. |
| `REQUIRED_FEATURE_KEYS` | `xmuse_core.core.schema` | Required by validation. |
| `REQUIRED_FEATURE_ARTIFACT_KEYS` | `xmuse_core.core.schema` | Required by validation. |
| `STATE_RANK` | `xmuse_core.core.schema` | Required by queue derivation. |
| `FEATURE_LOCAL_ACTIVE_STATES` | `xmuse_core.core.schema` | Required by queue derivation. |
| `MASTER_HELD_STATES` | `xmuse_core.core.schema` | Required by queue derivation. |
| `MASTER_BLOCKED_STATES` | `xmuse_core.core.schema` | Required by queue derivation. |
| `MASTER_REVIEW_STATES` | `xmuse_core.core.schema` | Required by queue derivation and shim compatibility. |
| `MERGE_REQUEST_STATES` | `xmuse_core.core.schema` | Required by queue derivation and shim compatibility. |
| `controller_path()` | `xmuse_core.core.paths` | Resolves `xmuse/...` refs relative to project root. |
| `resolve_controller_path()` | `xmuse_core.core.paths` | Preserves absolute paths and handles empty values. |
| `controller_display_path()` | `xmuse_core.core.paths` | Returns stable project-relative display paths. |

## Functions Explicitly Left In Shim Or Legacy Layer

| Function/helper | Reason |
|---|---|
| `validate_merge_queue_gate()` | Reads artifacts, checks target branch with git, validates approvals and integrated evidence. Core status receives an injected validator instead. |
| `validate_master_review_gate()` and review gate helpers | Master-owned artifact gate logic is out of scope. |
| `validate_merge_approval()` | Approval provenance validation is out of scope and remains in the runtime shim. |
| `validate_post_merge_verification()` | Approval/post-merge gate logic is out of scope. |
| `validate_merge_decision()` | Approval decision validation is out of scope. |
| `classify_feature_reconcile_state()` | Explicit non-goal for this feature. |
| `_optional_artifact_json()` and artifact readers | Artifact gate reads are out of core scope. |
| `_current_target_head()` and `_git_status_short()` | Git/subprocess helpers remain outside core. |
| active job helpers | Runtime job inspection and mutation remain outside core. |
| launcher/reporter helpers | Runner start/report behavior remains outside core. |

## Core Boundary Checks

- `xmuse_core.core.schema` must not import filesystem, subprocess, git, MemoryOS, or runner modules.
- `xmuse_core.core.state` may read JSON state files and must not write files or start jobs.
- `xmuse_core.core.status` must not import or call `validate_merge_queue_gate()` directly.
- `xmuse/hermes_hardening.py` remains the compatibility facade and may inject the legacy merge gate validator.
- Runtime `xmuse/` remains a non-package directory; no `xmuse/__init__.py` or `src/xmuse/` package is introduced.
