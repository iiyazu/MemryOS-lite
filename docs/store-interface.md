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
| Core memory | `core_memory_blocks`, `core_memory_history` | none | DB |
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

These tables store source-backed long-term facts/preferences/events and their
add/update/delete audit history.

## Initialization And Migrations

`create_store()` initializes tables with SQLAlchemy metadata and stamps
`alembic_version` to `0006_add_archival_memory` for fresh local databases.

Current migration head:

| Rev | Scope |
|---|---|
| `0001` | Baseline schema |
| `0002` | Add page supersession |
| `0003` | Add memory items |
| `0004` | Add episodes |
| `0005` | Add core memory |
| `0006` | Add archival memory |

Use Alembic for existing database upgrades:

```bash
uv run alembic upgrade head
```

## Embeddings

Embeddings are stored as JSON text in SQLite via `EmbeddingType`. Qdrant can be
enabled for ANN/vector experiments with `QDRANT_URL`, but SQLite remains the
relational source of truth.

## Derived Cache Watermarks

`session_memory_watermark(session_id)` returns a compact revision marker for
derived cache keys. It is not authoritative state. Cache users include it in
Redis keys so message, episode, page, item, core-memory, or archival mutations
select a new key and force recomputation from SQLite.

## Derived Cache Semantics

Derived cache is optional and never authoritative. SQLite remains the source of
truth for memory state and source references; cached values are accelerators for
recomputable retrieval products.

The current derived cache may store query analysis results, recall candidate
lists, and recall context packages. Query-analysis keys include the memory
architecture, recall pipeline, settings fingerprint, query hash, and scope
parameters. Recall-candidate and context-package keys additionally include a
watermark derived from SQLite state. When the watermark changes, callers select
a new key and recompute from SQLite. TTLs remain a fallback stale guard for
entries that are otherwise well-formed.

Redis read/write failures, corrupt entries, stale entries, and validation
failures fall back to SQLite recomputation. Cache diagnostics are surfaced in
`ContextPackage.metadata` and in v3 context layer metadata so callers can audit
hit, miss, stale, corrupt, invalid, disabled, and write-status behavior without
treating cache contents as state.

For the v3 composer path, the recall layer may reuse `RecallPipeline` internally
even when the top-level `MEMORYOS_RECALL_PIPELINE` route is `v1`. Derived cache
I/O is still gated by `MEMORYOS_RECALL_CACHE_ENABLED`; with that flag disabled,
the internal recall layer reports disabled cache diagnostics and performs no
cache reads or writes.
