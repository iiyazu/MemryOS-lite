# MemoryOS v2 Phase 1 Recall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an opt-in v2 recall pipeline that retrieves source-grounded evidence from episode/raw-message indices while preserving default v1 behavior.

**Architecture:** Add a new `Episode` data model and store layer, then add focused retrieval/planning modules under `src/memoryos_lite/retrieval/`. `MemoryOSService.build_context()` remains v1 by default and delegates to v2 only when `MEMORYOS_RECALL_PIPELINE=v2`.

**Tech Stack:** Python 3.11, Pydantic, SQLAlchemy/Alembic, rank-bm25, existing `TokenEstimator`, existing eval/public benchmark harness.

---

## File Structure

- Modify `src/memoryos_lite/config.py`: add `memoryos_recall_pipeline` defaulting to `"v1"`.
- Modify `src/memoryos_lite/schemas.py`: add `Episode`, extend `MemoryItem`, add optional evidence diagnostics fields to `ContextPackage`.
- Modify `src/memoryos_lite/store.py`: add `EpisodeRecord`, episode CRUD/backfill/embedding methods, and update fresh-DB Alembic stamping.
- Create `alembic/versions/0004_add_episodes.py`: migrate `episodes`.
- Create `src/memoryos_lite/retrieval/query_analyzer.py`: minimal deterministic query tagging.
- Create `src/memoryos_lite/retrieval/episode_searcher.py`: BM25 retrieval over `Episode.index_text`.
- Create `src/memoryos_lite/retrieval/recall_pipeline.py`: v2 planner/budgeter that returns `ContextPackage`.
- Modify `src/memoryos_lite/engine.py`: index episodes on ingest, ensure backfill before v2 recall, route build_context by config.
- Modify `src/memoryos_lite/evals.py`: carry v2 diagnostics through `BaselineOutput`.
- Modify `src/memoryos_lite/public_benchmarks.py`: expose v2 diagnostics in public reports.
- Add tests in `tests/test_episode_store.py`, `tests/test_episode_retrieval.py`, `tests/test_recall_pipeline.py`, and extend existing eval/API tests where needed.

---

### Task 1: Config Flag and Default v1 Safety

**Files:**
- Modify: `src/memoryos_lite/config.py`
- Test: `tests/test_engine.py`

- [ ] **Step 1: Write failing config/default behavior test**

Add this test near existing engine/config behavior tests in `tests/test_engine.py`:

```python
def test_recall_pipeline_defaults_to_v1(tmp_path):
    from memoryos_lite.config import Settings
    from memoryos_lite.engine import MemoryOSService

    settings = Settings(data_dir=tmp_path / ".memoryos")
    service = MemoryOSService(settings=settings)

    assert service.settings.memoryos_recall_pipeline == "v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_engine.py::test_recall_pipeline_defaults_to_v1 -q
```

Expected: FAIL with `AttributeError` or Pydantic validation missing field.

- [ ] **Step 3: Add settings field**

In `src/memoryos_lite/config.py`, add this field to `Settings` near other `memoryos_*` flags:

```python
memoryos_recall_pipeline: str = "v1"
```

Add a property to normalize and validate:

```python
@property
def resolved_recall_pipeline(self) -> str:
    val = self.memoryos_recall_pipeline.strip().lower()
    if val not in {"v1", "v2"}:
        raise ValueError("MEMORYOS_RECALL_PIPELINE must be 'v1' or 'v2'")
    return val
```

- [ ] **Step 4: Run targeted test**

Run:

```bash
uv run pytest tests/test_engine.py::test_recall_pipeline_defaults_to_v1 -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/config.py tests/test_engine.py
git commit -m "feat: add recall pipeline config flag"
```

---

### Task 2: Episode Schema and Store Round Trip

**Files:**
- Modify: `src/memoryos_lite/schemas.py`
- Modify: `src/memoryos_lite/store.py`
- Test: `tests/test_episode_store.py`

- [ ] **Step 1: Write failing episode store tests**

Create `tests/test_episode_store.py`:

