# feature: xmuse-core-state-extraction

Status: blueprint-only draft.
Feature class: `control_plane_migration`.
Feature lane: `xmuse/work/features/xmuse-core-state-extraction/`.

This blueprint defines the first frameworkization slice for xmuse. It must not
drive implementation until Master registers the lane, creates or confirms an
isolated worktree, and dispatches a Slave.

## Purpose

Extract the most stable state/status part of the current xmuse control plane
from the large runtime script `xmuse/hermes_hardening.py` into a reusable
package boundary.

This feature starts xmuse's move toward an independent control-plane package
without changing the active runtime schema, launcher behavior, feature lane
semantics, approval gates, or MemoryOS product behavior.

Long-term direction:

- xmuse becomes an independent multi-agent development control-plane package.
- `xmuse/` remains the current project runtime/control-plane directory for now.
- MemoryOS later plugs into xmuse as an optional memory adapter, not as a core
  dependency.
- A2A, Sisyphus, AutoGen, CrewAI, OpenClaw, Codex CLI, and Claude Code are
  future runner/framework adapters, not current core dependencies.

## Current Baseline

Current active control-plane facts:

- Active runtime dir: `xmuse/`.
- Active state source: `xmuse/master_state.json`.
- Active status projection: `xmuse/master_status.json` and
  `xmuse/master_status.md`.
- Current hardening/control helpers: `xmuse/hermes_hardening.py`.
- Current reporter/watchdog: `xmuse/hermes_reporter.py`.
- Current launcher: `xmuse/god_launcher.sh`.
- Legacy root-loop files under `xmuse/legacy/root-loop/` are audit-only.
- Current focused xmuse tests use `tests/test_hermes_*.py` names for
  compatibility.

Latest verified baseline before this blueprint:

```text
uv run pytest -q -> 599 passed, 1 warning
uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py -q -> 99 passed
```

## Problem

`xmuse/hermes_hardening.py` currently mixes multiple concerns:

- Master state schema validation.
- Active controller resolution.
- Queue/status projection.
- Feature artifact reading.
- Review and merge gate validation.
- Approval validation.
- Legacy migration helpers.
- Runtime job helpers.
- Git/subprocess checks.

This makes xmuse hard to turn into a reusable package. It also makes future
runner/framework/memory adapters risky because they would attach to a script
that is not clearly separated from runtime state and gate side effects.

## Goals

- Create a reusable package boundary under `src/xmuse_core/`.
- Extract Master state validation into `xmuse_core.core.schema`.
- Extract read-only active controller loading/resolution into
  `xmuse_core.core.state`.
- Extract status/queue projection into `xmuse_core.core.status`.
- Keep runtime `xmuse/` as a non-package control-plane directory.
- Keep all existing public entrypoints and behavior compatible through
  `xmuse/hermes_hardening.py`.
- Keep merge gate behavior compatible by injecting the legacy merge gate
  validator from the shim layer.
- Produce an API/dependency map before moving logic.
- Add direct unit tests for the new package boundary while preserving existing
  `tests/test_hermes_*.py` compatibility tests.

## Non-Goals

- Do not change `xmuse/master_state.json` schema.
- Do not change `xmuse/master_status.json` or Markdown semantics except for
  non-contractual formatting details covered by tests.
- Do not migrate review gate, merge approval gate, approval validation, or
  post-merge verification logic.
- Do not move `classify_feature_reconcile_state()` in this feature.
- Do not introduce A2A, Sisyphus, AutoGen, CrewAI, OpenClaw, or any external
  agent framework dependency.
- Do not implement runner adapters.
- Do not implement MemoryOS memory adapter.
- Do not split xmuse into a separate repository.
- Do not make runtime `xmuse/` a Python package.
- Do not add `xmuse/__init__.py`.
- Do not modify MemoryOS product runtime behavior.
- Do not modify MemoryOS retrieval, archive, eval, store, or benchmark logic as
  a dependency of this control-plane migration.
- Do not merge.

## Package Boundary

Use `xmuse_core` as the in-repository package name:

