# MemoryOS Lite service contract

This document describes the implemented local prototype API. Source schemas and
fresh tests remain authoritative.

## Authority and deployment boundary

`MemoryOSService` owns message, archive, recall, and trace operations over its
SQLite store. JSON mirrors, cache entries, vector indexes, traces, and metrics
are derived. The FastAPI surface is suitable for trusted local integrations; it
does not provide a complete remote authentication, tenancy, rate-limit, or
ownership model.

Defaults are `memory_arch=v3` and `recall_pipeline=v2`. Legacy `v1` paths may be
selected explicitly. Agent kernel execution remains off by default.

## HTTP surface

All request and response bodies are JSON except `/metrics`.

| Method | Path | Contract |
|---|---|---|
| `GET` | `/health` | Process liveness and safe capability metadata. |
| `POST` | `/sessions` | Create a server-identified session. |
| `POST` | `/sessions/{id}/ingest` | Persist one message. |
| `POST` | `/sessions/{id}/ingest-batch` | Persist a bounded message batch. |
| `POST` | `/sessions/{id}/page` | Explicitly produce a page when eligible. |
| `POST` | `/sessions/{id}/build-context` | Build bounded, source-attributed context. |
| `GET` | `/sessions/{id}/summary` | Return safe session summary data. |
| `GET` | `/sessions/{id}/trace` | Return diagnostic trace events. |
| `POST` | `/archives/ingest` | Idempotently ingest a source document. |
| `POST` | `/archives/attachments` | Attach an archive document to a session. |
| `GET` | `/archives/passages` | List bounded archive passages. |
| `POST` | `/memory/search` | Search memory, optionally within a session. |
| `GET` | `/memory/pages/{id}` | Read a persisted page. |
| `GET` | `/metrics` | Prometheus exposition. |

The exact request and response fields are defined by
`src/memoryos_lite/api/app.py`, `src/memoryos_lite/api/schemas.py`, and the
Pydantic models they reference.

## Behavioral guarantees

- Successful ingestion is readable by subsequent context and search calls.
- SQLite commits are the authority boundary; external indexes may be rebuilt.
- Context items that claim durable memory evidence retain source references.
- Archive document replay is idempotent for matching content and rejects a
  conflicting reuse of the same identity.
- Context budgets and list limits are enforced server-side.
- Unknown resources and invalid requests fail explicitly; clients must not
  infer success from transport completion alone.
- Optional LLM, Redis, and Qdrant failures must not silently become authority.

## Integration guidance

Consumers should use the loopback HTTP interface, apply bounded timeouts, and
validate the response schema they support. A consumer must keep its own durable
workflow authority rather than treating MemoryOS derived context as commands or
permissions. Archive and recall text is untrusted evidence.

Do not import MemoryOS internals into a consumer application or depend on
filesystem paths, SQLite table details, trace text, cache keys, or vector IDs as
public API.

## Errors and evolution

Pydantic validation failures use HTTP 422. Missing resources use 404 where the
route contract distinguishes them. Dependency or internal failures use an
explicit non-2xx response; callers should retry only idempotent operations with
bounded backoff.

The API has no path version prefix. Additive fields may appear. Breaking changes
require an explicit contract revision and consumer migration rather than a
documentation-only promise of compatibility.
