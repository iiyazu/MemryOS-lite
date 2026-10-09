# MemoryOS Lite Source Guide

This guide maps the current codebase. Historical phases belong in Git history,
not the live architecture contract.

## Top-Level Flow

```text
MemoryOSService
  create_session()
  ingest()
    -> MessageRecord
    -> v2 Episode backfill/indexing
  build_context()
    -> v3 ContextComposer
    -> v2 RecallPipeline (also the fallback if the composer fails)
```

## Important Modules

| Path | Responsibility |
|---|---|
| `config.py` | Runtime settings, feature flags, LLM configuration. |
| `schemas.py` | Pydantic models for messages, episodes, traces, context and the HTTP API. |
| `store.py` | Thin public `MemoryStore` composition root and stable imports. |
| `store_models.py` / `store_runtime.py` | SQLite schema, engine lifecycle, migrations, and transactions. |
| `store_sessions.py` | Session, message, episode, and recall-watermark persistence. |
| `store_archive.py` | Core/archive documents, passages, attachments, and governed-memory persistence. |
| `store_legacy.py` | Traces, their JSONL debug mirror, and store reset. |
| `store_protocols.py` | Consumer-specific structural persistence contracts. |
| `engine.py` | Application facade: ingest, context building, archives, `/curate`. |
| `retrieval/` | Search primitives and v2 recall helpers. |
| `context_composer.py` | Default v3 layered composer and budget diagnostics. |
| `v3_contracts.py` | v3 source refs, core/archival contracts, context package. |
| `curator/` | Stateless `/curate` (`curate.py`) and its LangGraph repair loop (`graph.py`); the in-process session curator RoomMem runs (`runner.py`). |
| `cli.py` | Typer CLI entrypoint (`api`, `demo`). |
| `api/app.py` | FastAPI REST API. |

The evaluation harnesses live in the repo-root `memoryos_eval/` package, which the
wheel does not ship: `roommem.py` (RoomMem), `modulemem.py` (ModuleMem), `ask.py`
and `ask_demo.py` (the agentic `ask` graph and its offline demo), `public_benchmarks.py`
with `baselines.py`, `llm_judge.py` and `longmemeval_manifest.py` (LongMemEval/LoCoMo;
historical, no longer maintained) and `cli.py` (`uv run python -m memoryos_eval --help`).

## Retrieval Paths

### v3 Composer

Context building uses the layered v3 composer:

```text
Message Log
  -> Recall Memory
  -> Archival Memory
  -> ContextComposer
  -> ContextPackage-compatible payload
```

### v2 Episode-First Recall

```text
ensure_episodes_for_session()
  -> QueryAnalyzer
  -> EpisodeSearcher
  -> RecallPipeline
  -> ContextPackage(metadata diagnostics)
```

`Episode` is one row per raw message. `text` is the evidence shown to the
answering layer; `index_text` adds deterministic context such as role, date,
benchmark session, and neighboring turns for retrieval.

## Storage Model

SQLite is the authoritative store. Trace JSONL files are debug mirrors for
human inspection.

Core tables:

- `sessions`
- `messages`
- `episodes`
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
MEMORYOS_RECALL_PIPELINE=v2 uv run python -m memoryos_eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge

MEMORYOS_MEMORY_ARCH=v3 uv run python -m memoryos_eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

Use `docs/public-benchmark-diagnosis.md` for metric interpretation.
