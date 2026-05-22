# phase: phase-6

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Decision

Phase 6 should continue with a focused TDD repeat, not escalate to `GOD_ADJUST` yet.

The review failure is inside the declared Phase 6 boundary: the new public-benchmark answer citation/refusal contract is wired into the real path, but its refusal behavior is too strict for LoCoMo cases where usable evidence is present or partially relevant. This is a contract-calibration bug, not evidence that the blueprint is structurally wrong. Escalate only if a narrow repeat cannot remove the pass-to-fail regressions without weakening citation/source accounting or hiding retrieval misses.

## Root-Cause Hypotheses

### `conv-26_qa_010`

Hypothesis: Phase 6 over-refuses on temporal relative evidence. The expected source `conv-26_qa_010:conv-26:D3:11` is retrieved, selected, rendered, and overlaps the expected source. The evidence says Caroline shared a picture from when they met up "last week" in a message dated `7:55 pm on 9 June, 2023`, which Phase 5 answered as "last week relative to 9 June 2023" and the judge accepted. Phase 6 instead returns the exact refusal string.

Likely failure surface: `PublicAnswerer` prompt/contract asks for exact citations and exact refusal, but does not sufficiently tell the model that relative temporal phrases are answerable when anchored by evidence date/session metadata. This creates an evidence-present answer-projection failure, not a retrieval failure.

### `conv-26_qa_028`

Hypothesis: this is not the same failure. The expected sources are `D7:5` and `D7:9`, but the retrieved/selected/rendered evidence does not overlap them in either Phase 5 or Phase 6. Phase 5 passed because the loose answerer used semantically related career evidence, especially `D4:11`, to answer that Caroline is interested in counseling/mental health rather than writing. Phase 6 refuses because the citation contract treats the missing expected sources as insufficient evidence.

Likely failure surface: retrieval remains a miss for the exact expected sources, while answer projection is now too binary for relevant-but-incomplete evidence. A focused Phase 6 fix may allow a cited partial answer from selected evidence, but diagnostics must still classify the case as retrieval/source miss unless expected-source overlap is actually restored.

## Focused TDD Repeat

A focused repeat is justified because there are only two pass-to-fail cases and both map to the Phase 6 answer boundary:

- `conv-26_qa_010`: evidence-present temporal refusal regression.
- `conv-26_qa_028`: retrieval miss plus strict-refusal regression on partially relevant evidence.

Do not escalate to `GOD_ADJUST` unless the focused repeat shows one of these:

- fixing refusal requires changing retrieval/storage architecture;
- tests can only pass by weakening citation validation or suppressing pass-to-fail reporting;
- LoCoMo pass-to-fail remains after a narrow prompt/contract change and repeat milestone eval;
- LongMemEval or LoCoMo source-grounding diagnostics regress.

## Required RED Coverage

Add failing tests before production changes for:

1. Temporal evidence-present answer behavior: a `PublicAnswerer` case with `conv-26_qa_010`-style evidence, date metadata, session metadata, and "last week" must guide the model toward a cited anchored answer instead of the exact refusal.
2. Relevant-but-incomplete evidence behavior: a `PublicAnswerer` case with `conv-26_qa_028`-style counseling/mental-health evidence must guide the model toward a cited partial answer with an explicit limitation instead of the exact refusal.
3. Diagnostics preservation: a refusal when expected evidence is retrieved/rendered must remain visible as `evidence_hit_answer_fail` or equivalent, not be reclassified as retrieval success.
4. Retrieval-miss preservation: `conv-26_qa_028`-style partial evidence must not be counted as expected-source hit unless expected source IDs overlap; it may become judge-pass, but the source-miss diagnostic must stay explicit.
5. Existing contract regressions: unsupported citations, missing citations, no-evidence refusal, v1 fallback, v3 default, and kernel default-off tests must keep passing.

## Risks

- Prompt-only tests with fake models can prove contract text and plumbing, but not real LLM behavior. They are necessary RED coverage, not ACK evidence.
- Allowing partial answers could blur retrieval-miss diagnostics if source overlap is not kept separate from judged answer quality.
- Fixing `conv-26_qa_028` by rewarding semantically related but non-expected sources may restore aggregate pass count while hiding that retrieval still missed `D7:5` and `D7:9`.
- LoCoMo temporal cases may be sensitive to wording; a fix for "last week" must not invent exact calendar dates unsupported by evidence.
- Stale ACK/PASS artifacts must remain superseded; no `ack.json` should be created from this failure state.

## Evidence Needed For ACK

ACK should be allowed only after a repeat result provides:

- focused RED then GREEN evidence for the temporal and partial-evidence cases;
- `uv run pytest tests/test_public_benchmarks.py tests/test_evals.py tests/test_agent_answer_eval.py -q` passing;
- `uv run pytest -q` passing;
- `uv run ruff check .` passing;
- fresh LongMemEval and LoCoMo milestone reports on the real `run_public_benchmark(..., baseline="memoryos_lite")` path with `MEMORYOS_MEMORY_ARCH=v3`;
- LoCoMo has no pass-to-fail cases versus `.memoryos/evals/phase5_repeat_20260522_1315_locomo_30_locomo.json`;
- case-level movement lists remain explicit, including `conv-26_qa_010` and `conv-26_qa_028`;
- retrieval/source metrics remain separate from judged answer pass/fail;
- `conv-26_qa_028` is still reported as a retrieval/source miss unless expected source IDs are retrieved;
- v3 remains default, `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off, and no kernel-default evidence is used for ACK.
