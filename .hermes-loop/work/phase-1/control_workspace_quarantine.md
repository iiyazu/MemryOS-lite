# phase: phase-1

# Control Workspace Quarantine - Phase 1

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Decision

This is a phase-local GOD_ADJUST boundary, not an ACK and not a promoted blueprint change.

Phase 1 may be reviewed only for the current phase-local contract artifacts under `.hermes-loop/work/phase-1/`. The dirty active-control files listed below remain outside Phase 1 ownership and must not be treated as Phase 1 implementation evidence, benchmark evidence, or ACK evidence.

## Triggering Evidence

The Phase 1 review failed with two blockers:

- stale `.hermes-loop/work/phase-1/ack.json` could falsely signal completion;
- active blueprint/orchestration/instruction files were dirty while Phase 1 claimed contract-only/no-control-file changes.

Current runtime-owned diff check remains clean:

```bash
git diff -- src tests docs benchmarks .hermes-loop/state.json
```

The current dirty active-control set is:

```text
.hermes-loop/blueprint.md
.hermes-loop/config.json
.hermes-loop/god_launcher.sh
.hermes-loop/god_loop_prompt.md
.hermes-loop/hermes_loop.py
.hermes-loop/hermes_reporter.py
AGENTS.md
CLAUDE.md
```

Current diff stat for that set:

```text
8 files changed, 1003 insertions(+), 1018 deletions(-)
```

## Boundary

The dirty control files are not proven by git provenance to predate Phase 1 execution. Therefore Phase 1 must not assert that they are harmless or already promoted.

For the purpose of re-review, this artifact establishes a narrower boundary:

- Phase 1 did not modify `src/`, `tests/`, `docs/`, `benchmarks/`, or `.hermes-loop/state.json`.
- Phase 1 does not claim the active control workspace is clean.
- Phase 1 does not claim benchmark movement, runtime improvement, blueprint promotion, launcher behavior changes, reporter behavior changes, or instruction-policy changes.
- Review must judge only whether the current phase-local contract artifacts satisfy the active goal without false ACK, hidden regressions, or kernel-default changes.
- The dirty control files remain a separate workspace risk for commit/promotion decisions.

## ACK Impact

The stale `ack.json` was deleted from the active ACK path. A new `.hermes-loop/work/phase-1/ack.json` may be written only after a fresh review passes and the ACK contract can be filled with evidence.

## Adjustment Record

Original hypothesis:

```text
Phase 1 can complete as contract/evidence planning only, without runtime or control-plane behavior changes.
```

Triggering evidence:

```text
review_verdict.json reported stale active ACK plus dirty active-control files contradicting the no-control-change claim.
```

Affected phase:

```text
phase-1
```

New hypothesis:

```text
Phase 1 may still complete as contract/evidence planning only if stale ACK is removed and dirty active-control files are explicitly excluded from Phase 1 ownership and ACK evidence.
```

Changed ordering or scope:

```text
No phase reordering. Scope is narrowed to phase-local contract artifacts plus explicit control-workspace quarantine.
```

Next minimum verification command:

```bash
python -m json.tool .hermes-loop/work/phase-1/god_dispatch.json
python -m json.tool .hermes-loop/work/phase-1/review_verdict.json
test ! -e .hermes-loop/work/phase-1/ack.json
test "$(sed -n '1p' .hermes-loop/work/phase-1/control_workspace_quarantine.md)" = "# phase: phase-1"
git diff -- src tests docs benchmarks .hermes-loop/state.json
```
