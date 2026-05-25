# feature: xmuse-console

Status: planned.
Feature lane: `xmuse/work/features/xmuse-console/`.
Runner: `local_codex` / `hermes-local` / `slave-god-xmuse-console`.

This blueprint intentionally uses a phase structure similar to the original
loop blueprint so xmuse can be built layer by layer. The old root-loop remains
audit-only; only this feature-local blueprint drives the `xmuse-console` lane.

## Purpose

xmuse is a read-only observation and understanding layer for `xmuse`.
It gives a Master/operator and project owner a stable way to inspect the
now-established Master/Slave multi-agent control plane while individual feature
lanes continue to evolve.

The first version answers four questions:

1. Is the loop active, trustworthy, and ready to continue?
2. Which feature lanes exist, and which are blocked, held, planned,
   reviewable, mergeable, or merged?
3. Why is each lane blocked or gated?
4. Which facts conflict across live JSON, feature artifacts, docs, and runtime
   files?

xmuse is not production MemoryOS. It does not change MemoryOS memory semantics,
benchmark behavior, retrieval behavior, store authority, or agent kernel
behavior.

## Current Baseline

Use live code, `AGENTS.md`, `consensus.md`, `xmuse/master_state.json`,
`xmuse/master_status.json`, `xmuse/contracts/*.json`, and
`xmuse/prompts/*_god_prompt.md` as current facts.

Current known baseline:

- MemoryOS Lite is an eval-driven, source-attributed Agent/RAG memory
  prototype.
- Default memory architecture is `v3`.
- `MEMORYOS_MEMORY_ARCH=v1` remains the explicit legacy fallback.
- `MEMORYOS_RECALL_PIPELINE=v2` remains opt-in.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- SQLite remains the authoritative MemoryOS store.
- `xmuse` is the current Master/Slave control plane.
- Master is the only active controller.
- Master owns registry, queues, integrated tests, Master review, approval gates,
  and final merge decisions.
- Slave owns feature-local plan/execute/review, result, ACK, review verdict,
  and `slave_state.json` within one assigned feature boundary.
- `xmuse/contracts/master_dispatch_template.json` and
  `xmuse/contracts/slave_dispatch_template.json` define required inputs,
  allowed writes, forbidden actions, required artifacts, and gates.
- `xmuse/contracts/state_machine.json` is deprecated and must be shown as
  historical/deprecated if surfaced.
- Legacy root-loop files are audit history.
- Current live registry has three registered feature lanes: `archive-rag` blocked,
  `xmuse-console` planned, and `benchmark-layer-organization` planned. This is
  an observation target, not a durable test fixture.

## Scope

### In

- A local-only, read-only xmuse snapshot adapter for `xmuse`.
- Stable xmuse DTOs that shield the frontend from `xmuse` schema drift.
- A restrained xmuse console frontend focused on operator understanding.
- Control-plane contract visibility for Master/Slave roles, allowed writes,
  required artifacts, gates, and deprecated legacy state-machine files.
- Conflict detection for selected live JSON, feature artifacts, docs, runtime
  files, and repository state.
- Hermetic tests using fixture directories, not the current live `xmuse`
  state as a long-term assertion.
- Phase-by-phase implementation with usable evidence before promotion.

### Out

- Dispatch, approve, merge, kill, relaunch, or other write operations.
- Blueprint editing in the UI.
- Chat-based agent control.
- Real-time streaming as a first-version requirement.
- Production deployment posture, authentication system, tenancy model, or
  public network exposure.
- Claims that MemoryOS Lite is production-ready.
- Any change to MemoryOS memory architecture, recall pipeline, kernel defaults,
  storage authority, or benchmark semantics.

## Product Names

- Product: `xmuse`
- API/adapter layer: `xmuse snapshot adapter`
- Core DTO: `XmuseSnapshot`
- Frontend surface: `xmuse console`

The name is intentionally separate from Hermes internals. Hermes may remain the
current implementation, but xmuse represents the stable observation surface for
the loop.

## Hard Constraints

- xmuse is read-only. No UI control or API endpoint may write `xmuse`,
  git state, MemoryOS data, approvals, or runtime process state.
