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
| `GET` | `/health` | Liveness, package `version`, the `capabilities` list, and safe capability details. |
| `POST` | `/sessions` | Create a server-identified session. |
| `POST` | `/sessions/{id}/ingest` | Persist one message. |
| `POST` | `/sessions/{id}/build-context` | Build bounded, source-attributed context. |
| `POST` | `/curate` | Stateless module memory curation (`memoryos_curate/v1`). |
| `POST` | `/recall` | Stateless, deterministic ranking of caller-supplied items (`memoryos_recall/v1`). |
| `POST` | `/similar` | Near-duplicate pairs by dense cosine (`memoryos_similar/v1`). |
| `POST` | `/archives/ingest` | Idempotently ingest a source document. |
| `POST` | `/archives/attachments` | Attach an archive document to a session. |

The exact request and response fields are defined by
`src/memoryos_lite/api/app.py`, `src/memoryos_lite/api/schemas.py`, and the
Pydantic models they reference.

## Health and capabilities

`GET /health` returns `status`, `version` (now `0.4.0`), `capabilities`, and
`capability_details`.

`capabilities` is the list the hub reads at startup and skips features that are
missing. In order: `curate` and `curate.collab` when an LLM (or its API key) is
configured and the LangGraph runtime is installed; `recall` always; `similar`
when the embedding model loads.

`capability_details` is the former `capabilities` object:
`build_context_profiles`, `hybrid` (`lexical`, `semantic`, `rrf`),
`message_ingest`, and `curate` (the curate schema). It serves the stateful
routes, which are scheduled for removal (MO-10).

## No session curator

The service runs no background curator and serves no advisories. A host that
wants durable memories calls `POST /curate` and keeps them itself. The
stateful room-profile host of the same graph (`Curator.run_session`) runs in
process only in the RoomMem evaluation.

## Ranking: `POST /recall`

A host (the xmuse 2 hub) sends the candidate items of one over-budget view
layer; MemoryOS ranks and truncates them. There is no LLM and no database read
or write. The only state is an in-process embedding cache keyed by the SHA-256
of the text: derived, rebuildable, and an LRU of 8192 entries.

Request (`RecallRequest`):

```json
{
  "schema": "memoryos_recall/v1",
  "query": "Decimal amounts",
  "items": [
    {"id": "E12", "text": "Amounts are Decimal strings", "kind": "decision",
     "thread_id": "task", "roles": ["impl"], "seq": 57}
  ],
  "hints": {"thread_id": "task", "role": "impl"},
  "budget_tokens": 1000,
  "k": 40
}
```

- `schema` must be `memoryos_recall/v1`; `query` may be empty (up to 4000
  characters). `items` holds up to 500 entries, each with a unique `id` (1-128
  characters), `text` (1-2000 characters), an optional free-label `kind` (up to
  32 characters, unused for scoring), optional `thread_id`, `roles` (up to 16),
  and `seq` (the host's monotonic version, 0 or greater; larger is newer).
- `hints` carries an optional `thread_id` and `role`. `budget_tokens` is
  1-200000, and `k` is 1-500, default 40.

`score` is the sum of the terms below.

| Constant | Value | Term |
|---|---|---|
| `RRF_K` | 60 | Reciprocal-rank fusion over the BM25 and dense cosine ranks. |
| `THREAD_BONUS` | 0.02 | The item's `thread_id` equals `hints.thread_id`. |
| `ROLE_BONUS` | 0.01 | `hints.role` is one of the item's `roles`. |
| `RECENCY_MAX` | 0.005 | Newest `seq`; oldest gets 0, linear in the rank of the item's `seq` among the distinct seqs. |

An item enters the BM25 ranking only when it shares a non-stopword token with
the query, and the dense ranking only when its cosine is greater than 0. Scores
are rounded to 6 decimals. Ordering is deterministic: score descending, then
`seq` descending, then `id` ascending, so identical input gives a byte-identical
response.

Budget: walk the ranking and include an item when it fits in the remaining
`budget_tokens` and fewer than `k` items are included; otherwise put its id in
`dropped` (in rank order) and continue. `tokens_used` is the sum over the
included items. Token counts come from the service's `TokenEstimator`;
`diagnostics.token_estimator` names it (`tiktoken:cl100k_base`, or
`regex:word_or_punct` when tiktoken has no encoding).

`why` lists the signals that contributed, in this order: `bm25`, `dense`,
`thread`, `role`. Recency always applies and is not listed.

Degrade: without an embedding provider, or when embedding fails, ranking is
BM25-only and `diagnostics.dense` is false. The response reports this rather
than staying silent. With an empty query no dense scores are needed, so `dense`
then only says whether the provider is configured.

Cost: BM25-only ranking of 500 items takes about 20-30 ms. Dense scoring embeds
each text once and then hits the cache: with FastEmbed on a 16-core CPU, 500
cached items take under 100 ms (p95), while 500 never-seen statement-sized
texts take about 5 s. The request still completes and fills the cache, so a
host that times out falls back once and is fast on the next call.

Response (`RecallResponse`):

```json
{
  "schema": "memoryos_recall/v1",
  "ranked": [{"id": "E12", "score": 0.046393, "why": ["bm25", "thread", "role"]}],
  "dropped": [],
  "tokens_used": 5,
  "diagnostics": {"dense": false, "token_estimator": "tiktoken:cl100k_base"}
}
```

Errors: 422 for an invalid request (wrong schema, too many items, text too long,
duplicate ids, or `budget_tokens`/`k` out of range).

## Near-duplicates: `POST /similar`

When one layer of the hub's alignment store is over its limit (the hub's
trigger is 120 % of the limit), the hub asks for near-duplicate pairs and
passes them to its next `/curate` call, which may propose a merge. There is no
LLM and no database. Embeddings use the same in-process cache as `/recall`.