```python
from memoryos_lite.config import Settings
from memoryos_lite.schemas import Episode, Message, Role
from memoryos_lite.store import create_store


def test_episode_round_trip(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    episode = Episode(
        session_id="ses_test",
        message_id="msg_1",
        role=Role.USER,
        text="Alice moved to Shanghai.",
        index_text="[session=s1 date=2026-05-01 speaker=user] Alice moved to Shanghai.",
        benchmark_session_id="s1",
        benchmark_date="2026-05-01",
        position=3,
        source_message_ids=["msg_1"],
    )

    store.save_episode(episode)
    loaded = store.list_episodes("ses_test")

    assert len(loaded) == 1
    assert loaded[0].message_id == "msg_1"
    assert loaded[0].index_text.startswith("[session=s1")


def test_ensure_episodes_for_session_backfills_store_inserted_messages(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    msg = Message(
        id="msg_direct",
        session_id="ses_direct",
        role=Role.USER,
        content="[D1] Bob prefers tea.",
        metadata={"benchmark_session_id": "D1", "benchmark_date": "2026-05-01"},
        token_count=5,
    )
    store.add_message(msg)

    created = store.ensure_episodes_for_session("ses_direct")
    episodes = store.list_episodes("ses_direct")

    assert created == 1
    assert [episode.message_id for episode in episodes] == ["msg_direct"]
    assert episodes[0].position == 1
    assert "Bob prefers tea" in episodes[0].index_text


def test_episode_embedding_round_trip(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    episode = Episode(
        session_id="ses_embed",
        message_id="msg_embed",
        role=Role.USER,
        text="Vector source.",
        index_text="Vector source.",
        position=1,
        source_message_ids=["msg_embed"],
    )
    store.save_episode(episode)

    store.set_episode_embedding(episode.id, [0.1, 0.2, 0.3])

    assert store.get_episode_embeddings([episode.id]) == {episode.id: [0.1, 0.2, 0.3]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_episode_store.py -q
```

Expected: FAIL because `Episode` and store methods are undefined.

- [ ] **Step 3: Add `Episode` schema**

In `src/memoryos_lite/schemas.py`, add after `Message`:

```python
class Episode(BaseModel):
    id: str = Field(default_factory=lambda: new_id("epi"))
    session_id: str
    message_id: str
    role: Role
    text: str
    index_text: str
    benchmark_session_id: str | None = None
    benchmark_date: str | None = None
    position: int
    source_message_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: Add store model and methods**

In `src/memoryos_lite/store.py`, import `Episode` from schemas, then add:

```python
class EpisodeRecord(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    index_text: Mapped[str] = mapped_column(Text, nullable=False)
    benchmark_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    benchmark_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_message_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_episodes_session_position", "session_id", "position"),
        Index("ix_episodes_session_message", "session_id", "message_id"),
    )
```

Add methods to `MemoryStore`:

```python
def save_episode(self, episode: Episode) -> Episode:
    with self.db() as db:
        existing = db.scalar(
            select(EpisodeRecord).where(
                EpisodeRecord.session_id == episode.session_id,
                EpisodeRecord.message_id == episode.message_id,
            )
        )
        if existing is not None:
            return episode
        db.add(
            EpisodeRecord(
                id=episode.id,
                session_id=episode.session_id,
                message_id=episode.message_id,
                role=episode.role.value,
                text=episode.text,
                index_text=episode.index_text,
                benchmark_session_id=episode.benchmark_session_id,
                benchmark_date=episode.benchmark_date,
                position=episode.position,
                source_message_ids_json=json.dumps(episode.source_message_ids),
                created_at=episode.created_at,
            )
        )
    return episode

def list_episodes(self, session_id: str) -> list[Episode]:
    with self.db() as db:
        records = list(
            db.scalars(
                select(EpisodeRecord)
                .where(EpisodeRecord.session_id == session_id)
                .order_by(EpisodeRecord.position.asc())
            )
        )
    return [
        Episode(
            id=row.id,
            session_id=row.session_id,
            message_id=row.message_id,
            role=Role(row.role),
            text=row.text,
            index_text=row.index_text,
            benchmark_session_id=row.benchmark_session_id,
            benchmark_date=row.benchmark_date,
            position=row.position,
            source_message_ids=json.loads(row.source_message_ids_json),
            created_at=row.created_at,
        )
        for row in records
    ]