- `xmuse/master_state.json` remains the current control-plane source of
  truth when it can be parsed.
- Master/slave dispatch contracts are first-class observation inputs. xmuse may
  summarize contract roles, required inputs, allowed writes, forbidden actions,
  required artifacts, and gates, but it must not execute or modify them.
- Deprecated loop files, including `contracts/state_machine.json` and legacy
  root-loop state, are diagnostics only and must not be treated as active
  execution state.
- The frontend must consume xmuse DTOs only, not raw Hermes JSON files.
- The adapter must use tolerant parsing: ignore unknown fields, represent
  missing fields as `unknown` or `missing`, and surface parse warnings.
- Conflicts must be visible rather than silently resolved.
- Feature lane lookup must be registry-based. `feature_id` route parameters may
  only resolve to ids present in `master_state.features[].id`; they must never
  be mapped directly to filesystem paths.
- Raw refs may expose source file labels and JSON paths, but must not provide a
  path traversal mechanism.
- Access is local-development only in the first version.
- xmuse endpoints must be disabled by default behind explicit opt-in setting
  `MEMORYOS_XMUSE_ENABLED=1`.
- When enabled through the existing FastAPI app, xmuse must be documented as
  safe only for local trusted use. It must not be presented as authenticated,
  rate-limited, multi-tenant, or production-safe.
- Absolute paths, PID values, dirty file counts, and branch names are sensitive
  local control-plane data. The default local mode may show them to trusted
  local users, but the DTO must support a redaction mode before any non-local
  exposure is considered.
- SQLite remains authoritative for MemoryOS memory. xmuse only observes
  `xmuse` and repository/runtime state.
- v1 fallback, v2 recall opt-in, v3 default composer behavior, and agent kernel
  opt-in behavior must not change.
- Tests must use hermetic fixtures under `tests/fixtures/xmuse/`. They must not
  assert against the current live `xmuse` state as a durable expectation.
- Do not create new `docs/superpowers/` specs or plans for this feature.

## Allowed Files

Slave-writable feature artifacts:

- `xmuse/work/features/xmuse-console/blueprint.md`
- `xmuse/work/features/xmuse-console/slave_state.json`
- `xmuse/work/features/xmuse-console/context_bundle.md`
- `xmuse/work/features/xmuse-console/brainstorm.md`
- `xmuse/work/features/xmuse-console/plan.md`
- `xmuse/work/features/xmuse-console/plan_final.md`
- `xmuse/work/features/xmuse-console/phase-*/result.md`
- `xmuse/work/features/xmuse-console/phase-*/execute_review.md`
- `xmuse/work/features/xmuse-console/phase-*/ack.json`
- `xmuse/work/features/xmuse-console/phase-*/review_verdict.json`
- `xmuse/work/features/xmuse-console/result.md`
- `xmuse/work/features/xmuse-console/execute_review.md`
- `xmuse/work/features/xmuse-console/ack.json`
- `xmuse/work/features/xmuse-console/review_verdict.json`

Master-owned gate artifacts:

- `xmuse/master/features/xmuse-console/master_review.json`
- `xmuse/master/features/xmuse-console/integrated_tests.json`
- `xmuse/approvals/xmuse-console/merge_approval_request.json`
- `xmuse/approvals/xmuse-console/merge_approval.json`
- `xmuse/approvals/xmuse-console/merge_decision.json`
- `xmuse/approvals/xmuse-console/post_merge_verification.json`

Product implementation, phase-scoped:

- `src/memoryos_lite/config.py`
  - Only add xmuse enablement, redaction, and local-only settings.
  - Do not change memory architecture, recall pipeline, agent kernel, provider,
    storage, or benchmark defaults.
- `src/memoryos_lite/xmuse/`
- `src/memoryos_lite/api/xmuse.py`
- `src/memoryos_lite/api/app.py`
- `frontend/xmuse/`
- `tests/fixtures/xmuse/`
- `tests/test_xmuse_adapter.py`
- `tests/test_xmuse_snapshot.py`
- `tests/test_xmuse_api.py`
- Frontend tests under the chosen frontend test layout.

