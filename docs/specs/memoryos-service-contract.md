# MemoryOS Lite service contract

This document describes the implemented local prototype API. Source schemas and
fresh tests remain authoritative.

## Authority and deployment boundary

`MemoryOSService` owns message, archive, recall, and trace operations over its
SQLite store. JSON mirrors, cache entries, vector indexes, traces, and metrics
are derived. The FastAPI surface is suitable for trusted local integrations; it
does not provide a complete remote authentication, tenancy, rate-limit, or
ownership model.

Context is built by the v3 composer over v2 recall; there is no v1 memory or
recall path.

## HTTP surface

All request and response bodies are JSON.

| Method | Path | Contract |
|---|---|---|
| `GET` | `/health` | Liveness, package `version`, and safe capability metadata. |
| `POST` | `/sessions` | Create a server-identified session. |
| `POST` | `/sessions/{id}/ingest` | Persist one message. |
| `POST` | `/sessions/{id}/build-context` | Build bounded, source-attributed context. |
| `POST` | `/curate` | Stateless module memory curation (`memoryos_curate/v1`). |
| `POST` | `/archives/ingest` | Idempotently ingest a source document. |
| `POST` | `/archives/attachments` | Attach an archive document to a session. |

The exact request and response fields are defined by
`src/memoryos_lite/api/app.py`, `src/memoryos_lite/api/schemas.py`, and the
Pydantic models they reference.

## No session curator

The service runs no background curator and serves no advisories. A host that
wants durable memories calls `POST /curate` and keeps them itself. The
stateful room-profile host of the same graph (`Curator.run_session`) runs in
process only in the RoomMem evaluation.

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
  is the profile of the in-process session curator (RoomMem): plain messages yield facts, decisions,
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

## Pull side: superseded marks

A superseded mark is the verbatim quote that grounded a now-superseded memory,
with the current statement when known. Evidence whose text contains such a
quote (whitespace- and case-insensitive) and no quote of an active memory
states an outdated value. Marks come from the host (`superseded` on the
request), which keeps the memories.

`build-context` with `response_profile: "source_evidence/v2"` accepts
`"superseded": [{"quote": "...", "current": "..."}]` (up to 64). Marked items
are ranked after the others, so a full envelope drops them first. Item text
and fields are unchanged; consumers keep re-proving text by `content_sha256`.

The service has no ask route. The agentic `ask` graph (`memoryos_memory_ask/v1`)
lives in the evaluation package (`memoryos_eval/ask.py`: RoomMem's `agentic`
evidence mode and `python -m memoryos_eval ask-demo`). Given an `AskRequest`
(`question`, optional `task`, `budget` up to 800, `max_rounds` 0-2, `superseded`)
it runs a LangGraph graph:
`retrieve` (one `build-context` + v2 projection, new items merged) → `grade`
(deterministic: enough when a current item covers at least half of the
question's keywords) → `rewrite` (the LLM proposes one new query) → `retrieve`
again, at most `max_rounds` extra times. Without an LLM it stops after the
first retrieval. The response (`memoryos_memory_ask/v1`) lists `queries` and
`items` (current items first, outdated last, within `budget`), each with
`text`, `source_refs`, the `query` that found it, `outdated`, and `current`;
`diagnostics` reports retrievals, LLM calls, the stop reason, and omitted
items.

## Behavioral guarantees

- Successful ingestion is readable by subsequent context and search calls.
- SQLite commits are the authority boundary; external indexes may be rebuilt.
- Context items that claim durable memory evidence retain source references.
- Archive document replay is idempotent for matching content and rejects a
  conflicting reuse of the same identity.
- Context budgets and list limits are enforced server-side.
- Unknown resources and invalid requests fail explicitly; clients must not
  infer success from transport completion alone.
- Optional LLM and vector-index failures must not silently become authority.
- `build-context` does not retry or degrade inside the service. A failure is an
  HTTP 500 without exception text, and the host decides how to degrade (for
  example, answer without memory).

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