def ensure_episodes_for_session(self, session_id: str) -> int:
    existing_ids = {episode.message_id for episode in self.list_episodes(session_id)}
    messages = self.list_messages(session_id)
    created = 0
    for position, message in enumerate(messages, start=1):
        if message.id in existing_ids:
            continue
        metadata = message.metadata or {}
        header = (
            f"[session={metadata.get('benchmark_session_id', '')} "
            f"date={metadata.get('benchmark_date', '')} "
            f"speaker={message.role.value} position={position}]"
        )
        episode = Episode(
            session_id=session_id,
            message_id=message.id,
            role=message.role,
            text=message.content,
            index_text=f"{header} {message.content}",
            benchmark_session_id=metadata.get("benchmark_session_id"),
            benchmark_date=metadata.get("benchmark_date"),
            position=position,
            source_message_ids=[message.id],
        )
        self.save_episode(episode)
        created += 1
    return created

def set_episode_embedding(self, episode_id: str, embedding: list[float]) -> None:
    with self.db() as db:
        record = db.get(EpisodeRecord, episode_id)
        if record is not None:
            record.embedding = embedding

def get_episode_embeddings(self, episode_ids: list[str]) -> dict[str, list[float]]:
    if not episode_ids:
        return {}
    with self.db() as db:
        stmt = select(EpisodeRecord.id, EpisodeRecord.embedding).where(
            EpisodeRecord.id.in_(episode_ids)
        )
        rows = list(db.execute(stmt))
    return {episode_id: emb for episode_id, emb in rows if emb is not None}
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
uv run pytest tests/test_episode_store.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/schemas.py src/memoryos_lite/store.py tests/test_episode_store.py
git commit -m "feat: add episode store"
```

---

### Task 3: Alembic Migration for Episodes

**Files:**
- Create: `alembic/versions/0004_add_episodes.py`

- [ ] **Step 1: Add migration file**

Create `alembic/versions/0004_add_episodes.py`:

```python
"""Add episodes table

Revision ID: 0004_add_episodes
Revises: 0003_add_memory_items
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_episodes"
down_revision: str = "0003_add_memory_items"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "episodes" in inspector.get_table_names():
        return
    op.create_table(
        "episodes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("index_text", sa.Text(), nullable=False),
        sa.Column("benchmark_session_id", sa.String(length=128), nullable=True),
        sa.Column("benchmark_date", sa.String(length=64), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_message_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_episodes_session_id", "episodes", ["session_id"])
    op.create_index("ix_episodes_message_id", "episodes", ["message_id"])
    op.create_index("ix_episodes_session_position", "episodes", ["session_id", "position"])
    op.create_index("ix_episodes_session_message", "episodes", ["session_id", "message_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "episodes" not in inspector.get_table_names():
        return
    op.drop_index("ix_episodes_session_message", table_name="episodes")
    op.drop_index("ix_episodes_session_position", table_name="episodes")
    op.drop_index("ix_episodes_message_id", table_name="episodes")
    op.drop_index("ix_episodes_session_id", table_name="episodes")
    op.drop_table("episodes")
```

- [ ] **Step 2: Update fresh DB stamp**

In `src/memoryos_lite/store.py`, update the `init_db()` insert so a brand-new
database created through `create_all()` is stamped to the current head:

```python
conn.execute(
    text(
        "INSERT INTO alembic_version (version_num)"
        " VALUES ('0004_add_episodes')"
    )
)
```

This only applies when `alembic_version` is empty. Do not overwrite an existing
version row.

- [ ] **Step 3: Run migration smoke command**

Run:

```bash
uv run alembic upgrade head
```

Expected: exits successfully.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/0004_add_episodes.py src/memoryos_lite/store.py
git commit -m "feat: add episodes migration"
```

---

### Task 4: Query Analyzer and Episode Searcher

**Files:**
- Create: `src/memoryos_lite/retrieval/query_analyzer.py`
- Create: `src/memoryos_lite/retrieval/episode_searcher.py`
- Modify: `src/memoryos_lite/retrieval/__init__.py`
- Test: `tests/test_episode_retrieval.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_episode_retrieval.py`:

```python
from memoryos_lite.retrieval.episode_searcher import EpisodeSearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalyzer, QueryKind
from memoryos_lite.schemas import Episode, Role


def test_query_analyzer_detects_assistant_source():
    result = QueryAnalyzer().analyze("What did you recommend last time?")
    assert result.kind == QueryKind.ASSISTANT_SOURCE


def test_episode_searcher_finds_exact_episode():
    episodes = [
        Episode(
            session_id="s",
            message_id="m1",
            role=Role.USER,
            text="Alice likes coffee.",
            index_text="[speaker=user] Alice likes coffee.",
            position=1,
            source_message_ids=["m1"],
        ),
        Episode(
            session_id="s",
            message_id="m2",
            role=Role.USER,
            text="Bob moved to Shanghai.",
            index_text="[speaker=user] Bob moved to Shanghai.",
            position=2,
            source_message_ids=["m2"],
        ),
    ]

    hits = EpisodeSearcher().search(episodes, "Where did Bob move?", top_k=1)

    assert hits[0].episode.message_id == "m2"
    assert hits[0].source == "episode_bm25"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_episode_retrieval.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement query analyzer**

Create `src/memoryos_lite/retrieval/query_analyzer.py`:

```python
from dataclasses import dataclass
from enum import StrEnum


class QueryKind(StrEnum):
    TEMPORAL = "temporal"
    ASSISTANT_SOURCE = "assistant_source"
    MULTI_SESSION = "multi_session"
    GENERAL = "general"


@dataclass(frozen=True)
class QueryAnalysis:
    kind: QueryKind


class QueryAnalyzer:
    def analyze(self, query: str) -> QueryAnalysis:
        normalized = query.lower()
        if any(marker in normalized for marker in ("last time", "you recommend", "you suggested", "you said")):
            return QueryAnalysis(QueryKind.ASSISTANT_SOURCE)
        if any(marker in normalized for marker in ("before", "after", "first", "how many days", "when")):
            return QueryAnalysis(QueryKind.TEMPORAL)
        if any(marker in normalized for marker in ("session", "conversation", "chat")):
            return QueryAnalysis(QueryKind.MULTI_SESSION)
        return QueryAnalysis(QueryKind.GENERAL)
```

- [ ] **Step 4: Implement episode searcher**

Create `src/memoryos_lite/retrieval/episode_searcher.py`:

```python
from dataclasses import dataclass

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.retrieval.query_analyzer import QueryAnalysis, QueryKind
from memoryos_lite.schemas import Episode, Role


@dataclass(frozen=True)
class EpisodeHit:
    episode: Episode
    score: float
    reason: str
    source: str = "episode_bm25"


class EpisodeSearcher:
    def search(
        self,
        episodes: list[Episode],
        query: str,
        top_k: int = 5,
        analysis: QueryAnalysis | None = None,
    ) -> list[EpisodeHit]:
        query_tokens = tokenize(query)
        if not episodes or not query_tokens:
            return []
        corpus = [tokenize(episode.index_text) for episode in episodes]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)
        hits: list[EpisodeHit] = []
        for episode, score in zip(episodes, scores, strict=False):
            token_overlap = len(set(query_tokens) & set(tokenize(episode.index_text)))
            if token_overlap <= 0:
                continue
            adjusted = float(score)
            if analysis is not None and analysis.kind == QueryKind.ASSISTANT_SOURCE and episode.role == Role.ASSISTANT:
                adjusted += 6.0
            if adjusted <= 0:
                continue
            hits.append(
                EpisodeHit(
                    episode=episode,
                    score=adjusted,
                    reason=f"episode_bm25={adjusted:.4f} overlap={token_overlap}",
                )
            )
        return sorted(hits, key=lambda hit: (hit.score, -hit.episode.position), reverse=True)[:top_k]
```

Update `src/memoryos_lite/retrieval/__init__.py`:

```python
from memoryos_lite.retrieval.episode_searcher import EpisodeHit, EpisodeSearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalysis, QueryAnalyzer, QueryKind
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
uv run pytest tests/test_episode_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/retrieval/query_analyzer.py src/memoryos_lite/retrieval/episode_searcher.py src/memoryos_lite/retrieval/__init__.py tests/test_episode_retrieval.py
git commit -m "feat: add episode retrieval"
```

---

### Task 5: Recall Pipeline Planner and Budgeter

**Files:**
- Create: `src/memoryos_lite/retrieval/recall_pipeline.py`
- Test: `tests/test_recall_pipeline.py`

- [ ] **Step 1: Write failing pipeline tests**

Create `tests/test_recall_pipeline.py`:

```python
from memoryos_lite.config import Settings
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import Message, Role
from memoryos_lite.store import create_store


def test_recall_pipeline_returns_episode_evidence(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    msg = Message(
        id="msg_bob",
        session_id="ses",
        role=Role.USER,
        content="Bob moved to Shanghai.",
        metadata={},
        token_count=5,
    )
    store.add_message(msg)
    store.ensure_episodes_for_session("ses")

    pipeline = RecallPipeline(store=store, settings=settings)
    package = pipeline.build_context(
        session_id="ses",
        task="Where did Bob move?",
        budget=200,
    )

    assert package.retrieved_evidence
    assert package.retrieved_evidence[0].message_id == "msg_bob"
    assert package.retrieved_evidence[0].metadata["origin"] == "episode"
    assert package.metadata["episode_candidate_message_ids"] == ["msg_bob"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_recall_pipeline.py -q
```

Expected: FAIL because `RecallPipeline` and `ContextPackage.metadata` are missing.

- [ ] **Step 3: Add diagnostics field to `ContextPackage`**

In `src/memoryos_lite/schemas.py`, add to `ContextPackage`:

```python
metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement recall pipeline**

Create `src/memoryos_lite/retrieval/recall_pipeline.py`:

```python
from memoryos_lite.config import Settings
from memoryos_lite.retrieval.episode_searcher import EpisodeSearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalyzer
from memoryos_lite.schemas import ContextEvidence, ContextPackage
from memoryos_lite.store import MemoryStore
from memoryos_lite.tokenizer import TokenEstimator


class RecallPipeline:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings,
        tokenizer: TokenEstimator | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.tokenizer = tokenizer or TokenEstimator()
        self.query_analyzer = QueryAnalyzer()
        self.episode_searcher = EpisodeSearcher()

    def build_context(
        self,
        session_id: str,
        task: str,
        budget: int,
        retrieval_query: str | None = None,
    ) -> ContextPackage:
        query = retrieval_query or task
        created = self.store.ensure_episodes_for_session(session_id)
        episodes = self.store.list_episodes(session_id)
        analysis = self.query_analyzer.analyze(query)
        hits = self.episode_searcher.search(episodes, query, top_k=10, analysis=analysis)
        package = ContextPackage(session_id=session_id, task=task, task_tokens=self.tokenizer.count(task))
        used = package.task_tokens
        candidate_ids = [hit.episode.message_id for hit in hits]
        indexed_source_ids = sorted(
            {
                source_id
                for episode in episodes
                for source_id in episode.source_message_ids
            }
        )
        planned_ids: list[str] = []
        dropped = 0
        for hit in hits:
            text = " ".join(hit.episode.text.split())
            tokens = self.tokenizer.count(text)
            if used + tokens > budget:
                dropped += 1
                continue
            package.retrieved_evidence.append(
                ContextEvidence(
                    message_id=hit.episode.message_id,
                    text=text,
                    role=hit.episode.role,
                    reason=hit.reason,
                    estimated_tokens=tokens,
                    metadata={
                        "origin": "episode",
                        "score": hit.score,
                        "benchmark_session_id": hit.episode.benchmark_session_id,
                        "benchmark_date": hit.episode.benchmark_date,
                    },
                )
            )
            planned_ids.append(hit.episode.message_id)
            used += tokens
        package.estimated_tokens = used
        package.candidate_budget_dropped = dropped
        package.metadata.update(
            {
                "episode_backfilled": created,
                "item_candidate_source_ids": [],
                "indexed_source_ids": indexed_source_ids,
                "episode_candidate_message_ids": candidate_ids,
                "planned_evidence_message_ids": planned_ids,
                "planned_evidence_origins": ["episode" for _ in planned_ids],
                "budget_dropped_relevant": dropped,
            }
        )
        return package
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
uv run pytest tests/test_recall_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/schemas.py src/memoryos_lite/retrieval/recall_pipeline.py tests/test_recall_pipeline.py
git commit -m "feat: add v2 recall pipeline"
```

---

### Task 6: Engine Integration Behind v2 Flag

**Files:**
- Modify: `src/memoryos_lite/engine.py`
- Test: `tests/test_recall_pipeline.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Add failing service integration test**

Append to `tests/test_recall_pipeline.py`:

```python
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MessageCreate, Role


def test_service_build_context_uses_v2_when_opted_in(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_recall_pipeline="v2",
    )
    service = MemoryOSService(settings=settings)
    session = service.create_session("v2")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Carol moved to Berlin."))

    package = service.build_context(session.id, "Where did Carol move?", budget=200)

    assert package.retrieved_evidence
    assert package.retrieved_evidence[0].metadata["origin"] == "episode"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_recall_pipeline.py::test_service_build_context_uses_v2_when_opted_in -q
```

Expected: FAIL because `MemoryOSService` does not route to v2.

- [ ] **Step 3: Wire pipeline in engine**

In `src/memoryos_lite/engine.py`, import:

```python
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
```

In `MemoryOSService.__init__`, after `self.dynamic_budget = ...`, add:

```python
self.recall_pipeline = RecallPipeline(
    store=self.store,
    settings=self.settings,
    tokenizer=self.tokenizer,
)
```

In `MemoryOSService.ingest()`, after `self.store.add_message(message)`, add:

```python
created = self.store.ensure_episodes_for_session(session_id)
if created:
    self.trace(session_id, "episode_indexed", {"created": created})
```

At the top of `MemoryOSService.build_context()` after `effective_budget` is computed and before item evidence is prepared, add:

```python
if self.settings.resolved_recall_pipeline == "v2":
    package = self.recall_pipeline.build_context(
        session_id=session_id,
        task=task,
        budget=effective_budget,
        retrieval_query=retrieval_query,
    )
    self.trace(
        session_id,
        "context_built",
        {
            "task": task,
            "budget": effective_budget,
            "budget_source": "explicit" if budget is not None else "dynamic",
            "estimated_tokens": package.estimated_tokens,
            "retrieved_evidence": [
                evidence.model_dump() for evidence in package.retrieved_evidence
            ],
            "recall_pipeline": "v2",
            **package.metadata,
        },
    )
    return package
```

- [ ] **Step 4: Run targeted tests**

Run:

```bash
uv run pytest tests/test_recall_pipeline.py tests/test_api.py -q
```

Expected: PASS. Existing API tests should continue using default v1.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/engine.py tests/test_recall_pipeline.py
git commit -m "feat: route build context through v2 recall pipeline"
```

---

### Task 7: Eval/Public Benchmark Diagnostics

**Files:**
- Modify: `src/memoryos_lite/evals.py`
- Modify: `src/memoryos_lite/public_benchmarks.py`
- Test: `tests/test_public_benchmarks.py`

- [ ] **Step 1: Extend `BaselineOutput`**

In `src/memoryos_lite/evals.py`, add fields to `BaselineOutput`:

```python
item_source_hit_at_10: bool | None = None
episode_source_hit_at_10: bool | None = None
planned_evidence_source_hit_at_5: bool | None = None
budget_dropped_relevant: int = 0
source_not_indexed: bool = False
indexed_source_ids: list[str] = field(default_factory=list)
item_candidate_source_ids: list[str] = field(default_factory=list)
episode_candidate_message_ids: list[str] = field(default_factory=list)
planned_evidence_message_ids: list[str] = field(default_factory=list)
```

- [ ] **Step 2: Populate v2 fields in memoryos baseline**

In `_run_baseline()` inside the `memoryos_lite` branch, after `context = service.build_context(...)`, compute:

```python
planned_evidence_message_ids = list(context.metadata.get("planned_evidence_message_ids", []))
episode_candidate_message_ids = list(context.metadata.get("episode_candidate_message_ids", []))
item_candidate_source_ids = list(context.metadata.get("item_candidate_source_ids", []))
indexed_source_ids = list(context.metadata.get("indexed_source_ids", []))
budget_dropped_relevant = int(context.metadata.get("budget_dropped_relevant", 0))
expected_sources = set(case.required_sources)
item_source_hit_at_10 = (
    bool(expected_sources & set(item_candidate_source_ids[:10]))
    if item_candidate_source_ids
    else None
)
episode_source_hit_at_10 = (
    bool(expected_sources & set(episode_candidate_message_ids[:10]))
    if episode_candidate_message_ids
    else None
)
planned_evidence_source_hit_at_5 = (
    bool(expected_sources & set(planned_evidence_message_ids[:5]))
    if planned_evidence_message_ids
    else None
)
all_indexed_source_ids = set(indexed_source_ids) | set(item_candidate_source_ids)
source_not_indexed = bool(expected_sources) and not bool(expected_sources & all_indexed_source_ids)
```

Pass these values into `_baseline_from_evidence(...)` and update `_baseline_from_evidence` to accept/forward the new keyword arguments into `BaselineOutput`.

- [ ] **Step 3: Extend public result model**

In `src/memoryos_lite/public_benchmarks.py`, add fields to `PublicBenchmarkResult`:

```python
episode_source_hit_at_10: bool | None = None
item_source_hit_at_10: bool | None = None
planned_evidence_source_hit_at_5: bool | None = None
budget_dropped_relevant: int = 0
source_not_indexed: bool = False
indexed_source_ids: list[str] = field(default_factory=list)
item_candidate_source_ids: list[str] = field(default_factory=list)
episode_candidate_message_ids: list[str] = field(default_factory=list)
planned_evidence_message_ids: list[str] = field(default_factory=list)
```

In `_to_public_result(...)`, pass through:

```python
item_source_hit_at_10=output.item_source_hit_at_10,
episode_source_hit_at_10=output.episode_source_hit_at_10,
planned_evidence_source_hit_at_5=output.planned_evidence_source_hit_at_5,
budget_dropped_relevant=output.budget_dropped_relevant,
source_not_indexed=output.source_not_indexed,
indexed_source_ids=output.indexed_source_ids,
item_candidate_source_ids=output.item_candidate_source_ids,
episode_candidate_message_ids=output.episode_candidate_message_ids,
planned_evidence_message_ids=output.planned_evidence_message_ids,
```

- [ ] **Step 4: Add small public benchmark assertion**

In `tests/test_public_benchmarks.py`, add or extend a smoke test that runs `memoryos_lite` with `memoryos_recall_pipeline="v2"` and asserts:

```python
assert "episode_candidate_message_ids" in report
assert report["episode_candidate_message_ids"]
assert "planned_evidence_message_ids" in report
assert "item_source_hit_at_10" in report
assert "source_not_indexed" in report
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
uv run pytest tests/test_public_benchmarks.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/evals.py src/memoryos_lite/public_benchmarks.py tests/test_public_benchmarks.py
git commit -m "feat: report v2 recall diagnostics"
```

---

### Task 8: Verification and Benchmark Smoke

**Files:**
- Modify: `docs/architecture-and-results-zh.md` only if numbers are intentionally refreshed after benchmark results.

- [ ] **Step 1: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run hard eval**

Run:

```bash
uv run memoryos eval run --case-set hard --baseline memoryos_lite
```

Expected: hard eval remains `1.00/1.00`.

- [ ] **Step 3: Run v2 public smoke on small slices**

Run:

```bash
MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge \
  --run-id v2_lme_smoke

MEMORYOS_RECALL_PIPELINE=v2 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite --limit 10 --no-llm-answer --no-llm-judge \
  --run-id v2_locomo_smoke
```

Expected: commands complete and reports include non-empty `episode_candidate_message_ids`.

- [ ] **Step 4: Summarize results**

Add a short local note in the final response with:

```text
pytest result
hard eval result
LME smoke source/episode/planned metrics
LoCoMo smoke source/episode/planned metrics
```

- [ ] **Step 5: Commit verification-only doc update if needed**

If benchmark summary docs are updated:

```bash
git add docs/architecture-and-results-zh.md
git commit -m "docs: summarize v2 recall smoke results"
```

If no docs are updated, do not create an empty commit.

---

## Self-Review

- Spec coverage: config safety, episode schema/store/migration, backfill, retrieval, planner, v2 engine routing, diagnostics, tests, and smoke verification all have tasks.
- No implementation step changes default API behavior unless `MEMORYOS_RECALL_PIPELINE=v2`.
- The plan intentionally keeps item retrieval supporting-only in Phase 1; direct item extraction is deferred.
- `MemoryOSService.search()` remains the page search API.
- Public benchmark diagnostics are extended before v2 scores are interpreted.
