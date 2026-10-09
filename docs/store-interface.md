# Store Interface

Storage is SQLite-first and DB-authoritative. Filesystem trace files are debug
mirrors, not the primary state.

## Authority

| Concern | DB | Filesystem | Authority |
|---|---|---|---|
| Sessions | `sessions` | none | DB |
| Messages | `messages` | none | DB |
| Episodes | `episodes` | none | DB |
| Pages, items, patches (v1, no longer written) | `memory_pages`, `memory_items`, `memory_patches` | none | DB |
| Traces | `trace_events` | `.memoryos/traces/*.jsonl` | DB |
| Core memory (unused) | `core_memory_blocks`, `core_memory_history` | none | DB |
| Archival memory | `archival_documents`, `archival_chunks`, `archival_passages`, `archival_memories`, `archival_memory_history` | none | DB |

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

### `memory_pages`

- `id`
- `session_id`
- `page_type`
- `title`
- `path`
- `content_json`
- `source_message_ids_json`
- `confidence`
- `version`
- `embedding`
- `superseded_by`
- `created_at`
- `updated_at`

### `memory_items`

- `id`
- `page_id`
- `session_id`
- `item_type`
- `content`
- `source_message_ids_json`
- `embedding`
- `created_at`

### `memory_patches`

- `id`
- `target_page_id`
- `payload_json`
- `verified`
- `created_at`

### `trace_events`

- `id`
- `session_id`
- `event_type`
- `payload_json`
- `created_at`

### `core_memory_blocks`

Kept in the schema for existing databases; no code reads or writes it.

- `id`
- `label`
- `description`
- `value`
- `limit_tokens`
- `source_refs_json`
- `metadata_json`
- `deleted`
- `created_at`
- `updated_at`

### `core_memory_history`

- `id`
- `memory_id`
- `memory_type`
- `operation`
- `before_json`
- `after_json`
- `source_refs_json`
- `actor`
- `reason`
- `created_at`

### `archival_documents`, `archival_chunks`, `archival_passages`

These tables back the default v3 archival route. Documents are long-lived source
containers, chunks are document spans, and passages are retrieval units returned
to the v3 composer.

### `archival_memories`, `archival_memory_history`

Kept in the schema for existing databases; no code reads or writes them. The
same holds for `promotion_candidates` and `context_policy_candidates`.

### `curated_memories`

One row per LLM-curated memory (fact/decision/rule/preference/lesson) with
`kind`, `topic_key`, `statement`, per-row `source_refs_json` (message ids and
verbatim quotes), `status` (`active`/`superseded`), the `supersedes_id` /
`superseded_by_id` link pair, and the producing `run_id`/`model`. Rows are only
written by the opt-in memory curator.

### `curator_state`

Per-session curator watermark and counters: `last_message_seq` (count of
consumed messages in `(created_at, id)` order), `last_run_at`, `last_error_code`,
and total `runs`/`proposals`/`rejected_grounding`/`rejected_schema`/`llm_errors`.

## Initialization And Migrations

`create_store()` initializes tables with SQLAlchemy metadata and stamps
`alembic_version` to `0010_add_curator_tables` for fresh local databases.

Current migration head:

| Rev | Scope |
|---|---|
| `0001` | Baseline schema |
| `0002` | Add page supersession |
| `0003` | Add memory items |
| `0004` | Add episodes |
| `0005` | Add core memory |
| `0006` | Add archival memory |
| `0007` | Add `read_only` and `tags_json` to core memory blocks |
| `0008` | Add promotion candidates |
| `0009` | Add context policy candidates |
| `0010` | Add curator tables (`curated_memories`, `curator_state`) |

Use Alembic for existing database upgrades:

```bash
uv run alembic upgrade head
```

## Embeddings

Embeddings are stored as JSON text in SQLite via `EmbeddingType`; archival vectors are
kept in a process-local index rebuilt from SQLite.
