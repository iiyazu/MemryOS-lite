from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.archival_vector import LocalArchivalVectorStore
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.schemas import (
    MessageCreate,
    Role,
)
from memoryos_lite.store import create_store


def test_v3_build_context_trace_includes_component_accounting_and_final_context_trace(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path / ".memoryos")
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
# Failures are not degraded inside the service: build-context answers a plain
# 500 (no exception text) and the next request is unaffected.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "method"),
    [
        ("v3_context_composer", "build"),
        ("recall_pipeline", "build_context"),
        ("store", "list_episodes"),
    ],
)
def test_build_context_failure_is_a_plain_500_and_leaves_no_state(tmp_path, target, method):
    service = MemoryOSService(settings=Settings(data_dir=tmp_path / ".memoryos"))
    session = service.create_session("fault-injection")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="Alice lives in Shanghai."))
    request = {"task": "Where does Alice live?", "budget": 200}
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    try:
        with patch.object(
            getattr(service, target), method, side_effect=RuntimeError("secret /data/path")
        ):
            failed = client.post(f"/sessions/{session.id}/build-context", json=request)
        recovered = client.post(f"/sessions/{session.id}/build-context", json=request)
    finally:
        app.dependency_overrides.clear()

    assert failed.status_code == 500
    assert "secret" not in failed.text
    assert recovered.status_code == 200
    assert "Shanghai" in str(recovered.json()["retrieved_evidence"])
