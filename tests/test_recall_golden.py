"""Golden replay of the hub-facing routes (MO-10: replaces the stateful-route replay).

``fixtures/recall_golden.json`` holds `/recall` and `/similar` requests with the
responses they produced when the fixture was frozen. Each case is replayed
three times through the app, with no embedding provider (BM25 only) or the
deterministic fake one, and must match byte for byte. A ranking change has
to update the fixture in the same commit, which makes it visible in review.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.retrieval.providers.fake import DeterministicEmbeddingClient

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "recall_golden.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_golden_replay(tmp_path, case):
    embeddings = DeterministicEmbeddingClient() if case["embeddings"] == "deterministic" else None
    service = MemoryOSService(
        settings=Settings(data_dir=tmp_path / ".memoryos"), embedding_client=embeddings
    )
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        replies = [client.post(case["path"], json=case["request"]) for _ in range(3)]
    finally:
        app.dependency_overrides.clear()

    assert [reply.status_code for reply in replies] == [case["status"]] * 3
    assert replies[0].json() == case["response"]
    assert replies[0].content == replies[1].content == replies[2].content
