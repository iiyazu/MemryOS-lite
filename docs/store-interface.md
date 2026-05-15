# Store Interface (SQLite-only)

Storage is **DB-authoritative** with a filesystem side-channel for human-debug purposes.

| Concern | DB column | FS path | Authority |
|---|---|---|---|
| Session | `sessions.*` | — | DB |
| Message | `messages.*` | — | DB |
| Page metadata | `memory_pages.*` | — | DB |
| Page content | `memory_pages.content_json` | `.memoryos/pages/{session}/{page_id}.json` | **DB**; FS is debug mirror |
| Patch | `memory_patches.*` | — | DB |
| Trace event | `trace_events.*` | `.memoryos/traces/{session_id}.jsonl` | **DB**; FS is append-only audit |
| **Embedding** | `memory_pages.embedding TEXT` (JSON-encoded `list[float]`) | — | DB |

## Table definitions

### `sessions`
- `id TEXT PRIMARY KEY`
- `title VARCHAR(255) NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

### `messages`
- `id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL` → index `(session_id, created_at)`
- `role VARCHAR(32) NOT NULL`
- `content TEXT NOT NULL`
- `metadata_json TEXT NOT NULL DEFAULT '{}'`
- `created_at TIMESTAMPTZ NOT NULL`
- `token_count INTEGER NOT NULL DEFAULT 0`

### `memory_pages`
- `id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL` → btree `(session_id, page_type)`
- `page_type VARCHAR(64) NOT NULL`
- `title VARCHAR(255) NOT NULL`
- `path TEXT NOT NULL` (legacy debug path)
- `content_json TEXT` (nullable; full `MemoryPage` JSON)
- `source_message_ids_json TEXT NOT NULL DEFAULT '[]'`
- `confidence INTEGER NOT NULL DEFAULT 80`
- `version INTEGER NOT NULL DEFAULT 1`
- `embedding TEXT` (nullable; JSON-encoded `list[float]`, 1536-dim)
- `superseded_by TEXT` (nullable; ID of the page that replaced this one)
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

### `memory_patches`
- `id TEXT PRIMARY KEY`
- `target_page_id TEXT NULL`
- `payload_json TEXT NOT NULL`
- `verified INTEGER NOT NULL DEFAULT 0`
- `created_at TIMESTAMPTZ NOT NULL`

### `trace_events`
- `id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL` → btree `(session_id, event_type, created_at)`
- `event_type VARCHAR(64) NOT NULL`
- `payload_json TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

## Initialization

`create_store()` calls `init_db()` which runs `Base.metadata.create_all()` and stamps
`alembic_version` to `0002_add_superseded_by`. This means:

- Fresh DB: tables created, alembic stamped — `alembic upgrade head` is a no-op.
- Existing DB (no alembic_version): tables already exist, alembic stamped — `alembic upgrade head` is a no-op.
- Existing DB (already stamped): no-op.

**Stale DB without `superseded_by` column**: delete `.memoryos/memoryos.db` and re-run.
The DB is a local cache; all durable state is in the page JSON files.

## Alembic migrations

Alembic is retained for historical reference and manual schema evolution.
The app does **not** call `alembic upgrade` at runtime — `create_all()` is the
authoritative initialization path.

| Rev | Scope |
|---|---|
| 0001 | Baseline schema (sessions, messages, memory_pages, memory_patches, trace_events) |
| 0002 | Add `superseded_by` column to `memory_pages` |

## Vector search

- **SQLite fallback**: Python-side cosine scoring over `embedding TEXT` column.
- **Qdrant (optional)**: set `QDRANT_URL` to enable ANN search. Qdrant stores only
  the embedding vectors; all relational data stays in SQLite.
