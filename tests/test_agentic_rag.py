"""Superseded-source demotion and the agentic ask graph."""

from __future__ import annotations

from typing import Any

from memoryos_eval.ask import (
    AskRequest,
    ask_with,
    build_ask_graph,
    coverage,
    render_ask_item,
    run_ask,
)
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.supersede import (
    SupersededQuote,
    demote_superseded,
    match_superseded,
    superseded_quotes,
)
from memoryos_lite.schemas import MessageCreate, Role
from memoryos_lite.source_evidence import build_source_evidence
from memoryos_lite.store_curator import CuratedMemoryWrite

OLD = "Decision: Helios launches in Porto next spring."
NEW = "Update: Helios now launches in Lisbon, Porto is off."


def _service(tmp_path, **overrides: Any) -> MemoryOSService:
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        openai_api_key=None,
        deepseek_api_key=None,
        opencode_api_key=None,
        **overrides,
    )
    return MemoryOSService(settings=settings)


def _seed(service: MemoryOSService) -> str:
    """Two messages and a curated decision whose old version is superseded."""

    session = service.create_session("helios")
    old_id = service.ingest(session.id, MessageCreate(role=Role.USER, content=OLD)).message.id
    new_id = service.ingest(session.id, MessageCreate(role=Role.USER, content=NEW)).message.id
    (old_row,) = service.store.apply_curator_window(
        session_id=session.id,
        run_id="r1",
        model="test",
        last_message_seq=1,
        writes=[
            CuratedMemoryWrite(
                kind="decision",
                topic_key="helios.launch_city",
                statement="Helios launches in Porto.",
                sources=[{"message_id": old_id, "quote": "Helios launches in Porto"}],
                version=1,
            )
        ],
    )
    service.store.apply_curator_window(
        session_id=session.id,
        run_id="r2",
        model="test",
        last_message_seq=2,
        writes=[
            CuratedMemoryWrite(
                kind="decision",
                topic_key="helios.launch_city",
                statement="Helios launches in Lisbon.",
                sources=[{"message_id": new_id, "quote": "Helios now launches in Lisbon"}],
                version=2,
                supersedes_id=old_row.id,
            )
        ],
    )
    return session.id


def test_marks_come_from_quotes_that_only_ground_superseded_memories(tmp_path):
    service = _service(tmp_path)
    session_id = _seed(service)

    (mark,) = service.superseded_marks(session_id)

    assert mark == SupersededQuote(
        quote="Helios launches in Porto", current="Helios launches in Lisbon."
    )
    assert match_superseded("note: HELIOS launches   in porto!", [mark]) == mark
    assert match_superseded(NEW, [mark]) is None


def test_quotes_shared_with_an_active_memory_are_not_marked(tmp_path):
    service = _service(tmp_path)
    session_id = _seed(service)
    rows = service.store.list_curated_memories(session_id)
    active = next(row for row in rows if row.status == "active")
    widened = [
        row
        if row.status != "active"
        else type(row)(**{**row.__dict__, "sources": [*row.sources, *rows[0].sources]})
        for row in rows
    ]
    assert active is not None
    assert superseded_quotes(widened) == []


def test_demotion_moves_outdated_items_behind_current_ones():
    marks = [SupersededQuote(quote="launches in Porto")]
    items = [{"text": OLD}, {"text": NEW}, {"text": "unrelated"}]
    assert [i["text"] for i in demote_superseded(items, lambda i: i["text"], marks)] == [
        NEW,
        "unrelated",
        OLD,
    ]
    assert demote_superseded(items, lambda i: i["text"], []) == items


def test_v2_envelope_ranks_the_superseded_message_last(tmp_path):
    service = _service(tmp_path)
    session_id = _seed(service)
    package = service.build_context(
        session_id=session_id, task="launch city", retrieval_query="Where does Helios launch?"
    )
    plain = build_source_evidence(package, schema_version="v2")
    demoted = build_source_evidence(
        package, schema_version="v2", superseded=service.superseded_marks(session_id)
    )

    def texts(envelope: dict[str, Any]) -> list[str]:
        return [item["text"] for item in envelope["items"]]  # type: ignore[index]

    assert sorted(texts(plain)) == sorted(texts(demoted))
    outdated = [i for i, text in enumerate(texts(demoted)) if "Porto next spring" in text]
    current = [i for i, text in enumerate(texts(demoted)) if "now launches in Lisbon" in text]
    assert outdated and current and max(current) < min(outdated)


