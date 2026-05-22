# phase: phase-6

phase: phase-6
original_hypothesis: Phase 6 expected the main blocker to be the answer projection boundary: selected/rendered evidence needed durable citation IDs or explicit unsupported refusal.
triggering_evidence: The focused repeat fixed LoCoMo `conv-26_qa_010` but left `conv-26_qa_028` as `pass_to_fail` in `.memoryos/evals/phase6_answer_contract_repeat_locomo_30_locomo.json`; LongMemEval stayed `18/30` with no pass-to-fail.
case_examples: `conv-26_qa_028` expected `D7:5` / `D7:9`, rendered only `D4:11`, had `source_hit=false`, `source_recall=0.0`, empty `source_overlap_ids`, and remained `failure_class=retrieval_miss`.
decision: Split and narrow before repeat. Keep the Phase 6 citation contract plumbing, but block ACK and route the next work to LoCoMo expected-source preservation for `conv-26_qa_028`. Do not continue prompt-only tuning.
phases_advanced: none
phases_delayed: phase-7 kernel/tool work remains delayed until phase-6 has no LoCoMo pass-to-fail.
phases_added_or_removed: no new numbered phase is promoted; current phase-6 repeat scope is narrowed to source recovery / neighbor-session evidence preservation.
next_verification_command: `MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge --comparison-report .memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json --run-id phase6_god_adjust_locomo_30`
risk: A judge pass from semantically related non-expected evidence could hide a retrieval/source miss. Future reports must keep source overlap and pass-to-fail movement separate from judged answer quality.

## Rationale

The repeat showed that the answer contract can solve an evidence-present temporal refusal (`conv-26_qa_010`) without changing defaults or enabling the kernel. The remaining blocker is different: `conv-26_qa_028` does not have expected source overlap, so restoring a pass by relaxing the answer prompt would hide the miss that the active goal requires us to expose.

Next execution must start with a focused failing test that reproduces a LoCoMo query retrieving nearby `D7` evidence while dropping the expected `D7:5` / `D7:9` pair. The fix should be general neighbor/session evidence preservation, not a case-id rule, expected-answer leak, or source-hit accounting shortcut.
