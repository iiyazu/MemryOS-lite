# Store Interface Design (M2)

This document freezes the storage-layer contract for the enhancement roadmap. Written before M2 implementation so Alembic migrations, Postgres adoption, and the embedding column are executed against an explicit target rather than evolving SQLite hacks.

## Layout

Storage is **DB-authoritative** with a filesystem side-channel for human-debug purposes.

| Concern | DB column | FS path | Authority |
|---|---|---|---|
| Session | `sessions.*` | — | DB |
| Message | `messages.*` | — | DB |
| Page metadata | `memory_pages.*` | — | DB |
| Page content (facts/decisions/...) | `memory_pages.content_json` | `.memoryos/pages/{session}/{page_id}.json` | **DB**; FS is debug mirror |
| Patch | `memory_patches.*` | — | DB |
| Trace event | `trace_events.*` | `.memoryos/traces/{session_id}.jsonl` (append log) | **DB**; FS is append-only audit |
| **Embedding** | `memory_pages.embedding vector(1536)` (Postgres) / `embedding_json TEXT` (SQLite fallback) | — | DB |

**Migration from current code**: The existing `PageRecord.path` column stays for backward compatibility. Reads prefer `content_json` and fall back to `path` when `content_json IS NULL`. New writes populate both `content_json` and the file. After one stable release, `path` is deprecated and dropped.

## Table definitions (authoritative, Postgres-first)

### `sessions`
- `id TEXT PRIMARY KEY` (prefix `ses_*`)
- `title VARCHAR(255) NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

### `messages`
- `id TEXT PRIMARY KEY` (prefix `msg_*`)
- `session_id TEXT NOT NULL` → index `(session_id, created_at)` for hot recency scan
- `role VARCHAR(32) NOT NULL`
- `content TEXT NOT NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'` (SQLite: TEXT)
- `created_at TIMESTAMPTZ NOT NULL`
- `token_count INTEGER NOT NULL DEFAULT 0`

### `memory_pages`
- `id TEXT PRIMARY KEY` (prefix `page_*`)
- `session_id TEXT NOT NULL` → btree `(session_id, page_type)`
- `page_type VARCHAR(64) NOT NULL`
- `title VARCHAR(255) NOT NULL`
- `path TEXT NOT NULL` (legacy; may be empty string after deprecation)
- `content_json JSONB` (nullable during transition; SQLite: TEXT) — full `MemoryPage` serialized
- `source_message_ids_json JSONB NOT NULL DEFAULT '[]'` (SQLite: TEXT) — kept as JSON array, NOT a join table
- `confidence INTEGER NOT NULL DEFAULT 80` (0–100)
- `version INTEGER NOT NULL DEFAULT 1`
- `embedding vector(1536)` (Postgres, pgvector; nullable) / `embedding_json TEXT` (SQLite fallback)
- `created_at TIMESTAMPTZ NOT NULL` → btree
- `updated_at TIMESTAMPTZ NOT NULL`

### `memory_patches`
- `id TEXT PRIMARY KEY` (prefix `patch_*`)
- `target_page_id TEXT NULL`
- `payload_json JSONB NOT NULL` (SQLite: TEXT) — full `MemoryPatch` serialized
- `verified INTEGER NOT NULL DEFAULT 0` (0/1 boolean; SMALLINT in Postgres)
- `conflict_layer SMALLINT NULL` — added in M3 (1=rule, 2=embedding, 3=LLM)
- `created_at TIMESTAMPTZ NOT NULL`

### `trace_events`
- `id TEXT PRIMARY KEY` (prefix `trace_*`)
- `session_id TEXT NOT NULL` → btree `(session_id, event_type, created_at)`
- `event_type VARCHAR(64) NOT NULL`
- `payload_json JSONB NOT NULL` (SQLite: TEXT)
- `created_at TIMESTAMPTZ NOT NULL`

## JSONB vs TEXT

Postgres JSONB wins for:
- Future-proofing queries like `WHERE metadata_json->>'foo' = 'bar'` (M4+ may need this for eval filtering)
- Index-ability (`GIN`) when corpus grows

SQLite keeps TEXT; the ORM writes the same JSON string, reads `json.loads` it back.

## `source_message_ids`: array field, not a join table

Reasons to NOT normalize into a `memory_page_messages` join table:
1. Only read as a whole list (provenance display); no JOIN queries planned
2. Message IDs are informational, not FK-enforced (messages may be compacted)
3. Normalization adds 2× writes per page save and extra index without payoff
4. JSONB array supports containment queries if ever needed

## Indexing strategy

Created in the initial Alembic migration. Postgres-only indexes are guarded by `op.execute(...) if bind.dialect.name == "postgresql"`.

| Table | Index | Kind | Rationale |
|---|---|---|---|
| `messages` | `(session_id, created_at)` | btree | recent-message pagination |
| `memory_pages` | `(session_id, page_type)` | btree | `list_pages` per session filtered by type |
| `memory_pages` | `created_at` | btree | secondary sort on retrieval tie-breaker |
| `memory_pages` | `embedding` | ivfflat (vector_cosine_ops, lists=100) | **added later** — only when corpus ≥ 500 pages; initial migration leaves it unindexed so KNN is exact |
| `trace_events` | `(session_id, event_type, created_at)` | btree | trace replay |

## Connection & engine policy

- Default DSN resolution order in `get_settings().sqlite_url`:
  1. explicit `DATABASE_URL` env
  2. derived Postgres DSN if `POSTGRES_*` env vars set (used inside docker-compose)
  3. fallback `sqlite:///{data_dir}/memoryos.db`
- `MemoryStore` chooses `connect_args` per dialect:
  - SQLite: `{"check_same_thread": False}`
  - Postgres: empty, but `pool_pre_ping=True` on `create_engine`

## Transaction boundaries

Current code uses `with self.db() as db:` which auto-commits on block exit. M2 keeps this, but flags one caveat:

- `save_page` first writes the filesystem JSON, then writes the DB row. If DB write fails, the FS copy is orphaned. **Acceptable for M2** — orphans are harmless. After `path` column is deprecated, this asymmetry disappears.
- Patch verification (M3) must be atomic with the page update it rewrites: a single `db` block covering both.

## Alembic migration plan

| Rev | Scope | Touches |
|---|---|---|
| 0001 | Baseline full schema | sessions, messages, memory_pages (incl `content_json`, `embedding`), memory_patches, trace_events, pgvector extension |
| 0002 | M3: `memory_patches.conflict_layer`, `llm_judge_json`, `embedding_similarity`, new indexes on session_id+verified | memory_patches |
| 0003 | M4 (if any) | reserved |

Revision 0001 covers current schema **and** the embedding column in one shot. Reason: since the project has no migration history, there is nothing to preserve — we just need the target state on a fresh DB. Existing dev data in `.memoryos/memoryos.db` is treated as throwaway (developer re-runs `memoryos demo run` or `eval run`).

## Environment matrix

| Env | DSN | Embedding column |
|---|---|---|
| local dev (default) | `sqlite:///.memoryos/memoryos.db` | `embedding_json TEXT` |
| docker-compose | `postgresql+psycopg://memoryos:...@postgres:5432/memoryos` | `embedding vector(1536)` |
| CI | SQLite (fast, no infra) | `embedding_json TEXT` |
| production target | Postgres 16 + pgvector | `embedding vector(1536)` |

The application code does not branch on dialect beyond the embedding column — all JSON handling is symmetric.
