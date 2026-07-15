from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import ContextPackage, MessageCreate, Role
from memoryos_lite.source_evidence import build_source_evidence, validate_source_evidence
from memoryos_lite.store import create_store
from memoryos_lite.v3_contracts import (
    ContextLayerItem,
    ContextPackageV3,
    SourceRef,
    SourceType,
)


def _service(tmp_path, **overrides) -> MemoryOSService:
    settings = Settings(
        data_dir=tmp_path / "memoryos",
        rot_safe_budget=1_000,
        memoryos_memory_arch=overrides.pop("memoryos_memory_arch", "v1"),
        memoryos_recall_pipeline=overrides.pop("memoryos_recall_pipeline", "v1"),
        **overrides,
    )
    return MemoryOSService(store=create_store(settings), settings=settings)


def test_external_message_id_replay_and_conflict(tmp_path):
    service = _service(tmp_path)
    session = service.create_session("idempotent")
    request = MessageCreate(
        role=Role.USER,
        content="durable message",
        external_id="activity-1",
        metadata={"room": "room-1"},
    )

    first = service.ingest(session.id, request)
    replay = service.ingest(session.id, request)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.message.id == first.message.id
    assert len(service.store.list_messages(session.id)) == 1

    with pytest.raises(ValueError, match="external_id conflict"):
        service.ingest(
            session.id,
            request.model_copy(update={"content": "tampered"}),
        )


def test_external_governance_advisory_is_durable_and_idempotent(tmp_path):
    service = _service(
        tmp_path,
        memoryos_memory_arch="v3",
        memoryos_recall_pipeline="v2",
        memoryos_agent_kernel="external",
    )
    session = service.create_session("advisory")
    source_refs = [{"source_type": "message", "source_id": "msg-1", "session_id": session.id}]

    first = service.store.add_maintenance_advisory(
        session_id=session.id,
        proposal_type="archive_write",
        content="Keep the Room source proof strict.",
        source_refs=source_refs,
    )
    replay = service.store.add_maintenance_advisory(
        session_id=session.id,
        proposal_type="archive_write",
        content="Keep the Room source proof strict.",
        source_refs=source_refs,
    )

    assert replay["advisory_id"] == first["advisory_id"]
    assert service.list_external_advisories(session.id) == [first]


def test_external_message_id_concurrent_first_writers_have_stable_result(tmp_path):
    service = _service(tmp_path)
    session = service.create_session("concurrent-idempotency")
    request = MessageCreate(
        role=Role.ASSISTANT,
        content="one durable result",
        external_id="activity-race",
    )

    def ingest_once():
        return service.ingest(session.id, request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: ingest_once(), range(2)))

    assert sorted(result.replayed for result in results) == [False, True]
    assert len(service.store.list_messages(session.id)) == 1


def test_external_message_replay_repairs_index_after_post_commit_failure(tmp_path, monkeypatch):
    service = _service(tmp_path, memoryos_recall_pipeline="v2")
    session = service.create_session("recover-derived-index")
    request = MessageCreate(
        role=Role.USER,
        content="durable before derived indexing",
        external_id="activity-recover-index",
    )
    original_ensure = service.store.ensure_episodes_for_session
    calls = 0

    def fail_once(session_id: str) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("simulated derived index crash")
        return original_ensure(session_id)

    monkeypatch.setattr(service.store, "ensure_episodes_for_session", fail_once)
    with pytest.raises(RuntimeError, match="simulated derived index crash"):
        service.ingest(session.id, request)

    # The message transaction committed before the derived index failed.  A
    # replay of the same external id must repair the missing episode instead
    # of returning replay=True while leaving recall incomplete.
    assert len(service.store.list_messages(session.id)) == 1
    assert service.store.list_episodes(session.id) == []
    replay = service.ingest(session.id, request)
    assert replay.replayed is True
    assert len(service.store.list_episodes(session.id)) == 1


