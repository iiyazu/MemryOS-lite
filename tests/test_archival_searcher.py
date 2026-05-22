from memoryos_lite.retrieval.archival_searcher import ArchivalPassageSearcher
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
