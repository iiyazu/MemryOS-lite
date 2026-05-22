# phase: phase-8

Active goal:

```text
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.
```

Controlling context: `work/phase-8/context_bundle.md`.

## Reflection

Phase 8 produced a usable promotion-gate ACK, but not a promotion. The correct decision is `continue_targeted`: LongMemEval is strong at `47/50`, but LoCoMo remains the controlling bottleneck at `30/50`.

The blueprint needs adjustment, but not broad promotion. Add a targeted LoCoMo reliability loop focused on session/temporal retrieval misses and answer use of already-selected evidence. Keep LongMemEval as a regression guard, preserve the v3 default and v1 fallback, and keep `MEMORYOS_AGENT_KERNEL=v1` opt-in only.

New evidence learned:

- Full checks passed: `uv run pytest -q` -> `410 passed, 1 warning`; `uv run ruff check .` -> `All checks passed!`.
- Phase-8 milestone evals used `MEMORYOS_MEMORY_ARCH=v3`, full LLM answer/judge, and no kernel opt-in.
- Same-subset comparison reported no pass-to-fail cases for either LongMemEval or LoCoMo.
- LongMemEval failures split into retrieval misses (`b86304ba`, `ccb36322`) and evidence-hit-answer-fail (`51a45a95`).
- LoCoMo failures split into retrieval/session localization misses and evidence-hit-answer-fail cases; this is not an aggregate-only weakness.
- The heartbeat retry artifacts ended partial/projected/no-judge and must remain excluded from promotion evidence.

Next targeted loop recommendation:

Run a fixed LoCoMo failure-slice loop over representative retrieval-miss and evidence-hit-answer-fail cases (`conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_012`, `conv-26_qa_033`, `conv-26_qa_041`, `conv-26_qa_048`, `conv-26_qa_050`) with explicit pass-to-fail, source-grounding, and answer-support gates, plus a 30-case LongMemEval regression guard. Do not expand eval until LoCoMo improves on both retrieval/session localization and answer use of selected evidence.
