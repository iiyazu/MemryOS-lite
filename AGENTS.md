# MemoryOS Lite contributor guide

## Direction and evidence

MemoryOS Lite is an eval-driven, source-attributed Agent/RAG memory prototype. Do not describe it as production-ready. Implementation and fresh tests are authoritative; documentation is descriptive.

Current defaults are `MEMORYOS_MEMORY_ARCH=v3`, `MEMORYOS_RECALL_PIPELINE=v2`, `MEMORYOS_PAGING_MODE=off`, and `MEMORYOS_AGENT_KERNEL=off`. The collected test suite currently contains 789 tests; do not freeze passing counts or timings in docs.

## Runtime boundaries

- SQLite is authoritative. Page mirrors, trace JSONL, Redis cache, Qdrant indexes, and benchmark reports are derived or experimental.
- v3 composes core, recall, archival, and recent layers. Source references and bounded context are part of the contract.
- v2 recall uses episode-first evidence retrieval. `v1` memory and recall paths remain explicit compatibility choices, not defaults.
- The Agent kernel and LangGraph graph are opt-in experiments, not a production agent runtime.
- The HTTP API is a local prototype surface without complete remote authentication, tenancy, rate limiting, or ownership controls.
- Optional consumers such as xmuse must use the public loopback HTTP contract; do not couple this package to a consumer repository.

## Layout

| Path | Role |
|---|---|
| `src/memoryos_lite/config.py` | Settings and feature selection. |
| `src/memoryos_lite/schemas.py` | Public and internal data contracts. |
| `src/memoryos_lite/store.py` | SQLite authority and persistence facade. |
| `src/memoryos_lite/engine.py` | Service orchestration. |
| `src/memoryos_lite/context_composer.py` | Default v3 layered context. |
| `src/memoryos_lite/retrieval/` | v2 evidence planning and retrieval. |
| `src/memoryos_lite/api/` | FastAPI loopback service. |
| `tests/` | Behavior, migration, source-proof, and evaluation tests. |

## Commands

Use Python 3.11+ and the uv-managed environment:

```bash
uv sync --frozen --all-groups
TMPDIR=/tmp uv run pytest -q
TMPDIR=/tmp uv run pytest -m "not slow" -q
uv run ruff check .
uv run mypy src
uv run memoryos api --reload
uv run memoryos demo run
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

## Stable documentation

- `README.md`
- `docs/source-guide.md`
- `docs/store-interface.md`
- `docs/specs/memoryos-service-contract.md`
- `docs/archive-rag-boundary.md`
- `docs/known-issues.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/agent-answer-diagnostics.md`
- `docs/agentic-memory-roadmap-zh.md`
- `docs/implementation-history-summary.md`

Use Git history for superseded plans and implementation chronology; do not recreate `legacy`, `archive`, or historical plan trees.

## Change rules

- Preserve source attribution, bounded context, SQLite authority, migration compatibility, and deterministic offline fallbacks.
- Keep optional integrations behind explicit settings and fail safely when an external dependency is absent.
- Do not make Redis, Qdrant, an LLM provider, or an agent runtime authoritative.
- Test behavior and interfaces; avoid tests that freeze file inventories, documentation wording, timings, or total passing counts.
- Do not commit databases, caches, benchmark datasets, API keys, traces, or generated runtime files.
- Preserve unrelated changes and never use `git reset --hard`.
