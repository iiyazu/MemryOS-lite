from memoryos_lite.config import Settings
from memoryos_lite.schemas import Episode, Message, Role
from memoryos_lite.store import create_store


def test_episode_round_trip(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    episode = Episode(
        session_id="ses_test",
        message_id="msg_1",
        role=Role.USER,
        text="Alice moved to Shanghai.",
        index_text="[session=s1 date=2026-05-01 speaker=user] Alice moved to Shanghai.",
        benchmark_session_id="s1",
        benchmark_date="2026-05-01",
        position=3,
        source_message_ids=["msg_1"],
    )

    store.save_episode(episode)
    loaded = store.list_episodes("ses_test")

    assert len(loaded) == 1
    assert loaded[0].message_id == "msg_1"
    assert loaded[0].index_text.startswith("[session=s1")


def test_ensure_episodes_for_session_backfills_store_inserted_messages(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    msg = Message(
        id="msg_direct",
        session_id="ses_direct",
        role=Role.USER,
        content="[D1] Bob prefers tea.",
        metadata={"benchmark_session_id": "D1", "benchmark_date": "2026-05-01"},
        token_count=5,
    )
    store.add_message(msg)

    created = store.ensure_episodes_for_session("ses_direct")
    episodes = store.list_episodes("ses_direct")

    assert created == 1
    assert [episode.message_id for episode in episodes] == ["msg_direct"]
    assert episodes[0].position == 1
    assert "Bob prefers tea" in episodes[0].index_text


def test_episode_embedding_round_trip(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    episode = Episode(
        session_id="ses_embed",
        message_id="msg_embed",
        role=Role.USER,
        text="Vector source.",
        index_text="Vector source.",
        position=1,
        source_message_ids=["msg_embed"],
    )
    store.save_episode(episode)

    store.set_episode_embedding(episode.id, [0.1, 0.2, 0.3])

    assert store.get_episode_embeddings([episode.id]) == {episode.id: [0.1, 0.2, 0.3]}
