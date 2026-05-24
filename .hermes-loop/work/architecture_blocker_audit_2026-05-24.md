# Architecture Blocker Audit - 2026-05-24

Scope: Hermes loop control plane, multi-god integration surface, and the
MemoryOS Lite memory-routing invariants needed for v1 quarantine and archive
RAG feature lanes.

## Current Architecture Invariants Checked

- Default memory architecture remains `v3` in `src/memoryos_lite/config.py`.
- Explicit v1 fallback remains `MEMORYOS_MEMORY_ARCH=v1`.
- Agent kernel remains default-off and opt-in through `MEMORYOS_AGENT_KERNEL=v1`.
- `MemoryOSService.build_context()` routes to v3 by default and reaches legacy
  builder only when the resolved memory architecture is not v3.
- Archive RAG remains MemoryOS-owned: current archive retrieval is scoped through
  `V3ContextComposer`, `ArchiveEligibilityScope`, store eligibility, and
  `ArchivalPassageSearcher`; no external RAG framework owns memory semantics.

## Blocking Risks Found

1. Reporter stale on DONE state.
   - Root cause: `.hermes-loop/hermes_reporter.py` returned early when
     `state.json.current_state == DONE`.
   - Impact: `.hermes-loop/reports/latest.*` and master/slave status could keep
     showing stale phase-14 facts after phase-18 completed.
   - Fix: DONE state now refreshes latest report and master/slave status without
     starting God.

2. Master/slave status path churn.
   - Root cause: hardening summaries emitted absolute or relative controller
     paths depending on how the helper was invoked.
   - Impact: reporter could create meaningless dirty diffs in committed
     `master_slave_status.*`, polluting merge gates.
   - Fix: controller artifact paths are normalized to project-relative paths.

3. Runtime artifacts polluted git status.
   - Root cause: `.hermes-loop/active_job.json` and phase eval `.log` files were
     not ignored.
   - Impact: orchestration runs could leave dirty worktrees unrelated to code or
     phase evidence.
   - Fix: `.hermes-loop/.gitignore` now ignores `active_job.json` and
     `work/**/*.log`.

4. Phase-18 evidence was untracked.
   - Root cause: phase-18 context, plan, result, review, and ACK artifacts were
     generated but not yet committed.
   - Impact: the phase0-18 history baseline could not be fully audited from git.
   - Fix: phase-18 artifacts are included in the next control-plane commit.

## Status After Fixes

- Phase-18 ACK gate: pass.
- Phase-18 review eval decision gate: pass.
- State phase order gate: pass.
- Master/slave registry: loaded, two feature lanes, one mergeable
  (`v1-quarantine`), zero blockers.

No benchmark improvement, promotion, or chain-level improvement is claimed from
these fixes.
