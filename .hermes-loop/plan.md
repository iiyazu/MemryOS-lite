# Recall Memory Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the opt-in episode recall path into a Recall Memory Layer with structured diagnostics while keeping default `v1` and old benchmark fields compatible.

**Architecture:** Keep the existing `episodes` table as physical storage, adapt rows into `RecallMemoryEntry`, and evolve the current episode searcher into a diagnostic-rich recall searcher. `RecallPipeline` remains the `ContextPackage` compatibility boundary and maps recall-native metadata back to old `episode_*` report fields.

**Tech Stack:** Python 3.11, Pydantic v2 contracts in `v3_contracts.py`, rank-bm25, pytest, existing SQLAlchemy-backed `MemoryStore`.

---

## File Structure

- Modify: `src/memoryos_lite/retrieval/episode_searcher.py`
  - Add recall-native hit diagnostics, neighbor expansion, dedupe, and a `RecallMemorySearcher` compatibility surface.
- Modify: `src/memoryos_lite/retrieval/__init__.py`
  - Export `RecallMemorySearcher` while keeping `EpisodeSearcher` and `EpisodeHit`.
- Modify: `src/memoryos_lite/retrieval/recall_pipeline.py`
  - Convert backfilled episodes into `RecallMemoryEntry`, use recall diagnostics, and emit recall-native plus legacy metadata.
- Modify: `src/memoryos_lite/evals.py`
  - Read recall-native metadata first and keep old `episode_*` fields as compatibility output.
- Modify: `src/memoryos_lite/public_benchmarks.py`
  - Keep public report compatibility and verify no report schema regression.
- Modify: `tests/test_episode_retrieval.py`
  - Add searcher tests for direct hit, neighbor expansion, dedupe, role/session diagnostics.
- Modify: `tests/test_recall_pipeline.py`
  - Add pipeline tests for backfill, recall metadata, budget drop diagnostics, and legacy mapping.
- Modify: `tests/test_evals.py`
  - Add eval mapping coverage for recall metadata to `episode_*` fields.
- Modify: `tests/test_public_benchmarks.py`
  - Keep public report coverage for `episode_source_hit_at_10` and mapped diagnostics.

## Task 1: Searcher Tests for Recall Diagnostics

**Files:**
- Modify: `tests/test_episode_retrieval.py`

- [ ] **Step 1: Add failing tests for recall hit diagnostics and neighbor expansion**

Append these tests to `tests/test_episode_retrieval.py`:

```python
from memoryos_lite.v3_contracts import RecallMemoryEntry, SourceRef


def _recall_entry(
    message_id: str,
    text: str,
    position: int,
    role: Role = Role.USER,
    session_id: str = "ses",
    benchmark_session_id: str | None = None,
    benchmark_date: str | None = None,
) -> RecallMemoryEntry:
    temporal_scope = {}
    if benchmark_session_id is not None:
        temporal_scope["benchmark_session_id"] = benchmark_session_id
    if benchmark_date is not None:
        temporal_scope["benchmark_date"] = benchmark_date
    return RecallMemoryEntry(
        id=f"rec_{message_id}",
        session_id=session_id,
        message_id=message_id,
        role=role,
        text=text,
        index_text=f"[speaker={role.value}] {text}",
        position=position,
        source_message_ids=[message_id],
        source_refs=[
            SourceRef(
                source_type="message",
                source_id=message_id,
                session_id=session_id,
            )
        ],
        temporal_scope=temporal_scope,
    )


def test_recall_searcher_returns_structured_direct_hit_diagnostics():
    entries = [
        _recall_entry("msg_1", "Alice likes coffee.", 1),
        _recall_entry(
            "msg_2",
            "Bob moved to Shanghai.",
            2,
            benchmark_session_id="D2",
            benchmark_date="2026-05-20",
        ),
    ]

    hits = EpisodeSearcher().search(entries, "Where did Bob move?", top_k=1)

    assert hits[0].episode.message_id == "msg_2"
    assert hits[0].source == "recall_memory"
    assert hits[0].rank_features["token_overlap"] > 0
    assert {event.reason_code for event in hits[0].diagnostics} >= {
        "direct_hit",
        "rank",
    }


def test_recall_searcher_expands_neighbors_and_dedupes_message_ids():
    entries = [
        _recall_entry("msg_1", "Project kickoff notes.", 1),
        _recall_entry("msg_2", "The deployment target is Osaka.", 2),
        _recall_entry("msg_3", "The team confirmed the rollout window.", 3),
    ]

    hits = EpisodeSearcher().search(entries, "deployment target", top_k=3)

    assert [hit.episode.message_id for hit in hits] == ["msg_2", "msg_1", "msg_3"]
    assert len({hit.episode.message_id for hit in hits}) == 3
    neighbor_hits = [
        hit for hit in hits if any(event.reason_code == "neighbor" for event in hit.diagnostics)
    ]
    assert [hit.episode.message_id for hit in neighbor_hits] == ["msg_1", "msg_3"]
    assert any(
        event.reason_code == "dedupe"
        for hit in hits
        for event in hit.diagnostics
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_episode_retrieval.py -q
```