```text
src/xmuse_core/
  __init__.py
  core/
    __init__.py
    paths.py
    schema.py
    state.py
    status.py

xmuse/
  hermes_hardening.py
  hermes_reporter.py
  god_launcher.sh
  master_state.json
  master_status.json
  master_status.md
```

Do not create `src/xmuse/` in this feature. The repository root already has a
runtime directory named `xmuse/`; creating a same-named import package would
risk unstable imports in raw script execution such as:

```text
python3 xmuse/hermes_reporter.py
bash xmuse/god_launcher.sh
```

`xmuse/` must remain a runtime/control-plane directory, not an import package.

## Module Responsibilities

### `xmuse_core.core.paths`

Allowed responsibilities:

- Resolve project-relative `xmuse/...` refs.
- Resolve loop-relative refs.
- Preserve absolute paths.
- Produce stable display paths.

Allowed functions:

```text
controller_path(loop, ref)
resolve_controller_path(loop, value)
controller_display_path(loop, path)
```

Constraints:

- No writes.
- No runner launch.
- No git/subprocess.
- No MemoryOS imports.
- No agent framework imports.

### `xmuse_core.core.schema`

Allowed responsibilities:

- Hold Master state validation constants.
- Validate Master state structure.
- Validate required feature/artifact keys.

Candidate exports:

```text
MASTER_ACTIVATION_STATES
MASTER_QUEUE_NAMES
REQUIRED_MASTER_STATE_KEYS
REQUIRED_FEATURE_KEYS
REQUIRED_FEATURE_ARTIFACT_KEYS
STATE_RANK
validate_master_state(state)
```

Constraints:

- No filesystem access.
- No artifact reads.
- No git/subprocess.
- No runner launch.
- No merge approval validation.
- Error messages should preserve key semantics, but tests should not require
  byte-for-byte legacy text unless the text is part of a documented contract.

### `xmuse_core.core.state`

Allowed responsibilities:

- Read `master_state.json`.
- Resolve the active controller source.
- Represent invalid/missing state as structured blocked/error results.
- Read legacy audit state only when required for existing compatibility.

Candidate exports:

```text
load_master_state(loop)
resolve_active_controller(loop)
```

Constraints:

- Read-only filesystem access is allowed for state files.
- No writes.
- No runner launch.
- No reporter/launcher calls.
- No git/subprocess.
- Legacy root-loop is audit-only and must not become an active execution
  source.

### `xmuse_core.core.status`

Allowed responsibilities:

- Build Master status payload.
- Build status Markdown.
- Derive queues/counts from state plus an injected merge gate validator.

Candidate exports:

```text
derive_master_queues(master_state, *, merge_gate_validator=None)
build_master_status(master_state, *, merge_gate_validator=None)
master_status_markdown(status)
```

Core status does not own merge gate logic. For `ready_for_merge` or
`merge_requested` features:

- if `merge_gate_validator` is provided, core uses its result to preserve
  current merge_queue/blocked semantics;
- if it is not provided, core must not mark the feature mergeable and must emit
  an explicit blocked/error reason.

Constraints:

- No direct import or call to `validate_merge_queue_gate()`.
- No artifact reads.
- No git/subprocess.
- No runner launch.
- No MemoryOS imports.
- No external agent framework imports.

### Runtime shim: `xmuse/hermes_hardening.py`

The runtime script remains the compatibility facade.

It may import `xmuse_core` and expose old public function names, including:

```text
validate_master_state()
resolve_active_controller()
derive_master_queues()
build_master_status()
write_master_status()
```

Legacy wrapper behavior:

- `derive_master_queues(master_state, loop_root=loop)` must keep current merge
  gate behavior by injecting a wrapper around existing
  `validate_merge_queue_gate(loop, feature)`.
- `write_master_status(loop, state)` remains a runtime I/O helper in the shim.
  It can call `xmuse_core.core.status.build_master_status()` and
  `master_status_markdown()`, then write `xmuse/master_status.*`.
- Unmigrated gate/migration/runtime helpers remain in this file.

