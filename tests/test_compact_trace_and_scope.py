import json

from memoryos_lite.config import Settings
from memoryos_lite.schemas import TraceEvent
from memoryos_lite.store import create_store
from memoryos_lite.v3_contracts import (
    ArchivalPassage,
    ArchiveAttachment,
    ArchiveEligibilityScope,
    SourceRef,
)


def _ref(source_id: str = "message_1") -> SourceRef:
    return SourceRef(source_type="message", source_id=source_id, session_id="session_1")


def test_scope_filter_uses_sql_queries_without_loading_unscoped_archive(tmp_path, monkeypatch):
    store = create_store(Settings(data_dir=tmp_path / "data"))
    store.create_archive_attachment(
        ArchiveAttachment(
            id="attachment_1",
            archive_id="archive_allowed",
            scope_type="session",
            scope_id="session_1",
            source_refs=[_ref()],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="passage_allowed",
            archive_id="archive_allowed",
            text="allowed",
            source_refs=[_ref()],
        )
    )
    store.create_archival_passage(
        ArchivalPassage(
            id="passage_excluded",
            archive_id="archive_other",
            text="excluded",
            source_refs=[_ref()],
        )
    )
    monkeypatch.setattr(
        store,
        "list_archival_passages",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full scan")),
    )

    result = store.list_archival_passages_for_scope(ArchiveEligibilityScope(session_id="session_1"))

    assert [passage.id for passage in result.eligible_passages] == ["passage_allowed"]
    assert result.scope_excluded_passage_ids == ["passage_excluded"]


def test_compact_trace_is_bounded_and_does_not_write_jsonl(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", memoryos_trace_mode="compact")
    store = create_store(settings)
    event = TraceEvent(
        session_id="session_1",
        event_type="context_built",
        payload={
            "stage": "retrieval",
            "prompt": "do not persist this",
            "selected_count": 3,
            "source_ids": ["source_1", "source_2"],
        },
    )
    store.add_trace(event)

    traces = store.list_traces("session_1")
    payload = traces[0].payload
    assert payload["schema"] == "memoryos_trace_compact/v1"
    assert payload["stage"] == "retrieval"
    assert payload["counts"] == {"selected_count": 3, "source_ids_count": 2}
    assert payload["digest"]
    assert "prompt" not in json.dumps(payload)
    assert not list((tmp_path / "data" / "traces").glob("*.jsonl"))


def test_compact_trace_caps_count_fields(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", memoryos_trace_mode="compact")
    store = create_store(settings)
    store.add_trace(
        TraceEvent(
            session_id="session_1",
            event_type="large_payload",
            payload={f"metric_{index}_count": index for index in range(200)},
        )
    )

    payload = store.list_traces("session_1")[0].payload
    assert len(payload["counts"]) <= 64
    assert len(json.dumps(payload, ensure_ascii=False)) < 8 * 1024
