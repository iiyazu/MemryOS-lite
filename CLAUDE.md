# AUTONOMOUS MODE: No user interaction. All agent prompts include autonomy instructions.
# CLAUDE.md

This file provides working guidance for Claude Code and other coding agents in this repository.

## Project Status

MemoryOS Lite is an **eval-driven, source-attributed Agent/RAG memory prototype**. Do not describe it as production-ready MemoryOS.

Current baseline:

- Default memory architecture is `v3` layered composer.
- Legacy `v1` ContextBuilder is still available with `MEMORYOS_MEMORY_ARCH=v1`.
- Episode-first recall is opt-in with `MEMORYOS_RECALL_PIPELINE=v2`.
- The v3 kernel remains opt-in with `MEMORYOS_AGENT_KERNEL=v1`.
- Storage is SQLite-first with Alembic migrations through `0004_add_episodes`.
- Qdrant is optional for ANN/vector experiments.
- No separate production database backend is configured in the current code.
- Full verification: `uv run pytest -q` -> `352 passed, 1 warning`.
- Hard eval: `uv run memoryos eval run --case-set hard --baseline memoryos_lite` -> `1.00/1.00`.
- v2 smoke diagnostics:
  - LongMemEval limit 10: `episode_source_hit_at_10 = 8/10`, `planned_evidence_source_hit_at_5 = 8/10`.
  - LoCoMo limit 10: `episode_source_hit_at_10 = 5/10`, `planned_evidence_source_hit_at_5 = 5/10`.

## Xmuse Control Plane Status

Snapshot: 2026-05-25 17:16 Asia/Shanghai.

Xmuse is the current local multi-agent control plane. The active control-plane
source is `xmuse/master_state.json`; legacy `.hermes-loop` paths are not the
active controller.

Current read-only status:

- Master/God liveness: not running.
- `xmuse/run.lock`: stale.
- `xmuse/jobs/benchmark-layer-organization.json`: `runtime.status = frozen_for_audit`.
- `xmuse/jobs/xmuse-console.json`: `runtime.status = frozen_for_audit`.
- Freeze record: `xmuse/freeze_snapshot.json`, reason `user requested xmuse freeze for manual audit`.
- Master queue counts from `xmuse/master_status.json`: total 6, reviewable 0, mergeable 0, held 1, blocked 3, merged 0.
- Active lanes in Master status: `xmuse-console`, `benchmark-layer-organization`.
- Held lane: `archive-rag`.
- Blocked lanes: `memoryos-redis-cache-probe`, `xmuse-core-state-extraction`, `xmuse-error-knowledge`.

Feature worktrees and latest observed heads:

| Feature | Worktree | Branch | HEAD / State |
|---|---|---|---|
| `archive-rag` | `/home/iiyatu/projects/python/memoryOS-archive-rag` | `feat/archive-rag` | `15c6edf`, held by Master approval/merge gate. |
| `memoryos-redis-cache-probe` | `/home/iiyatu/projects/python/memoryOS-memoryos-redis-cache-probe` | `feat/memoryos-redis-cache-probe` | `a8f2a8e`, feature ACK usable / review PASS; Master gate reports stale or failing integrated-test evidence. |
| `xmuse-console` | `/home/iiyatu/projects/python/memoryOS-xmuse-console` | `feat/xmuse-console` | `e5c8ae8`, frozen for audit; focused xmuse checks pass, full-project mypy remains blocked by non-xmuse errors. |
| `benchmark-layer-organization` | `/home/iiyatu/projects/python/memoryOS-benchmark-layer-organization` | `feat/benchmark-layer-organization` | `5aaa329`, frozen for audit with dirty feature-local/type-cleanup changes. |
| `xmuse-core-state-extraction` | `/home/iiyatu/projects/python/memoryOS-xmuse-core-state-extraction` | `feat/xmuse-core-state-extraction` | `7f7d40b`, blocked_needs_master. |
| `xmuse-error-knowledge` | `/home/iiyatu/projects/python/memoryOS-xmuse-error-knowledge` | `feat/xmuse-error-knowledge` | `dd58b3b`, Master gate blocked by missing integrated tests. |

