from memoryos_lite.retrieval.evidence_representer import EvidenceRepresenter
from memoryos_lite.schemas import MemoryPage, Message, Role


def _msg(content, role=Role.USER, msg_id="m1", session_id="s1"):
    return Message(id=msg_id, session_id=session_id, role=role, content=content)


def _page(title="Test Page", summary="A summary of events"):
    return MemoryPage(
        id="p1",
        session_id="s1",
        title=title,
        summary=summary,
        source_message_ids=["m1", "m2", "m3"],
    )


def test_raw_strategy():
    r = EvidenceRepresenter(strategy="raw")
    msg = _msg("She is single now.", msg_id="m2")
    c = r.build_candidate(msg, neighbors_before=[], neighbors_after=[], session_id="s1")
    assert c.index_text == "She is single now."
    assert c.original_text == "She is single now."
    assert c.message_id == "m2"


def test_deterministic_context():
    r = EvidenceRepresenter(strategy="deterministic_context")
    msg = _msg("She is single now.", msg_id="m2")
    prev = [_msg("What is Caroline's relationship status?", msg_id="m1")]
    c = r.build_candidate(msg, neighbors_before=prev, neighbors_after=[], session_id="conv-1")
    assert "session=conv-1" in c.index_text
    assert "Caroline" in c.index_text
    assert "She is single now." in c.index_text
    assert c.original_text == "She is single now."


def test_page_context_plus_raw():
    r = EvidenceRepresenter(strategy="page_context_plus_raw")
    msg = _msg("She is single now.", msg_id="m2")
    page = _page(title="Relationships", summary="Caroline discusses her personal life")
    c = r.build_candidate(msg, neighbors_before=[], neighbors_after=[], session_id="s1", page=page)
    assert "Relationships" in c.index_text
    assert "Caroline discusses" in c.index_text
    assert "She is single now." in c.index_text
    assert c.original_text == "She is single now."


def test_truncates_long_neighbors():
    r = EvidenceRepresenter(strategy="deterministic_context")
    msg = _msg("target", msg_id="m2")
    prev = [_msg("x" * 200, msg_id="m1")]
    c = r.build_candidate(msg, neighbors_before=prev, neighbors_after=[], session_id="s1")
    assert "x" * 101 not in c.index_text
    assert "x" * 100 in c.index_text


def test_display_text_equals_original():
    r = EvidenceRepresenter(strategy="deterministic_context")
    msg = _msg("original content", msg_id="m1")
    c = r.build_candidate(msg, neighbors_before=[], neighbors_after=[], session_id="s1")
    assert c.display_text == "original content"
