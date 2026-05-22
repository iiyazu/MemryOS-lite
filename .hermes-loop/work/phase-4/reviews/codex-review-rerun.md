# phase: phase-4

# Codex Review Rerun

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Verdict: FAIL.

The implementation is close to the phase objective, but it is not ready for usable ACK because archival eligibility can overstate selected evidence. In `src/memoryos_lite/context_composer.py`, archive search hits are written into `selected_passage_ids` and `selected_source_refs` before the archival layer passes through the budget gate. A current-tree reproduction showed `apsg_big` listed as selected while the archival budget decision dropped it and the final package contained only the task item.

This is a source-grounding issue, not just wording: public case diagnostics consume `archival_eligibility`, so a benchmark report can imply evidence was selected when it was absent from the actual context. The required fix is to make selected archival diagnostics reflect post-budget included items, or to split pre-budget matches from selected items explicitly.

Other review points:

- Scoped eligibility is wired into the real v3 composer path.
- Public benchmark diagnostics receive archival eligibility append-only.
- v1 fallback isolation has a guard test.
- v3 remains the default memory architecture.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off.
- LongMemEval and LoCoMo milestone evidence is separated.
- LoCoMo remains weak at 0/30 and is not hidden.
- No changed production source code appears to contain benchmark case-id hacks.

Stale artifact risk remains: `reviews/codex-review.md` and `ack.json` still describe the older Archival Memory Store phase and must not be used as the current ACK basis.

Required fixes:

1. Add a failing test proving budget-dropped archival hits are not reported as selected.
2. Correct `archival_eligibility` selected fields and archival selected diagnostics to match final context inclusion.
3. Regenerate/supersede stale phase-4 review and ACK artifacts before ACK.
