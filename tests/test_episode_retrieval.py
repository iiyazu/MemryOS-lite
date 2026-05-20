from memoryos_lite.retrieval.episode_searcher import EpisodeSearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalyzer, QueryKind
from memoryos_lite.schemas import Episode, Role


def test_query_analyzer_detects_assistant_source():
    result = QueryAnalyzer().analyze("What did you recommend last time?")
    assert result.kind == QueryKind.ASSISTANT_SOURCE


def test_episode_searcher_finds_exact_episode():
    episodes = [
        Episode(
            session_id="s",
            message_id="m1",
            role=Role.USER,
            text="Alice likes coffee.",
            index_text="[speaker=user] Alice likes coffee.",
            position=1,
            source_message_ids=["m1"],
        ),
        Episode(
            session_id="s",
            message_id="m2",
            role=Role.USER,
            text="Bob moved to Shanghai.",
            index_text="[speaker=user] Bob moved to Shanghai.",
            position=2,
            source_message_ids=["m2"],
        ),
    ]

    hits = EpisodeSearcher().search(episodes, "Where did Bob move?", top_k=1)

    assert hits[0].episode.message_id == "m2"
    assert hits[0].source == "episode_bm25"


def test_episode_searcher_returns_empty_when_no_tokens_overlap():
    episodes = [
        Episode(
            session_id="s",
            message_id="m1",
            role=Role.USER,
            text="Alice likes coffee.",
            index_text="[speaker=user] Alice likes coffee.",
            position=1,
            source_message_ids=["m1"],
        ),
    ]

    hits = EpisodeSearcher().search(episodes, "Where did Bob move?", top_k=1)

    assert hits == []


def test_episode_searcher_returns_empty_for_stopword_only_overlap():
    episodes = [
        Episode(
            session_id="s",
            message_id="m1",
            role=Role.USER,
            text="Alice moved to Shanghai.",
            index_text="[speaker=user] Alice moved to Shanghai.",
            position=1,
            source_message_ids=["m1"],
        ),
    ]

    hits = EpisodeSearcher().search(episodes, "to the and", top_k=1)

    assert hits == []
