# phase: phase-8

## Verdict

PASS

## Active Goal

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

## Context Bundle Use

The plan used `work/phase-8/context_bundle.md` as controlling context. It cites the bundle directly, follows the dispatch/spec derived from it, and treats older `work/phase-8/research.md` and `work/phase-8/reviews/codex-review.md` as stale unless superseded by fresh artifacts that cite the bundle.

## Findings

- PASS: Anti-demo gate is explicit. The plan defines RED as missing fresh Phase 8 evidence plus stale artifacts, and requires fresh verification/eval outputs before `promotion_decision.md`, `review_verdict.json`, or `ack.json`.
- PASS: v1 fallback and v3 default are preserved. The plan names `MEMORYOS_MEMORY_ARCH=v1` as the fallback to preserve and runs promotion evals with `MEMORYOS_MEMORY_ARCH=v3`.
- PASS: Kernel opt-in is preserved. The promotion eval commands do not set `MEMORYOS_AGENT_KERNEL=v1`, and the focused guard checks default-off kernel behavior.
- PASS: Benchmark overfitting risk is addressed. The plan forbids case-id hacks and expected-answer leaks, requires same-subset movement, and refuses invented fail-to-pass/pass-to-fail movement when a comparable baseline is missing.
- PASS: LoCoMo-specific risk is handled independently. The plan requires LoCoMo case groups, local-cap reporting, and clustering by conversation, temporal, speaker, and multi-hop behavior.
- PASS: Source grounding is separated from aggregate score. The plan requires retrieval/source movement, unsupported-answer handling, evidence-hit-answer-fail grouping, and an explicit statement that aggregate score alone is not the decision basis.
- PASS: Stale phase artifact handling is explicit. Existing Phase 8 stale artifacts are marked non-authoritative unless replaced by fresh outputs citing `work/phase-8/context_bundle.md`.

## Residual Notes For EXECUTE Lane

- If full-chain LLM answer/judge access fails, fallback no-LLM diagnostics must remain non-promotional and the decision must be `continue_targeted` or `hold`.
- `ack.json` must not be written unless `review_verdict.json.verdict` is `usable_ack` and both benchmark analyses satisfy the evidence contract.