class RewriteLLM:
    def __init__(self, *queries: str) -> None:
        self.queries = list(queries)
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        assert "[outdated]" in user
        return {"query": self.queries.pop(0)}


def _item(item_id: str, text: str) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "layer": "recall",
        "text": text,
        "estimated_tokens": 20,
        "source_refs": [{"source_type": "message", "source_id": item_id, "session_id": "s"}],
    }


def test_ask_rewrites_when_only_outdated_evidence_matches():
    marks = [SupersededQuote(quote="launches in Porto", current="Helios launches in Lisbon.")]
    corpus = {
        "Which city does Helios launch in?": [_item("m1", OLD)],
        "Helios launch city Lisbon": [_item("m2", NEW), _item("m1", OLD)],
    }
    llm = RewriteLLM("Helios launch city Lisbon")

    response = run_ask(
        session_id="s",
        request=AskRequest(question="Which city does Helios launch in?"),
        retrieve=lambda query: corpus.get(query, []),
        marks=marks,
        llm=llm,
    )

    assert response.queries == ["Which city does Helios launch in?", "Helios launch city Lisbon"]
    assert [(i.item_id, i.outdated) for i in response.items] == [("m2", False), ("m1", True)]
    assert response.items[1].current == "Helios launches in Lisbon."
    assert render_ask_item(response.items[1]).startswith(
        "[outdated; current: Helios launches in Lisbon.]"
    )
    assert (response.diagnostics.retrievals, response.diagnostics.llm_calls) == (2, 1)
    assert response.diagnostics.stopped == "enough"


def test_ask_stops_without_llm_or_when_rounds_run_out():
    marks = [SupersededQuote(quote="launches in Porto")]
    request = AskRequest(question="Which city does Helios launch in?", max_rounds=1)
    only_old = lambda query: [_item("m1", OLD)]  # noqa: E731

    no_llm = run_ask(session_id="s", request=request, retrieve=only_old, marks=marks, llm=None)
    assert (no_llm.diagnostics.retrievals, no_llm.diagnostics.stopped) == (1, "no_llm")

    capped = run_ask(
        session_id="s",
        request=request,
        retrieve=only_old,
        marks=marks,
        llm=RewriteLLM("Helios city", "never used"),
    )
    assert (capped.diagnostics.retrievals, capped.diagnostics.stopped) == (2, "no_rounds")


def test_coverage_ignores_stopwords_and_handles_cjk():
    # helios + launch(es) match; "city" names the answer type and never appears.
    assert coverage("Which city does Helios launch in?", NEW) == 2 / 3
    assert coverage("Which city does Helios launch in?", "Porto weather is mild") == 0
    assert coverage("Helios 在哪个城市发布？", "Helios 将在里斯本城市发布") > 0.5
    graph = build_ask_graph(lambda q: [], [], None, max_rounds=0).get_graph().draw_mermaid()
    for node in ("retrieve", "grade", "rewrite", "finalize"):
        assert node in graph


def test_ask_with_marks_the_session_outdated_item(tmp_path):
    service = _service(tmp_path)
    session_id = _seed(service)

    response = ask_with(
        service,
        session_id,
        AskRequest(question="Which city does Helios launch in?", max_rounds=0),
        llm=None,
        marks=service.superseded_marks(session_id),
    )

    assert response.schema_version == "memoryos_memory_ask/v1"
    flags = {item.text: item.outdated for item in response.items}
    assert flags.get(OLD) is True and flags.get(NEW) is False


def test_host_marks_rank_the_superseded_message_last(tmp_path):
    service = _service(tmp_path)
    session_id = _seed(service)
    package = service.build_context(
        session_id, "launch", retrieval_query="Where does Helios launch?"
    )
    envelope = build_source_evidence(
        package, schema_version="v2", superseded=service.superseded_marks(session_id)
    )

    texts = [item["text"] for item in envelope["items"]]
    assert texts.index(NEW) < texts.index(OLD)
