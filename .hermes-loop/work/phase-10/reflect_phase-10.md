# phase: phase-10

# Phase 10 Reflection

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Evidence Considered

- `.hermes-loop/work/phase-10/context_bundle.md`
- `.hermes-loop/work/phase-10/ack.json`
- `.hermes-loop/work/phase-10/review_verdict.json`
- `.hermes-loop/work/phase-10/result.md`
- `.hermes-loop/work/phase-10/case_matrix.md`
- `.hermes-loop/work/phase-10/execute_review.md`
- `.hermes-loop/work/phase-10/reviews/codex-review-phase-10.md`
- `.hermes-loop/work/phase-10/reviews/codex-review-phase-10-cli.md`
- `.hermes-loop/blueprint.md`
- `.hermes-loop/state.json`

Phase 10 evidence is usable for advancement. The implemented packet/session recall behavior is wired into the real v3/public benchmark path, has RED-before-fix test evidence, and preserves v1 fallback, v3 default, and kernel-default-off constraints.

The accepted case-level signal is narrow but sufficient for the Phase 10 gate:

- LoCoMo 30 full-chain LLM judge: `20 pass / 10 fail`.
- LoCoMo fail-to-pass: `conv-26_qa_011`, `conv-26_qa_012`.
- Primary ACK signal: `conv-26_qa_011` moved from Phase 9 `session_localization_miss` to supported pass with expected source `conv-26_qa_011:conv-26:D3:13` present in projected and LLM context.
- Supporting signal: `conv-26_qa_012` moved from fail to pass with expected sources present, but it was a Phase 9 `temporal_date_miss`, so it should not be overclaimed as the primary session-localization proof.
- LoCoMo pass-to-fail: none.
- LongMemEval 30 full-chain LLM judge: `29 pass / 1 fail`.
- LongMemEval pass-to-fail: none.

Remaining LoCoMo failures are still material:

- Retrieval misses: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_008`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_025`.
- Evidence-hit-answer-fail: `conv-26_qa_006`, `conv-26_qa_016`, `conv-26_qa_024`, `conv-26_qa_027`.

Review notes are low severity but should shape Phase 11:

- Raw Phase 10 report rows still have `movement_status: new_case_no_baseline`; same-case movement is re-derived in `case_matrix.md` and is not self-contained in the raw report JSON.
- LongMemEval guard coverage is mainly the 30-case gate plus existing direct-hit behavior; add a narrower LongMemEval-style guard if packet/context selection broadens.

## Recommendation

Advance to Phase 11, but do not repeat broad recall work as the next phase. Phase 10 converted at least one repeated recall/session failure into a supported pass without pass-to-fail regressions, so the next bottleneck should be treated as evidence handoff, context selection, rendering, and report diagnostics.

Phase 11 should focus on the existing blueprint target: trace every expected source through `indexed -> retrieved -> selected -> rendered -> cited -> judged`, especially for the four remaining evidence-hit-answer-fail LoCoMo cases. The six remaining retrieval misses should stay visible in Phase 11 reports, but they should not pull the phase back into another generic recall iteration unless Phase 11 proves a selected/rendered handoff diagnostic is missing or misleading.

## Blueprint Amendment

Do not amend `.hermes-loop/blueprint.md` before Phase 11. The current Phase 11 scope already matches the evidence: evidence handoff and context selection are the next layer after recall packet reliability.

Required dispatch clarification for Phase 11, without root blueprint change:

- carry forward Phase 10's two low review notes;
- require self-contained same-case comparison output or an explicit comparison artifact instead of relying on raw report `movement_status`;
- include a LongMemEval-style focused guard if Phase 11 changes packet selection, final-context selection, or rendering rules;
- preserve kernel default off and keep any kernel evidence out of default public benchmark claims.

## Affected Future Phases

- Phase 11: proceed as evidence handoff/context selection, with special attention to selected-drop vs render-drop vs answer-use failures.
- Phase 12: no change; archival/RAG unification should wait until Phase 11 confirms handoff diagnostics are reliable.
- Phase 13: no change.
- Phase 14: no change; do not use remaining LoCoMo failures to justify enabling the v3 kernel by default.
- Phase 15: promotion governance must not consume raw report-row `movement_status` from Phase 10 as self-contained movement evidence.

## Next Minimum Verification Command

After Phase 11 changes, the minimum gate is the paired 30-case full-chain run, launched in parallel:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark longmemeval --data-path benchmarks/longmemeval/longmemeval.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge
```

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public --benchmark locomo --data-path benchmarks/locomo/locomo10.json --baseline memoryos_lite --limit 30 --llm-answer --llm-judge
```

The Phase 11 report must include explicit fail-to-pass, pass-to-fail, unchanged-fail, retrieval-miss, selected-drop, render-drop, and evidence-hit-answer-fail movement against the Phase 8/Phase 10 same-case baseline.
