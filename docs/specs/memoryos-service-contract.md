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
| `POST` | `/sessions` | Create a server-identified session, optionally module-scoped. |
| `POST` | `/sessions/{id}/ingest` | Persist one message; activity metadata is validated. |
| `POST` | `/sessions/{id}/ingest-batch` | Persist a bounded message batch. |
| `POST` | `/sessions/{id}/page` | Explicitly produce a page when eligible. |
| `POST` | `/sessions/{id}/build-context` | Build bounded, source-attributed context; `response_profile: "module_pack/v1"` returns a module resume pack. |
| `GET` | `/sessions/{id}/summary` | Return safe session summary data. |
| `GET` | `/sessions/{id}/trace` | Return diagnostic trace events. |
| `GET` | `/sessions/{id}/advisories` | Host-facing advisories; `?version=2` selects curated-memory advisories, `?version=3` the scoped curated-memory payload. |
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

## Module sessions

A host that assigns one owning agent per module creates the session with
`"scope": {"type": "module", "id": "<module_id>"}`. MemoryOS stores and echoes
the scope; it does not interpret module ownership.

### Activity metadata (`memoryos_activity/v1`)

Ingested message `metadata` may carry `activity_type`, one of `message`,
`review_objection`, `gate_failure`, or `contract_revision`; any session rejects
an unknown value. A module session additionally requires `activity_type`,
`module_id` equal to the scope id, and a non-negative integer `activity_seq`;
a `contract_revision` also requires `contract_id` and a positive integer
`contract_version`. Violations fail with HTTP 422. Gate logs are stored in
full; the curator prompt sees only a bounded head and tail.

### Curated module memories

In a module session a `lesson` must quote at least one `review_objection` or
`gate_failure` message, otherwise it is rejected. A memory's version is the highest
`activity_seq` among its cited messages, and with the default deterministic
consolidation the newest version per `(memory_kind, topic_key)` wins. A
repeated mistake is recorded under the same `topic_key`: each newly cited
review-objection or gate-failure message adds one to the lesson's
`occurrences` (once per message id; plain messages add nothing). A lesson
keeps its newest 8 sources, while `occurrences` keeps accumulating.

### `module_pack/v1`

`POST /sessions/{id}/build-context` with `"response_profile": "module_pack/v1"`
returns a resume pack for the module owner after compaction, a crash, or a
restart. `task` is still required by the request model; `budget` defaults to
1500 and is capped at 4000. A non-module session or an out-of-range budget
fails with HTTP 422.

The pack is composed deterministically, with no retrieval and no LLM, from the
archive documents attached to the module session:

```json
{
  "schema": "memoryos_module_pack/v1",
  "scope": {"type": "module", "id": "auth"},
  "sections": {
    "contracts": [
      {"contract_id": "...", "version": 3, "document_id": "...", "summary": "<one line>",
       "content_sha256": "...", "source_refs": []}
    ],
    "lessons": [
      {"document_id": "...", "memory_kind": "lesson", "topic_key": "auth.refresh_lock",
       "version": 7, "text": "...", "occurrences": 2, "content_sha256": "...", "source_refs": []}
    ],
    "decisions": []
  },
  "omitted": {"contracts": 0, "lessons": 0, "decisions": 0},
  "estimated_tokens": 412,
  "budget": 1500,
  "truncated": false,
  "diagnostics": {"conflict_check": "unavailable"},
  "diagnostics_digest": "<sha256 of the canonical payload>"
}
```

- `contracts`: newest `contract_version` per `contract_id`, as a pointer only;
  the host reads the full text from its own copy and can check `content_sha256`.
- `lessons`: highest version per `topic_key`, most `occurrences` first, then
  newest.
- `decisions`: decisions and facts, highest version per `topic_key`, newest
  first.

Items are added in that order until the token budget or 24 items are reached;
the rest are counted in `omitted`. Every item is an attached archive document,
so the host re-proves it through its normal source checks. When
`MEMORYOS_MODULE_PACK_CONFLICT_THRESHOLD` is set, included memories with
different topic keys whose FastEmbed cosine reaches the threshold are marked
`possible_conflict_with`; it is unset by default.

### Advisories v3

`?version=3` returns `memoryos_external_advisories/v3`: the v2 item fields plus
`scope`, `memory_kind`, `version`, `occurrences`, and per-source
`activity_type` / `external_id`, under a top-level `session_scope`. Module
lessons and decisions use the kinds `module_lesson` and `module_decision`. See
`docs/contracts/memoryos_external_advisories_v3.example.json`.

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
