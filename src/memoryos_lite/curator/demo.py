"""A small, offline example for ``memoryos demo curate``.

The scripted LLM first forgets one failure and misquotes another, so the demo
shows the graph's repair loop; the second reply is clean.
"""

from __future__ import annotations

from typing import Any

from memoryos_lite.curator.curate import CurateRequest

DEMO_REQUEST = CurateRequest.model_validate(
    {
        "scope_id": "billing",
        "active": [
            {
                "id": "mem_demo_lesson",
                "kind": "lesson",
                "topic_key": "billing.amount_repr",
                "statement": "Represent money as integer cents; float dollars round wrongly.",
                "version": 7,
                "occurrences": 1,
                "sources": [{"activity_id": "a07", "quote": "float dollars causes rounding"}],
            }
        ],
        "context": [
            {
                "id": "a20",
                "seq": 20,
                "type": "message",
                "speaker": "owner",
                "text": "Starting proration for mid-cycle plan changes.",
            }
        ],
        "window": [
            {
                "id": "a21",
                "seq": 21,
                "type": "gate_failure",
                "speaker": "ci",
                "text": "FAILED test_proration.py::test_upgrade - expected 1667 cents, got 16.67",
            },
            {
                "id": "a22",
                "seq": 22,
                "type": "message",
                "speaker": "owner",
                "text": "Decision: proration rounds half up to the nearest cent.",
            },
            {
                "id": "a23",
                "seq": 23,
                "type": "gate_failure",
                "speaker": "ci",
                "text": "FAILED install: registry.npmjs.org timed out (ETIMEDOUT)",
            },
        ],
    }
)

_CLEAN: dict[str, Any] = {
    "assignments": [
        {"activity_id": "a21", "lesson": "billing.amount_repr", "quote": "got 16.67"},
        {"activity_id": "a23", "dismiss": "registry timeout, infrastructure"},
    ],
    "lessons": [
        {
            "topic_key": "billing.amount_repr",
            "statement": (
                "Represent money as integer cents everywhere, including proration; "
                "float dollars cause rounding errors."
            ),
        }
    ],
    "memories": [
        {
            "kind": "decision",
            "topic_key": "billing.proration_rounding",
            "statement": "Proration rounds half up to the nearest cent.",
            "sources": [{"activity_id": "a22", "quote": "rounds half up to the nearest cent"}],
        }
    ],
}
_BROKEN: dict[str, Any] = {
    **_CLEAN,
    "assignments": [
        {"activity_id": "a21", "lesson": "billing.amount_repr", "quote": "got 16.67 dollars"}
    ],
}


class DemoCuratorLLM:
    """Replies with a broken answer first and a clean one after."""

    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        return _BROKEN if self.calls == 1 else _CLEAN
