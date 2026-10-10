from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient


class BrokenEmbeddings(DeterministicEmbeddingClient):
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("model missing")


class StubLLM:
    def complete_json(self, system: str, user: str) -> dict:
        return {}


@pytest.fixture()
def client_for(tmp_path: Path):
    def make(embeddings=None, curate_llm=None) -> TestClient:
        service = MemoryOSService(
            settings=Settings(data_dir=tmp_path / ".memoryos"),
            embedding_client=embeddings,
            curate_llm=curate_llm,
        )
        app.dependency_overrides[get_service] = lambda: service
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


ITEMS = [
    {"id": "E9", "text": "Amounts are Decimal strings"},
    {"id": "E3", "text": "Amounts are Decimal strings"},
    {"id": "E5", "text": "Review objections go to the topic owner"},
    {"id": "E1", "text": "Amounts are Decimal strings"},
]


def _body(**overrides):
    body = {"schema": "memoryos_similar/v1", "items": ITEMS, "threshold": 0.88}
    body.update(overrides)
    return body


def test_similar_lists_pairs_ordered_and_deterministic(client_for):
    client = client_for(DeterministicEmbeddingClient())
    first = client.post("/similar", json=_body())
    assert first.status_code == 200
    assert first.content == client.post("/similar", json=_body()).content
    payload = first.json()
    assert payload["schema"] == "memoryos_similar/v1"
    assert payload["diagnostics"] == {"dense": True}
    assert payload["pairs"] == [
        {"a": "E1", "b": "E3", "score": 1.0},
        {"a": "E1", "b": "E9", "score": 1.0},
        {"a": "E3", "b": "E9", "score": 1.0},
    ]


def test_similar_threshold_and_small_inputs(client_for):
    client = client_for(DeterministicEmbeddingClient())
    assert client.post("/similar", json=_body(items=ITEMS[:1])).json()["pairs"] == []
    assert client.post("/similar", json=_body(items=[])).json()["pairs"] == []
    exact_only = client.post("/similar", json=_body(threshold=1.0)).json()["pairs"]
    assert len(exact_only) == 3


@pytest.mark.parametrize("embeddings", [None, BrokenEmbeddings()])
def test_similar_without_dense_is_503(client_for, embeddings):
    response = client_for(embeddings).post("/similar", json=_body())
    assert response.status_code == 503
    assert response.json() == {"detail": "similar_unavailable"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema": "memoryos_similar/v2"},
        {"threshold": 0},
        {"threshold": 1.5},
        {"items": [{"id": "E1", "text": "a"}, {"id": "E1", "text": "b"}]},
        {"items": [{"id": f"E{i}", "text": "x"} for i in range(501)]},
    ],
)
def test_similar_rejects_invalid_requests(client_for, overrides):
    response = client_for(DeterministicEmbeddingClient()).post("/similar", json=_body(**overrides))
    assert response.status_code == 422


def test_health_capabilities_follow_what_can_run(client_for):
    bare = client_for().get("/health").json()
    assert bare["version"] == "0.5.0"
    assert "recall" in bare["capabilities"]
    assert "similar" not in bare["capabilities"]
    full = client_for(DeterministicEmbeddingClient(), StubLLM()).get("/health").json()
    assert full["capabilities"] == ["curate", "curate.collab", "recall", "similar"]
