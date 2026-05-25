# Hermes Main Loop History: Phase 0-18

Archived at: 2026-05-24

## Scope

The original single-mainline Hermes loop has completed through `phase-18`.
`state.json` is currently `DONE` with `current_phase_idx=19`.

This history package makes phase 0-18 the baseline for the new multi-god
feature overlay. It does not start new execution by itself.

## Baseline

- MemoryOS Lite remains an eval-driven, source-attributed Agent/RAG memory
  prototype, not production MemoryOS.
- Default memory architecture is `v3`.
- `MEMORYOS_MEMORY_ARCH=v1` remains the explicit fallback.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
- SQLite is the authoritative store.
- Qdrant/vector paths remain optional experiments.

## Accepted Evidence

Phase 8:

- LongMemEval 50 full-chain LLM judge: 47 pass / 3 fail.
- LoCoMo 50 full-chain LLM judge: 30 pass / 20 fail.
- This is accepted governance baseline evidence, not final graduation.

Phase 17:

- LoCoMo r3 baseline: 8 pass / 2 fail.
- LoCoMo r3 opt-in repair-smoke: 8 pass / 2 fail.
- `fail_to_pass=[]`.
- `pass_to_fail=[]`.
- Same-slice repair smoke is diagnostic only.
- Promotion gate remained unsatisfied.

Phase 18:

- Governance-only phase.
- ACK usable.
- Review PASS.
- Decision: `continue_targeted`.
- No product behavior changed.

## Continuing Bottlenecks

- LoCoMo remains the controlling bottleneck.
- `conv-26_qa_008` remains a useful retrieval-miss case.
- `conv-26_qa_006` remains a useful evidence-hit-answer-fail case.
- `conv-26_qa_002` through `conv-26_qa_005` show source-miss judge-pass risk.
- LongMemEval-only evidence must not be used to claim chain-level improvement.

## New Control Mode

Future feature work should use optional `xmuse/feature_lanes.json`.

`master_god`:

- owns integration;
- resolves cross-feature conflicts;
- decides merge timing;
- requires integrated tests before merge.

`slave_god`:

- owns one feature branch/worktree;
- may use plan/execute/review/subagent workflow inside that feature boundary;
- reports result, review verdict, ACK, branch, worktree, and merge target.

Merge remains blocked unless the feature has:

- usable ACK;
- PASS review;
- result artifact;
- clean worktree;
- documented target branch;
- integrated test evidence;
- no v3 default regression;
- no v1 fallback regression;
- kernel still opt-in;
- no benchmark leakage.