def test_source_evidence_v2_projects_recall_and_archival_with_proof():
    context = ContextPackageV3(
        session_id="session-1",
        task="recall",
        items=[
            ContextLayerItem(
                layer="recall",
                item_id="message-1",
                text="A recalled decision",
                estimated_tokens=3,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.MESSAGE,
                        source_id="message-1",
                        session_id="session-1",
                    )
                ],
                metadata={"score": 0.8},
            ),
            ContextLayerItem(
                layer="archival",
                item_id="passage-1",
                text="An exact archive passage",
                estimated_tokens=4,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.DOCUMENT,
                        source_id="document-1",
                    )
                ],
                metadata={
                    "archive_id": "archive-1",
                    "document_id": "xmuse-room-memory-candidate-c-1",
                    "score": 0.7,
                },
            ),
        ],
    )
    package = ContextPackage(
        session_id="session-1",
        task="recall",
        metadata={"v3_context": context.model_dump(mode="json")},
    )

    payload = build_source_evidence(package, schema_version="v2")

    assert payload["schema"] == "memoryos_source_evidence/v2"
    assert [item["layer"] for item in payload["items"]] == ["recall", "archival"]
    assert payload["items"][0]["derived"] is True
    assert payload["items"][0]["source_complete"] is True
    assert payload["items"][1]["document_id"] == "xmuse-room-memory-candidate-c-1"
    assert validate_source_evidence(payload) == payload


def test_source_evidence_v2_keeps_archival_proof_when_recall_fills_window():
    recall_items = [
        ContextLayerItem(
            layer="recall",
            item_id=f"message-{index}",
            text=f"derived recall {index}",
            estimated_tokens=2,
            source_refs=[
                SourceRef(
                    source_type=SourceType.MESSAGE,
                    source_id=f"message-{index}",
                    session_id="session-1",
                )
            ],
            metadata={"score": 0.8},
        )
        for index in range(10)
    ]
    archival = [
        ContextLayerItem(
            layer="archival",
            item_id=f"passage-proof-{index}",
            text=f"An exact cross-scope archive passage {index}",
            estimated_tokens=5,
            source_refs=[
                SourceRef(
                    source_type=SourceType.DOCUMENT,
                    source_id=f"document-proof-{index}",
                )
            ],
            metadata={
                "archive_id": f"archive-proof-{index}",
                "document_id": f"xmuse-room-memory-candidate-proof-{index}",
                "score": 0.7,
            },
        )
        for index in range(2)
    ]
    package = ContextPackage(
        session_id="session-1",
        task="recall",
        metadata={
            "v3_context": ContextPackageV3(
                session_id="session-1",
                task="recall",
                items=[*recall_items, *archival],
            ).model_dump(mode="json")
        },
    )

    payload = build_source_evidence(package, schema_version="v2")

    assert len(payload["items"]) == 8
    assert [item["layer"] for item in payload["items"][-2:]] == ["archival", "archival"]
    assert [item["document_id"] for item in payload["items"][-2:]] == [
        "xmuse-room-memory-candidate-proof-0",
        "xmuse-room-memory-candidate-proof-1",
    ]


def test_source_evidence_v2_omits_archival_items_without_document_identity():
    context = ContextPackageV3(
        session_id="session-1",
        task="recall",
        items=[
            ContextLayerItem(
                layer="archival",
                item_id="passage-1",
                text="unproved archive passage",
                estimated_tokens=3,
                source_refs=[SourceRef(source_type=SourceType.DOCUMENT, source_id="activity-1")],
                metadata={"score": 0.7},
            )
        ],
    )
    package = ContextPackage(
        session_id="session-1",
        task="recall",
        metadata={"v3_context": context.model_dump(mode="json")},
    )

    payload = build_source_evidence(package, schema_version="v2")

    assert payload["items"] == []
    assert payload["omitted_count"] == 1


def test_external_kernel_mode_is_advisory_only(tmp_path):
    service = _service(
        tmp_path,
        memoryos_memory_arch="v3",
        memoryos_recall_pipeline="v2",
        memoryos_agent_kernel="external",
    )

    assert service.agent_kernel is None
    assert service.kernel_maintenance_executor is None
    assert service.kernel_maintenance_analyzer is not None