## Write Boundary

Core package:

- `xmuse_core.core.paths`: read-free utility only.
- `xmuse_core.core.schema`: pure validation only.
- `xmuse_core.core.state`: read-only state loading/resolution only.
- `xmuse_core.core.status`: pure status payload/Markdown construction only.

Runtime shim:

- `xmuse/hermes_hardening.py::write_master_status()` may write
  `xmuse/master_status.json` and `xmuse/master_status.md`.
- No core function may start a runner, invoke reporter, invoke launcher, write
  approvals, mutate feature artifacts, or modify product files.

## Control-Plane Migration Policy

This feature is a `control_plane_migration` and must follow stricter isolation.

### No Direct Active State Mutation By Slave

A Slave may write only feature-local artifacts under:

```text
xmuse/work/features/xmuse-core-state-extraction/
```

It must not directly write:

```text
xmuse/master_state.json
xmuse/master_status.json
xmuse/master_status.md
xmuse/approvals/**
xmuse/master/features/**
```

Any active state change must be performed by Master and recorded as an
append-only decision or amendment artifact.

### Compatibility Before Switch

Required order:

```text
compatible reader/wrapper
old behavior still readable
new xmuse_core implementation
old/new behavior comparison
Master-only activation of shim delegation
```

No one-step replacement of the active loop is allowed.

### Staged Activation

Migration stage values:

```text
migration_pending
migration_validated
migration_active
rollback_required
```

Before `migration_active`, this feature must not change ordinary feature
dispatch, review, ACK, queue derivation, or merge gate semantics.

### Rollback

The feature must retain a rollback path to the previous
`xmuse/hermes_hardening.py` direct implementation behavior. Rollback must not
reactivate legacy root-loop as an execution source.

### Ordinary Lane Isolation

Before activation, this migration must not alter behavior for:

```text
archive-rag
benchmark-layer-organization
memoryos-redis-cache-probe
xmuse-console
```

### Gate Preservation

Migration success is not merge approval. Normal gates still apply:

```text
usable ACK
PASS review_verdict
Master review
integrated tests
external approval
fresh target gate
```

### Control-Plane Merge Quarantine

This lane changes xmuse itself, so it has an additional merge quarantine beyond
ordinary feature gates. `migration_active is not merge readiness`: proving the
shim delegation can run is only migration evidence, not permission to merge the
lane into the target branch.

Before Master records a successful staged activation, merge.status must remain `not_requested`.
Master must not move this lane to `ready_for_merge` or `merge_requested` from
Slave output alone.

The quarantine can be lifted only after all of these are true:

```text
migration_stage == migration_active
dry-run validator exists and is current
rollback plan exists and is current
ordinary lane semantic equivalence is documented
no-start reporter/status smoke passes
launcher/reporter/hardening/prompt/contract compatibility is verified
Master review accepts the migration evidence
integrated tests pass against a fresh target head
external approval exists and binds the current evidence
fresh target gate passes
```

If any item is missing, Master may keep the lane active, held, or in rework, but
must not place it in the merge queue.

### Independent Worktree

This feature must use its own branch/worktree. It must not share a worktree with
product feature lanes.

### Dry-Run Validator

Before activation, produce a dry-run artifact with:

```text
files_to_change
active_sources_before
active_sources_after
legacy_audit_only_sources
expected_status_projection
rollback_plan
blast_radius
```

### Required Runtime Surface Verification

Any state source or core boundary change must verify:

```text
xmuse/god_launcher.sh
xmuse/hermes_reporter.py
xmuse/hermes_hardening.py
xmuse/prompts/master_god_prompt.md
xmuse/prompts/slave_god_prompt.md
xmuse/contracts/master_dispatch_template.json
xmuse/contracts/slave_dispatch_template.json
```

### Blast Radius Declaration

Every result/review artifact must declare:

```text
control_plane_only: true
state_schema_change: false
launcher_change: false
reporter_change: false
migration_required: true
product_code_change: false
memoryos_runtime_change: false
```

