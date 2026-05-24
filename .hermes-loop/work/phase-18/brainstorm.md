# phase: phase-18

# Brainstorm: K5 Benchmark Governance And Promotion

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle cited: `.hermes-loop/work/phase-18/context_bundle.md`.

## Decision Frame

Phase 18 should make a governance decision, not a product-behavior change by default. The valid evidence currently says:

- Phase 8 accepted milestone baseline: LongMemEval 50 full-chain LLM judge `47/50`; LoCoMo 50 full-chain LLM judge `30/50`.
- Phase 17 r3 LoCoMo 10 baseline: `8 pass / 2 fail`, `judge_done=10/10`.
- Phase 17 r3 opt-in kernel repair smoke: `8 pass / 2 fail`, `judge_done=10/10`.
- Phase 17 r3 movement: `fail_to_pass=[]`, `pass_to_fail=[]`, `unchanged_fail=["conv-26_qa_006","conv-26_qa_008"]`.
- Phase 17 r3 failure classes: `retrieval_miss=["conv-26_qa_008"]`, `evidence_hit_answer_fail=["conv-26_qa_006"]`, `source_miss_judge_pass=["conv-26_qa_002","conv-26_qa_003","conv-26_qa_004","conv-26_qa_005"]`.
- Phase 17 r3 source metrics did not improve or regress: `source_hit`, `planned_evidence_source_hit_at_5`, and `episode_source_hit_at_10` movement were all empty.
- Phase 17 r3 summary reported `full_chain_gate_status="not_satisfied"` because same-slice repair smoke remains diagnostic only and cannot satisfy a promotion gate.

This evidence blocks promotion from aggregate pass rate, LongMemEval-only strength, kernel trace presence, or the same-slice repair smoke.

## Approach 1: Governance-Only `continue_targeted` From Current Valid Evidence

Treat Phase 18 as a control-plane decision. Use the accepted Phase 8 milestone reports and Phase 17 r3 diagnostic evidence to choose `continue_targeted`, then require the next execution slice to target the separate bottlenecks:

- source-localization defects hidden behind judged passes: `conv-26_qa_002` through `conv-26_qa_005`;
- answer projection or citation use over available evidence: `conv-26_qa_006`;
- retrieval/query/source ranking failure: `conv-26_qa_008`.

Pros:

- Safest against false promotion because it honors `full_chain_gate_status="not_satisfied"`.
- Does not depend on fresh provider availability or noisy partial evals.
- Keeps LoCoMo visible as the controlling bottleneck instead of letting LongMemEval dominate the narrative.
- Preserves current default boundaries: v3 default, `MEMORYOS_MEMORY_ARCH=v1` explicit fallback, and `MEMORYOS_AGENT_KERNEL=v1` opt-in only.
- Avoids product edits or benchmark-data changes before the governance question is settled.

Cons:

- Does not produce fresh Phase 18 milestone scores.
- Leaves the root blueprint unpromoted.
- Requires the next phase to do targeted implementation and validation before any quality claim.

Governance decision this supports: `continue_targeted`.

## Approach 2: Fresh Milestone `expand_eval` Rebaseline Before Deciding

Run Phase 18 as a fresh benchmark governance pass: structural no-LLM wiring smoke, then LongMemEval 50 and LoCoMo 50 full-chain LLM answer/judge under `MEMORYOS_MEMORY_ARCH=v3`, with case-level comparison against accepted Phase 8 evidence. Quarantine heartbeat-only, partial, projected, stale, mismatched, or no-judge artifacts. Report LongMemEval and LoCoMo separately, and split judged answer quality from retrieval/source metrics.

Pros:

- Produces the cleanest current promotion or hold evidence if provider conditions are stable.
- Can detect drift since Phase 8, including LongMemEval regression or hidden LoCoMo pass-to-fail rows.
- Gives reviewers a complete case matrix for `promote_blueprint`, `hold`, or `continue_targeted`.

Cons:

- More expensive and vulnerable to provider/API instability.
- A valid rebaseline can still end in `continue_targeted` if LoCoMo source grounding remains weak.
- It must not use repair-smoke archive writes or kernel opt-in as the default public benchmark path.
- It is unsafe to interpret aggregate pass movement without source-metric and source-miss judge-pass accounting.

Governance decision this supports: `expand_eval` only if the controller needs fresh 50-case evidence before final governance. It does not by itself justify promotion.

## Approach 3: Promote Blueprint Or Kernel Repair Path Now

Use Phase 17 kernel repair-smoke execution as evidence that Letta-style maintenance writes are usable, then promote blueprint status or move the kernel closer to default behavior.

Pros:

