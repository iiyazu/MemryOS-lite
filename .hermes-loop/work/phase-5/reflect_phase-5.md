# phase: phase-5

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context source: `.hermes-loop/work/phase-5/context_bundle.md`.

## Reflection

Phase 5 reached usable ACK as a context-composer/accounting phase. The review verdict is `PASS`, the ACK level is `usable`, and the decision is `advance` to `phase-6`.

Future blueprint adjustment required: no immediate rewrite of `.hermes-loop/blueprint.md` is required before the next dispatch. The existing Phase 5 dynamic rule already points to Phase 6 when evidence reaches the answerer but answers still fail. The next controller step should consume the Phase 5 evidence in the Phase 6 context bundle; a formal blueprint amendment is only needed if Phase 6 milestone evidence changes ordering, adds scope, or shows the current answer-projection phase is insufficient.

## What Phase 5 Proved

- The real v3 `MemoryOSService.build_context()` path now emits component accounting and final-context trace metadata, not just a side artifact.
- Public benchmark reports expose v3 accounting fields append-only: `v3_component_accounting`, `v3_final_context_trace`, `v3_component_token_totals`, `v3_component_drop_counts`, and `locomo_neighbor_diagnostics`.
- Public case diagnostics use final-context trace source refs and no longer count dropped v3 diagnostics as selected evidence.
- Focused tests covered selected evidence survival, component budget drops, LoCoMo same-session neighbor handling, explicit v1 fallback exclusion, and kernel default-off constraints.
- Verification evidence recorded by ACK/review includes `uv run pytest -q` with `388 passed, 1 warning`, `uv run ruff check .` passing, and 30-row full-chain LLM judge milestone reports for both LongMemEval and LoCoMo.

## What Phase 5 Did Not Prove

- It did not prove benchmark-quality answer improvement. LongMemEval was `18/30` and LoCoMo was `7/30`, with `0` fail-to-pass and `0` pass-to-fail in both reports.
- It did not resolve LoCoMo. LoCoMo still had `23` unchanged failures, including `11` retrieval misses, `10` context-missing-evidence cases, and `9` unsupported-answer cases.
- It did not prove source-grounded answer projection. Both milestone reports recorded `unsupported_answer` for all 30 rows.
- It did not prove the kernel should become default. `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off.
- It did not prove Phase 8 promotion evidence is usable. Any stale Phase 8 promotion gate remains blocked until Phase 6 and later gates are rerun from current evidence.

## Next-Phase Implication

Advance to Phase 6: Answer Projection And Citation Contract. The Phase 6 context bundle should use the Phase 5 report artifacts as RED evidence for the retrieval-to-answer boundary, especially cases where evidence/context tracing is now visible but answer support remains `unsupported_answer`. Phase 6 should require structured evidence input, citation IDs from selected evidence, explicit unsupported handling, and milestone LongMemEval/LoCoMo full-chain judge reports that continue to list LoCoMo failures case by case.