Docs may be touched only to document local-only usage and security boundaries.

## Architecture Target

```text
xmuse files
  -> xmuse snapshot adapter
  -> stable XmuseSnapshot DTO
  -> xmuse console frontend
```

The adapter may reuse or mirror logic from `xmuse/hermes_reporter.py`,
but xmuse must define stable response contracts instead of exposing reporter
internals.

Initial endpoints:

```text
GET /xmuse/snapshot
GET /xmuse/lanes/{feature_id}
```

These endpoints are available only when `MEMORYOS_XMUSE_ENABLED=1`.

## Data Model Target

### XmuseSnapshot

Required fields:

- `generated_at`
- `source_root`
- `control_plane`
- `queues`
- `lanes`
- `blockers`
- `conflicts`
- `runtime`
- `repository`
- `contracts`
- `freshness`
- `redaction`

`control_plane` reports Master activation state, active flag, source files,
and known schema/version metadata.

`queues` summarizes blocked, held, planning, review, merge, merged, and active
lane queues.

`lanes` contains compact lane cards: feature id, name, state, owner, branch,
worktree, target branch, gate summary, and missing artifact counts.

`blockers` is a sorted cross-lane list of attention items such as missing
artifacts, stale integrated tests, absent approval, or stale runtime state.

`conflicts` records contradictions. Example conflict types:

- Master state and slave state disagree about a lane state.
- Live config and README disagree about the default memory architecture.
- Store code and docs disagree about the current migration head.

`runtime` reports `active_job.json`, `run.lock`, heartbeat freshness, and
whether referenced PIDs are alive.

`repository` reports current branch, dirty state, tracked/untracked change
counts, and known feature worktree health when available without mutating git
state.

`contracts` reports contract source paths, Master and Slave role summaries,
required inputs, allowed writes, forbidden actions, required artifacts, gates,
and deprecated contract markers such as the inactive state-machine file.

`freshness` records source file mtime, missing files, stale files, and parse
warnings.

`redaction` reports whether local-sensitive fields are shown or redacted.

### XmuseLaneDetail

`GET /xmuse/lanes/{feature_id}` returns a detailed lane view only for features
found in the Master registry.

Required fields:

- `lane`
- `blueprint_summary`
- `master_decisions`
- `artifacts`
- `gates`
- `verification`
- `worktree`
- `conflicts`
- `raw_refs`
- `redaction`

`artifacts` is a first-class checklist. Missing artifacts are represented as
state, not as generic 404 failures.

`raw_refs` points to source labels and JSON paths used to derive the view. It
does not make raw JSON the frontend's primary model and does not allow the
client to request arbitrary paths.

## Console Target

The first version has five primary views:

- Overview
- Control Plane
- Lanes
- Conflicts
- Runtime

The global top status bar remains visible and reports:

```text
Master state | Snapshot time | Dirty state | Runtime health | Highest gate
```

Overview answers what needs attention now. It shows active lanes, blocked
lanes, held lanes, mergeable lanes, and an `Attention Required` list sorted by
severity.

Control Plane explains the stable loop architecture. It shows Master authority,
Slave boundary, dispatch contract paths, required artifacts, queue/gate names,
deprecated state-machine status, and external approval/fresh target merge
requirements.

Lanes compares all feature lanes by feature id, state, gate summary, owner,
branch, target branch, worktree health, and missing artifact count.

Lane Detail explains one feature using lane summary, gate status, decision
timeline, artifact checklist, conflicts, source files, and worktree state.

Conflicts centralizes contradictions instead of hiding them.

Runtime shows active job status, lock file status, heartbeat age, reporter
output freshness, and referenced PID liveness.

Allowed interactions:

- refresh snapshot
- filter by state
- filter by severity
- expand lane rows
- open lane detail
- inspect control-plane contract summaries
- copy file path when local-sensitive fields are not redacted
- inspect raw refs summary

No UI control writes `xmuse` files.

## Visual Design Target

xmuse follows a restrained AI/system product aesthetic inspired by OpenAI,
Apple, and Anthropic.

Principles:

