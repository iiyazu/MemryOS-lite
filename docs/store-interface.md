# Store Interface

This is the in-process session store of the evaluation harness
(`memoryos_eval/memory/store*.py`); the HTTP service keeps no state and the
wheel does not ship it. Storage is SQLite-first and DB-authoritative.
Filesystem trace files are debug mirrors, not the primary state.

## Authority

| Concern | DB | Filesystem | Authority |
|---|---|---|---|
| Sessions | `sessions` | none | DB |
| Messages | `messages` | none | DB |
| Episodes | `episodes` | none | DB |
| Traces | `trace_events` | `.memoryos/traces/*.jsonl` | DB |
| Archives | `archival_documents`, `archival_chunks`, `archival_passages`, `archive_attachments` | none | DB |
| Curated memories (RoomMem's in-process curator) | `curated_memories`, `curator_state` | none | DB |

## Tables

### `sessions`

- `id`
- `title`
- `created_at`

### `messages`

- `id`
- `session_id`
- `role`
- `content`
- `metadata_json`
- `created_at`
- `token_count`

### `episodes`

One episode is persisted per raw message for v2 recall.

- `id`
- `session_id`
- `message_id`
- `role`
- `text`
- `index_text`
- `benchmark_session_id`
- `benchmark_date`
- `position`
- `source_message_ids_json`
- `embedding`
- `created_at`

Indexes:

- `ix_episodes_message_id`
- `ix_episodes_session_position`
- `ix_episodes_session_message`

Store methods:

- `save_episode(episode)`
- `list_episodes(session_id)`
- `ensure_episodes_for_session(session_id)`
- `session_memory_watermark(session_id)`
- `set_episode_embedding(episode_id, embedding)`
- `get_episode_embeddings(episode_ids)`

### `trace_events`

- `id`
- `session_id`
- `event_type`
- `payload_json`
- `created_at`

### `archival_documents`, `archival_chunks`, `archival_passages`

These tables back the default v3 archival route. Documents are long-lived source
containers, chunks are document spans, and passages are retrieval units returned
to the v3 composer.

### `curated_memories`

One row per LLM-curated memory (fact/decision/rule/preference/lesson) with
`kind`, `topic_key`, `statement`, per-row `source_refs_json` (message ids and
verbatim quotes), `status` (`active`/`superseded`), the `supersedes_id` /
`superseded_by_id` link pair, and the producing `run_id`/`model`. Rows are only
written by the session curator that RoomMem runs in process.

### `curator_state`

Per-session curator watermark and counters: `last_message_seq` (count of
consumed messages in `(created_at, id)` order), `last_run_at`, `last_error_code`,
and total `runs`/`proposals`/`rejected_grounding`/`rejected_schema`/`llm_errors`.

## Initialization

`create_store()` creates any missing table from the current SQLAlchemy models
and alters nothing. There are no migrations: a data directory written by
0.2.x (with the v1, core-memory or curator columns of that release) is not
upgraded; start from an empty `DATA_DIR`. Hosts keep their durable facts
themselves, so MemoryOS data is rebuildable.

## Embeddings

Embeddings are stored as JSON text in SQLite via `EmbeddingType`; archival vectors are
kept in a process-local index rebuilt from SQLite.
