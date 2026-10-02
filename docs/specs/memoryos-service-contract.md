# MemoryOS Lite service contract

This document describes the implemented local prototype API. Source schemas and
fresh tests remain authoritative.

## Authority and deployment boundary

`MemoryOSService` owns message, archive, recall, and trace operations over its
SQLite store. JSON mirrors, cache entries, vector indexes, traces, and metrics
are derived. The FastAPI surface is suitable for trusted local integrations; it
does not provide a complete remote authentication, tenancy, rate-limit, or
ownership model.

Defaults are `memory_arch=v3` and `recall_pipeline=v2`. Legacy `v1` memory and
recall paths may be selected explicitly. The agent kernel is off by default;
`external` mode only emits source-attributed advisories for a host process. The
memory curator is likewise off by default.

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
| `GET` | `/sessions/{id}/advisories` | Host-facing advisories; `?version=2` selects curated-memory advisories. |
| `POST` | `/archives/ingest` | Idempotently ingest a source document. |
| `POST` | `/archives/attachments` | Attach an archive document to a session. |
| `GET` | `/archives/passages` | List bounded archive passages. |
| `POST` | `/memory/search` | Search memory, optionally within a session. |
| `GET` | `/memory/pages/{id}` | Read a persisted page. |
| `GET` | `/metrics` | Prometheus exposition. |

The exact request and response fields are defined by
`src/memoryos_lite/api/app.py`, `src/memoryos_lite/api/schemas.py`, and the
Pydantic models they reference.

## Advisories and the memory curator

`GET /sessions/{id}/advisories` without a `version` parameter (or with
`version=1`) keeps the original `memoryos_external_advisories/v1` response
unchanged. `version=2` serves curated-memory advisories:

```json
{
  "schema": "memoryos_external_advisories/v2",
  "items": [
    {
      "advisory_id": "advisory_<40 hex chars>",
      "fingerprint": "<64 hex chars: sha256 over kind, content, and sources>",
      "proposal_type": "curated_memory",
      "kind": "room_fact | room_decision | project_rule | user_preference",
      "topic_key": "project.launch_city",
      "content": "Helios launches in Lisbon.",
      "source_refs": [
        {
          "source_type": "message",
          "source_id": "msg_...",
          "session_id": "sess_...",
          "quote": "<verbatim substring of the cited message>"
        }
      ],
      "supersedes_advisory_id": null
    }
  ]
}
```

Items are bounded to the 32 newest, `advisory_id` is stable for identical
(kind, content, sources), and `supersedes_advisory_id` links a memory to the
advisory it replaced. Any other `version` value is rejected with HTTP 400.

The curator is opt-in via `MEMORYOS_CURATOR_ENABLED=true`; only then does the
app lifespan start the background worker that extracts memories from new
session messages. `/health` always reports a `curator` block:

```json
{
  "enabled": true,
  "state": "ready | degraded | disabled",
  "reason_code": "curator_disabled | curator_llm_key_missing | curator_llm_init_error | curator_llm_error | curator_schema_error | null",
  "model": "gpt-4o-mini",
  "counters": {
    "sessions": 0,
    "runs": 0,
    "proposals": 0,
    "rejected_grounding": 0,
    "rejected_schema": 0,
    "llm_errors": 0
  }
}
```

The block never contains provider keys or provider error text. While the curator
is enabled, the heuristic agent-kernel maintenance advisories are suppressed so
the two advisory producers do not compete.

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
