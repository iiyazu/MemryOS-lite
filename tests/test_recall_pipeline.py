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
    assert package.metadata["episode_candidate_message_ids"] == ["msg_bob"]


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
    assert package.metadata["episode_candidate_message_ids"] == ["msg_bob"]
    assert package.metadata["planned_evidence_message_ids"] == []


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
    assert package.metadata["budget_dropped_relevant"] == 1
    assert package.metadata["episode_candidate_message_ids"] == ["msg_bob"]
    assert package.metadata["planned_evidence_message_ids"] == []


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
