# MemoryOS Lite

MemoryOS Lite is a context-window memory middleware for long-running agents.

It treats the LLM context window as working memory, pages stale conversation state
into external memory before context rot, and builds a token-budgeted context package
with traceable source pages.

## Quick Start

```bash
uv venv --python 3.11
source .venv/bin/activate
uv sync
uv run memoryos demo run
uv run memoryos eval run --baseline all
```

Start the API:

```bash
uv run memoryos api --reload
```

Core API:

- `POST /sessions`
- `POST /sessions/{session_id}/ingest`
- `POST /sessions/{session_id}/page`
- `POST /sessions/{session_id}/build-context`
- `POST /memory/search`
- `GET /sessions/{session_id}/trace`

Local data is stored under `.memoryos/` by default:

- `.memoryos/memoryos.db`
- `.memoryos/pages/{session_id}/{page_id}.json`
- `.memoryos/traces/{session_id}.jsonl`
- `.memoryos/eval_runs/{run_id}/`
- `.memoryos/evals/{run_id}.json`

## Benchmark

The built-in benchmark is a deterministic synthetic, lexical, rule-scored
context retrieval and source-support eval for reproducible local development.
It currently contains 81 cases: 10 template families plus one dropped-page audit
case. It is not an LLM answer benchmark, not a real-world large-scale benchmark,
and should not be read as broad retrieval superiority. It compares:

- `sliding_window`
- `naive_summary`
- `vector_rag`
- `memoryos_lite`

Example:

```bash
uv run memoryos eval run --run-id local-check --baseline all
```

`memoryos_lite` uses paging, source trace, recall, and strict token-budgeted
context building. Easy synthetic cases validate scoring and source semantics;
hard synthetic cases stress long-context compression, conflict updates, and
source-support loss under budget pressure. Additional deterministic cases vary
noise position, in-conversation session distractors, and lexical recall without
the benchmark's strongest recency/update marker words. Eval runs are isolated by
default and do not reset the main `.memoryos/memoryos.db`. Built-in eval runs
force heuristic paging so `.env` or shell LLM settings do not affect
reproducibility.

`dropped_page_audit_001` exists to verify dropped-page report fields. It is not
evidence that MemoryOS Lite is more accurate than BM25 RAG in that scenario.

`answer_accuracy` requires all expected facts to appear in a clean generated
rule-based answer. `source_accuracy` additionally requires each expected fact to
be supported by the answer-selected source text; answers containing forbidden
facts receive no source credit. Built-in cases use stable source message ids,
including multi-fact cases with per-fact required sources. The scorer is
deliberately lexical and does not model natural-language negation of old entity
names as answer-span citation semantics.

The CLI prints answer accuracy, source accuracy, average context tokens, average
page count, loaded/dropped pages, selected source count, and credited supporting
source count. Reports include source ids, full selected-evidence snippets,
supporting source snippets, expected-fact support maps, missing answer facts,
and unsupported answered facts so source support can be inspected across runs.
Build-context traces and eval reports include dropped page details with budget
reasons such as `task_exceeds_budget`, `core_profile_exceeds_budget`, or a
retrieval reason such as `lexical_overlap=3` when a retrieved page does not fit
the remaining budget.
This is evidence-level source support, not exact answer-span citation
attribution. `source_snippets` is the full debug view;
`supporting_source_snippets` is the smaller audit view for source credit. Eval
reports may include raw answers, selected evidence text, source
summaries, and source snippets. Do not publish reports generated from private
logs.

The baselines are intentionally simple: `sliding_window` shows early-fact loss,
`naive_summary` shows fixed-summary degradation on harder cases, and
`vector_rag` is a strong lexical BM25 retrieval baseline. MemoryOS Lite is not
expected to beat BM25 RAG on every synthetic case. In the current deterministic
benchmark, MemoryOS Lite reaches the same accuracy/source score as the strong
lexical BM25 baseline while using more tokens, in exchange for persistent memory
pages, source trace, context packaging, and richer audit reports.

## LLM Eval Boundary

The default eval remains deterministic and does not call an LLM. A future LLM
answer-generation eval should be a separate mode that compares the same context
builders with generated answers, for example `sliding_window` context + LLM,
`vector_rag` context + LLM, and `memoryos_lite` context + LLM. Useful metrics
would include answer factuality, citation support, forbidden fact leakage, token
cost, and latency. Because this would not be deterministic, reports should fix
the model, temperature, seed or model version where available, and preserve the
raw prompt/context/answer evidence used for scoring.

## LLM Paging

Heuristic paging is the default so demos and tests run without an API key.
To enable OpenAI-compatible structured paging:

```bash
export MEMORYOS_PAGING_MODE=llm
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=...
export MEMORYOS_MODEL=gpt-4o-mini
```

If LLM paging fails, MemoryOS falls back to the heuristic paging agent and records
the fallback reason in trace events.

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