Expected: FAIL because `EpisodeHit` does not expose `diagnostics`,
`rank_features`, or recall neighbor expansion yet.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_episode_retrieval.py
git commit -m "test: define recall search diagnostics"
```

## Task 2: Implement RecallMemorySearcher With Compatibility Wrapper

**Files:**
- Modify: `src/memoryos_lite/retrieval/episode_searcher.py`
- Modify: `src/memoryos_lite/retrieval/__init__.py`

- [ ] **Step 1: Add recall hit fields and diagnostics helpers**

In `src/memoryos_lite/retrieval/episode_searcher.py`, replace the current
`EpisodeHit` dataclass with:

```python
@dataclass(frozen=True)
class EpisodeHit:
    episode: Episode | RecallMemoryEntry
    score: float
    reason: str
    source: str = "recall_memory"
    diagnostics: tuple[DiagnosticEvent, ...] = ()
    rank_features: dict[str, float] = field(default_factory=dict)
    neighbor_of: str | None = None
```

Add these imports:

```python
from dataclasses import dataclass, field

from memoryos_lite.v3_contracts import DiagnosticEvent, RecallMemoryEntry, SourceRef
```

Add this helper below `_content_tokens`:

```python
def _diagnostic(
    entry: Episode | RecallMemoryEntry,
    reason_code: str,
    score: float | None,
    included: bool,
    metadata: dict[str, object] | None = None,
) -> DiagnosticEvent:
    return DiagnosticEvent(
        layer="recall",
        event_type="candidate",
        item_id=entry.message_id,
        reason_code=reason_code,
        score=score,
        included=included,
        source_refs=[
            SourceRef(
                source_type="message",
                source_id=source_id,
                session_id=entry.session_id,
            )
            for source_id in entry.source_message_ids
        ],
        metadata=metadata or {},
    )
