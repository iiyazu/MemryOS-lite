from unittest.mock import patch

import pytest

from memoryos_eval.memory.retrieval.archival_vector import LocalArchivalVectorStore
from memoryos_eval.memory.schemas import (
    MessageCreate,
    Role,
)
from memoryos_eval.memory.service import SessionMemoryService
from memoryos_eval.memory.store import create_store
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient


def test_v3_build_context_trace_includes_component_accounting_and_final_context_trace(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    service = SessionMemoryService(settings=settings)
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


def test_fastembed_provider_falls_back_to_no_embedding_when_unavailable(tmp_path):
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        memoryos_embedding_provider="fastembed",
    )

    with patch(
        "memoryos_lite.retrieval.providers.fastembed_client.FastEmbedClient",
        side_effect=RuntimeError("model unavailable"),
    ):
        service = MemoryOSService(settings=settings)

    assert service.embedding_client is None


def test_product_service_opens_no_database(tmp_path):
    data_dir = tmp_path / ".memoryos"

    service = MemoryOSService(settings=Settings(data_dir=data_dir))

    assert not hasattr(service, "store")
    assert not data_dir.exists()


def test_session_service_owns_the_sqlite_store(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)

    service = SessionMemoryService(store=store, settings=settings)

    assert service.store is store
    assert (tmp_path / ".memoryos" / "memoryos.db").exists()


def test_service_uses_local_archival_vectors_without_qdrant(tmp_path):
    service = SessionMemoryService(
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
# Failures are not degraded inside the engine: build_context raises, and the
# next call is unaffected (there is no breaker state).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "method"),
    [
        ("v3_context_composer", "build"),
        ("recall_pipeline", "build_context"),
        ("store", "list_episodes"),
    ],
)
def test_build_context_failure_raises_and_leaves_no_state(tmp_path, target, method):
    service = SessionMemoryService(settings=Settings(data_dir=tmp_path / ".memoryos"))
    session = service.create_session("fault-injection")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Alice lives in Shanghai."))
    with (
        patch.object(getattr(service, target), method, side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError, match="boom"),
    ):
        service.build_context(session.id, "Where does Alice live?", budget=200)

    recovered = service.build_context(session.id, "Where does Alice live?", budget=200)
    assert "Shanghai" in str(recovered.retrieved_evidence)
