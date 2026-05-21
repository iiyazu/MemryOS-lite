# phase: phase-2

# Context Bundle - Phase 2 Evidence Harness And Failure Taxonomy

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Phase Objective

Phase 2 builds the diagnostic/evidence harness that separates retrieval, evidence, context rendering, answer projection, judge behavior, and kernel trace signals before any optimization.

Target chain components:

```text
public benchmark case
  -> query tags and retrieval evidence ids
  -> selected context ids
  -> rendered answer-context evidence ids
  -> projected answer citations / unsupported status
  -> judge result
  -> case-level taxonomy
```

This phase exists so later retrieval/scope work and answer-projection work can be prioritized from case-level evidence instead of aggregate pass rate.

## Why This Phase Exists Now

Phase 1 reached `ack_level=usable` as a contract-only Letta gap matrix and decision phase in commit `51e29ba`. It did not improve benchmark behavior and did not change runtime code.

Phase 1 reflection recommended `no_adjustment`: keep Phase 2 before archive/scope optimization or answer projection because current smoke cases show split bottlenecks:

- LongMemEval sampled pressure is mostly `evidence_hit_answer_fail`.
- LoCoMo sampled pressure is mostly `retrieval_miss` / retrieval-scope miss.
- `source_hit` remains final projection/source overlap, not pure evidence localization.
- Kernel trace presence remains opt-in audit evidence, not answer-quality evidence.

## Current Hypothesis

The next useful behavior-changing phase is not retrieval optimization or answer prompt tuning. The next useful phase is a report/test contract that proves where each case fails.

Disconfirming evidence:

- The existing public report already exposes all required IDs/statuses and tests can prove the taxonomy without code changes.
- Adding diagnostics would require benchmark-specific answer leaks or case-id rules.
- Diagnostics cannot be emitted without breaking legacy public report compatibility.
- Phase 2 starts optimizing retrieval, answer prompts, archive scope, or kernel tools before the taxonomy can distinguish failure classes.
- Full-chain LLM judge is unavailable and no equivalent milestone evidence is recorded.

## Scope

In scope:

- Read this `context_bundle.md` before any other phase-local artifact.
- Discard old Phase 2 artifacts whose first line or schema belongs to the obsolete Recall/Core-Memory phase chain.
- Add or harden public benchmark diagnostics needed to classify each case.
- Preserve existing report compatibility while adding new diagnostic fields.
- Add failing tests before production changes.
- Separate `retrieval_miss`, `evidence_hit_answer_fail`, `unsupported_answer`, `supported_cited_answer`, `pass_to_fail`, `fail_to_pass`, and `judge_questionable`.
- Keep LongMemEval and LoCoMo analysis separate.
- Treat `source_hit` as final projection/source overlap, not pure retrieval localization.

Non-goals:

- No archive retrieval optimization or attachment-scope implementation unless a missing diagnostic blocks taxonomy.
- No answer prompt tuning or answer-quality optimization unless a missing diagnostic blocks taxonomy.
- No core-memory mutation expansion.
- No kernel tool expansion.
- No Letta runtime dependency.
- No benchmark case-id hacks, expected-answer leaks, or aggregate-only claims.
- No default kernel enablement.

## Lane Write Protocol

- `execute_lane` may write `src/`, `tests/`, and phase-local work artifacts.
- `plan_lane` may write only phase-local planning files after reading this bundle.
- `research_lane` may write only phase-local `research.md`.
- `review_lane` is read-only except `work/phase-2/reviews/*.md` and review verdict output if requested by God.

All new phase-local markdown must start with `# phase: phase-2`. All JSON artifacts must contain `"phase": "phase-2"`.

## Active Blueprint Sections

Use `.hermes-loop/blueprint.md` sections:

- Purpose and Current Baseline.
- Hard Constraints.
- Completion Levels.
- Required ACK Evidence.
- Context Bundle Requirement.
- Phase 2 - Evidence Harness And Failure Taxonomy.
- Dynamic Blueprint Amendment Protocol.
- Stop Conditions.

No blueprint adjustment was promoted after Phase 1. `work/phase-1/reflect_phase-1.md` recommends `no_adjustment`.

## Required Read-First Files

Phase-local source of truth:

