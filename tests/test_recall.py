from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.recall import RECENCY_MAX, ROLE_BONUS, THREAD_BONUS, RecallRequest
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient
from memoryos_lite.tokenizer import TokenEstimator


class CountingEmbeddings(DeterministicEmbeddingClient):
    def __init__(self) -> None:
        self.embedded: list[str] = []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return super().embed_batch(texts)


class BrokenEmbeddings(DeterministicEmbeddingClient):
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("model missing")


def _service(tmp_path: Path, embeddings=None) -> MemoryOSService:
    return MemoryOSService(
        settings=Settings(data_dir=tmp_path / ".memoryos"), embedding_client=embeddings
    )


@pytest.fixture()
def client_for(tmp_path: Path):
    def make(embeddings=None) -> TestClient:
        service = _service(tmp_path, embeddings)
        app.dependency_overrides[get_service] = lambda: service
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


ITEMS = [
    {
        "id": "E1",
        "text": "接口金额一律用 Decimal 字符串传递",
        "kind": "decision",
        "thread_id": "task",
        "roles": ["impl"],
        "seq": 57,
    },
    {"id": "E2", "text": "Amounts in the payment API are Decimal strings", "seq": 40},
    {
        "id": "E3",
        "text": "Review objections go to the topic owner",
        "thread_id": "review",
        "roles": ["review"],
        "seq": 12,
    },
    {"id": "E4", "text": "日志里不得打印密钥", "kind": "convention", "seq": 3},
    {"id": "E5", "text": "The refresh lock must be held while rotating tokens", "seq": 20},
]


def _body(**overrides):
    body = {
        "schema": "memoryos_recall/v1",
        "query": "payment amount Decimal 金额",
        "items": ITEMS,
        "hints": {"thread_id": "task", "role": "impl"},
        "budget_tokens": 1000,
        "k": 40,
    }
    body.update(overrides)
    return body


def test_recall_is_byte_identical_across_calls(client_for):
    client = client_for(DeterministicEmbeddingClient())
    first = client.post("/recall", json=_body())
    second = client.post("/recall", json=_body())
    assert first.status_code == 200
    assert first.content == second.content
    payload = first.json()
    assert payload["schema"] == "memoryos_recall/v1"
    assert payload["diagnostics"]["dense"] is True
    assert payload["diagnostics"]["token_estimator"]
    assert {row["id"] for row in payload["ranked"]} | set(payload["dropped"]) == {
        item["id"] for item in ITEMS
    }


def test_recall_ranks_lexical_and_hint_matches_first(client_for):
    payload = client_for().post("/recall", json=_body()).json()
    ranked = payload["ranked"]
    assert ranked[0]["id"] == "E1"
    assert ranked[0]["why"] == ["bm25", "thread", "role"]
    assert ranked[1]["id"] == "E2"
    assert ranked[1]["why"] == ["bm25"]
    assert payload["diagnostics"]["dense"] is False


def test_recall_ties_break_by_seq_then_id(client_for):
    items = [
        {"id": "b", "text": "same", "seq": 5},
        {"id": "a", "text": "same", "seq": 5},
        {"id": "c", "text": "same", "seq": 5},
        {"id": "z", "text": "same", "seq": 1},
    ]
    body = _body(query="", items=items, hints={})
    payload = client_for().post("/recall", json=body).json()
    assert [row["id"] for row in payload["ranked"]] == ["a", "b", "c", "z"]
    assert payload["ranked"][0]["score"] == RECENCY_MAX
    assert payload["ranked"][-1]["score"] == 0.0


def test_recall_empty_query_orders_by_hints_then_recency(client_for):
    payload = client_for().post("/recall", json=_body(query="")).json()
    ids = [row["id"] for row in payload["ranked"]]
    assert ids == ["E1", "E2", "E5", "E3", "E4"]
    assert payload["ranked"][0]["score"] == pytest.approx(THREAD_BONUS + ROLE_BONUS + RECENCY_MAX)


def test_recall_budget_and_k_truncate_greedily(client_for):
    client = client_for()
    full = client.post("/recall", json=_body()).json()
    assert full["dropped"] == []
    budget = full["tokens_used"] - 1
    cut = client.post("/recall", json=_body(budget_tokens=budget)).json()
    assert cut["tokens_used"] <= budget
    assert cut["dropped"]
    assert [row["id"] for row in cut["ranked"]] == [
        row["id"] for row in full["ranked"] if row["id"] not in cut["dropped"]
    ]
    top2 = client.post("/recall", json=_body(k=2)).json()
    assert [row["id"] for row in top2["ranked"]] == [row["id"] for row in full["ranked"][:2]]
    assert top2["dropped"] == [row["id"] for row in full["ranked"][2:]]


def test_recall_falls_back_to_bm25_when_dense_fails(client_for):
    payload = client_for(BrokenEmbeddings()).post("/recall", json=_body()).json()
    assert payload["diagnostics"]["dense"] is False
    assert all("dense" not in row["why"] for row in payload["ranked"])
    bm25_only = client_for().post("/recall", json=_body()).json()
    assert payload["ranked"] == bm25_only["ranked"]


def test_recall_caches_embeddings_by_text(tmp_path):
    embeddings = CountingEmbeddings()
    service = _service(tmp_path, embeddings)
    request = RecallRequest.model_validate(_body())
    service.recall(request)
    first = len(embeddings.embedded)
    assert first == len(ITEMS) + 1
    service.recall(request)
    assert len(embeddings.embedded) == first
    service.recall(RecallRequest.model_validate(_body(query="token rotation")))
    assert embeddings.embedded[first:] == ["token rotation"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema": "memoryos_recall/v2"},
        {"items": [{"id": f"E{i}", "text": "x"} for i in range(501)]},
        {"items": [{"id": "E1", "text": "x" * 2001}]},
        {"items": [{"id": "E1", "text": "a"}, {"id": "E1", "text": "b"}]},
        {"budget_tokens": 0},
        {"k": 0},
    ],
)
def test_recall_rejects_invalid_requests(client_for, overrides):
    assert client_for().post("/recall", json=_body(**overrides)).status_code == 422


def test_recall_accepts_the_maximum_request(client_for):
    items = [{"id": f"E{i:03d}", "text": "决定 " * 300, "seq": i} for i in range(500)]
    payload = client_for().post("/recall", json=_body(items=items, k=500)).json()
    assert len(payload["ranked"]) + len(payload["dropped"]) == 500
    assert payload["tokens_used"] <= 1000


def test_recall_matches_the_contract_example(client_for):
    item = {
        "id": "E12",
        "text": "Amounts are Decimal strings",
        "kind": "decision",
        "thread_id": "task",
        "roles": ["impl"],
        "seq": 57,
    }
    body = _body(query="Decimal amounts", items=[item])
    payload = client_for().post("/recall", json=body).json()
    assert payload["ranked"] == [
        {"id": "E12", "score": 0.046393, "why": ["bm25", "thread", "role"]}
    ]
    assert payload["tokens_used"] == TokenEstimator().count(item["text"])