- Recognizes that the repair-smoke harness is real-path and not a demo stub.
- Builds on the opt-in kernel trace, approval, and archive-write verification work.

Cons:

- Unsafe: Phase 17 same-slice repair smoke showed no judged pass improvement and no source-metric improvement.
- The four `source_miss_judge_pass` rows prove aggregate judged pass can hide source-grounding defects.
- `full_chain_gate_status="not_satisfied"` explicitly blocks promotion from the repair smoke.
- Kernel trace presence is not memory-quality evidence.
- Enabling or normalizing kernel behavior would violate the active boundary unless separately approved by later evidence.

Governance decision this supports: rejected for Phase 18.

## Recommended Route

Choose Approach 1 now: record a conservative `continue_targeted` recommendation for Phase 18 planning, with Approach 2 available only as a later review/milestone option if the controller needs fresh 50-case governance evidence.

Rationale:

- Current valid evidence is sufficient to reject promotion but not sufficient to claim broader improvement.
- LoCoMo remains the bottleneck: Phase 8 LoCoMo 50 was `30/50`, and Phase 17 r3 exposed unresolved source-grounding and answer/retrieval failures on the fixed 10-case slice.
- The repair-smoke path is measurable and safely opt-in, but same-slice repair smoke is non-promotion evidence.
- The safest next implementation work is targeted, not a root blueprint promotion.

## Rejected Alternatives

- Promote from aggregate pass rate: rejected because source-miss judged-pass rows can make judged quality look better than source-grounded quality.
- Promote from LongMemEval-only evidence: rejected because LoCoMo remains harder and must be reported separately.
- Promote from Phase 17 same-slice repair smoke: rejected because it stayed `8 pass / 2 fail`, had no source-metric movement, and reported `full_chain_gate_status="not_satisfied"`.
- Promote from kernel trace presence: rejected because tool execution proves wiring, not benchmark quality.
- Hide or merge `source_miss_judge_pass` under generic pass counts: rejected because Phase 17 made this a first-class governance risk.
- Enable the v3 kernel by default: rejected because the active goal and blueprint require kernel opt-in.

## Risks To Carry Forward

- Source-grounding risk: judged-pass rows `conv-26_qa_002` through `conv-26_qa_005` still miss source localization.
- Retrieval risk: `conv-26_qa_008` remains a retrieval miss.
- Answer-projection risk: `conv-26_qa_006` has evidence available but still fails judged answer quality.
- Overfitting risk: repeated fixed-slice LoCoMo work can optimize case behavior without held-out or clean-store validation.
- Artifact-validity risk: partial, heartbeat-only, projected, stale, or mismatched reports can create false promotion pressure.
- Masking risk: strong LongMemEval results can hide LoCoMo regressions unless both benchmarks are reported separately.
- Boundary risk: repair-smoke or kernel behavior could drift into default public benchmark behavior unless `MEMORYOS_AGENT_KERNEL=v1` remains explicit.

## What Would Count As Demo-Only

- A plan that lists benchmark gates but does not produce or consume case-level evidence.
- A summary that reports only aggregate pass counts without pass-to-fail, fail-to-pass, unchanged fail, retrieval miss, evidence-hit-answer-fail, context-missing-evidence, unsupported-answer, judge-questionable, and source-miss judge-pass rows.
- Any claim of promotion from LoCoMo 10 same-slice repair smoke.
- Any claim of promotion from LongMemEval without a separate LoCoMo 50 full-chain result.
- Any eval artifact that is no-LLM, heartbeat-only, partial, projected, stale, or baseline-mismatched but treated as milestone evidence.
- Any repair proposal, archive artifact, or context input that uses benchmark gold fields, expected answers, expected source ids, judge labels, or case-id rules.
- Any path where the v3 kernel becomes default or public benchmark quality depends on `MEMORYOS_AGENT_KERNEL=v1`.

## Governance Criteria For Later Promotion

`promote_blueprint` should remain unavailable unless all of the following are true:

- LongMemEval 50 and LoCoMo 50 are both full-chain LLM answer/judge runs under the real v3 public benchmark path.
- LoCoMo has no unexplained same-case pass-to-fail movement.
- LoCoMo source localization does not regress, including source-miss judged-pass rows.
- Judged pass rate and source-grounded pass rate are reported separately.
- Invalid artifacts are quarantined explicitly.
- Any improvement claim is supported by held-out or clean-store evidence, not same-slice repair smoke.
- v3 remains default, `MEMORYOS_MEMORY_ARCH=v1` remains an explicit fallback, and `MEMORYOS_AGENT_KERNEL=v1` remains opt-in.