```

- [ ] **Step 2: Implement `RecallMemorySearcher` and keep `EpisodeSearcher`**

Replace the current `EpisodeSearcher` class with:

```python
class RecallMemorySearcher:
    def search(
        self,
        episodes: list[Episode | RecallMemoryEntry],
        query: str,
        top_k: int = 5,
        analysis: QueryAnalysis | None = None,
        neighbor_window: int = 1,
    ) -> list[EpisodeHit]:
        query_tokens = tokenize(query)
        query_content_tokens = _content_tokens(query_tokens)
        if not episodes or not query_content_tokens:
            return []

        corpus = [tokenize(episode.index_text) for episode in episodes]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)
        direct_hits: list[EpisodeHit] = []

        for episode, episode_tokens, score in zip(episodes, corpus, scores, strict=False):
            token_overlap = len(query_content_tokens & _content_tokens(episode_tokens))
            if token_overlap <= 0:
                continue
            adjusted = float(score) + token_overlap
            diagnostics = [
                _diagnostic(
                    episode,
                    "direct_hit",
                    adjusted,
                    True,
                    {"token_overlap": token_overlap},
                ),
                _diagnostic(
                    episode,
                    "rank",
                    adjusted,
                    True,
                    {"base_score": float(score), "token_overlap": token_overlap},
                ),
            ]
            if (
                analysis is not None
                and analysis.kind == QueryKind.ASSISTANT_SOURCE
                and episode.role == Role.ASSISTANT
            ):
                adjusted += 6.0
                diagnostics.append(
                    _diagnostic(episode, "role_match", adjusted, True, {"role": "assistant"})
                )
            if adjusted <= 0:
                continue
            direct_hits.append(
                EpisodeHit(
                    episode=episode,
                    score=adjusted,
                    reason=f"recall_bm25={adjusted:.4f} overlap={token_overlap}",
                    diagnostics=tuple(diagnostics),
                    rank_features={
                        "bm25_score": float(score),
                        "token_overlap": float(token_overlap),
                        "adjusted_score": adjusted,
                    },
                )
            )

        ranked = sorted(
            direct_hits,
            key=lambda hit: (hit.score, -hit.episode.position),
            reverse=True,
        )
        return self._with_neighbors(ranked, episodes, top_k, neighbor_window)

    def _with_neighbors(
        self,
        direct_hits: list[EpisodeHit],
        episodes: list[Episode | RecallMemoryEntry],
        top_k: int,
        neighbor_window: int,
    ) -> list[EpisodeHit]:
        by_position = {episode.position: episode for episode in episodes}
        selected: list[EpisodeHit] = []
        seen_message_ids: set[str] = set()
        dedupe_events: list[DiagnosticEvent] = []

        for hit in direct_hits:
            if hit.episode.message_id not in seen_message_ids:
                selected.append(hit)
                seen_message_ids.add(hit.episode.message_id)
            else:
                dedupe_events.append(
                    _diagnostic(hit.episode, "dedupe", hit.score, False, {"duplicate": True})
                )
            if len(selected) >= top_k:
                break
            for offset in range(1, neighbor_window + 1):
                for position in (hit.episode.position - offset, hit.episode.position + offset):
                    neighbor = by_position.get(position)
                    if neighbor is None:
                        continue
                    if neighbor.message_id in seen_message_ids:
                        dedupe_events.append(
                            _diagnostic(
                                neighbor,
                                "dedupe",
                                hit.score,
                                False,
                                {"neighbor_of": hit.episode.message_id},
                            )
                        )
                        continue
                    selected.append(
                        EpisodeHit(
                            episode=neighbor,
                            score=max(0.0, hit.score - 0.01),
                            reason=f"neighbor_of={hit.episode.message_id}",
                            diagnostics=(
                                _diagnostic(
                                    neighbor,
                                    "neighbor",
                                    hit.score,
                                    True,
                                    {"neighbor_of": hit.episode.message_id},
                                ),
                            ),
                            rank_features={"neighbor_of_rank": hit.score},
                            neighbor_of=hit.episode.message_id,
                        )
                    )
                    seen_message_ids.add(neighbor.message_id)
                    if len(selected) >= top_k:
                        break
                if len(selected) >= top_k:
                    break
            if len(selected) >= top_k:
                break

        if dedupe_events and selected:
            first = selected[0]
            selected[0] = EpisodeHit(
                episode=first.episode,
                score=first.score,
                reason=first.reason,
                source=first.source,
                diagnostics=first.diagnostics + tuple(dedupe_events),
                rank_features=first.rank_features,
                neighbor_of=first.neighbor_of,
            )
        return selected[:top_k]


class EpisodeSearcher(RecallMemorySearcher):
    pass