- quiet, rational, and precise
- light theme in the first version
- high whitespace and clear hierarchy
- thin borders and minimal shadows
- small, restrained badges for state
- color used only for severity and gates
- no cyber control-room treatment
- no landing-page hero
- no decorative gradients, orbs, or chart wall
- 8px or smaller border radius
- design tokens prepared for future dark mode

Recommended visual vocabulary:

- warm off-white or neutral white background
- white or very light gray surfaces
- near-black primary text
- neutral gray secondary text
- soft gray borders
- restrained blue or graphite accent
- muted red for critical
- muted amber for held/warning
- subdued green for success

Tables should be light and scannable. Timelines should use thin lines and
short labels. Checklists should use clear status icons and text instead of
large color blocks.

## Completion Levels

No phase may advance unless it reaches level 3.

```text
0. plan-only: only plan/docs, no real implementation or usable artifact.
1. demo-only: UI or adapter stub exists but is not wired to the real path.
2. partial: some real path wiring exists but lacks tests, access gates, or
   conflict diagnostics.
3. usable: wired into the intended local-only read path, tested with hermetic
   fixtures, disabled by default, reviewed, and documented.
```

Research-only output is usable only if it is consumed by the next phase and
contains concrete, testable decisions.

## Required ACK Evidence Per Phase

Each phase ACK must provide:

- `ack_level = usable`;
- phase id and objective;
- affected files;
- confirmation that no write operation was added;
- confirmation that `MEMORYOS_XMUSE_ENABLED` remains disabled by default;
- verification commands and summarized outputs;
- fixture scenarios added or reused;
- whether local-sensitive fields are shown or redacted;
- review verdict on read-only behavior, local-only boundary, registry-only
  routing, path traversal resistance, and fixture independence;
- known limitations and follow-up scope.

If this evidence cannot be provided, the lane must repeat or adjust the
blueprint instead of advancing.

## Phase 0: Contract, Fixtures, And Local-Only Gate

### Objective

Establish the xmuse contract layer, hermetic fixtures, and configuration gate
before any UI work.

### Scope

- Add xmuse settings in `src/memoryos_lite/config.py`.
- Define DTO contracts under `src/memoryos_lite/xmuse/`.
- Add hermetic fixture directories under `tests/fixtures/xmuse/`.
- Add tests proving xmuse is disabled by default.
- Add fixtures for Master/Slave dispatch contracts and deprecated
  `state_machine.json`.

### Required Behavior

- `MEMORYOS_XMUSE_ENABLED` defaults to false.
- Redaction mode exists in settings and defaults to the conservative mode
  chosen by implementation.
- Fixture files represent healthy Master state, state conflict, missing
  artifact, stale runtime, damaged optional JSON, missing master state, and
  path-like feature ids.
- Fixture files represent the current Master/Slave contract model and the
  deprecated state-machine marker.
- No route is available unless xmuse is explicitly enabled.

### Required Verification

```bash
uv run pytest tests/test_xmuse_snapshot.py -q
uv run pytest tests/test_xmuse_api.py -q
```

### Promotion Gate

Phase 0 may advance only when settings, DTO contracts, fixtures, and
disabled-by-default route tests exist and pass, and the contract/deprecation
fixtures are covered.

## Phase 1: Snapshot Adapter

### Objective

Build the read-only adapter that converts `xmuse` fixture state into a
stable `XmuseSnapshot`.

### Scope

- Implement tolerant JSON reading.
- Parse `master_state.json` and optional `master_status.json`.
- Parse Master/Slave dispatch contracts as read-only contract summaries.
- Detect deprecated state-machine files as historical/deprecated diagnostics.
- Derive queues, lanes, blockers, artifact states, freshness, runtime state,
  repository state, contract state, and conflicts.
- Keep all behavior fixture-driven.

### Required Behavior

- Missing or malformed `master_status.json` degrades the snapshot but still
  attempts `master_state.json`.
- Missing or malformed `master_state.json` creates critical degraded status.
- Missing feature artifacts become artifact checklist states.
- Stale `run.lock` and dead PID become runtime warnings.
- Master/slave lane-state disagreement becomes a conflict.
- Master/Slave contract summaries include required inputs, allowed writes,
  forbidden actions, required artifacts, and gates.
