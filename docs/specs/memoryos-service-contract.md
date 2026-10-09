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
recall paths may be selected explicitly. The memory curator is off by default.

## HTTP surface

All request and response bodies are JSON.

| Method | Path | Contract |
|---|---|---|
| `GET` | `/health` | Process liveness and safe capability metadata. |
| `POST` | `/sessions` | Create a server-identified session. |
| `POST` | `/sessions/{id}/ingest` | Persist one message. |
| `POST` | `/sessions/{id}/build-context` | Build bounded, source-attributed context. |
| `GET` | `/sessions/{id}/advisories` | Host-facing advisories; `?version=2` selects curated-memory advisories. |
| `POST` | `/curate` | Stateless module memory curation (`memoryos_curate/v1`). |
| `POST` | `/sessions/{id}/ask` | Agentic retrieval with superseded marks (`memoryos_memory_ask/v1`). |
| `POST` | `/archives/ingest` | Idempotently ingest a source document. |
| `POST` | `/archives/attachments` | Attach an archive document to a session. |

The exact request and response fields are defined by
`src/memoryos_lite/api/app.py`, `src/memoryos_lite/api/schemas.py`, and the
Pydantic models they reference.

## Advisories and the memory curator

`GET /sessions/{id}/advisories?version=2` serves curated-memory advisories; any
other `version` (or none) answers `400`:

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
session messages. The worker is a stateful host of the `/curate` graph below:
it sends each window with the session's active memories under
`profile: "room"` and stores the returned versions. `/health` always reports a `curator` block:

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

The block never contains provider keys or provider error text.

## Module memory: `POST /curate`

A host that assigns one long-lived owning agent per module keeps that module's
memories itself and asks MemoryOS to curate new activity. MemoryOS stores
nothing for this endpoint, so a retried request is safe.

Request (`CurateRequest`):

```json
{
  "scope_id": "auth",
  "profile": "module",
  "active": [
    {"id": "mem_...", "kind": "lesson", "topic_key": "auth.refresh_lock",
     "statement": "...", "version": 7, "occurrences": 2,
     "sources": [{"activity_id": "a07", "quote": "..."}]}
  ],
  "context": [{"id": "a19", "seq": 19, "type": "message", "speaker": "owner", "text": "..."}],
  "window": [{"id": "a20", "seq": 20, "type": "gate_failure", "speaker": "ci", "text": "..."}],
  "max_repairs": 2
}
```

- `profile` is `module` (default) or `room`. Under `module`, `memories` may
  only hold decisions and facts; lessons come from failure assignments. `room`
  is the session curator's profile: plain messages yield facts, decisions,
  rules, preferences, and lessons, and a lesson proposal that cites a new
  activity adds one occurrence to the active lesson on its topic key.
- `kind` is `lesson`, `decision`, `fact`, `rule`, or `preference`; activity
  `type` is `message`, `review_objection`, `gate_failure`, or
  `contract_revision`.
- `window` holds 1-32 activities, `context` up to 8 (read-only, quotable),
  `active` up to 60. Activity ids must be unique across `context` and `window`.
  `seq` is the host's monotonic activity order and becomes memory versions.
- Gate logs may be sent in full; the prompt shows a bounded head and tail, and
  quotes are checked against the full text.

Closed-world lesson accounting: every `review_objection` and `gate_failure`
in `window` must receive exactly one assignment, either a lesson topic key with
a verbatim quote from that activity, or a dismissal with a reason. A lesson is
created or reworded only together with an assigned failure, and its
`occurrences` is the number of failures assigned to it; a failure the active
lesson already cites is not counted again. Decisions and facts quote 1-3
activities; per topic key the newest wins, a restatement of the active memory
is a noop, and a proposal older than it is dropped as stale.

The curation runs as a LangGraph graph: `extract` (LLM) → `check`
(deterministic rule validation) → `repair` (the previous reply and the broken
rules go back to the LLM, at most `max_repairs` times) → `consolidate`. After
the last repair, invalid parts are dropped and failures without an assignment
are listed in `unaccounted`.

Response (`CurateResponse`):

```json
{
  "schema_version": "memoryos_curate/v1",
  "scope_id": "auth",
  "memories": [
    {"id": "mem_<content hash>", "kind": "lesson", "topic_key": "auth.refresh_lock",
     "statement": "...", "version": 20, "occurrences": 3,
     "sources": [{"activity_id": "a20", "quote": "..."}], "supersedes_id": "mem_..."}
  ],
  "assignments": [
    {"activity_id": "a20", "lesson": "auth.refresh_lock", "quote": "...", "dismiss": null}
  ],
  "unaccounted": [],
  "diagnostics": {"llm_calls": 1, "repairs": 0, "initial_violations": [],
                  "final_violations": [], "rejected_memories": 0,
                  "noop_memories": 0, "stale_memories": 0}
}
```

`memories` are the new versions to store; `supersedes_id` names the active
memory each one replaces. Memory ids are derived from content, so a replayed
request yields the same ids. Lessons keep their newest 8 sources while
`occurrences` keeps counting.

Errors: 422 for an invalid request, 503 with `curator_llm_key_missing`,
`curator_llm_init_error`, or `curate_requires_langgraph` when curation cannot
run, and 502 with `curator_llm_error` when the provider call fails. No error
carries provider text. `/health` reports `capabilities.curate` as
`memoryos_curate/v1`.

## Pull side: superseded marks and `POST /sessions/{id}/ask`

A superseded mark is the verbatim quote that grounded a now-superseded memory,
with the current statement when known. Evidence whose text contains such a
quote (whitespace- and case-insensitive) and no quote of an active memory
states an outdated value. Marks come from the host (`superseded` on the
request, for hosts that keep memories themselves) and, when
`MEMORYOS_DEMOTE_SUPERSEDED=true`, from the session's own curated memories.

`build-context` with `response_profile: "source_evidence/v2"` accepts
`"superseded": [{"quote": "...", "current": "..."}]` (up to 64). Marked items
are ranked after the others, so a full envelope drops them first. Item text
and fields are unchanged; consumers keep re-proving text by `content_sha256`.

`POST /sessions/{id}/ask` (`AskRequest`: `question`, optional `task`,
`budget` up to 800, `max_rounds` 0-2, `superseded`) runs a LangGraph graph:
`retrieve` (one `build-context` + v2 projection, new items merged) → `grade`
(deterministic: enough when a current item covers at least half of the
question's keywords) → `rewrite` (the LLM proposes one new query) → `retrieve`
again, at most `max_rounds` extra times. Without an LLM it stops after the
first retrieval. The response (`memoryos_memory_ask/v1`) lists `queries` and
`items` (current items first, outdated last, within `budget`), each with
`text`, `source_refs`, the `query` that found it, `outdated`, and `current`;
`diagnostics` reports retrievals, LLM calls, the stop reason, and omitted
items. 404 for an unknown session, 503 `ask_requires_langgraph` when the
graph runtime is missing.

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