```

- [ ] **Step 3: Export the new recall searcher**

In `src/memoryos_lite/retrieval/__init__.py`, change the import to:

```python
from memoryos_lite.retrieval.episode_searcher import (
    EpisodeHit,
    EpisodeSearcher,
    RecallMemorySearcher,
)
```

Add `"RecallMemorySearcher"` to `__all__`.

- [ ] **Step 4: Run tests to verify searcher behavior**

Run:

```bash
uv run pytest tests/test_episode_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/retrieval/episode_searcher.py src/memoryos_lite/retrieval/__init__.py tests/test_episode_retrieval.py
git commit -m "feat: add recall memory search diagnostics"
```

## Task 3: RecallPipeline Metadata and Budget Diagnostics

**Files:**
- Modify: `tests/test_recall_pipeline.py`
- Modify: `src/memoryos_lite/retrieval/recall_pipeline.py`

- [ ] **Step 1: Add failing pipeline tests for recall-native metadata**

Append to `tests/test_recall_pipeline.py`:

```python
def test_recall_pipeline_backfills_recall_entries_and_maps_legacy_metadata(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    msg = Message(
        id="msg_osaka",
        session_id="ses",
        role=Role.USER,
        content="The deployment target is Osaka.",
        metadata={},
        token_count=5,
    )
    store.add_message(msg)

    pipeline = RecallPipeline(store=store, settings=settings, tokenizer=WordTokenizer())
    package = pipeline.build_context(
        session_id="ses",
        task="What is the deployment target?",
        budget=200,
    )

    assert package.retrieved_evidence
    assert package.metadata["episode_backfilled"] == 1
    assert package.metadata["recall_candidate_message_ids"] == ["msg_osaka"]
    assert package.metadata["episode_candidate_message_ids"] == ["msg_osaka"]
    assert package.metadata["recall_planned_message_ids"] == ["msg_osaka"]
    assert package.metadata["planned_evidence_message_ids"] == ["msg_osaka"]
    assert package.metadata["recall_indexed_source_ids"] == ["msg_osaka"]
    assert package.metadata["indexed_source_ids"] == ["msg_osaka"]
    assert any(
        event["reason_code"] == "direct_hit"
        for event in package.metadata["recall_diagnostics"]
    )


def test_recall_pipeline_records_budget_drop_diagnostics(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    msg = Message(
        id="msg_big",
        session_id="ses",
        role=Role.USER,
        content=" ".join(["deployment"] * 20),
        metadata={},
        token_count=20,
    )
    store.add_message(msg)

    pipeline = RecallPipeline(store=store, settings=settings, tokenizer=WordTokenizer())
    package = pipeline.build_context(session_id="ses", task="deployment", budget=2)

    assert package.retrieved_evidence == []
    assert package.candidate_budget_dropped == 1
    assert package.metadata["recall_budget_dropped"] == 1
    assert package.metadata["budget_dropped_relevant"] == 1
    assert any(
        event["reason_code"] == "budget_drop"
        for event in package.metadata["recall_diagnostics"]
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_recall_pipeline.py -q
```

Expected: FAIL because `RecallPipeline` does not emit recall-native metadata or
serialized recall diagnostics yet.

- [ ] **Step 3: Adapt recall pipeline around `RecallMemoryEntry`**

In `src/memoryos_lite/retrieval/recall_pipeline.py`, update imports:

```python
from memoryos_lite.retrieval.episode_searcher import EpisodeHit, RecallMemorySearcher
from memoryos_lite.v3_contracts import DiagnosticEvent, episode_to_recall_entry
```

In `__init__`, replace:

```python
self.episode_searcher = EpisodeSearcher()
```

with:

```python
self.recall_searcher = RecallMemorySearcher()
```

Add helper methods to `RecallPipeline`:

```python
    def _serialize_diagnostics(self, hits: list[EpisodeHit]) -> list[dict[str, object]]:
        diagnostics: list[dict[str, object]] = []
        for hit in hits:
            diagnostics.extend(event.model_dump(mode="json") for event in hit.diagnostics)
        return diagnostics

    def _budget_drop_event(self, hit: EpisodeHit, tokens: int) -> DiagnosticEvent:
        return DiagnosticEvent(
            layer="recall",
            event_type="candidate",
            item_id=hit.episode.message_id,
            reason_code="budget_drop",
            score=hit.score,
            dropped=True,
            budget_tokens=tokens,
            metadata={"reason": "recall evidence exceeded remaining budget"},
        )
```

Change the search setup in `build_context` to:

```python
        episodes = self.store.list_episodes(session_id)
        recall_entries = [episode_to_recall_entry(episode) for episode in episodes]
        analysis = self.query_analyzer.analyze(query)
        hits = self.recall_searcher.search(
            recall_entries,
            query,
            top_k=10,
            analysis=analysis,
        )
```

Replace candidate/index metadata construction with:

```python
        candidate_ids = [hit.episode.message_id for hit in hits]
        indexed_source_ids = sorted(
            {
                source_id
                for entry in recall_entries
                for source_id in entry.source_message_ids
            }
        )
        diagnostics = self._serialize_diagnostics(hits)
```

When the task exceeds budget, update metadata with both recall-native and
legacy keys:

```python
                    "recall_candidate_message_ids": candidate_ids,
                    "recall_planned_message_ids": [],
                    "recall_indexed_source_ids": indexed_source_ids,
                    "recall_diagnostics": diagnostics,
                    "recall_budget_dropped": dropped,
                    "episode_candidate_message_ids": candidate_ids,
                    "planned_evidence_message_ids": [],
                    "indexed_source_ids": indexed_source_ids,
                    "budget_dropped_relevant": dropped,
```

Inside the evidence budget loop, append a budget-drop diagnostic when a hit is
not selected:

```python
                diagnostics.append(
                    self._budget_drop_event(hit, tokens).model_dump(mode="json")
                )
                dropped += 1
                continue
```

For selected evidence metadata, keep legacy origin and add recall details:

```python
                    "origin": "episode",
                    "memory_layer": "recall",
                    "score": hit.score,
                    "rank_features": hit.rank_features,
                    "neighbor_of": hit.neighbor_of,
```

At the successful return path, update metadata with:

```python
                "recall_candidate_message_ids": candidate_ids,
                "recall_planned_message_ids": planned_ids,
                "recall_indexed_source_ids": indexed_source_ids,
                "recall_diagnostics": diagnostics,
                "recall_budget_dropped": dropped,
                "episode_candidate_message_ids": candidate_ids,
                "planned_evidence_message_ids": planned_ids,
                "indexed_source_ids": indexed_source_ids,
                "budget_dropped_relevant": dropped,
```

- [ ] **Step 4: Run recall pipeline tests**

Run:

```bash
uv run pytest tests/test_recall_pipeline.py tests/test_episode_retrieval.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/retrieval/recall_pipeline.py tests/test_recall_pipeline.py
git commit -m "feat: emit recall pipeline diagnostics"
```

## Task 4: Eval and Public Benchmark Compatibility Mapping

**Files:**
- Modify: `tests/test_evals.py`
- Modify: `tests/test_public_benchmarks.py`
- Modify: `src/memoryos_lite/evals.py`
- Modify: `src/memoryos_lite/public_benchmarks.py`

- [ ] **Step 1: Add failing eval mapping test**

Append to `tests/test_evals.py`:

```python
from memoryos_lite.evals import _metadata_string_list_preferring


def test_eval_metadata_prefers_recall_candidates_over_legacy_episode_keys():
    metadata = {
        "recall_candidate_message_ids": ["msg_recall"],
        "episode_candidate_message_ids": ["msg_legacy"],
        "recall_planned_message_ids": ["msg_planned"],
        "planned_evidence_message_ids": ["msg_old_planned"],
        "recall_indexed_source_ids": ["msg_indexed"],
        "indexed_source_ids": ["msg_old_indexed"],
    }

    assert _metadata_string_list_preferring(
        metadata,
        "recall_candidate_message_ids",
        "episode_candidate_message_ids",
    ) == ["msg_recall"]
    assert _metadata_string_list_preferring(
        metadata,
        "recall_planned_message_ids",
        "planned_evidence_message_ids",
    ) == ["msg_planned"]
    assert _metadata_string_list_preferring(
        metadata,
        "recall_indexed_source_ids",
        "indexed_source_ids",
    ) == ["msg_indexed"]
```

Add this assertion to the existing public benchmark v2 diagnostics test
`test_public_benchmark_reports_v2_recall_diagnostics` in
`tests/test_public_benchmarks.py`:

```python
    assert report["episode_source_hit_at_10"] is True
    assert report["episode_candidate_message_ids"]
    assert report["planned_evidence_message_ids"]
```

- [ ] **Step 2: Run tests to verify current mapping gaps**

Run:

```bash
uv run pytest tests/test_evals.py::test_eval_metadata_prefers_recall_candidates_over_legacy_episode_keys tests/test_public_benchmarks.py::test_public_benchmark_reports_v2_recall_diagnostics -q
```

Expected: the eval helper test fails first because
`_metadata_string_list_preferring` does not exist yet.

- [ ] **Step 3: Update eval mapping to prefer recall metadata**

In `src/memoryos_lite/evals.py`, add this helper near `_metadata_string_list`:

```python
def _metadata_string_list_preferring(
    metadata: dict[str, object],
    preferred_key: str,
    fallback_key: str,
) -> list[str]:
    preferred = _metadata_string_list(metadata, preferred_key)
    return preferred or _metadata_string_list(metadata, fallback_key)
```

Inside the `memoryos_lite` baseline branch, replace the metadata reads for
episode/planned/indexed IDs with:

```python
        indexed_source_ids = _metadata_string_list_preferring(
            context.metadata,
            "recall_indexed_source_ids",
            "indexed_source_ids",
        )
        item_candidate_source_ids = _metadata_string_list(
            context.metadata, "item_candidate_source_ids"
        )
        episode_candidate_message_ids = _metadata_string_list_preferring(
            context.metadata,
            "recall_candidate_message_ids",
            "episode_candidate_message_ids",
        )
        planned_evidence_message_ids = _metadata_string_list_preferring(
            context.metadata,
            "recall_planned_message_ids",
            "planned_evidence_message_ids",
        )
```

Replace the budget-drop read with:

```python
            budget_dropped_relevant=(
                _metadata_int(context.metadata, "recall_budget_dropped")
                or _metadata_int(context.metadata, "budget_dropped_relevant")
            ),
```

Keep assigning these values to the existing `BaselineOutput` fields
`episode_candidate_message_ids`, `planned_evidence_message_ids`,
`episode_source_hit_at_10`, and `planned_evidence_source_hit_at_5`.

- [ ] **Step 4: Keep public benchmark schema stable**

In `src/memoryos_lite/public_benchmarks.py`, leave
`PublicBenchmarkResult.to_report()` field names unchanged. Add this guard near
the `episode_source_hit_at_10` assignment in `_to_public_result`:

```python
        episode_source_hit_at_10=(
            output.episode_source_hit_at_10
            if output.episode_source_hit_at_10 is not None
            else (
                bool(set(output.episode_candidate_message_ids) & expected_source_set)
                if expected_source_set
                else None
            )
        ),
```

- [ ] **Step 5: Run eval and public benchmark tests**

Run:

```bash
uv run pytest tests/test_evals.py tests/test_public_benchmarks.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memoryos_lite/evals.py src/memoryos_lite/public_benchmarks.py tests/test_evals.py tests/test_public_benchmarks.py
git commit -m "feat: map recall diagnostics to benchmark fields"
```

## Task 5: Regression Verification

**Files:**
- No source file changes.

- [ ] **Step 1: Run focused recall tests**

Run:

```bash
uv run pytest tests/test_episode_retrieval.py tests/test_recall_pipeline.py tests/test_public_benchmarks.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS. The regression bar from God is no unintended regressions and at
least the recorded baseline of `311 passed`.

- [ ] **Step 3: Run smoke benchmark commands when data is available**

Run the local smoke command used by the project for LongMemEval and LoCoMo. If
fixture paths are not configured locally, record the missing path and keep the
pytest result as the executable acceptance evidence for this phase.

Expected when benchmark data is available:

- LongMemEval `episode_source_hit_at_10 >= 8/10`
- LoCoMo `episode_source_hit_at_10 >= 5/10`
- `source_not_indexed = 0/10` for both smoke reports

- [ ] **Step 4: Commit verification evidence if files changed**

```bash
git status --short
```

Expected: no uncommitted source changes after implementation commits, unless
generated reports were intentionally retained for review.
