from memoryos_lite.config import Settings
from memoryos_lite.retrieval.recall_pipeline import RecallPipeline
from memoryos_lite.schemas import Message, Role
from memoryos_lite.store import create_store


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
