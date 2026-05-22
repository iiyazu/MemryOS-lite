# phase: phase-10

# Phase 10 Final Plan

Context bundle: `.hermes-loop/work/phase-10/context_bundle.md`.

decision=ready_for_execute

Active goal:

> Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Accepted plan summary:

1. Add RED tests before production changes:
   - `tests/test_episode_retrieval.py` for LoCoMo-like weak same-session anchor retention, unrelated-neighbor control, and strong LongMemEval-like direct-hit stability.
   - `tests/test_recall_pipeline.py` for packet metadata in `ContextPackage`.
   - `tests/test_public_benchmarks.py` for packet diagnostics visible through the real v3/public benchmark report and kernel trace default-off behavior.
   - Run the focused RED set and record exact failure text.

2. Implement the narrow GREEN path:
   - Extend `RecallMemorySearcher` with bounded session-aware direct-hit selection only when neighbor/session preservation is explicitly active and benchmark session metadata exists.
   - Attach deterministic packet metadata to real recall hits and same-session bounded neighbors.
   - Propagate packet metadata through `RecallPipeline`, v3 `ContextComposer`, `MemoryOSService._context_package_from_v3`, and public benchmark diagnostics as append-only metadata.
   - Do not change scoring semantics, answer prompts/projection, v1 fallback behavior, v3 default behavior, or kernel default behavior.

3. Refactor narrowly:
   - Keep changes inside existing recall, composer, engine, and public diagnostic modules.
   - Avoid broad architecture changes and Letta runtime dependencies.
   - Keep packet metadata construction consistent across searcher, pipeline, composer, and eval/reporting.

4. Verify focused behavior:
   - `uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py -q`
   - `uv run pytest tests/test_public_benchmarks.py -q`
   - `uv run ruff check .`

5. Verify baseline and defaults:
   - `uv run pytest -q`
   - `uv run ruff check .`
   - Explicit guards for v1 fallback, v3 default, and kernel trace default-off.

6. Run real public benchmark evidence:
   - First run deterministic LoCoMo no-LLM smoke with `MEMORYOS_MEMORY_ARCH=v3`.
   - If LLM provider access is available, run LongMemEval 30 and LoCoMo 30 full-chain public evals with `--llm-answer --llm-judge`.
   - Maintain heartbeat files for long evals.
   - Do not mark the milestone gate satisfied if provider access is unavailable or reports are projected/no-judge.

7. Produce case-level phase artifacts:
   - `case_matrix.md`, `result.md`, `execute_review.md`, and eval heartbeat files.
   - List fail-to-pass, pass-to-fail, unchanged-fail, retrieval/source movement, selected/rendered movement, failure-class movement, packet/session movement, and cause/disposition for every pass-to-fail.

Execution constraints:

- No case-id, expected-source, expected-answer, fixed QA-string, or known failed-term hacks.
- No scoring semantic changes.
- No aggregate-only promotion.
- No default enablement of `MEMORYOS_RECALL_PIPELINE=v2` or `MEMORYOS_AGENT_KERNEL=v1`.
- No Letta dependency or direct Letta internals port.
