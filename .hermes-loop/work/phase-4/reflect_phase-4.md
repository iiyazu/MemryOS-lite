# phase: phase-4

# Reflection: Phase 4

## Blueprint Amendment

Phase-4 completion does not require a promoted blueprint amendment.

Reason: the existing blueprint already anticipated this decision point after a mandatory 30-50 case milestone, and the phase-4 result does not justify changing phase order. Phase 4 reached usable diagnostic plumbing for scoped archive eligibility, append-only public diagnostics, v1 isolation, v3 default preservation, and kernel default-off preservation. It did not produce benchmark-quality evidence or a LoCoMo improvement claim.

A `work/phase-4/blueprint_amendment.md` should only be written if God decides to change active execution order. Current evidence supports a narrowed phase-5 dispatch, not a phase reorder.

## Evidence For Phase 5/6 Ordering

New evidence that matters:

- LongMemEval 30 full-chain v3 run: 17 pass / 13 fail.
- LoCoMo 30 full-chain v3 run: 0 pass / 30 fail.
- LoCoMo failure classes are split: 11 retrieval misses, 10 context-missing-evidence cases, and 9 evidence-hit-answer-fail cases.
- Archival eligibility totals are zero in both 30-case reports because benchmark cases did not seed attached archives. This proves diagnostic plumbing was exercised, not archive-quality improvement.
- Phase-4 archival selected diagnostics are now post-budget, so selected passage IDs/source refs no longer claim budget-dropped passages.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off, and v1 fallback remains isolated from v3 archival diagnostics.

This evidence does not satisfy the Phase 5 dynamic rule for immediately prioritizing Phase 6, because evidence does not reliably enter the answerer on LoCoMo. Most LoCoMo cases still fail before or at context inclusion, not only at answer projection.

## LoCoMo Decision

LoCoMo 0/30 should trigger narrow, not repeat, reorder, or broad continue-as-planned.

Recommended action:

- Advance to Phase 5.
- Narrow Phase 5 first dispatch around LoCoMo temporal/session context accounting and query-to-evidence-to-final-context traceability.
- Keep Phase 6 after Phase 5 unless a focused Phase 5 run shows correct evidence reliably reaches answerer input while answers still fail.
- Do not repeat Phase 4: scoped archive eligibility and append-only diagnostics are usable, and the LoCoMo failures are visible rather than hidden.
- Do not claim benchmark improvement from phase-4 results.

Concrete LoCoMo cases to carry into Phase 5:

- Retrieval miss: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_014`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`, `conv-26_qa_028`.
- Context missing evidence: `conv-26_qa_009`, `conv-26_qa_013`, `conv-26_qa_015`, `conv-26_qa_016`, `conv-26_qa_021`, `conv-26_qa_023`, `conv-26_qa_024`, `conv-26_qa_026`, `conv-26_qa_029`, `conv-26_qa_030`.
- Evidence-hit-answer-fail: `conv-26_qa_001`, `conv-26_qa_006`, `conv-26_qa_007`, `conv-26_qa_010`, `conv-26_qa_012`, `conv-26_qa_017`, `conv-26_qa_018`, `conv-26_qa_022`, `conv-26_qa_027`.

## Next Minimum Verification Command

Use the smallest command that rechecks phase-4 guardrails before phase-5 planning depends on them:

```bash
uv run pytest tests/test_context_composer.py::test_v3_composer_does_not_report_budget_dropped_archival_passages_as_selected tests/test_public_benchmarks.py::test_public_benchmark_v3_archival_scope_diagnostics_are_append_only tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_engine.py::test_explicit_v1_build_context_excludes_v3_archival_scope_diagnostics -q
```

After that passes, Phase 5 should add a RED test for LoCoMo temporal/session evidence preserving enough neighboring context before changing composer behavior.
