from memoryos_lite.retrieval.archival_searcher import (
    ArchivalPassageHit,
    ArchivalPassageSearcher,
)
from memoryos_lite.retrieval.archival_vector import (
    ArchivalEmbeddingConfig,
    ArchivalVectorHit,
    ArchivalVectorIndex,
)
from memoryos_lite.retrieval.providers.qdrant_archival import (
    QdrantArchivalPassageStore,
)
from memoryos_lite.v3_contracts import ArchivalPassage, SourceRef, SourceSpan


def _passage(
    passage_id: str,
    text: str,
    *,
    archive_id: str = "archive_1",
    source_id: str | None = None,
    file_id: str = "file_1",
    tags: list[str] | None = None,
) -> ArchivalPassage:
    return ArchivalPassage(
        id=passage_id,
        document_id=f"doc_{passage_id}",
        archive_id=archive_id,
        text=text,
        citation=SourceSpan(start=0, end=len(text)),
        source_id=source_id,
        file_id=file_id,
        tags=tags or [],
        source_refs=[SourceRef(source_type="message", source_id="msg_1")],
    )


def test_archival_search_returns_passage_level_evidence_with_metadata():
    searcher = ArchivalPassageSearcher()
    passages = [
        _passage("apsg_1", "Alice moved to Shanghai and likes rail.", tags=["travel"]),
        _passage("apsg_2", "Bob prefers remote work.", archive_id="archive_2"),
    ]

    hits = searcher.search(
        passages,
        "Shanghai rail",
        top_k=5,
        archive_id="archive_1",
        tags=["travel"],
        mode="text",
    )

    assert [hit.passage.id for hit in hits] == ["apsg_1"]
    assert hits[0].source == "archival_text"
    assert hits[0].citation == SourceSpan(start=0, end=len(passages[0].text))
    assert hits[0].source_refs[0].source_id == "msg_1"
    assert hits[0].metadata["archive_id"] == "archive_1"


def test_archival_search_accepts_vector_and_hybrid_modes_without_ann_backend():
    searcher = ArchivalPassageSearcher()
    passages = [_passage("apsg_1", "Alice moved to Shanghai and likes rail.")]

    vector_hits = searcher.search(passages, "Shanghai", mode="vector", top_k=5)
    hybrid_hits = searcher.search(passages, "Shanghai", mode="hybrid", top_k=5)

    assert vector_hits[0].source == "archival_vector"
    assert "vector_unavailable" in vector_hits[0].reason
    assert hybrid_hits[0].source == "archival_hybrid"
    assert "lexical" in hybrid_hits[0].reason


class TinyEmbeddingClient:
    @property
    def dim(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        if normalized == "favorite transport" or "semantic-target" in normalized:
            return [1.0, 0.0, 0.0]
        if "favorite transport" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class FailingEmbeddingClient(TinyEmbeddingClient):
    def embed(self, text: str) -> list[float]:
        raise RuntimeError("embedding unavailable")


def _vector_index(
    collection: str,
    *,
    embedding_client: TinyEmbeddingClient | None = None,
) -> ArchivalVectorIndex:
    return ArchivalVectorIndex(
        embedding_client=embedding_client or TinyEmbeddingClient(),
        vector_store=QdrantArchivalPassageStore(
            url=":memory:",
            collection=collection,
            dim=3,
        ),
        config=ArchivalEmbeddingConfig(provider="test", model="tiny", dim=3),
    )


def test_archival_search_uses_vector_primary_and_rehydrates_hits_from_loader():
    target = _passage(
        "apsg_target",
        "semantic-target metro preference",
        tags=["transport"],
    )
    lexical_distractor = _passage(
        "apsg_lexical",
        "favorite transport distractor",
        archive_id="archive_2",
    )
    loaded_ids: list[str] = []

    def loader(passage_ids: list[str]) -> dict[str, ArchivalPassage]:
        loaded_ids.extend(passage_ids)
        return {
            passage.id: passage
            for passage in [target, lexical_distractor]
            if passage.id in passage_ids
        }

    searcher = ArchivalPassageSearcher(
        vector_index=_vector_index("memoryos_archival_searcher_primary"),
        passage_loader=loader,
    )

    hits = searcher.search(
        [target, lexical_distractor],
        "favorite transport",
        mode="vector",
        top_k=1,
    )

    assert [hit.passage.id for hit in hits] == ["apsg_target"]
    assert loaded_ids == ["apsg_target"]
    assert hits[0].source == "archival_vector"
    assert hits[0].source_refs[0].source_id == "msg_1"
    assert hits[0].metadata["vector_provider"] == "test"


def test_archival_search_falls_back_to_lexical_when_vector_unavailable():
    passage = _passage("apsg_lexical", "Shanghai rail lexical fallback")
    searcher = ArchivalPassageSearcher(
        vector_index=_vector_index(
            "memoryos_archival_searcher_fallback",
            embedding_client=FailingEmbeddingClient(),
        ),
        passage_loader=lambda ids: {passage.id: passage},
    )

    hits = searcher.search([passage], "Shanghai rail", mode="vector", top_k=5)

    assert [hit.passage.id for hit in hits] == ["apsg_lexical"]
    assert hits[0].source == "archival_vector"
    assert "vector_unavailable" in hits[0].reason
    assert "lexical_fallback" in hits[0].reason
    assert any(
        diagnostic.event_type == "archival_vector_unavailable"
        for diagnostic in searcher.last_diagnostics
    )
    assert any(
        diagnostic.event_type == "archival_lexical_fallback"
        for diagnostic in searcher.last_diagnostics
    )


class StaleVectorStore:
    def upsert_passage(
        self,
        passage: ArchivalPassage,
        vector: list[float],
        config: ArchivalEmbeddingConfig,
    ) -> None:
        return None

    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        passage_ids: list[str] | None,
        config: ArchivalEmbeddingConfig,
    ) -> list[ArchivalVectorHit]:
        return [
            ArchivalVectorHit(passage_id="apsg_stale", score=0.99),
            ArchivalVectorHit(passage_id="apsg_live", score=0.75),
        ][:top_k]


