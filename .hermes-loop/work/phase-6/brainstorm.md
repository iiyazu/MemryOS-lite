# phase: phase-6

# Brainstorm: Answer Projection And Citation Contract

Context source: `.hermes-loop/work/phase-6/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Problem Frame

Phase 5 made v3 final-context trace and component accounting visible in the real public benchmark path, but the 30-case reports still classified every row as unsupported at answer level. Phase 6 should not claim benchmark improvement from a prompt tweak. It should define and wire a durable answer evidence contract: selected/rendered evidence gets stable IDs, answers cite those IDs, unsupported or no-evidence cases refuse explicitly, and reports preserve case-level failure separation.

Letta semantics to borrow, design-only: stable block/passage IDs, rendered memory with metadata, passage/source identity, tool/approval trace durability, and per-component context accounting. Do not port Letta internals or add a Letta dependency.

## Options

### Option A: Structured evidence contract at the public benchmark answer boundary

Introduce a small structured evidence representation for `run_public_benchmark(... baseline="memoryos_lite")`, render it into deterministic projection and LLM answer prompts, validate answer citations against rendered IDs, and extend diagnostics append-only.

Tradeoffs:

- Best match for Phase 6 because it touches the retrieval-to-answer boundary directly.
- Keeps retrieval, storage, v3 composer, v1 fallback, and kernel defaults out of scope.
- Requires careful tests so deterministic no-LLM output remains useful and LLM failures are not hidden.

### Option B: Prompt-only LLM answerer change

Keep `output.sources` as loose text and update `PublicAnswerer` instructions to ask the model for citations.

Tradeoffs:

- Fastest code change.
- Demo-only risk is high: it can look better on happy-path LLM output while citations still point to unrendered IDs or deterministic projected answers remain unsupported.
- Does not satisfy the context bundle requirement for projected/no-LLM diagnostics.

### Option C: Add a post-hoc citation normalizer

Leave answer generation unchanged, then append citations after the fact by matching answer text to rendered evidence snippets.

Tradeoffs:

- Could reduce unsupported classifications without changing answerer input.
- High overfitting and masking risk: post-hoc citations can make unsupported answers appear grounded even when the answerer did not use evidence.
- Hard to keep LoCoMo temporal/session grounding honest.

## Choice

Choose Option A.

The execute lane should make selected/rendered evidence an explicit input contract, not just prompt decoration. Deterministic projection should cite selected evidence IDs itself. The LLM answerer should receive structured evidence with allowed IDs and be instructed to cite only those IDs or refuse. Diagnostics should validate the final answer against the rendered evidence IDs and report missing, unsupported, no-evidence, and judge-questionable cases separately.

## Risks

- Citation syntax can collide with existing answer text. Mitigation: keep a narrow `[source_id]` contract and validate only bracketed source IDs against rendered evidence IDs.
- Deterministic projection may cite selected evidence but still fail answer quality. Mitigation: preserve `evidence_hit_answer_fail` as distinct from `unsupported_answer`.
- LoCoMo date/session answers may regress if the structured rendering drops timestamps or session IDs. Mitigation: include session/date metadata when available and add a temporal LoCoMo test.
- Aggregate scores may move without proving the contract helped. Mitigation: milestone reports must list LongMemEval and LoCoMo case movements, pass-to-fail, fail-to-pass, unsupported citations, and evidence-hit-answer-fail separately.
- Provider access may be unavailable for full-chain milestone eval. Mitigation: record blocker and run deterministic no-LLM smoke only as fallback, without treating it as the milestone gate.

## Demo-Only Definition

This phase is demo-only if any of the following are true:

- citations are required only in a prompt but not validated against rendered evidence IDs;
- projected/no-LLM answers remain uncited or hallucinate no-evidence answers;
- diagnostics collapse retrieval miss, context missing evidence, unsupported citation, and answer fail into one failure class;
- changes run only through fixtures or a side helper, not the real `run_public_benchmark(... baseline="memoryos_lite")` path;
- reports show only aggregate pass rate and omit case-level pass-to-fail/fail-to-pass lists;
- `MEMORYOS_AGENT_KERNEL=v1` becomes enabled by default or required for Phase 6 success.
