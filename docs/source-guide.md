# MemoryOS Lite Source Guide

This guide maps the current codebase. Historical phases belong in Git history,
not the live architecture contract.

## Top-Level Flow

```text
SessionMemoryService (memoryos_eval/memory/service.py, in process only)
  create_session()
  ingest()
    -> MessageRecord
    -> v2 Episode backfill/indexing
  build_context()
    -> v3 ContextComposer
    -> v2 RecallPipeline
```

## Important Modules

| Path | Responsibility |
|---|---|
| `config.py` | Runtime settings, feature flags, LLM configuration. |
| `engine.py` | `MemoryOSService`, the stateless service behind `/curate`, `/recall`, `/similar`; it opens no database. |
| `retrieval/` | `/recall` primitives: the `EmbeddingClient` protocol, cosine, the bilingual tokenizer and stopword filter, embedding providers. |
| `recall.py` | Stateless `/recall` (deterministic BM25 + dense RRF ranking of caller-supplied items within a token budget) and `/similar` (near-duplicate pairs by dense cosine). |
| `curator/` | Stateless `/curate` (`curate.py`) and its LangGraph repair loop (`graph.py`). |
| `cli.py` | Typer CLI entrypoint (`api`, `demo`). |
| `api/app.py` | FastAPI REST API: the stateless `/health`, `/curate`, `/recall`, `/similar`. Sessions, ingest, context building, and archives are in-process only (evaluation harness). |

The evaluation harnesses live in the repo-root `memoryos_eval/` package, which the
wheel does not ship: `roommem.py` (RoomMem), `modulemem.py` (ModuleMem), `collab.py`
(`eval collab`: quality of the collab curate profile), `ask.py`
and `ask_demo.py` (the agentic `ask` graph and its offline demo), `public_benchmarks.py`
with `baselines.py`, `llm_judge.py` and `longmemeval_manifest.py` (LongMemEval/LoCoMo;
historical, no longer maintained) and `cli.py` (`uv run python -m memoryos_eval --help`).

`memoryos_eval/memory/` is the in-process session memory those harnesses measure:

| Path | Responsibility |
|---|---|
| `service.py` | `SessionMemoryService`: the product service plus sessions, ingest, `build_context`, archives and traces. |
| `context_composer.py` | The v3 layered composer and its budget diagnostics. |
| `retrieval/` | v2 episode-first recall (`recall_pipeline.py`, `episode_searcher.py`, `query_analyzer.py`), archival passages (`archival_searcher.py`, `archival_vector.py`) and superseded marks (`supersede.py`). |
| `source_evidence.py` | The compact `source_evidence/v2` envelope built from a context package. |
| `archive_rag.py` | Archive document ingest adapters (see `docs/archive-rag-boundary.md`). |
| `session_curator.py` | The session curator RoomMem runs: room-profile `/curate` windows over a stored session. |
| `budget.py`, `utils.py` | Dynamic context budget; generic-acknowledgement filter for baselines. |
| `schemas.py` | Pydantic models for messages, episodes, traces, context packages and archive requests. |
| `v3_contracts.py` | v3 source refs, core/archival contracts, context package. |
| `store.py` | Thin `MemoryStore` composition root. |
| `store_models.py` / `store_runtime.py` | SQLite schema, engine lifecycle, migrations, and transactions. |
| `store_sessions.py` | Session, message, episode, and recall-watermark persistence. |
| `store_archive.py` | Archive documents, passages, attachments. |
| `store_curator.py` | Curated memories and the session curator watermark. |
| `store_legacy.py` | Traces, their JSONL debug mirror, and store reset. |
| `store_protocols.py` | Consumer-specific structural persistence contracts. |

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

The session store (`memoryos_eval/memory/`, in process only) is SQLite-authoritative. Trace JSONL files are debug mirrors for
human inspection.

Core tables:

- `sessions`
- `messages`
- `episodes`
- `trace_events`
- `archival_documents`
- `archival_chunks`
- `archival_passages`
- `archive_attachments`
- `curated_memories`
- `curator_state`

See `docs/store-interface.md` for the table contract.

## Benchmark Entry Points

```bash
uv run python -m memoryos_eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge

uv run python -m memoryos_eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 10 \
  --no-llm-answer \
  --no-llm-judge
```

Use `docs/public-benchmark-diagnosis.md` for metric interpretation.
