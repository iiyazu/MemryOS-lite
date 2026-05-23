# phase: phase-11

# Phase 11 Plan Review: PASS

Context bundle: `.hermes-loop/work/phase-11/context_bundle.md`.
Reviewed files:

- `.hermes-loop/work/phase-11/context_bundle.md`
- `.hermes-loop/work/phase-11/god_dispatch.json`
- `.hermes-loop/work/phase-11/brainstorm.md`
- `.hermes-loop/work/phase-11/spec.md`
- `.hermes-loop/work/phase-11/plan.md`
- `.hermes-loop/work/phase-11/plan_review.md`
- `.hermes-loop/blueprint.md`

## Verdict

PASS. The updated plan satisfies the Phase 11 planning gate and fixes the prior blocking heartbeat-contract issue. `plan_final.md` may be written from the accepted plan with a PASS header.

## Review Checklist

- Active goal: PASS. The plan targets the real v3/public benchmark handoff path and explicitly avoids demo-only completion, hidden case-level regressions, and kernel-default changes.
- Anti-demo gate: PASS. It requires RED evidence, real `memoryos eval public` execution, case matrix artifacts, comparison reports, heartbeat files, and review before ACK eligibility.
- TDD requirement: PASS. It starts with concrete RED tests before production changes and requires RED output to be recorded in `.hermes-loop/work/phase-11/red_result.md`.
- v1 fallback: PASS with execution verification required. The diagnostic changes are append-only, default answer-evidence ids preserve existing source behavior, and focused/full tests must keep fallback behavior green.
- v3 default: PASS. The plan keeps the default path on `MEMORYOS_MEMORY_ARCH=v3` and requires public rows to emit v3 diagnostics without extra flags.
- Kernel opt-in: PASS. The plan preserves `MEMORYOS_AGENT_KERNEL=v1` as opt-in and requires default rows to keep `kernel_trace_events == []`.
- Same-case benchmark evidence: PASS. The milestone commands use Phase 10 comparison reports, require fail-to-pass/pass-to-fail/unchanged-fail lists, and separate retrieval/source movement from judged-answer movement.
- Benchmark overfitting: PASS. The plan prohibits case-id branches, expected-answer leaks, expected-source-specific logic, benchmark lexical hacks, scoring changes, and prompt-only promotion without diagnostics.
- Context-bundle coverage: PASS. The plan cites the bundle, follows the required scope, includes the required read/verification/eval gates, and does not contradict the bundle's non-goals.
- Phase binding: PASS. The plan starts with `# phase: phase-11` and requires downstream Markdown/JSON artifacts to carry phase binding.
- Blocking heartbeat fixes: PASS. The plan now requires `.hermes-loop/work/phase-11/eval_heartbeat_longmemeval.json` and `.hermes-loop/work/phase-11/eval_heartbeat_locomo.json` as valid single JSON objects, includes the required fields, updates them during running evals, rejects `.jsonl` substitutes, and blocks promotion on failed/stalled/missing final evidence.

## Execution Notes

- The final heartbeat may be treated as promotion evidence only when the final report exists and the execute/review artifacts verify the expected row count.
- If LLM provider access is unavailable, deterministic/no-LLM fallback evidence may be recorded, but it must not satisfy the full-chain milestone gate.
- Remaining retrieval misses must stay visible in `case_matrix.md`; answer-quality movement must not be collapsed into retrieval/source movement.