Credential note for benchmark work:

- `OPENAI_API_KEY` is not available.
- DeepSeek credentials are available through the relevant feature worktree `.env`.
- See `xmuse/work/features/benchmark-layer-organization/operator_note.md`.

Read-only status checks should avoid starting the runner. Prefer importing
`xmuse/hermes_reporter.py` and calling liveness helpers with `read_only=True`;
do not run bare `python3 xmuse/hermes_reporter.py` unless start side effects are
intended.

## Current Architecture

Main lifecycle:

```text
ingest(message)
  -> store Message
  -> v3 default: layered context composer path
  -> v1 fallback: existing page/item/recent-message path when MEMORYOS_MEMORY_ARCH=v1
  -> v2 opt-in: ensure Episode records for raw-message recall

build_context(task)
  -> v3 ContextComposer by default
  -> v1 ContextBuilder when settings.resolved_memory_arch == "v1"
  -> v2 RecallPipeline when settings.resolved_recall_pipeline == "v2"
```

Important modules:

| Path | Role |
|---|---|
| `src/memoryos_lite/config.py` | Pydantic settings and feature flags. |
| `src/memoryos_lite/schemas.py` | `Message`, `Episode`, `MemoryPage`, `MemoryItem`, `ContextPackage`, eval schemas. |
| `src/memoryos_lite/store.py` | SQLite store, page JSON debug mirror, traces, episode backfill, Alembic stamping. |
| `src/memoryos_lite/engine.py` | Service facade, paging, v1 context building, v2 routing. |
| `src/memoryos_lite/retrieval/episode_searcher.py` | BM25 retrieval over `Episode.index_text`. |
| `src/memoryos_lite/retrieval/query_analyzer.py` | Deterministic query tags for retrieval weighting. |
| `src/memoryos_lite/retrieval/recall_pipeline.py` | v2 evidence planning and context packaging. |
| `src/memoryos_lite/public_benchmarks.py` | LongMemEval/LoCoMo adapter and diagnostics. |
| `src/memoryos_lite/agent_graph.py` | Experimental LangGraph demo. |
| `src/memoryos_lite/agent_answer_eval.py` | Deterministic answer citation diagnostics. |

## Development Commands

```bash
uv run pytest -q
uv run pytest -m "not slow" -q
uv run ruff check .
uv run mypy src
make lint
make eval
uv run memoryos api --reload
uv run memoryos demo run
uv run memoryos demo agent
uv run memoryos eval run --baseline all
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Use `uv` and Python 3.11+.

- `pytest -m "not slow"`: daily dev verification (~5 min, 709 tests).
- `pytest -m slow`: full eval pipelines only (~4.5 min, 12 tests).
- `pytest -q`: full suite (~9.5 min, 721 tests, use for CI/pre-merge).

## Eval Commands

v2 public smoke, no LLM answer/judge:

```bash
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

```bash
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

## Documentation

Current baseline docs:

- `README.md`
- `docs/public-benchmark-diagnosis.md`
- `docs/source-guide.md`
- `docs/store-interface.md`
- `docs/known-issues.md`
- `docs/agentic-memory-roadmap-zh.md`
- `docs/agent-answer-diagnostics.md`
- `docs/implementation-history-summary.md`

Historical implementation specs/plans were summarized into
`docs/implementation-history-summary.md`.

## Conventions

- Preserve default `v1` behavior unless a task explicitly changes it.
- Keep v2 side effects behind `settings.resolved_recall_pipeline == "v2"` unless a new flag is intentionally designed.
- Prefer source-grounded evidence over page-summary-only claims.
- Do not treat public `source_hit` as pure evidence localization unless the metric explicitly comes from planned/retrieved evidence.
- SQLite is the authoritative current store. Filesystem page/trace outputs are debug mirrors.
- Commit focused changes with messages like `feat: ...`, `fix: ...`, or `docs: ...`.
