from memoryos_lite.retrieval.episode_searcher import EpisodeSearcher, RecallMemorySearcher
from memoryos_lite.retrieval.query_analyzer import QueryAnalyzer, QueryKind
from memoryos_lite.schemas import Episode, Role
from memoryos_lite.v3_contracts import RecallMemoryEntry


def _recall_entry(
    message_id: str,
    text: str,
    position: int,
    role: Role = Role.USER,
    session_id: str = "ses",
    entry_id: str | None = None,
) -> RecallMemoryEntry:
    return RecallMemoryEntry(
        id=entry_id or f"rec_{message_id}",
        session_id=session_id,
        message_id=message_id,
        role=role,
        text=text,
        index_text=f"[speaker={role.value}] {text}",
        position=position,
        source_message_ids=[message_id],
        temporal_scope={},
    )


def test_retrieval_package_imports_without_optional_providers():
    import memoryos_lite.retrieval  # noqa: F401


def test_engine_imports_without_optional_retrieval_providers():
    import memoryos_lite.engine  # noqa: F401


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


def test_recall_searcher_returns_structured_direct_hit_diagnostics():
    entries = [
        _recall_entry("msg_1", "Alice likes coffee.", 1),
        _recall_entry("msg_2", "Bob moved to Shanghai.", 2),
    ]

    hits = RecallMemorySearcher().search(entries, "Where did Bob move?", top_k=1)

    assert hits[0].episode.message_id == "msg_2"
    assert hits[0].source == "recall_memory"
    assert hits[0].rank_features["token_overlap"] > 0
    assert {event.reason_code for event in hits[0].diagnostics} >= {
        "direct_hit",
        "rank",
    }


def test_recall_searcher_expands_neighbors_and_dedupes_message_ids():
    entries = [
        _recall_entry("msg_1", "Project kickoff notes.", 1),
        _recall_entry("msg_2", "The deployment target is Osaka.", 2),
        _recall_entry("msg_3", "The team confirmed the rollout window.", 3),
        _recall_entry("msg_2", "The deployment status is Osaka.", 4, entry_id="rec_msg_2_dup"),
    ]

    hits = RecallMemorySearcher().search(entries, "deployment target", top_k=4)

    assert [hit.episode.message_id for hit in hits] == ["msg_2", "msg_1", "msg_3"]
    assert len({hit.episode.message_id for hit in hits}) == 3
    neighbor_hits = [
        hit for hit in hits if any(event.reason_code == "neighbor" for event in hit.diagnostics)
    ]
    assert [hit.episode.message_id for hit in neighbor_hits] == ["msg_1", "msg_3"]
    assert any(event.reason_code == "dedupe" for hit in hits for event in hit.diagnostics)


def test_recall_searcher_prioritizes_direct_hits_before_neighbors():
    entries = [
        _recall_entry("msg_1", "Unrelated setup.", 1),
        _recall_entry("msg_2", "Alpha target detail.", 2),
        _recall_entry("msg_3", "Unrelated bridge.", 3),
        _recall_entry("msg_4", "Beta target detail.", 4),
        _recall_entry("msg_5", "Gamma target detail.", 5),
    ]

    hits = RecallMemorySearcher().search(entries, "target detail", top_k=2)

    assert [hit.episode.message_id for hit in hits] == ["msg_2", "msg_4"]
    assert all(hit.neighbor_of is None for hit in hits)


def test_recall_searcher_session_diversity_keeps_weak_same_session_anchor():
    entries = [
        _recall_entry(
            "d1_weak",
            "Caroline started psychology classes after considering her education.",
            1,
        ),
        _recall_entry("d2_strong", "Caroline education fields pursue career research.", 2),
        _recall_entry("d3_strong", "Caroline education fields pursue career support.", 3),
        _recall_entry("d4_strong", "Caroline education fields pursue career planning.", 4),
        _recall_entry("d5_strong", "Caroline education fields pursue career options.", 5),
    ]
    for index, entry in enumerate(entries, start=1):
        entry.temporal_scope["benchmark_session_id"] = f"D{index}"

    hits = RecallMemorySearcher().search(
        entries,
        "What fields would Caroline pursue in her education?",
        top_k=3,
        preserve_neighbors=True,
    )

    assert "d1_weak" in [hit.episode.message_id for hit in hits]
    weak_hit = next(hit for hit in hits if hit.episode.message_id == "d1_weak")
    assert weak_hit.rank_features["session_diversified_anchor"] == 1.0
    assert weak_hit.rank_features["packet_rank"] >= 0.0


def test_recall_searcher_preserves_packet_neighbors_when_direct_hits_fill_top_k():
    entries = [
        _recall_entry("d1_anchor", "Friends support Caroline through change.", 1),
        _recall_entry("d2_anchor", "Pride friends support Caroline.", 2),
        _recall_entry("d3_anchor", "Current friends supported Caroline.", 3),
        _recall_entry("d3_answer", "She has known these friends for four years.", 4),
    ]
    for index, entry in enumerate(entries, start=1):
        entry.temporal_scope["benchmark_session_id"] = f"D{min(index, 3)}"

    hits = RecallMemorySearcher().search(
        entries,
        "How long has Caroline had her current group of friends?",
        top_k=2,
        neighbors_after=1,
        preserve_neighbors=True,
    )

    assert "d3_anchor" in [hit.episode.message_id for hit in hits]
    neighbor = next(hit for hit in hits if hit.episode.message_id == "d3_answer")
    assert neighbor.neighbor_of == "d3_anchor"
    assert neighbor.packet_metadata["packet_session_id"] == "D3"


def test_recall_searcher_records_signed_packet_member_offsets():
    entries = [
        _recall_entry("d1_prev", "Lena packed the notebooks.", 1),
        _recall_entry("d1_anchor", "Lena chose the target cafe.", 2),
        _recall_entry("d1_next", "She ordered jasmine tea.", 3),
    ]
    for entry in entries:
        entry.temporal_scope["benchmark_session_id"] = "D1"

    hits = RecallMemorySearcher().search(
        entries,
        "target cafe",
        top_k=1,
        neighbors_before=1,
        neighbors_after=1,
        preserve_neighbors=True,
    )

    anchor = next(hit for hit in hits if hit.episode.message_id == "d1_anchor")
    assert anchor.packet_metadata["packet_member_neighbor_offsets"] == [
        {"message_id": "d1_prev", "neighbor_offset": -1},
        {"message_id": "d1_anchor", "neighbor_offset": 0},
        {"message_id": "d1_next", "neighbor_offset": 1},
    ]


def test_recall_searcher_boosts_assistant_source_queries():
    entries = [
        _recall_entry("msg_1", "I suggest using MemoryOS Lite.", 1, role=Role.ASSISTANT),
        _recall_entry("msg_2", "I like MemoryOS Lite.", 2, role=Role.USER),
    ]

    query = "What MemoryOS Lite did you recommend last time?"
    hits = RecallMemorySearcher().search(
        entries,
        query,
        top_k=1,
        analysis=QueryAnalyzer().analyze(query),
    )

    assert hits[0].episode.message_id == "msg_1"
    assert hits[0].rank_features["role_boost"] > 0
