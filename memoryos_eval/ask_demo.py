"""A small, offline example for ``python -m memoryos_eval ask-demo``.

The retriever and the rewrite LLM are scripted. The first search finds only a
message stating a superseded value (marked outdated, so it does not count as
evidence); the rewritten query finds the current value.
The answer lists the current item first and the outdated one with its
replacement.
"""

from __future__ import annotations

from typing import Any

from memoryos_eval.ask import AskRequest
from memoryos_lite.retrieval.supersede import SupersededQuote

DEMO_QUESTION = "Which gateway runs in front of the public API today?"
DEMO_REQUEST = AskRequest(question=DEMO_QUESTION)
DEMO_REWRITE = "API gateway migration Kong Envoy cutover"
DEMO_MARKS = [
    SupersededQuote(
        quote="We run the public API on Kong",
        current="Envoy is the gateway in front of the public API.",
    )
]

_MESSAGES: dict[str, str] = {
    "m03": "We run the public API on Kong for now, in front of every service.",
    "m17": "Gateway cutover done: Envoy now runs in front of the public API; Kong is retired.",
}
_RESULTS: dict[str, list[str]] = {DEMO_QUESTION: ["m03"], DEMO_REWRITE: ["m17", "m03"]}


def demo_retrieve(query: str) -> list[dict[str, Any]]:
    """Scripted retrieval: fixed hits per query, shaped like ``source_evidence/v2`` items."""

    return [
        {
            "item_id": message_id,
            "layer": "archival",
            "text": _MESSAGES[message_id],
            "estimated_tokens": len(_MESSAGES[message_id]) // 4,
            "document_id": f"room-activity-{message_id}",
            "source_refs": [{"source_type": "message", "source_id": message_id}],
        }
        for message_id in _RESULTS.get(query, [])
    ]


class DemoRewriteLLM:
    """Proposes one better query, then nothing new."""

    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        return {"query": DEMO_REWRITE if self.calls == 1 else ""}