def test_archival_search_ignores_stale_vector_hits_missing_from_sqlite():
    live = _passage("apsg_live", "semantic-target live passage")
    searcher = ArchivalPassageSearcher(
        vector_index=ArchivalVectorIndex(
            embedding_client=TinyEmbeddingClient(),
            vector_store=StaleVectorStore(),
            config=ArchivalEmbeddingConfig(provider="test", model="tiny", dim=3),
        ),
        passage_loader=lambda ids: {"apsg_live": live},
    )

    hits = searcher.search([live], "favorite transport", mode="vector", top_k=5)

    assert [hit.passage.id for hit in hits] == ["apsg_live"]
    stale = [
        diagnostic
        for diagnostic in searcher.last_diagnostics
        if diagnostic.event_type == "archival_stale_vector_hit"
    ]
    assert len(stale) == 1
    assert stale[0].item_id == "apsg_stale"


def test_archival_search_reindexes_updated_passage_vectors():
    collection = "memoryos_archival_searcher_reindex"
    vector_index = _vector_index(collection)
    updated = _passage("apsg_updated", "semantic-target old passage")
    replacement = _passage(
        "apsg_replacement",
        "semantic-target replacement passage",
        archive_id="archive_2",
    )
    searcher = ArchivalPassageSearcher(
        vector_index=vector_index,
        passage_loader=lambda ids: {
            passage.id: passage
            for passage in [updated, replacement]
            if passage.id in ids
        },
    )

    first_hits = searcher.search([updated], "favorite transport", mode="vector", top_k=1)
    updated = updated.model_copy(update={"text": "favorite transport stale text"})
    second_hits = searcher.search(
        [updated, replacement],
        "favorite transport",
        mode="vector",
        top_k=1,
    )

    assert [hit.passage.id for hit in first_hits] == ["apsg_updated"]
    assert [hit.passage.id for hit in second_hits] == ["apsg_replacement"]


class ReorderingReranker:
    def rerank(
        self,
        hits: list[ArchivalPassageHit],
        query: str,
        top_k: int,
    ) -> list[ArchivalPassageHit]:
        injected = ArchivalPassageHit(
            passage=_passage(
                "apsg_external",
                "rail external unscoped passage",
                archive_id="archive_external",
            ),
            score=99.0,
            reason=f"external rerank for {query}",
            source="external_reranker",
        )
        reordered = sorted(hits, key=lambda hit: hit.passage.id, reverse=True)
        return [injected, *reordered][:top_k]


def test_archival_search_reranker_can_reorder_but_cannot_inject_external_hits():
    first = _passage("apsg_first", "Shanghai rail first note")
    second = _passage("apsg_second", "Shanghai rail second note")
    searcher = ArchivalPassageSearcher(reranker=ReorderingReranker())

    hits = searcher.search([first, second], "Shanghai rail", mode="text", top_k=5)

    assert [hit.passage.id for hit in hits] == ["apsg_second", "apsg_first"]
    assert all(hit.passage.id != "apsg_external" for hit in hits)
    assert all(hit.source_refs for hit in hits)
    injected_diagnostics = [
        diagnostic
        for diagnostic in searcher.last_diagnostics
        if diagnostic.event_type == "archival_reranker_dropped_external_hit"
    ]
    assert len(injected_diagnostics) == 1
    assert injected_diagnostics[0].item_id == "apsg_external"
