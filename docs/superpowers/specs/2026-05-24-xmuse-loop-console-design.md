# xmuse Loop Console Design

Date: 2026-05-24

## Purpose

xmuse is a read-only observation and understanding layer for `.hermes-loop`.
It gives a Master/operator and project owner a stable way to inspect the
multi-agent control plane while `.hermes-loop` is still being hardened and
refactored.

The first version answers four questions:

1. Is the loop active, trustworthy, and ready to continue?
2. Which feature lanes exist, and which are blocked, held, planned,
   reviewable, mergeable, or merged?
3. Why is each lane blocked or gated?
4. Which facts conflict across live JSON, feature artifacts, docs, and runtime
   files?

xmuse is not a production MemoryOS surface and does not change MemoryOS memory
semantics.

## Non-Goals

- No dispatch, approve, merge, kill, relaunch, or other write operation.
- No blueprint editing.
- No chat-based agent controller.
- No direct frontend dependency on `.hermes-loop` internal JSON schemas.
- No real-time streaming requirement in the first version.
- No claim that MemoryOS Lite is production-ready.

## Product Name

- Product: `xmuse`
- API/adapter layer: `xmuse snapshot adapter`
- Core DTO: `XmuseSnapshot`
- Frontend surface: `xmuse console`

The name is intentionally separate from Hermes internals. Hermes may remain the
current implementation, but xmuse represents the stable observation surface for
the loop.

## Architecture

The first version uses a read-only backend aggregation API:

```text
.hermes-loop files
  -> xmuse snapshot adapter
  -> stable XmuseSnapshot DTO
  -> xmuse console frontend
```

The frontend consumes stable xmuse DTOs only. If `.hermes-loop` changes its file
layout or JSON shape, the adapter absorbs that change.

Initial endpoints:

```text
GET /xmuse/snapshot
GET /xmuse/lanes/{feature_id}
```

The adapter may reuse or mirror logic from `.hermes-loop/hermes_reporter.py`,
but xmuse should define its own stable response contracts instead of exposing
reporter internals.

## Data Model

### XmuseSnapshot

`XmuseSnapshot` is the global view-model for the console.

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
- `freshness`

`control_plane` reports Master activation state, active flag, source files,
and known schema/version metadata.

`queues` summarizes blocked, held, planning, review, merge, merged, and active
lane queues.

`lanes` contains compact lane cards: feature id, name, state, owner, branch,
worktree, target branch, gate summary, and missing artifact counts.

`blockers` is a sorted cross-lane list of attention items such as missing
artifacts, stale integrated tests, absent approval, or stale runtime state.

`conflicts` records contradictions. Examples:

- Master says `archive-rag` is blocked while `slave_state.json` says planned.
- Live config says v3 is default while README says v1 is default.
- Store code stamps migration `0008` while docs still mention `0006`.

`runtime` reports `active_job.json`, `run.lock`, heartbeat freshness, and
whether referenced PIDs are alive.

`repository` reports the current branch, whether the main worktree is dirty,
tracked/untracked change counts, and known feature worktree health when that
information is available without mutating git state.

`freshness` records source file mtime, missing files, stale files, and parse
warnings.

### XmuseLaneDetail

`GET /xmuse/lanes/{feature_id}` returns a detailed lane view.

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

`artifacts` is a first-class checklist. Missing artifacts are represented as
state, not as generic 404 failures.

`raw_refs` points to source files and JSON paths used to derive the view. It
does not make raw JSON the frontend's primary model.

## Information Architecture

The first version has four primary views:

- Overview
- Lanes
- Conflicts
- Runtime

The global top status bar remains visible and reports:

```text
Master state | Snapshot time | Dirty state | Runtime health | Highest gate
```

### Overview

Overview answers what needs attention now.

It shows compact metrics:

- active lanes
- blocked lanes
- held lanes
- mergeable lanes

It also shows an `Attention Required` list sorted by severity. Example items:

- `archive-rag` is blocked because result, ack, and review verdict artifacts
  are missing after slave shutdown.
- `v1-quarantine` is held because external approval is absent and integrated
  tests are stale.
- README memory-architecture text conflicts with live config.
- `run.lock` exists but the recorded PID is not alive.

### Lanes

Lanes is the main comparison view.

Each row shows:

- feature id
- state
- gate summary
- owner
- branch
- target branch
- worktree health
- missing artifact count

Rows may expand to show last decision, required verification, artifact gaps,
and source refs.

### Lane Detail

Lane Detail explains one feature.

The layout is:

```text
Left: lane summary and gate status
Center: decision timeline and artifact checklist
Right: conflicts, source files, and worktree state
```

The artifact checklist is central:

```text
result.md              missing
ack.json               missing
review_verdict.json    missing
master_review.json     not requested
integrated_tests.json  not requested
merge_approval.json    blocked
```

### Conflicts

Conflicts centralizes contradictions instead of hiding them.

Each conflict includes:

- severity
- topic
- sources
- current interpretation
- recommended next inspection target

### Runtime

Runtime shows process and file health:

- active job status
- lock file status
- heartbeat age
- reporter output freshness
- referenced PID liveness

Runtime warnings do not make the whole snapshot unusable unless Master state
cannot be established.

## Interactions

The first version only allows read-oriented interactions:

- refresh snapshot
- filter by state
- filter by severity
- expand lane rows
- open lane detail
- copy file path
- inspect raw refs summary

No UI control writes `.hermes-loop` files.

## Error Handling

The adapter degrades gracefully.

Rules:

- Missing or malformed `master_status.json` degrades the snapshot but still
  attempts `master_state.json`.
- Missing or malformed `master_state.json` is critical because control-plane
  facts cannot be established.
- Missing feature artifacts become artifact states.
- Missing worktrees become lane warnings.
- A stale lock or dead PID becomes a runtime warning.
- Parse warnings are visible in the UI.

The frontend must never render an empty dashboard without explaining the source
of failure.

## Schema Drift

The adapter uses tolerant parsing:

- Read only fields required by the xmuse DTO.
- Ignore unknown fields.
- Convert missing fields to `unknown` or `missing`.
- Convert type mismatches into parse warnings or conflicts.
- Preserve source refs for derived facts.

Conflicts are not silently resolved. When live sources disagree, xmuse reports
the disagreement and identifies the sources.

## Visual Design

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

## Testing Strategy

Backend tests come first:

```text
tests/test_xmuse_adapter.py
tests/test_xmuse_snapshot.py
tests/test_xmuse_api.py
```

Required backend coverage:

- Current `.hermes-loop` fixtures can generate a snapshot.
- `archive-rag` blocked in Master and planned in slave state creates a
  conflict.
- Missing artifacts appear in checklist state.
- Stale `run.lock` and dead PID create runtime warnings.
- Damaged optional JSON creates parse warnings without a 500.
- Missing `master_state.json` creates critical degraded status.

Frontend tests use mock snapshots:

```text
Overview renders blockers
Lanes renders state, gate, and missing artifacts
Lane Detail renders artifact checklist
Conflicts sorts by severity
Runtime shows stale lock and dead PID
```

## Success Criteria

The first version is successful when:

- An operator can understand current loop status within 30 seconds.
- Blocked and held lane reasons are visible without opening raw JSON.
- Missing artifacts and merge gates are explicit.
- Small `.hermes-loop` schema changes do not break the frontend.
- Runtime and document conflicts are visible rather than hidden.
- No write action is available from the UI.

## Implementation Boundary

This design authorizes only the design direction. Implementation requires a
separate plan before code changes.
