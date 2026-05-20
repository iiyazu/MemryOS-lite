# Store Interface

Storage is SQLite-first and DB-authoritative. Filesystem page and trace files
are debug mirrors, not the primary state.

## Authority

| Concern | DB | Filesystem | Authority |
|---|---|---|---|
| Sessions | `sessions` | none | DB |
| Messages | `messages` | none | DB |
| Episodes | `episodes` | none | DB |
| Pages | `memory_pages.content_json` | `.memoryos/pages/.../*.json` | DB |
| Items | `memory_items` | none | DB |
| Patches | `memory_patches` | none | DB |
| Traces | `trace_events` | `.memoryos/traces/*.jsonl` | DB |

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

## Initialization And Migrations

`create_store()` initializes tables with SQLAlchemy metadata and stamps
`alembic_version` to `0004_add_episodes` for fresh local databases.

Current migration head:

| Rev | Scope |
|---|---|
| `0001` | Baseline schema |
| `0002` | Add page supersession |
| `0003` | Add memory items |
| `0004` | Add episodes |

Use Alembic for existing database upgrades:

```bash
uv run alembic upgrade head
```

## Embeddings

Embeddings are stored as JSON text in SQLite via `EmbeddingType`. Qdrant can be
enabled for ANN/vector experiments with `QDRANT_URL`, but SQLite remains the
relational source of truth.