Request (`SimilarRequest`):

```json
{
  "schema": "memoryos_similar/v1",
  "items": [
    {"id": "E3", "text": "Amounts are Decimal strings"},
    {"id": "E9", "text": "Amounts are decimal strings."}
  ],
  "threshold": 0.88
}
```

- `schema` must be `memoryos_similar/v1`. `items` holds up to 500 entries, each
  with a unique `id` (1-128 characters) and `text` (1-2000 characters).
- `threshold` is greater than 0 and at most 1, default 0.88.

Response (`SimilarResponse`):

```json
{
  "schema": "memoryos_similar/v1",
  "pairs": [{"a": "E3", "b": "E9", "score": 0.97}],
  "diagnostics": {"dense": true}
}
```

`pairs` holds every pair whose cosine, rounded to 6 decimals, is at least
`threshold`; each pair names its ids as `a` and `b` with `a < b` in string
order. Pairs are ordered by score descending, then `(a, b)`. The example score
is illustrative. `diagnostics.dense` is always true. With FastEmbed on a
16-core CPU, 500 cached items take about 100 ms and 500 never-seen
statement-sized texts about 3 s.

Errors: 422 for an invalid request (wrong schema, too many items, text too long,
duplicate ids, or `threshold` out of range), and 503 with
`similar_unavailable` when no embedding provider is configured or embedding
fails. BM25 never stands in for dense similarity.

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

- `profile` is `module` (default), `room`, or `collab`. Under `module`, `memories` may
  only hold decisions and facts; lessons come from failure assignments. `room`
  is the profile of the in-process session curator (RoomMem): plain messages yield facts, decisions,
  rules, preferences, and lessons, and a lesson proposal that cites a new
  activity adds one occurrence to the active lesson on its topic key. `collab`
  is the alignment curator for one xmuse topic (see "The collab profile").
- `kind` is `lesson`, `decision`, `fact`, `rule`, `preference`, `convention`,
  `assumption`, or `question`; activity `type` is `message`, `review_objection`,
  `gate_failure`, or `contract_revision`. An activity may also carry an optional
  `kind` (the xmuse message kind: `message`, `handoff`, `review_request`,
  `decision`, `assumption`, or `question`), used only by `collab` to label a
  `message` activity in the prompt.
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

### The collab profile

`collab` proposes alignment entries for one xmuse topic, where several agents
collaborate; `scope_id` is the topic id. The host (the xmuse 2 hub) keeps every
entry, so everything MemoryOS returns is a proposal that the topic owner or a
human confirms. MemoryOS never decides which side of a contradiction wins.

`memories` may hold `decision`, `convention`, `assumption`, `question`, and
`lesson` (room-style lesson proposals); `fact`, `rule`, and `preference` are
rejected. A `review_objection` or `gate_failure` activity in the window still
gets the closed-world assignment accounting of the `module` profile.

`active` entries include the ones agents declared themselves. A proposal whose
statement equals any active statement (whitespace- and case-insensitive, under
any topic key) is a noop. Reusing an active entry's topic key proposes a
replacement (`supersedes_id`).

A memory in the LLM reply may carry `"resolves": [ids]`; every id must be an
active entry of kind `question`, otherwise the memory is rejected and the rule
goes back to the LLM. The response memory then carries `resolves_ids` (an empty
list when it answers nothing). `resolves_ids` is part of the content-derived
memory id only when it is non-empty.

Conflicts: the reply may list `{"a_id", "b_id", "reason", "sources"}`. Each side
is an active id or the topic key of a memory proposed in the same reply; at most
one side may be new; a reason of 1-200 characters and 0-3 verbatim sources are
required. In the response, a new side is replaced by the id of the proposed
version or, when that proposal turned out to be a noop, by the id of the active
entry with that topic key; duplicate pairs and self-pairs are dropped. Invalid
conflicts are violations and go through the repair loop like any other rule.

The prompt asks for short statements that keep every qualifier (scope,
conditions, exceptions, units), and lists the active entries with their ids. The
repair prompt asks for all "memories, assignments and conflicts".

Output stability: `conflicts` (response) and `resolves_ids` (memory) are present
only under `collab`; module and room responses are byte-identical to before.

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
memory each one replaces. Under `collab` the response also has `conflicts` and
each memory has `resolves_ids`. Memory ids are derived from content, so a replayed
request yields the same ids. Lessons keep their newest 8 sources while
`occurrences` keeps counting.

Errors: 422 for an invalid request, 503 with `curator_llm_key_missing`,
`curator_llm_init_error`, or `curate_requires_langgraph` when curation cannot
run, and 502 with `curator_llm_error` when the provider call fails. No error
carries provider text. `/health` lists `curate` and `curate.collab` in
`capabilities` when curation can run, and reports the schema as
`capability_details.curate`.

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
