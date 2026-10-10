from memoryos_eval.memory.store import create_store
from memoryos_eval.memory.v3_contracts import (
    ArchivalPassage,
    ArchiveAttachment,
    ArchiveEligibilityScope,
    SourceRef,
)
from memoryos_lite.config import Settings


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
