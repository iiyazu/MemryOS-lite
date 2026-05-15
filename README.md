# MemoryOS Lite

Eval-driven, source-attributed Agent/RAG memory prototype for long-running
AI conversations.

MemoryOS Lite explores how long conversations can be ingested, paged into
auditable memory pages, retrieved under a token budget, patched, and evaluated
against deterministic source-attribution checks. It is a prototype for backend
and agent-application work, not a production memory platform.

## Why

Long conversations fail in ways that are hard to debug when an answer is not
tied back to source messages. The motivating failure mode for MemoryOS Lite is
source attribution drift: a memory system may retrieve a broad page, or even
produce a plausible answer, while losing the exact message that supports it.
This prototype turns that into an eval problem by tracking page-level overlap,
message-level evidence hits, and final deterministic source accuracy separately.
The goal is an interview-ready backend/RAG story: diagnose the failure, change
the memory path, and show the measured tradeoff.

## Key Features

- **Automatic paging prototype** — ContextRotGuard triggers paging when token budget is exceeded; heuristic or LLM-based page drafting
- **Hybrid retrieval** — BM25 lexical + embedding cosine similarity, fused via Reciprocal Rank Fusion (RRF)
- **Token-budgeted context building** — Dynamic budget allocation with pinned core profiles, recent messages, and retrieved pages
- **Conflict detection guardrail** — slot/negation heuristics flag patches that contradict existing memory
- **Source traceability** — Every fact in a context package traces back to source messages
- **Experimental LangGraph agent demo** — tool-calling memory agent with
  evidence-grounded citation answers, patch conflict interrupt, bounded tool
  loops, and cross-session read rejection
- **Evaluation harness** — deterministic recall/source checks plus optional LLM-as-judge scoring
- **Observability** — Prometheus metrics for paging, retrieval, context build latency, and budget utilization

## Architecture

```
Message Ingest → ContextRotGuard → PagingAgent → MemoryPages
                                                      ↓
Task Request → DynamicBudget → ContextBuilder ← HybridSearcher
                                    ↓
                            ContextPackage (token-budgeted)
```

**Core abstractions:**

| Concept | OS Analogy | Role |
|---------|-----------|------|
| Context Window | RAM | Active working memory |
| Memory Pages | Paged storage | Compressed historical state |
| ContextRotGuard | OOM killer | Triggers paging before rot |
| ContextBuilder | Page fault handler | Recalls relevant pages within budget |
| HybridSearcher | Page table lookup | BM25 + embedding retrieval |

## Quick Start

```bash
uv venv --python 3.11 && source .venv/bin/activate
uv sync
uv run memoryos demo run
```

### API Server

```bash
uv run memoryos api --reload
# or with Docker
make up
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/sessions` | Create session |
| POST | `/sessions/{id}/ingest` | Ingest message |
| POST | `/sessions/{id}/page` | Trigger paging |
| POST | `/sessions/{id}/build-context` | Build context package |
| POST | `/memory/search` | Hybrid search |
| GET | `/sessions/{id}/trace` | Audit trail |
| GET | `/metrics` | Prometheus metrics |

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | Full DSN (highest priority) | — |
| `POSTGRES_*` | Postgres connection parts | — |
| _(none)_ | Auto-fallback to SQLite | `.memoryos/memoryos.db` |
| `OPENAI_API_KEY` | LLM paging + embeddings | — |
| `MEMORYOS_LLM_PROVIDER` | `auto` / `openai` / `deepseek` for chat LLM calls | `auto` |
| `OPENAI_BASE_URL` | OpenAI-compatible chat/embedding base URL | — |
| `DEEPSEEK_API_KEY` | DeepSeek key for chat LLM calls | — |
| `DEEPSEEK_BASE_URL` | DeepSeek OpenAI-compatible base URL | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | DeepSeek chat model | `deepseek-v4-flash` |
| `MEMORYOS_PAGING_MODE` | `heuristic` / `llm` | `heuristic` |
| `ROT_SAFE_BUDGET` | Paging trigger threshold | 2400 tokens |
| `HARD_LIMIT` | Absolute context cap | 8000 tokens |

