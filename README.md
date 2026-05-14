# MemoryOS Lite

Eval-driven, source-attributed Agent/RAG memory prototype for long-running
AI conversations.

MemoryOS Lite explores how long conversations can be ingested, paged into
auditable memory pages, retrieved under a token budget, patched, and evaluated
against deterministic source-attribution checks. It is a prototype for backend
and agent-application work, not a production memory platform.

## Why

Long context is not automatically reliable context. As conversations grow, LLMs
can lose attention over facts, dates, and source evidence. MemoryOS Lite uses an
OS-inspired paging metaphor to make that failure mode measurable: every recall
claim should be tied back to source messages, and every optimization should be
checked against baselines.

## Key Features

- **Automatic paging prototype** — ContextRotGuard triggers paging when token budget is exceeded; heuristic or LLM-based page drafting
- **Hybrid retrieval** — BM25 lexical + embedding cosine similarity, fused via Reciprocal Rank Fusion (RRF)
- **Token-budgeted context building** — Dynamic budget allocation with pinned core profiles, recent messages, and retrieved pages
- **Conflict detection guardrail** — slot/negation heuristics flag patches that contradict existing memory
- **Source traceability** — Every fact in a context package traces back to source messages
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
The important known gap is LoCoMo-style multi-session recall: the current
page-level RAG can compress hundreds of messages into one oversized page and
drop it under a strict context budget. The next optimization target is
raw-message/evidence-chunk retrieval, not production agent orchestration.

## Prototype Boundaries

- LangGraph integration is an experimental demo, not production orchestration.
- Heuristic paging is a deterministic fallback, not full semantic compression.
- Conflict detection is a first-pass slot/negation guardrail.
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
