import pytest

from memoryos_lite.retrieval.archival_vector import (
    ArchivalEmbeddingConfig,
    ArchivalVectorIndex,
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
