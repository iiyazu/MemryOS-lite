# phase: phase-2

# Phase 2 Reflection

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Blueprint Adjustment

No blueprint adjustment is needed now.

Phase 2 satisfied the diagnostic-harness shape described in the context bundle: diagnostics are wired into the real public benchmark path, reports remain append-only, v3 remains the default architecture, explicit v1 fallback remains available, and the v3 kernel remains opt-in. The next work should execute the existing blueprint sequence from diagnostic evidence into targeted behavior changes, not amend the blueprint to claim benchmark improvement from this phase.

## Original Phase 2 Hypothesis

Original hypothesis: the next useful phase was not retrieval optimization or answer prompt tuning. It was a report/test contract that proves where each case fails across retrieval, selected context, rendered answer context, answer support, judge result, and movement status.

Evidence supports that hypothesis for phase completion. The implementation added `case_diagnostics`, `failure_class`, `movement_status`, `answer_support_status`, and `judge_status` to the real `run_public_benchmark()` path, added comparison-report movement handling, and preserved report compatibility. Verification recorded `33 passed` for focused public benchmark / answer eval / judge tests, `366 passed, 1 warning` for the full suite, `ruff check` clean, and full-chain 30-case LLM answer/judge reports for both LongMemEval and LoCoMo.

This evidence does not support a global benchmark-improvement claim. Phase 2 is diagnostic-only.

## Triggering Evidence

LongMemEval limit 30 full-chain report `.memoryos/evals/public_20260521_213550_longmemeval.json`:

- Judge pass rate: `18/30`.
- Failure taxonomy: `retrieval_miss=3`, `context_missing_evidence=12`, `unsupported_answer=15`, `evidence_hit_answer_fail=0`, `supported_cited_answer=0`, `judge_questionable=0`.
- Movement coverage is limited: Phase 0 comparison covers only `5/30`; `25/30` are `new_case_no_baseline`.
- No `pass_to_fail` was recorded, but this does not prove broad improvement because most rows lack prior movement evidence.

LoCoMo limit 30 full-chain report `.memoryos/evals/public_20260521_214906_locomo.json`:

- Judge pass rate: `7/30`; this remains the main weakness and must not be hidden behind LongMemEval.
- Failure taxonomy: `retrieval_miss=11`, `context_missing_evidence=10`, `unsupported_answer=9`, `evidence_hit_answer_fail=0`, `supported_cited_answer=0`, `judge_questionable=0`.
- Movement coverage is limited: Phase 0 comparison covers only `5/30`; `25/30` are `new_case_no_baseline`.
- `conv-26_qa_001` is `fail_to_pass`, while `conv-26_qa_002` through `conv-26_qa_005` remain `unchanged_fail`; no `pass_to_fail` was recorded in the covered subset.

Source-grounding taxonomy caveats:

- `source_hit` / `source_accuracy` must not be read as pure retrieval localization. The diagnostic fields distinguish retrieval candidates, selected context ids, rendered answer-context ids, answer support status, and judge status.
- `failure_class` is a source-grounding diagnostic class, not the same thing as judge verdict. Judge-passing rows can still be `unsupported_answer`, `context_missing_evidence`, or `retrieval_miss` when the answer passes without a grounded source chain.
- Current full-chain answers do not cite sources, so many judge-pass rows remain `unsupported_answer`; this is a source-grounding gap, not a prompt-quality win.
- Review noted that `selected_context_ids` can include non-evidence task ids. This did not block Phase 2 classification, but the next phase should avoid treating those ids as proof that expected evidence was selected.

## Recommended Next Phase Ordering

1. Preserve the Phase 2 diagnostic harness as the gate. Every behavior-changing phase should compare against the Phase 2 LongMemEval and LoCoMo reports and list `fail_to_pass`, `pass_to_fail`, unchanged failures, and new/no-baseline rows separately.
2. Target LoCoMo retrieval and context-scope first. The 7/30 LoCoMo result, with `11` retrieval misses and `10` context-missing-evidence cases, is the clearest blocker to benchmark usability.
3. In the same retrieval/context phase, track LongMemEval `context_missing_evidence` regressions, but do not optimize only for LongMemEval because it can mask LoCoMo weakness.
4. After evidence is reliably retrieved and rendered, run a separate answer-projection/source-citation phase. That phase should focus on turning rendered evidence into cited, supported answers, not on judge-passing unsupported answers.
5. Keep kernel changes out of the default path. Kernel trace may remain an opt-in audit signal under `MEMORYOS_AGENT_KERNEL=v1`, not a default benchmark dependency.

## Next Minimum Verification Command

For the next behavior-changing phase, the minimum benchmark gate should start with the weak benchmark and compare against this Phase 2 report:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge \
  --comparison-report .memoryos/evals/public_20260521_214906_locomo.json
```

If provider access is unavailable, record the exact blocker and run deterministic no-LLM diagnostics only as fallback evidence. Do not call that fallback a milestone-equivalent full-chain verification.

## Stop Or Pause Conditions

- Any default enablement of `MEMORYOS_AGENT_KERNEL=v1`.
- Any loss of default v3 routing or explicit `MEMORYOS_MEMORY_ARCH=v1` fallback.
- Any benchmark case-id hack, expected-answer leak, or benchmark-specific answer shortcut.
- Any report compatibility break that drops legacy public report fields or omits `case_diagnostics`.
- Any hidden case-level regression, especially LoCoMo `pass_to_fail` or increased retrieval/context-missing failures against the Phase 2 report.
- Any claim of global benchmark improvement without same-case LongMemEval and LoCoMo evidence.
- Any attempt to promote judge-passing but uncited/unsupported answers as source-grounded wins.
