from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import Message, MessageCreate, Role
from memoryos_lite.store import create_store


class WordTokenizer:
    def count(self, text: str) -> int:
        return len(text.split())


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
    assert package.metadata["recall_candidate_message_ids"] == ["msg_bob"]
    assert package.metadata["episode_candidate_message_ids"] == ["msg_bob"]
    assert package.metadata["recall_planned_message_ids"] == ["msg_bob"]
    assert package.metadata["planned_evidence_message_ids"] == ["msg_bob"]
    assert package.metadata["recall_indexed_source_ids"] == ["msg_bob"]
    assert package.metadata["indexed_source_ids"] == ["msg_bob"]
    assert package.metadata["recall_budget_dropped"] == 0
    assert package.metadata["budget_dropped_relevant"] == 0
    assert package.metadata["recall_diagnostics"]


def test_recall_pipeline_truncates_when_task_exceeds_budget(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    msg = Message(
        id="msg_bob",
        session_id="ses",
        role=Role.USER,
        content="Bob moved to Shanghai.",
        metadata={},
        token_count=4,
    )
    store.add_message(msg)

    pipeline = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    )
    package = pipeline.build_context(
        session_id="ses",
        task="Where did Bob move?",
        budget=3,
    )

    assert package.task_truncated is True
    assert package.estimated_tokens == 4
    assert package.retrieved_evidence == []
    assert package.metadata["recall_candidate_message_ids"] == ["msg_bob"]
    assert package.metadata["episode_candidate_message_ids"] == ["msg_bob"]
    assert package.metadata["recall_planned_message_ids"] == []
    assert package.metadata["planned_evidence_message_ids"] == []
    assert package.metadata["recall_indexed_source_ids"] == ["msg_bob"]
    assert package.metadata["indexed_source_ids"] == ["msg_bob"]
    assert package.metadata["recall_budget_dropped"] == 1
    assert package.metadata["budget_dropped_relevant"] == 1
    assert package.metadata["recall_diagnostics"]


def test_recall_pipeline_tracks_dropped_evidence_when_evidence_exceeds_budget(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    msg = Message(
        id="msg_bob",
        session_id="ses",
        role=Role.USER,
        content="Bob moved to Shanghai.",
        metadata={},
        token_count=4,
    )
    store.add_message(msg)

    pipeline = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    )
    package = pipeline.build_context(
        session_id="ses",
        task="Bob",
        budget=3,
    )

    assert package.task_truncated is False
    assert package.retrieved_evidence == []
    assert package.candidate_budget_dropped == 1
    assert package.metadata["recall_budget_dropped"] == 1
    assert package.metadata["budget_dropped_relevant"] == 1
    assert package.metadata["recall_candidate_message_ids"] == ["msg_bob"]
    assert package.metadata["episode_candidate_message_ids"] == ["msg_bob"]
    assert package.metadata["recall_planned_message_ids"] == []
    assert package.metadata["planned_evidence_message_ids"] == []
    assert package.metadata["recall_diagnostics"]


def test_recall_pipeline_emits_session_packet_metadata(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    for message_id, session_marker, content in [
        ("d1_1", "D1", "Caroline is weighing psychology classes."),
        ("d1_2", "D1", "Caroline said counseling could help people."),
        ("d2_1", "D2", "Caroline education fields career options distractor."),
        ("d3_1", "D3", "Caroline education fields career planning distractor."),
    ]:
        store.add_message(
            Message(
                id=message_id,
                session_id="ses",
                role=Role.USER,
                content=content,
                metadata={"benchmark_session_id": session_marker},
                token_count=len(content.split()),
            )
        )

    package = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build_context(
        session_id="ses",
        task="What fields would Caroline pursue in education?",
        budget=200,
    )

    assert package.metadata["recall_evidence_packets"]
    assert "D1" in package.metadata["recall_planned_session_ids"]
    assert any(
        evidence.metadata.get("packet_session_id") == "D1"
        for evidence in package.retrieved_evidence
    )


def test_recall_pipeline_exposes_signed_packet_member_offsets(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    for message_id, content in [
        ("d1_prev", "Lena packed the notebooks."),
        ("d1_anchor", "Lena chose the target cafe."),
        ("d1_next", "She ordered jasmine tea."),
    ]:
        store.add_message(
            Message(
                id=message_id,
                session_id="ses",
                role=Role.USER,
                content=content,
                metadata={"benchmark_session_id": "D1"},
                token_count=len(content.split()),
            )
        )

    package = RecallPipeline(
        store=store,
        settings=settings,
        tokenizer=WordTokenizer(),
    ).build_context(
        session_id="ses",
        task="target cafe",
        budget=200,
    )

    expected_offsets = [
        {"message_id": "d1_prev", "neighbor_offset": -1},
        {"message_id": "d1_anchor", "neighbor_offset": 0},
        {"message_id": "d1_next", "neighbor_offset": 1},
    ]
    packet = package.metadata["recall_evidence_packets"][0]
    assert packet["packet_member_neighbor_offsets"] == expected_offsets
    anchor = next(
        evidence for evidence in package.retrieved_evidence if evidence.message_id == "d1_anchor"
    )
    assert anchor.metadata["packet_member_neighbor_offsets"] == expected_offsets


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
