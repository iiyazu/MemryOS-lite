from unittest.mock import patch

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.archival_vector import LocalArchivalVectorStore
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.schemas import (
    MemoryItem,
    MemoryItemType,
    MessageCreate,
    Role,
)
from memoryos_lite.store import create_store


def test_v3_build_context_trace_includes_component_accounting_and_final_context_trace(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos", memoryos_memory_arch="v3")
    service = MemoryOSService(settings=settings)
    session = service.create_session("v3-accounting")
    service.ingest(
        session.id,
        MessageCreate(role=Role.USER, content="Carol's benchmark marker is MemoryOS Lite."),
    )

    context = service.build_context(session.id, "What is Carol's benchmark marker?", budget=120)

    assert context.metadata["v3_component_accounting"]
    assert context.metadata["v3_final_context_trace"]
    assert context.metadata["v3_component_token_totals"]["recall"] > 0
    assert context.metadata["v3_component_drop_counts"]["recall"] == 0
    context_built = service.store.list_traces(session.id)[-1]
    assert (
        context_built.payload["v3_component_accounting"]
        == context.metadata["v3_component_accounting"]
    )
    assert (
        context_built.payload["v3_final_context_trace"]
        == context.metadata["v3_final_context_trace"]
    )


def test_recall_pipeline_defaults_to_v2(tmp_path, monkeypatch):
    from memoryos_lite.config import Settings
    from memoryos_lite.engine import MemoryOSService

    monkeypatch.delenv("MEMORYOS_RECALL_PIPELINE", raising=False)
    settings = Settings(data_dir=tmp_path / ".memoryos")
    service = MemoryOSService(settings=settings)
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="事实 A"))

    assert service.settings.memoryos_recall_pipeline == "v2"


def test_fastembed_provider_falls_back_to_no_embedding_when_unavailable(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_embedding_provider="fastembed",
    )
    store = create_store(settings)
    store.reset()

    with patch(
        "memoryos_lite.retrieval.providers.fastembed_client.FastEmbedClient",
        side_effect=RuntimeError("model unavailable"),
    ):
        service = MemoryOSService(store=store, settings=settings)

    assert service.embedding_client is None


def test_service_uses_local_archival_vectors_without_qdrant(tmp_path):
    service = MemoryOSService(
        settings=Settings(
            data_dir=tmp_path / ".memoryos",
            memoryos_archival_vector_enabled=True,
        ),
        embedding_client=DeterministicEmbeddingClient(),
    )

    vector_index = service.v3_context_composer.archival_searcher.vector_index
    assert vector_index is not None
    assert isinstance(vector_index.vector_store, LocalArchivalVectorStore)


# ---------------------------------------------------------------------------
# Error recovery mechanisms (evbundle_6ef398723414454ba7212973e08e05f5)
# Tests: retry logic, graceful degradation, state preservation under failure.
# ---------------------------------------------------------------------------


def test_v3_context_composer_retry_then_degrades_to_recall_pipeline(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_memory_arch="v3",
        memoryos_recovery_max_attempts=2,
        memoryos_recovery_initial_delay_s=0,
    )
    store = create_store(settings)
    store.reset()
    service = MemoryOSService(store=store, settings=settings)
    service.recovery._sleep = lambda _delay: None
    session = service.create_session("v3-recovery")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Alice lives in Shanghai."))

    with patch.object(
        service.v3_context_composer,
        "build",
        side_effect=TimeoutError("temporary composer outage"),
    ):
        context = service.build_context(session.id, "Where does Alice live?", budget=200)

    assert context.session_id == session.id
    traces = service.store.list_traces(session.id)
    recovery_events = [t for t in traces if t.event_type == "recovery_event"]
    assert any(t.payload["kind"] == "retry_scheduled" for t in recovery_events)
    assert any(t.event_type == "context_degraded" for t in traces)


def test_store_allows_embeddings_from_different_providers(service):
    session = service.create_session("mixed-embedding-dims")
    first = MemoryItem(
        page_id="page_test",
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="OpenAI sized vector",
        source_message_ids=["msg_001"],
    )
    second = MemoryItem(
        page_id="page_test",
        session_id=session.id,
        item_type=MemoryItemType.KNOWLEDGE,
        content="fastembed sized vector",
        source_message_ids=["msg_002"],
    )
    service.store.save_items([first, second])

    service.store.set_item_embedding(first.id, [0.1] * 1536)
    service.store.set_item_embedding(second.id, [0.2] * 384)

    embeddings = service.store.get_item_embeddings([first.id, second.id])
    assert len(embeddings[first.id]) == 1536
    assert len(embeddings[second.id]) == 384
