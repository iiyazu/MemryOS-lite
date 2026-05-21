# phase: phase-1

# Adjust Analysis - Phase 1 FAIL

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Evidence Read

- `context_bundle.md` defines Phase 1 as contract/evidence planning only, with no `src/`, `tests/`, active docs, benchmark-data, state promotion, default-kernel, or behavior optimization changes (`context_bundle.md:72-79`).
- `context_bundle.md` says execute owns final `letta_gap_matrix.md`, `result.md`, `execute_review.md`, review verdict, and ACK artifacts (`context_bundle.md:81-89`), but ACK is allowed only after usable criteria are met.
- `review_verdict.json` is `fail` and recommends `repeat/adjust before ACK` (`review_verdict.json:4-5`).
- `review_verdict.json` has two blockers: stale active ACK and dirty active control files (`review_verdict.json:23-44`).
- `git diff -- src tests docs benchmarks .hermes-loop/state.json` is empty in the current workspace.
- `git status --short` still reports dirty active control files: `.hermes-loop/blueprint.md`, `.hermes-loop/config.json`, `.hermes-loop/god_launcher.sh`, `.hermes-loop/god_loop_prompt.md`, `.hermes-loop/hermes_loop.py`, `.hermes-loop/hermes_reporter.py`, `AGENTS.md`, and `CLAUDE.md`.
- The dirty control-file diff is broad: `8 files changed, 1003 insertions(+), 1018 deletions(-)`, including a wholesale active-blueprint replacement.

## Blocker Root Causes

1. `stale_phase1_ack_present`

   Root cause: `.hermes-loop/work/phase-1/ack.json` is a leftover ACK from the older "Memory v3 Contracts" phase state, not an ACK produced after the current Letta-gap contract review. The file still says `verdict: ACK`, `phase_name: Memory v3 Contracts`, and `target_state: legacy-stable` (`ack.json:2-5`), while the current execute result says no `ack.json` was written by this execute step (`result.md:41`). This creates a false-completion artifact and violates the active goal's "without demo-only phase completion" constraint.

2. `active_control_files_dirty_despite_no_behavior_change_claim`

   Root cause: Phase 1 claims contract-only/no-control-change behavior, but the worktree has large uncommitted diffs in files that control dispatch, launcher behavior, reporter behavior, model/instruction policy, and the active blueprint. `result.md` currently says a dirty `.hermes-loop/blueprint.md` should be treated as pre-existing unless this execute step changed it (`result.md:70`), but the current evidence does not prove provenance. The context bundle says no promoted amendment is active (`context_bundle.md:104`) and forbids active docs/state/blueprint behavior changes for this phase (`context_bundle.md:72-79`). Therefore the review cannot safely accept the no-behavior-change claim.

## Stale ACK Handling

God should delete or quarantine the stale ACK before any PASS/ACK decision.

Preferred conservative action: quarantine it out of the active ACK path, for example:

```text
.hermes-loop/work/phase-1/_quarantine/ack.legacy-stable.stale.json
```

If the controller scans any file under the phase directory as an ACK, deletion is safer than quarantine. The key requirement is that `.hermes-loop/work/phase-1/ack.json` must not exist until a fresh PASS review creates a new usable ACK for the current active goal.

Review lane must not perform this write. It should be done by God or the owning execute/adjust lane.

## Dirty Control Files

The dirty control files must block Phase 1 ACK in the current state.

They cannot be treated as harmless pre-existing external workspace state by assertion alone. The current evidence proves they are dirty and active; it does not prove they predate Phase 1 execution, nor that they were promoted through the blueprint amendment protocol. Because these files can change dispatch, benchmark commands, reporter behavior, launcher behavior, and agent instructions, accepting them without a recorded boundary would weaken the anti-demo gate.

They may become acceptable external workspace state only after God records an explicit adjustment/quarantine decision with evidence. That decision should list the exact dirty control-file set, diff stat, current `src/tests/docs/benchmarks/.hermes-loop/state.json` cleanliness, and the rule that Phase 1 ACK may only judge phase-local contract artifacts while those control diffs remain excluded from Phase 1 ownership.

If God cannot or will not record that boundary, Phase 1 must pause rather than ACK.

## Minimal Artifact Changes Allowed

Allowed minimal changes to resolve this FAIL should stay phase-local:

- Remove or quarantine `.hermes-loop/work/phase-1/ack.json` so no active stale ACK remains.
- Write a phase-local GOD_ADJUST artifact, preferably `.hermes-loop/work/phase-1/blueprint_amendment.md` if using the Dynamic Blueprint Amendment Protocol, or a narrower `.hermes-loop/work/phase-1/control_workspace_quarantine.md` if no blueprint amendment is intended.
- Optionally update only `.hermes-loop/work/phase-1/result.md` and `.hermes-loop/work/phase-1/execute_review.md` to remove the unsupported "treat dirty blueprint as pre-existing" assertion and cite the adjustment/quarantine artifact.
- Write a fresh review artifact such as `.hermes-loop/work/phase-1/reviews/codex-review-rerun.md` and update `.hermes-loop/work/phase-1/review_verdict.json` after re-review.

Not allowed for this adjustment:

- No changes to `src/`, `tests/`, `docs/`, `benchmarks/`, `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, `AGENTS.md`, `CLAUDE.md`, launcher/reporter/config files, or benchmark data.
- No new `ack.json` until the rerun review passes.
- No claim of benchmark movement or runtime improvement from Phase 1.

## Re-review Requirement

Re-review is required. The current FAIL is valid until both blockers are resolved or explicitly quarantined. The rerun review should verify:

- `.hermes-loop/work/phase-1/ack.json` is absent or freshly created only after PASS.
- The dirty active control-file set is either clean or documented as outside Phase 1 by a GOD_ADJUST/quarantine artifact.
- `git diff -- src tests docs benchmarks .hermes-loop/state.json` remains empty.
- Phase artifacts still preserve separate LongMemEval/LoCoMo case taxonomies, conservative `source_hit`, v1 fallback, v3 default verification as future work, and kernel opt-in.

## Recommended Decision

Decision: `adjust`.

God should run `GOD_ADJUST`, not ACK and not a normal local repeat-only fix. A repeat can remove the stale ACK, but it cannot honestly solve the active control-file provenance problem without an adjustment/quarantine record. `pause` is not yet required because the runtime and state diffs are clean and the blockers are artifact/control-plane hygiene issues. If GOD_ADJUST cannot establish a conservative boundary for the dirty control files, then the next decision should be `pause`.