### Product Code Isolation

Do not modify MemoryOS product logic as a dependency of this feature.

Forbidden unless explicitly re-scoped by Master:

```text
src/memoryos_lite/retrieval/**
src/memoryos_lite/store.py
src/memoryos_lite/engine.py
src/memoryos_lite/context_composer.py
benchmarks/**
eval logic
```

### Append-Only Decisions

All re-scope, hold, activate, rollback, and archive decisions must be recorded
as Master decision/amendment artifacts. Direct state edits without a decision
record are forbidden.

## Migration Phases

### Phase 0: Baseline And Dependency Map

Record current behavior before moving logic.

Required artifacts:

```text
xmuse/work/features/xmuse-core-state-extraction/api_dependency_map.md
xmuse/work/features/xmuse-core-state-extraction/baseline.md
```

The dependency map must list:

- public functions considered for migration;
- public functions explicitly left in the shim;
- constants/helpers each function depends on;
- whether each function reads filesystem;
- whether each function writes filesystem;
- whether each function calls git/subprocess;
- whether each function touches gate logic;
- whether each function starts or inspects runtime jobs.

Expected initial classification:

```text
Migrate now:
- validate_master_state()
- resolve_active_controller()
- pure state constants required by validation
- pure path helpers needed by state/status
- pure status payload and Markdown builders

Keep in shim/legacy layer:
- validate_merge_queue_gate()
- validate_master_review_gate()
- approval validation
- classify_feature_reconcile_state()
- artifact gate readers used for promotion/merge
- subprocess/git target-head checks
- runner/launcher/job helpers
```

Baseline verification must include focused tests and no-start status checks.

### Phase 1: Package Skeleton

Add:

```text
src/xmuse_core/__init__.py
src/xmuse_core/core/__init__.py
src/xmuse_core/core/paths.py
src/xmuse_core/core/schema.py
src/xmuse_core/core/state.py
src/xmuse_core/core/status.py
```

Tests must prove:

- `xmuse_core` imports under `uv run`.
- importing `xmuse_core.core.*` has no filesystem writes;
- importing core modules does not start runner/reporter/launcher;
- runtime `xmuse/` remains non-package.

### Phase 2: Paths And Schema Extraction

Move pure path utilities and Master state validation constants/functions.

Compatibility requirements:

- `xmuse/hermes_hardening.py::validate_master_state()` still works.
- Existing validation tests pass.
- Direct `xmuse_core.core.schema.validate_master_state()` tests exist.
- Key error semantics are preserved.

### Phase 3: Active Controller Extraction

Move read-only active controller resolution.

Compatibility requirements:

- `xmuse/hermes_hardening.py::resolve_active_controller()` still works.
- Direct `xmuse_core.core.state.resolve_active_controller()` tests exist.
- Invalid/missing state returns structured blocked/errors as before.
- Legacy audit state is not active execution state.
- No writes occur.

### Phase 4: Status Projection With Injected Merge Gate

Move pure status payload and Markdown construction.

Use injected merge gate:

```text
xmuse_core.core.status.derive_master_queues(
  master_state,
  merge_gate_validator=<optional callable>
)
```

Compatibility requirements:

- Core status does not import merge gate.
- Shim-level `derive_master_queues(master_state, loop_root=loop)` injects the
  legacy merge gate validator.
- Existing merge_queue/blocked semantics are preserved through shim tests.
- Direct core tests cover both:
  - no validator -> merge requested feature is blocked with explicit error;
  - fake validator -> queue result follows validator result.

### Phase 5A: Dry-Run Migration Validator

Add a feature-local dry-run artifact before activation.

The dry-run must state:

- what files are changed;
- what source remains active;
- what legacy sources remain audit-only;
- status projection before/after;
- rollback plan;
- blast radius.

### Phase 5B: Master-Only Staged Activation

Only Master may activate shim delegation.

Activation criteria:

- focused tests pass;
- direct core tests pass;
- no-start reporter/status smoke passes;
- dry-run validator artifact exists;
- ordinary lane queue/status semantic equivalence is documented;
- rollback plan exists.