- Deprecated `state_machine.json` is reported as inactive/deprecated, never as
  active execution state.
- README/config and store/docs disagreement detectors may be narrow but must
  report conflicts when fixture sources are present.

### Required Verification

```bash
uv run pytest tests/test_xmuse_adapter.py -q
uv run pytest tests/test_xmuse_snapshot.py -q
```

### Promotion Gate

Phase 1 may advance only when fixture-based adapter tests pass without reading
the current live `xmuse` as a durable expectation.

## Phase 2: Opt-In API Boundary

### Objective

Expose the snapshot through the existing FastAPI app only when explicitly
enabled, while preserving local-only and registry-only constraints.

### Scope

- Add `src/memoryos_lite/api/xmuse.py`.
- Wire routes in `src/memoryos_lite/api/app.py` behind the xmuse setting.
- Add route tests for disabled-by-default behavior.

### Required Behavior

- `/xmuse/snapshot` and `/xmuse/lanes/{feature_id}` are unavailable by default.
- With `MEMORYOS_XMUSE_ENABLED=1`, routes return DTOs derived from configured
  fixture/root paths.
- Lane detail resolves only feature ids present in
  `master_state.features[].id`.
- Unknown ids return 404.
- Path-like ids such as `../master_state.json` are rejected and cannot read
  filesystem paths.
- Redaction mode hides or normalizes absolute paths and PID values when
  configured.

### Required Verification

```bash
uv run pytest tests/test_xmuse_api.py -q
uv run pytest tests/test_api.py -q
```

### Promotion Gate

Phase 2 may advance only when route registration and access tests prove
disabled-by-default behavior and registry-only lane lookup.

## Phase 3: Console Shell, Overview, Control Plane, And Lanes

### Objective

Create the first xmuse console surface that consumes only `XmuseSnapshot` and
renders operator-relevant global, control-plane, and lane state.

### Scope

- Create `frontend/xmuse/`.
- Implement the app shell, top status bar, Overview view, Control Plane view,
  and Lanes view.
- Use mocked `XmuseSnapshot` data for frontend tests.

### Required Behavior

- Frontend never reads `xmuse` raw files.
- Overview renders Master state, snapshot time, dirty state, runtime health,
  highest gate, compact metrics, and attention items.
- Control Plane renders Master authority, Slave boundary, dispatch contract
  source paths, required artifacts, gates, forbidden actions, and deprecated
  state-machine status.
- Lanes renders feature id, state, gate summary, owner, branch, target branch,
  worktree health, and missing artifact count.
- UI follows the visual design target.
- No UI write controls exist.

### Required Verification

Frontend test command must be defined by implementation in this phase and must
cover:

```text
Overview renders blockers
Control Plane renders Master/Slave contract summaries
Control Plane marks state_machine as deprecated
Lanes renders state, gate, and missing artifacts
No write controls are present
```

### Promotion Gate

Phase 3 may advance only when the console shell can render snapshot mocks and
the frontend has no direct raw Hermes file dependency, and the stable
Master/Slave contract model is visible.

## Phase 4: Lane Detail, Conflicts, Runtime, And Redaction UX

### Objective

Complete the explanation views that make xmuse useful for understanding why a
lane is blocked or why a snapshot is degraded.

### Scope

- Implement Lane Detail view.
- Implement Conflicts view.
- Implement Runtime view.
- Implement redaction-visible UI states.

### Required Behavior

- Lane Detail renders lane summary, gate status, decision timeline, artifact
  checklist, conflicts, source refs, and worktree state.
- Conflicts sorts by severity and shows topic, sources, current
  interpretation, and recommended next inspection target.
- Runtime shows active job status, lock state, heartbeat age, reporter output
  freshness, and PID liveness.
- Active registry examples such as `archive-rag`, `xmuse-console`, and
  `benchmark-layer-organization` may appear when returned by fixtures or live
  local snapshots, but tests must assert categories and fields rather than
  depending on current live lane names.
- Redacted fields remain understandable and never produce broken empty UI.
- No UI write controls exist.

### Required Verification

Frontend test command must cover:

