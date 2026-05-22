# phase: phase-6

## GOD_ADJUST Analysis

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Original Hypothesis

Phase 6 hypothesized that a major benchmark weakness sat at the retrieval-to-answer boundary: selected/rendered evidence was not projected into answers with durable citation IDs, so answers were classified as unsupported even when evidence was present.

The focused repeat narrowed that hypothesis:

- `conv-26_qa_010`: an evidence-present temporal case was over-refused because the answer contract did not clearly allow relative temporal evidence anchored by date/session metadata.
- `conv-26_qa_028`: a relevant-but-incomplete evidence case was over-refused because the stricter citation contract treated missing expected sources as insufficient, even though Phase 5's loose answerer had passed using semantically related counseling evidence.

## Triggering Evidence

The focused repeat fixed `conv-26_qa_010`:

- repeat LoCoMo `conv-26_qa_010` verdict: `pass`;
- movement: `unchanged_pass`;
- `failure_class`: `supported_cited_answer`;
- expected/rendered/cited source: `conv-26_qa_010:conv-26:D3:11`;
- answer: cites `D3:11` and anchors "last week" to `9 June 2023`.

But the same repeat still has one LoCoMo pass-to-fail:

- repeat LoCoMo total: `6/30`, down from Phase 5 `7/30`;
- movement summary: `pass_to_fail = 1`;
- blocker: `conv-26_qa_028`;
- Phase 5 `conv-26_qa_028`: `pass`, `failure_class=retrieval_miss`, answer used counseling/mental-health evidence;
- Phase 6 repeat `conv-26_qa_028`: `fail`, `movement_status=pass_to_fail`, `failure_class=retrieval_miss`;
- expected sources: `conv-26_qa_028:conv-26:D7:5`, `conv-26_qa_028:conv-26:D7:9`;
- retrieved/source answer evidence: `conv-26_qa_028:conv-26:D4:11`;
- source overlap: empty;
- missing sources: both expected `D7` sources;
- answer: `Insufficient retrieved evidence to answer with source citations.`

LongMemEval did not create a new blocker in this repeat:

- repeat LongMemEval total: `18/30`;
- movement summary: `18 unchanged_pass`, `12 unchanged_fail`;
- no pass-to-fail cases.

## Root Cause For Remaining Blocker

`conv-26_qa_028` is not primarily an answer-citation formatting bug anymore. It is a source-recovery and evidence-sufficiency blocker exposed by the citation contract.

The expected evidence is in session `D7`, but neither expected source ID appears in the retrieved/source-overlap set. The repeat retrieves nearby or related material, including `D7:8` in candidates and `D7:7` in planned evidence, but not the expected `D7:5` / `D7:9` pair. The answerer receives/rendered evidence anchored on `D4:11`, which supports that Caroline is interested in counseling and mental health, but does not directly answer whether she would pursue writing. Under the stricter contract, refusing is defensible; under the benchmark judge, the refusal fails because Phase 5 had produced the expected semantic answer from partial evidence.

The code diff confirms this boundary: Phase 6 added structured `AnswerEvidence`, allowed citation IDs, missing/unsupported citation diagnostics, and prompt instructions for partial evidence. Focused fake-model tests can prove the prompt text exists, but the live LoCoMo repeat shows the real path still refuses `conv-26_qa_028`. Therefore this cannot be ACKed as a solved answer-contract phase.

## Decision

Escalate to `GOD_ADJUST`.

Use split + narrow + repeat:

- Split Phase 6 into completed contract plumbing vs. unresolved LoCoMo source-recovery blocker.
- Pause Phase 6 ACK while `conv-26_qa_028` remains `pass_to_fail`.
- Narrow the next work to the `conv-26_qa_028` failure mode: recover or preserve the expected `D7:5` / `D7:9` evidence through retrieval, neighbor expansion, selected context, rendered evidence, and citation-aware answer input.
- Repeat only after a test-backed source/context fix, not another prompt-only adjustment.
- Do not reorder into Phase 7 kernel work; the blocker is on the default v3 public benchmark path, and the kernel must remain default-off.

## Exact Future Scope

Future work should be limited to:

- add a failing focused test for a `conv-26_qa_028`-style LoCoMo case where the query retrieves a nearby `D7` message but expected neighboring evidence `D7:5` / `D7:9` must survive into selected/rendered evidence;
- inspect and adjust general LoCoMo neighbor/session expansion or evidence selection so nearby expected message evidence can be included without case-id hacks or expected-answer leakage;
- keep citation validation strict: cited IDs must be present in selected/rendered evidence;
- keep source metrics strict: `conv-26_qa_028` must remain a retrieval/source miss unless expected source IDs actually overlap;
- rerun focused tests, full public benchmark tests, then the LoCoMo 30-case LLM repeat against the Phase 5 comparison report.

Out of scope for the next repeat:

- enabling `MEMORYOS_AGENT_KERNEL=v1` by default;
- changing Phase 7 kernel/tool behavior;
- marking semantically related non-expected sources as expected-source hits;
- suppressing pass-to-fail reporting;
- judging aggregate LoCoMo score without case-level movement.

## Next Minimum Verification Command

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 30 \
  --llm-answer \
  --llm-judge \
  --comparison-report .memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json \
  --run-id phase6_god_adjust_locomo_30
```

Minimum pass condition for this command: no `pass_to_fail` cases versus `.memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json`, with `conv-26_qa_028` explicitly listed as either fixed with expected-source recovery or still blocked.

## What Must Not Be Hidden

- `conv-26_qa_028` is still `pass_to_fail` after the focused repeat.
- LoCoMo repeat is `6/30`, while the Phase 5 comparison is `7/30`.
- `conv-26_qa_028` has `source_hit=false`, `source_recall=0.0`, empty `source_overlap_ids`, and missing expected sources `D7:5` / `D7:9`.
- The rendered/cited source available to the answer path is not the expected source pair; it is semantically related `D4:11` evidence.
- The fake-model prompt tests are not milestone evidence that the live LLM path is fixed.
- Any future judge-pass based on partial evidence must still report the retrieval/source miss unless expected source overlap is restored.
- The v3 kernel remains opt-in/default-off and cannot be used as ACK evidence for this default-path blocker.