### Phase 6: Follow-Up Roadmap

Document follow-up feature lanes only; do not implement them here:

```text
xmuse-review-gate-extraction
xmuse-merge-approval-gate-extraction
xmuse-reconcile-classifier-extraction
xmuse-runner-adapter-contract
xmuse-framework-adapter-probes
xmuse-memory-adapter-contract
xmuse-package-boundary-hardening
xmuse-hermes-naming-cleanup
```

## Reporter And Smoke Testing Policy

Do not use `python3 xmuse/hermes_reporter.py` as a generic smoke test if it may
start a runner.

Allowed no-start checks:

```text
import xmuse/hermes_reporter.py with importlib and call master_report()
call xmuse/hermes_hardening.py::write_master_status() directly
use a future XMUSE_REPORT_ONLY=1 path if implemented
```

If `XMUSE_REPORT_ONLY=1` is added in a later feature, it must guarantee:

- no `start_god()`;
- no launcher invocation;
- no runner process;
- no active state mutation beyond explicit report/status outputs.

## Error Compatibility Policy

Preserve key error semantics, not byte-for-byte incidental strings.

Tests should assert:

- `source`;
- `activation_state`;
- `valid`;
- `execution_allowed`;
- queue membership;
- counts;
- error categories or core substrings.

Tests should avoid overfitting to:

- exact module names;
- absolute temp paths;
- incidental exception formatting;
- full concatenated error strings unless already contractually required.

## Framework And Protocol Extension Policy

This feature does not introduce external frameworks or protocols. It only
preserves extension points.

Future layering:

```text
xmuse_core.core
  state / status / artifacts / gates

xmuse runners
  ShellRunner
  CodexCliRunner
  ClaudeCodeRunner
  A2ARunner
  SisyphusRunner
  AutoGenRunner
  CrewAIRunner

xmuse memory
  NoopMemory
  FileMemory
  MemoryOSMemoryAdapter
```

Core accepts runner outputs as artifacts and metadata. It does not know or care
whether the runner was a CLI agent, A2A peer, multi-agent chat, retry engine, or
human-supervised process.

## MemoryOS Adapter Direction

MemoryOS is a future optional memory adapter for xmuse.

Candidate future API:

```text
remember_event(event)
retrieve_context(query, scope)
summarize_feature_history(feature_id)
record_failure_pattern(pattern)
```

Potential uses:

- Master/Slave session bootstrap;
- feature lineage retrieval;
- recurring failure/error knowledge;
- architecture recall;
- prior review/gate evidence retrieval.

This feature must not implement this adapter.

## Allowed Files

Feature-local artifacts:

```text
xmuse/work/features/xmuse-core-state-extraction/blueprint.md
xmuse/work/features/xmuse-core-state-extraction/api_dependency_map.md
xmuse/work/features/xmuse-core-state-extraction/baseline.md
xmuse/work/features/xmuse-core-state-extraction/dry_run_validator.md
xmuse/work/features/xmuse-core-state-extraction/result.md
xmuse/work/features/xmuse-core-state-extraction/execute_review.md
xmuse/work/features/xmuse-core-state-extraction/review_verdict.json
xmuse/work/features/xmuse-core-state-extraction/ack.json
xmuse/work/features/xmuse-core-state-extraction/slave_state.json
```

Implementation files after Master dispatch:

```text
src/xmuse_core/__init__.py
src/xmuse_core/core/__init__.py
src/xmuse_core/core/paths.py
src/xmuse_core/core/schema.py
src/xmuse_core/core/state.py
src/xmuse_core/core/status.py
xmuse/hermes_hardening.py
tests/test_xmuse_core_*.py
tests/test_hermes_hardening.py
tests/test_hermes_reporter.py
tests/test_hermes_master_state.py
```

Read-only validation inputs:

```text
xmuse/master_state.json
xmuse/master_status.json
xmuse/master_status.md
xmuse/master_config.json
xmuse/prompts/master_god_prompt.md
xmuse/prompts/slave_god_prompt.md
xmuse/contracts/master_dispatch_template.json
xmuse/contracts/slave_dispatch_template.json
```