```text
Lane Detail renders artifact checklist
Conflicts sorts by severity
Runtime shows stale lock and dead PID
Redaction mode hides local-sensitive values
No write controls are present
```

### Promotion Gate

Phase 4 may advance only when blocked/held lane explanation, conflicts, runtime
health, and redaction behavior are visible from mocks and API fixtures.

## Phase 5: Integrated Verification And Handoff

### Objective

Harden the complete local-only xmuse read path and prepare the feature for
Master review.

### Scope

- Run focused backend tests.
- Run frontend tests.
- Run full project checks.
- Document local-only usage and disabled-by-default behavior if needed.
- Produce result, ack, and review verdict artifacts.

### Required Verification

```bash
uv run pytest tests/test_xmuse_adapter.py -q
uv run pytest tests/test_xmuse_snapshot.py -q
uv run pytest tests/test_xmuse_api.py -q
uv run pytest tests/test_api.py -q
uv run pytest -q
uv run ruff check .
uv run mypy src
```

No public benchmark or hard eval is required unless implementation changes
MemoryOS memory behavior, which remains out of scope.

### Promotion Gate

Phase 5 may complete only when all required checks pass, no write path exists,
and artifacts document exact commands, outputs, limitations, and follow-up
work.

## Review Failure Criteria

Master review must fail if:

- xmuse exposes any write operation.
- xmuse is enabled by default.
- xmuse is documented or implemented as production-safe, authenticated,
  rate-limited, or multi-tenant without a dedicated reviewed design.
- Frontend reads `xmuse` raw files directly instead of xmuse DTOs.
- `feature_id` is used as a filesystem path or can escape the Master registry.
- Absolute paths or PID values are exposed in a non-local/redacted mode.
- Tests depend on the current live `xmuse` state instead of fixtures.
- Conflicting source facts are silently resolved or hidden.
- v1 fallback, v2 recall opt-in, v3 default composer behavior, or agent kernel
  opt-in behavior changes.
- The implementation recreates `docs/superpowers/` specs or plans for active
  work.
- A phase advances with only plan-only or demo-only evidence.

## Handoff Artifacts

- blueprint: `xmuse/work/features/xmuse-console/blueprint.md`
- slave_state: `xmuse/work/features/xmuse-console/slave_state.json`
- context_bundle: `xmuse/work/features/xmuse-console/context_bundle.md`
- brainstorm: `xmuse/work/features/xmuse-console/brainstorm.md`
- plan: `xmuse/work/features/xmuse-console/plan.md`
- plan_final: `xmuse/work/features/xmuse-console/plan_final.md`
- phase results: `xmuse/work/features/xmuse-console/phase-*/result.md`
- phase execute reviews:
  `xmuse/work/features/xmuse-console/phase-*/execute_review.md`
- phase ACKs: `xmuse/work/features/xmuse-console/phase-*/ack.json`
- phase review verdicts:
  `xmuse/work/features/xmuse-console/phase-*/review_verdict.json`
- feature result: `xmuse/work/features/xmuse-console/result.md`
- execute_review: `xmuse/work/features/xmuse-console/execute_review.md`
- feature ack: `xmuse/work/features/xmuse-console/ack.json`
- feature review verdict:
  `xmuse/work/features/xmuse-console/review_verdict.json`
- master_review: `xmuse/master/features/xmuse-console/master_review.json`
- integrated_tests:
  `xmuse/master/features/xmuse-console/integrated_tests.json`
- merge_approval_request:
  `xmuse/approvals/xmuse-console/merge_approval_request.json`
- merge_approval: `xmuse/approvals/xmuse-console/merge_approval.json`
- merge_decision: `xmuse/approvals/xmuse-console/merge_decision.json`
- post_merge_verification:
  `xmuse/approvals/xmuse-console/post_merge_verification.json`

## Merge And Approval Gates

Implementation may not merge until:

- All phases reach usable completion or are explicitly descoped by Master.
- Slave produces result, ack, and review verdict artifacts.
- Master review passes.
- Integrated tests pass on a fresh target branch.
- Explicit external merge approval exists.
- Post-merge verification is defined and passes.
