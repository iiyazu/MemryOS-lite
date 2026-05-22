# phase: phase-3

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Commit: `420c727` (`feat: add structured core memory blocks`).

## Reflection Verdict

Verdict: advance phase-3 without claiming benchmark improvement.

Phase-3 evidence supports a usable structural/core-memory ACK: structured core blocks are wired into the real v3 context composer and public benchmark diagnostics, explicit v1 fallback remains isolated, and the v3 kernel remains opt-in/default-off. The review found no blocking overfitting, source-grounding regression, or benchmark leakage.

The smoke evidence does not support a benchmark-quality improvement claim. LongMemEval was `3/10` projected no-LLM smoke and LoCoMo was `0/10`; all cases had `movement_status=new_case_no_baseline`, so there is no valid pass-to-fail or fail-to-pass movement claim. The correct reading is that v3 diagnostics are now present and useful, while benchmark behavior remains weak, especially for LoCoMo.

## Blueprint And State Action

Recommended blueprint action: no blueprint amendment for phase-3.

Reason: the blueprint amendment protocol is intended for mandatory 30-50 case milestone evidence or future phase-ordering changes. Phase-3 ran the required 10-case no-LLM smoke only, and the result confirms the existing blueprint direction rather than contradicting it. Retrieval misses remain substantial, especially LoCoMo `5/10`, so phase-4 archive/passage scope remains the right next target before moving answer projection earlier.

Recommended state action: advance phase-3 through the normal controller path and prepare phase-4 dispatch/context; do not edit `state.json` from this reflection agent. Record the carry-forward items below in the phase-4 context bundle, dispatch, plan, and review checklist.

## Carry-Forward Requirements For Phase 4

- Preserve the no-improvement claim boundary: phase-4 must treat phase-3 smoke as diagnostic wiring evidence only, not baseline movement.
- Keep `MEMORYOS_MEMORY_ARCH=v3` as default, preserve explicit `MEMORYOS_MEMORY_ARCH=v1` fallback, and keep `MEMORYOS_AGENT_KERNEL=v1` opt-in.
- Phase-4 archive/passage work must keep retrieval miss vs scope exclusion diagnosable at case level, with LoCoMo failures called out explicitly.
- If phase-4 introduces any automatic core-memory writer, it must route through `CoreMemoryService` or add an equivalent store-level provenance guard before direct persistence is allowed.
- Before broader agent-authored core-memory writes or tool-mediated core updates, add prompt-surface tests for XML-like delimiter labels/content such as `</value>`, `</memory_blocks>`, and section-looking tags.
- Keep public benchmark diagnostics append-only; do not let core-memory source refs pollute retrieval/source-hit candidate metrics.
- Use full-chain LLM judge evidence only when the blueprint requires it for phase-4 milestone gates; if provider access is unavailable, record the blocker and do not treat no-LLM smoke as a full-chain substitute.
