# MemoryOS Lite

Context-window memory middleware for long-running AI agents.

Treats the LLM context window as working memory (RAM), proactively pages stale conversation into structured memory pages before context rot, and builds token-budgeted context packages with full source traceability.

## Why

Long context ≠ reliable context. As conversations grow, LLMs suffer attention dilution, fact loss, and context rot. MemoryOS Lite sets a conservative working-window budget and manages overflow through an OS-inspired paging mechanism — so agents work in smaller, cleaner, higher-signal contexts.

## Key Features

- **Automatic paging** — ContextRotGuard triggers paging when token budget is exceeded; heuristic or LLM-based page drafting
- **Hybrid retrieval** — BM25 lexical + embedding cosine similarity, fused via Reciprocal Rank Fusion (RRF)
- **Token-budgeted context building** — Dynamic budget allocation with pinned core profiles, recent messages, and retrieved pages
- **Conflict detection** — BM25 + negation heuristics flag patches that contradict existing memory
- **Source traceability** — Every fact in a context package traces back to source messages
- **LLM-as-judge evaluation** — GPT-based semantic accuracy scoring beyond lexical matching
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
| `MEMORYOS_PAGING_MODE` | `heuristic` / `llm` | `heuristic` |
| `ROT_SAFE_BUDGET` | Paging trigger threshold | 2400 tokens |
| `HARD_LIMIT` | Absolute context cap | 8000 tokens |

## Evaluation

81 deterministic eval cases across 4 baselines (`sliding_window`, `naive_summary`, `vector_rag`, `memoryos_lite`):

```bash
uv run memoryos eval run --baseline all
```

LLM-as-judge mode for semantic accuracy (requires `OPENAI_API_KEY`):

```bash
uv run memoryos eval run --llm-judge
```

## Development

```bash
uv run pytest -q          # 63 tests
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
