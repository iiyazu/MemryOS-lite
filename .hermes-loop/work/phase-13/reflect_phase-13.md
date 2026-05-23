# phase: phase-13

# Phase 13 Reflection

## Active Goal

Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Evidence Considered

- `.hermes-loop/work/phase-13/context_bundle.md`: phase-13 objective was core-memory lifecycle hardening, with no benchmark improvement claim allowed from structural evidence.
- `.hermes-loop/work/phase-13/result.md`: approved archival-to-core promotion was wired through store, lifecycle, and v3 composer paths; focused tests, regression tests, full pytest, and ruff passed.
- `.hermes-loop/work/phase-13/execute_review.md`: review found no remaining demo-only core-memory lifecycle behavior, but explicitly retained LoCoMo answer/retrieval debt.
- `.hermes-loop/work/phase-13/review_verdict.json`: verdict was `PASS`, with notes that LoCoMo evidence was structural/no-judge only and kernel default stayed off.
- `.hermes-loop/work/phase-13/ack.json`: ACK level was `usable`, decision was `advance`, and case-level no-LLM smoke failures were recorded instead of hidden.
- `.hermes-loop/blueprint.md`: root policy forbids benchmark quality claims from projected/no-LLM evidence, requires case-level movement, preserves v1 fallback/v3 default/kernel opt-in, and mandates parallel 30/50-case gates.
- `.hermes-loop/work/phase-14/context_bundle.md`: phase 14 correctly treats phase 13 as usable structural evidence, keeps kernel work opt-in, and does not claim benchmark movement from phase 13.

## Decision

Phase 13 core-memory lifecycle evidence is sufficient for a usable ACK and does not require repeating the phase. It proves real-path structural wiring, audit metadata enforcement, read-only protection, history preservation, and v3 composer rendering for approved core promotion.

However, phase 13 does require a narrow root blueprint amendment before further benchmark-gated advancement: the public smoke discovered that parallel evals sharing the default `.memoryos` store can interfere and crash. Since the root blueprint requires LongMemEval and LoCoMo milestone gates to run in parallel, the gate policy must require isolated `DATA_DIR` values per benchmark/run.

No benchmark improvement should be claimed from the phase-13 structural no-LLM smokes. The LoCoMo debt from phase 11 remains active and visible. `MEMORYOS_AGENT_KERNEL=v1` must remain opt-in.

## Blueprint Amendment

Required, narrow operational amendment only.

Add to the root blueprint eval gate policy:

```text
Parallel public benchmark gates and smokes must use isolated DATA_DIR values per benchmark and run id. Reports from shared default .memoryos stores are invalid for promotion if either parallel process crashes, cross-contaminates sessions, or cannot prove store isolation. Record each DATA_DIR and report path in the phase result.
```

No amendment is required to the phase-13 architecture scope or to the benchmark quality target.

## Future Phase Notes

- Phase 14 may proceed as opt-in kernel-loop work only after the root eval-isolation rule is recorded.
- Do not treat kernel trace visibility as LongMemEval or LoCoMo quality improvement.
- Keep unsupported or out-of-scope memory tools denied explicitly unless a phase-14 RED test justifies implementation.
- Preserve phase-11 LoCoMo debt visibility, especially `conv-26_qa_028` pass-to-fail risk, `conv-26_qa_005` source-miss judged-pass risk, and unchanged failures `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, and `conv-26_qa_025`.
- Future milestone gates must separate retrieval/source movement from judged answer movement and must list pass-to-fail and fail-to-pass cases explicitly.

## Next Minimum Verification Command

```bash
uv run pytest tests/test_agent_kernel.py -q
```