Forbidden unless Master explicitly re-scopes:

```text
xmuse/master_state.json
xmuse/approvals/**
xmuse/master/features/**
src/memoryos_lite/**
benchmarks/**
```

## Required Tests And Verification

Focused compatibility:

```bash
uv run pytest tests/test_hermes_hardening.py tests/test_hermes_reporter.py tests/test_hermes_master_state.py -q
```

New direct core tests:

```bash
uv run pytest tests/test_xmuse_core_*.py -q
```

Static checks:

```bash
uv run ruff check src/xmuse_core xmuse/hermes_hardening.py xmuse/hermes_reporter.py tests/test_hermes_*.py tests/test_xmuse_core_*.py
python3 -m py_compile src/xmuse_core xmuse/hermes_hardening.py xmuse/hermes_reporter.py
bash -n xmuse/god_launcher.sh
```

No-start status smoke:

```bash
python3 - <<'PY'
import importlib.util
from pathlib import Path

module_path = Path("xmuse/hermes_reporter.py")
spec = importlib.util.spec_from_file_location("xmuse_reporter", module_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
report = module.master_report()
assert report["source"] == "xmuse/master_state.json"
PY
```

Full regression before completion:

```bash
uv run pytest -q
```

## Completion Criteria

This feature is complete only when:

- `src/xmuse_core/core/*` owns the approved state/status logic.
- Runtime `xmuse/` remains non-package.
- No `src/xmuse/` package is created.
- `xmuse/hermes_hardening.py` keeps old public entrypoints working.
- `validate_master_state()` behavior remains compatible.
- `resolve_active_controller()` behavior remains compatible.
- `derive_master_queues()` preserves merge gate behavior through shim
  injection.
- `xmuse_core.core.status` does not import or call merge gate logic.
- `classify_feature_reconcile_state()` remains in the shim/legacy layer with
  unchanged behavior.
- `write_master_status()` runtime writes remain in the shim or are explicitly
  implemented as a thin I/O helper with no runner/artifact/git side effects.
- API/dependency map exists.
- Dry-run validator artifact exists.
- Rollback plan exists.
- No-start reporter/status smoke passes.
- Focused compatibility tests pass.
- Direct core tests pass.
- Full regression passes, or any failure is proven unrelated and documented.
- No external agent framework dependency is introduced.
- No MemoryOS product behavior changes.

## Review Failure Criteria

Fail review if:

- `xmuse/master_state.json` schema changes without explicit Master migration.
- Runtime `xmuse/` becomes a Python package.
- `src/xmuse/` is introduced and shadows runtime `xmuse/`.
- Core status imports or calls merge gate logic directly.
- Merge requested features become mergeable without the legacy gate validator.
- `classify_feature_reconcile_state()` behavior changes unintentionally.
- Reporter smoke starts `god_launcher.sh` or a runner.
- Core package imports MemoryOS product modules.
- Core package imports A2A, Sisyphus, AutoGen, CrewAI, OpenClaw, Codex, or
  Claude Code runtime dependencies.
- Product code is modified as part of the migration.
- Ordinary feature lane queue/review/ACK semantics change before Master
  activation.
- Migration decisions are not recorded append-only.
- Tests only validate wrappers and do not directly validate `xmuse_core`.

## Open Risks

- Moving constants/helper functions out of `hermes_hardening.py` can create
  double-source maintenance. Mitigation: move one dependency group at a time,
  re-export/wrap from the shim, and run focused tests after each group.
- Status projection currently touches merge gate behavior through
  `derive_master_queues()`. Mitigation: use injected merge gate validator and
  keep actual gate implementation in the shim.
- Raw script execution may not see editable package imports in every context.
  Mitigation: use `xmuse_core` package name and verify through launcher/reporter
  compatible smoke paths.
- Exact error text may drift after extraction. Mitigation: test key semantics
  and core substrings rather than incidental full strings.
