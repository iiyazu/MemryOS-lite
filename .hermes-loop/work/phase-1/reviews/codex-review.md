# phase: phase-1

# Codex Review Verdict - FAIL

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Blocking Findings

1. Stale Phase 1 ACK remains present and contradicts the active phase contract.

   Evidence: `.hermes-loop/work/phase-1/ack.json:2-5` still says `ACK`, `phase_name: Memory v3 Contracts`, and `target_state: legacy-stable`. The current context bundle says Phase 1 is "Letta Gap Matrix And Contract Decisions" and says ACK is only allowed if usable (`.hermes-loop/work/phase-1/context_bundle.md:3`, `.hermes-loop/work/phase-1/context_bundle.md:188-194`). `result.md` also says no ACK was written by the execute step (`.hermes-loop/work/phase-1/result.md:41`), but the stale ACK is still in the phase directory and can be consumed by automation.

   Impact: This is a stale phase artifact that can cause false advancement or a demo-only completion signal. It fails the "without demo-only phase completion" requirement.

   Required adjustment: Remove, replace, or quarantine the stale ACK through the owning lane before any PASS/ACK decision. Review lane must not write `ack.json`.

2. The workspace has active blueprint/orchestration/instruction diffs while Phase 1 claims no blueprint or runtime-behavior changes.

   Evidence: `git status --short` shows modified `.hermes-loop/blueprint.md`, `.hermes-loop/config.json`, `.hermes-loop/god_launcher.sh`, `.hermes-loop/god_loop_prompt.md`, `.hermes-loop/hermes_loop.py`, `.hermes-loop/hermes_reporter.py`, `AGENTS.md`, and `CLAUDE.md`. `git diff --name-only -- src tests docs benchmarks .hermes-loop/state.json .hermes-loop/blueprint.md AGENTS.md CLAUDE.md .hermes-loop/config.json .hermes-loop/god_launcher.sh .hermes-loop/god_loop_prompt.md .hermes-loop/hermes_loop.py .hermes-loop/hermes_reporter.py` reports those same non-runtime-code but active-control files. The context bundle forbids active docs/state/blueprint changes for Phase 1 (`.hermes-loop/work/phase-1/context_bundle.md:72-79`) and says no promoted amendment is active (`.hermes-loop/work/phase-1/context_bundle.md:104`). `result.md` claims no `.hermes-loop/blueprint.md` or runtime behavior changes (`.hermes-loop/work/phase-1/result.md:70-74`).

   Impact: Even though `src/`, `tests/`, `docs/`, `benchmarks`, and `.hermes-loop/state.json` are clean, the active controller/blueprint diffs are not harmless review artifacts. They change phase dispatch, model policy, benchmark commands, launcher invocation, reporter behavior, and agent instructions. That invalidates the contract-only/no-behavior-change claim unless these diffs are explicitly proven pre-existing and excluded from Phase 1.

   Required adjustment: Repeat/adjust the phase gate after either reverting/separating those non-phase diffs or documenting them as a prior promoted amendment outside Phase 1. Current review cannot PASS with this contradictory workspace state.

## Non-Blocking Checks

- Behavioral regression in MemoryOS runtime paths: not observed from the current diff. `git diff -- src tests docs benchmarks .hermes-loop/state.json` is empty.
- v1 fallback: preserved as a contract in `plan_final.md` and `result.md`; no runtime diff touched it.
- v3 default: preserved as a contract and explicitly marked for future real-path verification. No runtime diff proves or disproves it in this phase.
- Kernel default: no `src/` diff enables the kernel. The phase artifacts keep `MEMORYOS_AGENT_KERNEL=v1` opt-in.
- Source grounding: no regression observed. The matrix and plan keep `source_hit` conservative as final projection/source overlap, not pure evidence localization.
- LoCoMo-specific failure modes: not hidden. LoCoMo retrieval/scope misses remain separated from LongMemEval answer-use failures.
- Prompt-hack / benchmark-overfitting risk: medium-low in the phase artifacts because case IDs are used as diagnostic anchors and future RED tests, not as implementation rules. Risk remains because the contract set is based on a 5-case smoke and must be checked with per-case shared-seed evals later.
- Missing failing tests: acceptable for Phase 1 because it is contract-only, but the next implementation phase must start from RED tests or concrete failing benchmark cases.
- Context bundle coverage: used by `research.md`, `brainstorm.md`, `spec.md`, `plan.md`, `plan_review.md`, `plan_final.md`, `letta_gap_matrix.md`, `result.md`, and `execute_review.md`.

## Decision Recommendation

FAIL. Recommend `repeat/adjust` before ACK: clear the stale ACK and resolve or explicitly segregate the active blueprint/orchestration/instruction diffs. After that, rerun this review against a clean contract-only phase state.