DeepSeek is used for chat-compatible LLM features such as LLM paging,
query rewriting, reranking, agent routing, and LLM-as-judge. Embeddings
still use `OPENAI_API_KEY` and `MEMORYOS_EMBEDDING_MODEL`.

## Evaluation

Deterministic eval cases compare 4 baselines (`sliding_window`, `naive_summary`, `vector_rag`, `memoryos_lite`):

```bash
uv run memoryos eval run --baseline all
```

LLM-as-judge mode for semantic accuracy (requires a configured chat LLM key such
as `OPENAI_API_KEY` or `DEEPSEEK_API_KEY`):

```bash
uv run memoryos eval run --llm-judge
```

Public benchmark adapter for LongMemEval and LoCoMo:

```bash
uv run memoryos eval public \
  --benchmark locomo \
  --data-path /tmp/memoryos-public-benchmarks/locomo10.json \
  --limit 50 \
  --compare-baselines \
  --no-llm-answer \
  --no-llm-judge
```

Current public-benchmark diagnosis is tracked in
[`docs/public-benchmark-diagnosis.md`](docs/public-benchmark-diagnosis.md).

## Milestone Progress

| Milestone | LongMemEval memoryos_lite | LoCoMo memoryos_lite | Main diagnosis |
|-----------|---------------------------|----------------------|----------------|
| M1 page diagnostics | source/session `0.96/0.98`, page overlap `1.00/1.00` | source/session `0.00/0.00`, page overlap `0.98/1.00` | page overlap was broad, not evidence localization |
| M2 raw-message evidence | source/session `0.96/0.98`, msg@5 `0.90/1.00` | source/session `0.21/0.36`, msg@5 `0.46/0.74` | raw evidence path recovered source IDs but did not solve answers |
| M3 session/window paging | source/session `0.86/1.00`, msg@5 `0.48/0.84` | source/session `0.15/0.15`, msg@5 `0.00/0.00` | smaller pages exposed supersession and budget failures |
| M3b supersession-aware evidence | source/session `0.94/1.00`, msg@5 `0.12/0.50` | source/session `0.00/0.00`, msg@5 `0.2083/0.383` | evidence loading improved, final LoCoMo answer quality did not |

M3b is the current checkpoint. It lets superseded pages contribute raw-message
evidence candidates, marks those snippets as historical, and reserves evidence
budget only in multi-page contexts. This improves LoCoMo actual message
evidence from `0.00` to `0.2083`, while LongMemEval final source hit remains
above the acceptance floor at `0.94`.

## Prototype Boundaries

- LangGraph integration is an experimental demo, not production orchestration; its
  answer node is evidence-grounded, but it is not a general-purpose QA agent.
- Heuristic paging is a deterministic fallback, not full semantic compression.
- Conflict detection is a first-pass slot/negation guardrail.
- Public eval metrics are deterministic retrieval/source-attribution diagnostics,
  not a measurement of generated-answer quality.
- LoCoMo remains a mixed/negative result: M3b improves actual evidence loading,
  but final deterministic LoCoMo source/session hit is still `0.00/0.00`.
- The FastAPI wrapper has no authentication, rate limiting, or production
  ownership model.
- SQLite embedding search is Python-side cosine scoring, not ANN search.

## Development

```bash
uv run pytest -q
uv run ruff check .       # lint
uv run mypy src           # type check
make lint                 # all checks
```

## Tech Stack

- Python 3.11+ / uv
- FastAPI + Uvicorn
- SQLAlchemy + Alembic (Postgres/pgvector or SQLite)
- LangChain + LangGraph
- tiktoken, rank-bm25
- Prometheus client
- Docker + docker-compose

## License

MIT
