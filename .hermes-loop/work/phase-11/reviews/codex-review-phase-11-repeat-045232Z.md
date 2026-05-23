# phase: phase-11

# Review: Phase 11 Repeat 045232Z

Verdict: FAIL. ACK eligible: false.

Context bundle used first: `.hermes-loop/work/phase-11/context_bundle.md`.

## Blocking Findings

1. Source-grounding regressed on a judged-pass LoCoMo case and the regression is hidden by the current phase summaries.

   Current report evidence: `.memoryos/evals/phase11_locomo30_handoff_20260523T045232Z_locomo.json`, case `conv-26_qa_007`.

   - Current verdict: `pass`, `movement_status=unchanged_pass`, but `failure_class=unsupported_answer`.
   - Current citation diagnostics: `citation_contract_status=unsupported_citation`; `cited_source_ids=["D2:7","D6:16","D8:32","D10:12","D18:17"]`; all cited IDs are in `unsupported_citation_ids`.
   - Current handoff: expected source `conv-26_qa_007:conv-26:D2:7` was retrieved, selected, rendered, and present in answer evidence, but `evidence_handoff.failure_boundary=citation_drop`.
   - Phase 10 comparison row for the same case was `verdict=pass`, `failure_class=supported_cited_answer`, and cited the full supported ID `[conv-26_qa_007:conv-26:D2:7]`.

   This violates the Phase 11 source-grounding and no-hidden-regressions gate even though the LLM judge verdict did not flip to fail.

2. Current phase artifacts are stale/inaccurate for the same gate.

   `.hermes-loop/work/phase-11/case_matrix.md` lines 42-55 summarize LoCoMo as `supported_cited_answer=21`, `retrieval_miss=7`, `evidence_hit_answer_fail=4`, with no unsupported/refusal/citation issue. The actual current report counts are `supported_cited_answer=18`, `retrieval_miss=7`, `evidence_hit_answer_fail=4`, and `unsupported_answer=1`; the unsupported row is `conv-26_qa_007`.

   `.hermes-loop/work/phase-11/result.md` lines 76-79 and `.hermes-loop/work/phase-11/execute_review.md` lines 65-70 also omit `conv-26_qa_007`, so the ACK-facing artifacts do not preserve the full case-level regression surface.

3. Missing regression coverage allowed the source-citation regression through.

   The repeat-fix tests cover compact prompt metadata and qualifier retry behavior, but there is no focused failing test that a pass row with expected source `conv-26_qa_007:conv-26:D2:7` must preserve exact allowed citation IDs instead of shortened `[D2:7]`-style citations. The current report shows the answerer can pass the judge while failing the citation contract.

## Current Gate Checked

- LongMemEval 045232Z: 30 rows; `29 pass / 1 fail / 0 error`; `pass_to_fail=[]`; `fail_to_pass=[]`; all `kernel_trace_events` empty.
- LoCoMo 045232Z: 30 rows; `21 pass / 9 fail / 0 error`; `pass_to_fail=[]`; `fail_to_pass=["conv-26_qa_003"]`; all `kernel_trace_events` empty.
- Current reports expose `case_diagnostics.evidence_handoff` and top-level `answer_evidence` for all 60 rows.
- `config.py` still defaults `MEMORYOS_MEMORY_ARCH` to `v3` and `MEMORYOS_AGENT_KERNEL` to `off`; no diff was present in `config.py`, `engine.py`, or `context_composer.py`.
- I did not find a case-id branch in the source diff. The new answer prompt/retry wording is general, but it now needs exact-citation regression coverage because the current gate shows a citation-contract regression.

## Decision

Repeat Phase 11. Fix or explicitly gate the `conv-26_qa_007` source-grounding regression, regenerate the 30-case reports, and refresh `result.md`, `execute_review.md`, and `case_matrix.md` from the actual report rows before ACK.
