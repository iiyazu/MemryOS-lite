# MemoryOS Lite Source Guide

This guide maps the current codebase. It intentionally avoids historical phase
notes; implementation history lives under `docs/superpowers/`.

## Top-Level Flow

```text
MemoryOSService
  create_session()
  ingest()
    -> MessageRecord
    -> optional v2 Episode backfill/indexing
  page()
    -> MemoryPage / MemoryItem / trace
  build_context()
    -> v1 ContextBuilder by default
    -> v2 RecallPipeline when MEMORYOS_RECALL_PIPELINE=v2
```

## Important Modules

| Path | Responsibility |
|---|---|
| `config.py` | Runtime settings, feature flags, LLM/Qdrant configuration. |
| `schemas.py` | Pydantic models for messages, episodes, pages, items, traces, context, evals. |
| `store.py` | SQLite persistence, JSON debug mirrors, trace storage, episode backfill. |
| `engine.py` | Application facade and v1 context/paging orchestration. |
| `retrieval/` | Search primitives and v2 recall helpers. |
| `public_benchmarks.py` | LongMemEval/LoCoMo loading, baseline execution, report fields. |
| `evals.py` | Built-in deterministic evals and baseline output structure. |
| `agent_graph.py` | Experimental LangGraph demo nodes. |
| `cli.py` | Typer CLI entrypoint. |
| `api/app.py` | FastAPI REST API. |

## Retrieval Paths

### v1 Default

The default path keeps backward compatibility:

```text
Message
  -> MemoryPage / MemoryItem via paging
  -> ContextBuilder
  -> ContextPackage
```

This path remains the default because existing API/eval behavior depends on it.

### v2 Episode-First Recall

The v2 path is opt-in:

```text
MEMORYOS_RECALL_PIPELINE=v2
  -> ensure_episodes_for_session()
  -> QueryAnalyzer
  -> EpisodeSearcher
  -> RecallPipeline
  -> ContextPackage(metadata diagnostics)
```

`Episode` is one row per raw message. `text` is the evidence shown to the
answering layer; `index_text` adds deterministic context such as role, date,
benchmark session, and neighboring turns for retrieval.

## Storage Model

SQLite is the authoritative store. Page JSON files and trace JSONL files are
debug mirrors for human inspection.

Core tables:

- `sessions`
- `messages`
- `episodes`
- `memory_pages`
- `memory_items`
- `memory_patches`
- `trace_events`

See `docs/store-interface.md` for the table contract.

## Benchmark Entry Points

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite

MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

Use `docs/public-benchmark-diagnosis.md` for metric interpretation.
