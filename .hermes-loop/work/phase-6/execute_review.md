# phase: phase-6

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle cited: `.hermes-loop/work/phase-6/context_bundle.md`.

Review status: EXECUTE_SELF_REVIEW_PASS_FOR_REVIEW_LANE.

## Real Chain Changed

- `retrieval`: changed. LoCoMo/public benchmark recall now preserves bounded same-session neighbor spans when benchmark-session metadata is present. The change is general: it uses session metadata and rank/neighbor structure, not case IDs or expected answers.
- `context_composer`: verified. v3 final-context trace and LoCoMo neighbor diagnostics now show recovered same-session evidence such as `D7:5` and `D7:9`.
- `answer_projection`: changed. v3 recall/archival/episode evidence is treated as retrieved evidence for answer rendering, and answer evidence preserves final-context render order.
- `public_eval`: changed. Public LLM answer input is structured and citation-constrained; yes/no career/preference prompts now allow cautious cited likely yes/no answers from alternative-plan evidence instead of over-refusal.
- `ingest`, `store`, `kernel_loop`: not changed.

## Demo-Only Or Partial Remaining

No demo-only wiring remains for Phase 6 scope. The changes run through:

`load_public_benchmark_cases -> run_public_benchmark -> _run_baseline(memoryos_lite) -> MemoryOSService.build_context(v3) -> RecallPipeline -> V3ContextComposer -> BaselineOutput -> PublicAnswerer / projected answer -> case diagnostics`.

Remaining benchmark failures are still real failures and are not hidden:

- LongMemEval unchanged fail: `51a45a95`.
- LoCoMo unchanged fails: `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_011`, `conv-26_qa_012`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`, `conv-26_qa_027`.

## Tests Proving Behavior

Focused RED/GREEN coverage:

- LoCoMo neighbor source preservation into rendered answer evidence.
- Public answerer yes/no inference before refusal.
- Final-context render order preserved in answer evidence.
- Existing citation contract, unsupported citation, temporal evidence, partial evidence, v1 fallback, and kernel default-off tests remain passing.

Verification:

- `uv run pytest tests/test_public_benchmarks.py tests/test_evals.py tests/test_agent_answer_eval.py tests/test_episode_retrieval.py tests/test_context_composer.py -q` -> `106 passed`.
- `uv run pytest -q` -> `396 passed, 1 warning`.
- `uv run ruff check .` -> `All checks passed!`.

## Benchmark Movement

LongMemEval 30 full-chain LLM judge:

- report: `.memoryos/evals/phase6_god_adjust_prompt2_lme_30_longmemeval.json`
- result: `29/30`
- fail-to-pass: 11
- pass-to-fail: 0
- kernel trace non-empty rows: 0

LoCoMo 30 full-chain LLM judge:

- report: `.memoryos/evals/phase6_god_adjust_prompt2_locomo_30_locomo.json`
- result: `18/30`
- fail-to-pass: 11
- pass-to-fail: 0
- kernel trace non-empty rows: 0

`conv-26_qa_028` is now `unchanged_pass`, `supported_cited_answer`, with expected source overlap `D7:5` / `D7:9`.

## Guardrails

- v1 fallback preserved by tests.
- v3 default preserved by settings and tests.
- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in/default-off; milestone reports have no kernel trace events.
- Retrieval/source metrics remain separate from judged answer quality. Example: `conv-26_qa_028` has `source_hit=true` due final evidence overlap but `source_hit_at_k=false`, so top-k retrieval miss history is not hidden.
- No aggregate-only claim: case-level movement and failure classes are documented separately for LongMemEval and LoCoMo.

## Self-Review Decision

Ready for read-only review lane. If review passes, Phase 6 can produce a usable ACK. If review finds benchmark overfitting or hidden source-grounding regression, return to GOD_ADJUST.