- `.hermes-loop/work/phase-2/context_bundle.md`
- `.hermes-loop/work/phase-2/god_dispatch.json`
- `.hermes-loop/work/phase-1/letta_gap_matrix.md`
- `.hermes-loop/work/phase-1/plan_final.md`
- `.hermes-loop/work/phase-1/reflect_phase-1.md`
- `.hermes-loop/work/phase-1/control_workspace_quarantine.md`
- `.hermes-loop/work/phase-1/ack.json`
- `.hermes-loop/work/phase-0/baseline_case_matrix.md`

MemoryOS files:

- `src/memoryos_lite/config.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/schemas.py`
- `src/memoryos_lite/evals.py`
- `src/memoryos_lite/evals_advanced.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/agent_answer_eval.py`
- `src/memoryos_lite/llm_judge.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/agent_kernel.py`
- `src/memoryos_lite/retrieval/query_analyzer.py`
- `src/memoryos_lite/retrieval/episode_searcher.py`
- `src/memoryos_lite/retrieval/recall_pipeline.py`
- `src/memoryos_lite/retrieval/archival_searcher.py`

Tests:

- `tests/test_public_benchmarks.py`
- `tests/test_agent_answer_eval.py`
- `tests/test_llm_judge.py`
- `tests/test_context_composer.py`
- `tests/test_agent_kernel.py`
- `tests/test_evals.py`

Docs:

- `docs/public-benchmark-diagnosis.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`

Letta reference is already summarized in Phase 1. Re-open Letta files only if a diagnostic contract needs a precise Letta term.

## Current Benchmark Baseline

Phase 0 deterministic no-LLM smoke:

- LongMemEval limit 5: `1/5` projected.
  - pass: `1e043500`
  - retrieval miss: `58bf7951`
  - evidence hit but answer fail: `e47becba`, `118b2229`, `51a45a95`
- LoCoMo limit 5: `0/5` projected.
  - retrieval/scope misses: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`
  - evidence hit but answer fail: `conv-26_qa_001`
- Opt-in kernel LoCoMo limit 1: trace sequence present only with `MEMORYOS_AGENT_KERNEL=v1`; answer still projected fail.

These are smoke diagnostics, not global benchmark claims.

## Known Pass-To-Fail Risks

- Treating aggregate pass rate as sufficient evidence.
- Treating `source_hit` as pure retrieval localization.
- Hiding LoCoMo retrieval/scope misses behind LongMemEval answer-use failures.
- Hiding answer-use failures behind retrieval-hit metrics.
- Losing selected evidence between context composition and answer projection.
- Adding diagnostics that break legacy public report consumers.
- Creating case-id or expected-answer hacks.
- Enabling the v3 kernel by default.

## Stale Phase-2 Artifact Warning

Old `work/phase-2/brainstorm.md`, `spec.md`, `plan.md`, `plan_final.md`, `result.md`, `execute_review.md`, and `ack.json` belonged to the obsolete Recall/Core-Memory phase chain. They were deleted from the active path before this dispatch. Do not restore or consume them.

## Expected Tests And Eval Commands

Start with focused RED tests, then implementation, then focused regression:

```bash
uv run pytest tests/test_public_benchmarks.py tests/test_agent_answer_eval.py tests/test_llm_judge.py -q
```

Baseline checks before ACK:

```bash
uv run pytest -q
uv run ruff check .
```

Mandatory milestone eval unless blocked by provider/data availability:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 30
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30
```

If LLM answer/judge cannot run, record the exact blocker and run deterministic no-LLM smoke only as fallback evidence. Do not call the mandatory milestone satisfied.

## Anti-Demo Usable ACK Criteria

Phase 2 may ACK only if:

- diagnostics are wired into the real v3/public benchmark path;
- tests prove retrieval miss and evidence-hit-answer-fail are distinguishable;
- report compatibility is preserved;
- 30-case LongMemEval and LoCoMo full-chain LLM judge runs are completed or a concrete blocker is recorded;
- case-level analysis lists fail-to-pass, pass-to-fail, unchanged fail, retrieval miss, evidence-hit-answer-fail, context missing evidence, unsupported/overconfident answer, and judge-questionable cases separately for LongMemEval and LoCoMo;
- source/evidence metrics remain separate from final answer pass rate;
- v1 fallback, v3 default, and kernel opt-in remain intact;
- no benchmark improvement is claimed from diagnostics alone.

## Control Workspace Quarantine

Dirty active-control files remain outside phase ownership:

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

Do not use those dirty files as Phase 2 implementation evidence, benchmark evidence, or ACK evidence unless God explicitly resolves the quarantine.
