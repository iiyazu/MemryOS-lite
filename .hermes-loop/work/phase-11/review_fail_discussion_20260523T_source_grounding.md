# phase: phase-11

## Root Cause

This FAIL is best treated as a narrow repeat, not a GOD_ADJUST.

The blocker is a localized source-grounding regression on `conv-26_qa_007`:

- the expected source `conv-26_qa_007:conv-26:D2:7` is still retrieved, selected, rendered, and present in `answer_evidence`;
- the failure happens at the final citation projection step, where the report row carries shortened cited ids like `D2:7` instead of the exact allowed source id;
- `case_diagnostics.evidence_handoff.failure_boundary` is `citation_drop`, which means the handoff is intact until citation formatting/projection;
- the judge verdict is still `pass`, so this is a hidden source-grounding regression, not a broad benchmark collapse.

The stale phase summaries are a separate problem, but they are still local: `result.md`, `execute_review.md`, and `case_matrix.md` omit the unsupported-answer row and therefore hide the same-case regression surface. That is a reporting refresh failure, not a controller/goal failure.

## Recommended Action

Do a narrow repeat in Phase 11.

Fix or explicitly gate the exact citation contract for the affected LoCoMo row, add a focused regression test that fails on shortened citations, regenerate the 30-case reports, and refresh the phase artifacts from the actual report rows.

Escalate to GOD_ADJUST only if the fix cannot be localized to citation projection/reporting and instead requires changing the phase objective, controller behavior, or benchmark contract.

## Non-Goals

- Do not retune broad retrieval.
- Do not enable `MEMORYOS_AGENT_KERNEL=v1` by default.
- Do not change benchmark scoring or judge semantics.
- Do not hide `conv-26_qa_007` or relabel the regression as an aggregate-only improvement.
- Do not add case-id-specific hacks or answer overrides.
- Do not treat stale phase artifacts as acceptable ACK evidence.

## Minimum Verification

1. Add a focused test that fails when a pass row emits shortened LoCoMo citations instead of the exact allowed source id.
2. Re-run the public benchmark tests that cover answer evidence, citation contracts, and failure replay.
3. Re-run the 30-case LongMemEval and LoCoMo reports with comparison reports preserved.
4. Confirm `conv-26_qa_007` is either restored to `supported_cited_answer` with the exact citation id or remains explicitly surfaced as `unsupported_answer` in all phase summaries.
5. Refresh `result.md`, `execute_review.md`, and `case_matrix.md` from the actual report rows before any ACK decision.
