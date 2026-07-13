# MemoryOS Lite Source Guide

This guide maps the current codebase. Historical phases belong in Git history,
not the live architecture contract.

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
    -> v3 ContextComposer by default
    -> v1 ContextBuilder when MEMORYOS_MEMORY_ARCH=v1
    -> v2 RecallPipeline by default
    -> agent kernel remains opt-in
```

## Important Modules

| Path | Responsibility |
|---|---|
| `config.py` | Runtime settings, feature flags, LLM/Qdrant configuration. |
| `schemas.py` | Pydantic models for messages, episodes, pages, items, traces, context, evals. |
| `store.py` | Thin public `MemoryStore` composition root and stable imports. |
| `store_models.py` / `store_runtime.py` | SQLite schema, engine lifecycle, migrations, and transactions. |
| `store_sessions.py` | Session, message, episode, and recall-watermark persistence. |
| `store_archive.py` | Core/archive documents, passages, attachments, and governed-memory persistence. |
| `store_legacy.py` | Page/item indexes, patches, traces, debug mirrors, and maintenance. |
| `store_protocols.py` | Consumer-specific structural persistence contracts. |
| `engine.py` | Application facade and v1 context/paging orchestration. |
| `retrieval/` | Search primitives and v2 recall helpers. |
| `context_composer.py` | Default v3 layered composer and budget diagnostics. |
| `agent_kernel.py` | Opt-in v3 kernel step runner, policy decisions, approval pause traces. |
| `v3_contracts.py` | v3 source refs, core/archival contracts, context package, kernel contracts. |
| `core_memory.py` | Source-backed core memory block service. |
| `public_benchmarks.py` | LongMemEval/LoCoMo loading, baseline execution, report fields. |
| `evals.py` | Built-in deterministic evals and baseline output structure. |
| `agent_graph.py` | Experimental LangGraph demo nodes. |
| `cli.py` | Typer CLI entrypoint. |
| `api/app.py` | FastAPI REST API. |

## Retrieval Paths

### v3 Default

The default path now uses the layered v3 composer while preserving `v1`
as an explicit fallback:

```text
Message Log
  -> Recall Memory
  -> Archival Memory
  -> Core Memory
  -> ContextComposer
  -> ContextPackage-compatible payload
```

Pin `MEMORYOS_MEMORY_ARCH=v1` to recover the legacy path.

### v2 Episode-First Recall

The v2 path is the default:

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

### v1 Legacy Fallback

```text
MEMORYOS_MEMORY_ARCH=v1
  -> ContextBuilder
  -> MemoryPage / MemoryItem via paging
  -> ContextPackage
```

`MEMORYOS_RECALL_PIPELINE=v2` still enables the separate episode-first recall
path. `MEMORYOS_AGENT_KERNEL=v1` remains a separate experimental opt-in.

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
- `core_memory_blocks`
- `core_memory_history`
- `archival_documents`
- `archival_chunks`
- `archival_passages`
- `archival_memories`
- `archival_memory_history`

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

MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

Use `docs/public-benchmark-diagnosis.md` for metric interpretation.
