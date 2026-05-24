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
   - Root cause: `xmuse/hermes_reporter.py` returned early when
     `state.json.current_state == DONE`.
   - Impact: `xmuse/reports/latest.*` and master/slave status could keep
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
   - Root cause: `xmuse/active_job.json` and phase eval `.log` files were
     not ignored.
   - Impact: orchestration runs could leave dirty worktrees unrelated to code or
     phase evidence.
   - Fix: `xmuse/.gitignore` now ignores `active_job.json` and
     `work/**/*.log`.

4. Phase-18 evidence was untracked.
   - Root cause: phase-18 context, plan, result, review, and ACK artifacts were
     generated but not yet committed.
   - Impact: the phase0-18 history baseline could not be fully audited from git.
   - Fix: phase-18 artifacts are included in the next control-plane commit.

5. Feature review and merge queues were conflated.
   - Root cause: `ready_for_master_review` was treated as `mergeable=true`.
   - Impact: Master God could interpret a slave feature as safe to merge before
     master integration tests existed.
   - Fix: `ready_for_master_review` now enters `master_review_queue` only.
     `ready_for_merge` and `merge_requested` enter `merge_queue` only after
     required integrated-test evidence is present and passing.

6. Integrated-test evidence could still be skipped by omission.
   - Root cause: integrated tests were checked only when a feature explicitly
     set `merge.requires_integrated_tests=true`.
   - Impact: a feature could enter `ready_for_merge` without integrated-test
     evidence by omitting or disabling that flag, despite the master policy.
   - Fix: all merge request states now require passing `integrated_tests`
     artifact evidence. The per-feature flag no longer weakens the master
     merge policy.

7. Reporter summary hid master review work.
   - Root cause: `reports/latest.md` summarized only mergeable and blocked
     counts.
   - Impact: a feature in `master_review_queue` could make the report look like
     there was no pending multi-god work.
   - Fix: reporter markdown now includes `reviewable` count.

8. `merge.status` could bypass feature-state gates.
   - Root cause: branch, worktree, ACK, review, and result gates were keyed to
     `feature.state`, while `mergeable` was keyed to `merge.status`.
   - Impact: a malformed lane with `state=planned` and
     `merge.status=ready_for_merge` could bypass core readiness gates if
     integrated tests were present.
   - Fix: readiness gates now trigger when either feature state or merge status
     requests review/merge, and merge status is blocked when it is ahead of the
     feature state.

## Status After Fixes

- Phase-18 ACK gate: pass.
- Phase-18 review eval decision gate: pass.
- State phase order gate: pass.
- Master/slave registry: loaded, two feature lanes, one reviewable
  (`v1-quarantine`), zero mergeable, zero blockers; merge queue remains empty
  until integrated-test evidence is present.

No benchmark improvement, promotion, or chain-level improvement is claimed from
these fixes.
