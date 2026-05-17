from memoryos_lite.retrieval.evidence_representer import EvidenceCandidate
from memoryos_lite.retrieval.evidence_searcher import EvidenceSearcher


def _c(msg_id, index_text, original=None):
    return EvidenceCandidate(
        message_id=msg_id, index_text=index_text,
        original_text=original or index_text, display_text=original or index_text,
    )


def test_bm25_basic():
    s = EvidenceSearcher()
    hits = s.search([
        _c("m1", "hiking in the mountains"),
        _c("m2", "weather is nice today"),
        _c("m3", "went hiking in rocky mountains last weekend"),
    ], query="hiking mountains", top_k=2)
    assert len(hits) == 2
    assert hits[0].message_id in ("m1", "m3")


def test_empty():
    s = EvidenceSearcher()
    assert s.search([], query="x", top_k=5) == []
    assert s.search([_c("m1", "text")], query="", top_k=5) == []


def test_no_match():
    s = EvidenceSearcher()
    assert s.search([_c("m1", "apples oranges")], query="quantum physics", top_k=5) == []


def test_contextual_prefix_helps():
    s = EvidenceSearcher()
    ctx_prefix = (
        "[session=s1] Previous: What is Caroline's relationship status?"
        " Current: She is single now."
    )
    hits = s.search([
        _c("m1", ctx_prefix, "She is single now."),
        _c("m2", "[session=s1] Current: The weather is great.", "The weather is great."),
    ], query="Caroline relationship status", top_k=2)
    assert hits[0].message_id == "m1"
    assert hits[0].original_text == "She is single now."


def test_dedup():
    s = EvidenceSearcher()
    hits = s.search([_c("m1", "hiking trail"), _c("m1", "hiking trail")], query="hiking", top_k=5)
    assert len(hits) == 1
