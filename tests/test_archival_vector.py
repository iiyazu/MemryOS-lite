import pytest

from memoryos_lite.retrieval.archival_vector import (
    ArchivalEmbeddingConfig,
    ArchivalVectorHit,
    ArchivalVectorIndex,
    LocalArchivalVectorStore,
)
from memoryos_lite.retrieval.providers.qdrant_archival import (
    QdrantArchivalPassageStore,
)
from memoryos_lite.v3_contracts import ArchivalPassage, SourceRef


def _ref(source_id: str = "msg_1") -> SourceRef:
    return SourceRef(source_type="message", source_id=source_id, session_id="ses_1")


def _passage(
    passage_id: str,
    text: str,
    *,
    archive_id: str = "archive_1",
) -> ArchivalPassage:
    return ArchivalPassage(
        id=passage_id,
        archive_id=archive_id,
        text=text,
        source_refs=[_ref()],
    )


def _config(model: str = "tiny") -> ArchivalEmbeddingConfig:
    return ArchivalEmbeddingConfig(provider="test", model=model, dim=3)


class TinyEmbeddingClient:
    @property
    def dim(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        if "needle" in text.lower():
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class CountingEmbeddingClient(TinyEmbeddingClient):
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, text: str) -> list[float]:
        self.calls += 1
        return super().embed(text)


def test_archival_qdrant_points_use_passage_namespace_and_config_payload():
    vector_store = QdrantArchivalPassageStore(
        url=":memory:",
        collection="memoryos_archival_passages_test",
        dim=3,
    )
    config = _config()
    passage = _passage("apsg_needle", "needle passage")

    vector_store.upsert_passage(passage, [1.0, 0.0, 0.0], config)

    points = vector_store.client.retrieve(
        collection_name=vector_store.collection,
        ids=[vector_store.point_id(passage.id)],
        with_payload=True,
    )
    payload = points[0].payload or {}
    assert payload["namespace"] == "memoryos_archival_passage"
    assert payload["passage_id"] == "apsg_needle"
    assert payload["archive_id"] == "archive_1"
    assert payload["embedding_config_hash"] == config.config_hash
    assert "text" not in payload
    assert "source_refs" not in payload


def test_archival_qdrant_query_filters_to_eligible_passage_ids():
    vector_store = QdrantArchivalPassageStore(
        url=":memory:",
        collection="memoryos_archival_passages_test",
        dim=3,
    )
    config = _config()
    vector_store.upsert_passage(
        _passage("apsg_best", "best semantic match"),
        [1.0, 0.0, 0.0],
        config,
    )
    vector_store.upsert_passage(
        _passage("apsg_eligible", "eligible but weaker", archive_id="archive_2"),
        [0.0, 1.0, 0.0],
        config,
    )

    hits = vector_store.query(
        [1.0, 0.0, 0.0],
        top_k=5,
        passage_ids=["apsg_eligible"],
        config=config,
    )

    assert [hit.passage_id for hit in hits] == ["apsg_eligible"]
    assert all(hit.passage_id != "apsg_best" for hit in hits)


def test_archival_qdrant_rejects_dimension_mismatch():
    vector_store = QdrantArchivalPassageStore(
        url=":memory:",
        collection="memoryos_archival_passages_test",
        dim=3,
    )

    with pytest.raises(ValueError, match="embedding dimension mismatch"):
        vector_store.upsert_passage(
            _passage("apsg_bad", "bad dimension"),
            [1.0, 0.0],
            _config(),
        )


def test_archival_qdrant_query_filters_embedding_config_hash():
    vector_store = QdrantArchivalPassageStore(
        url=":memory:",
        collection="memoryos_archival_passages_test",
        dim=3,
    )
    vector_store.upsert_passage(
        _passage("apsg_old_model", "old model vector"),
        [1.0, 0.0, 0.0],
        _config(model="old"),
    )

    hits = vector_store.query(
        [1.0, 0.0, 0.0],
        top_k=5,
        passage_ids=["apsg_old_model"],
        config=_config(model="new"),
    )

    assert hits == []


def test_archival_vector_index_can_index_passages_before_query():
    vector_store = QdrantArchivalPassageStore(
        url=":memory:",
        collection="memoryos_archival_passages_index_test",
        dim=3,
    )
    config = _config()
    vector_index = ArchivalVectorIndex(
        embedding_client=TinyEmbeddingClient(),
        vector_store=vector_store,
        config=config,
    )

    diagnostics = vector_index.index_passages([_passage("apsg_indexed", "needle passage")])
    hits = vector_store.query(
        [1.0, 0.0, 0.0],
        top_k=1,
        passage_ids=["apsg_indexed"],
        config=config,
    )

    assert diagnostics == []
    assert [hit.passage_id for hit in hits] == ["apsg_indexed"]


def test_local_archival_vector_finds_semantic_match_without_lexical_overlap():
    vector_store = LocalArchivalVectorStore(dim=3)
    vector_index = ArchivalVectorIndex(
        embedding_client=TinyEmbeddingClient(),
        vector_store=vector_store,
        config=_config(),
    )

    result = vector_index.search(
        [
            _passage("apsg_target", "needle source"),
            _passage("apsg_distractor", "unrelated source"),
        ],
        "needle paraphrase",
        top_k=1,
    )

    assert [hit.passage_id for hit in result.hits] == ["apsg_target"]
    assert result.hits[0].payload["backend"] == "local"


def test_local_archival_vector_is_bounded_and_filters_out_of_scope_passages():
    vector_store = LocalArchivalVectorStore(dim=3, max_vectors=1)
    config = _config()
    first = _passage("apsg_first", "needle first")
    second = _passage("apsg_second", "needle second")
    vector_store.upsert_passage(first, [1.0, 0.0, 0.0], config)
    vector_store.upsert_passage(second, [1.0, 0.0, 0.0], config)

    assert vector_store.query(
        [1.0, 0.0, 0.0],
        top_k=2,
        passage_ids=[first.id, second.id],
        config=config,
    ) == [
        ArchivalVectorHit(
            passage_id=second.id,
            score=1.0,
            payload={
                "backend": "local",
                "embedding_config_hash": config.config_hash,
            },
        )
    ]

    assert (
        vector_store.query(
            [1.0, 0.0, 0.0],
            top_k=1,
            passage_ids=[],
            config=config,
        )
        == []
    )


def test_local_archival_vector_isolates_embedding_configurations():
    vector_store = LocalArchivalVectorStore(dim=3)
    old_config = _config(model="old")
    vector_store.upsert_passage(
        _passage("apsg_old_model", "needle"),
        [1.0, 0.0, 0.0],
        old_config,
    )

    assert (
        vector_store.query(
            [1.0, 0.0, 0.0],
            top_k=1,
            passage_ids=["apsg_old_model"],
            config=_config(model="new"),
        )
        == []
    )


def test_local_archival_vector_reuses_unchanged_passages_and_reindexes_edits():
    client = CountingEmbeddingClient()
    vector_index = ArchivalVectorIndex(
        embedding_client=client,
        vector_store=LocalArchivalVectorStore(dim=3),
        config=_config(),
    )
    original = _passage("apsg_cached", "needle original")

    vector_index.index_passages([original])
    vector_index.index_passages([original])
    assert client.calls == 1

    vector_index.index_passages([_passage("apsg_cached", "edited content")])
    assert client.calls == 2
