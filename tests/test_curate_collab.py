"""The collab profile of /curate: proposed alignment entries for one xmuse topic."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.curator.curate import CurateRequest
from memoryos_lite.curator.graph import render_request, run_curate
from memoryos_lite.engine import MemoryOSService

HANDOFF = "Handoff: payment API done. Amounts are Decimal strings, except ledger totals in cents."
ANSWER = "Lead: refunds go through the same endpoint, answering the open refund question."
ASSUME = "Impl: I assume the sandbox keys stay valid until Friday."
LOCK = "Review: the cache must be bypassed for admin users."


class ScriptedLLM:
    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        return self.replies.pop(0)


def _msg(activity_id: str, seq: int, kind: str, text: str) -> dict[str, Any]:
    return {
        "id": activity_id,
        "seq": seq,
        "type": "message",
        "kind": kind,
        "speaker": "a",
        "text": text,
    }


ACTIVE = [
    {
        "id": "Q1",
        "kind": "question",
        "topic_key": "payment.refunds",
        "statement": "Do refunds need their own endpoint?",
        "version": 3,
    },
    {
        "id": "D1",
        "kind": "decision",
        "topic_key": "payment.amount_repr",
        "statement": "Amounts are integer cents.",
        "version": 2,
    },
    {
        "id": "C1",
        "kind": "convention",
        "topic_key": "cache.admin",
        "statement": "Admin users are cached like everyone else.",
        "version": 1,
    },
]


def _request(**overrides: Any) -> CurateRequest:
    payload: dict[str, Any] = {
        "scope_id": "topic-7",
        "profile": "collab",
        "active": ACTIVE,
        "window": [
            _msg("m1", 10, "handoff", HANDOFF),
            _msg("m2", 11, "message", ANSWER),
            _msg("m3", 12, "assumption", ASSUME),
            _msg("m4", 13, "review_request", LOCK),
        ],
    }
    payload.update(overrides)
    return CurateRequest.model_validate(payload)


def _source(activity_id: str, quote: str) -> list[dict[str, str]]:
    return [{"activity_id": activity_id, "quote": quote}]


REPLY = {
    "memories": [
        {
            "kind": "decision",
            "topic_key": "payment.amount_repr",
            "statement": "Amounts are Decimal strings, except ledger totals in cents.",
            "sources": _source("m1", "Amounts are Decimal strings, except ledger totals in cents"),
        },
        {
            "kind": "decision",
            "topic_key": "payment.refund_endpoint",
            "statement": "Refunds go through the payment endpoint.",
            "sources": _source("m2", "refunds go through the same endpoint"),
            "resolves": ["Q1"],
        },
        {
            "kind": "assumption",
            "topic_key": "env.sandbox_keys",
            "statement": "Sandbox keys stay valid until Friday.",
            "sources": _source("m3", "sandbox keys stay valid until Friday"),
        },
        {
            "kind": "convention",
            "topic_key": "cache.admin_bypass",
            "statement": "The cache must be bypassed for admin users.",
            "sources": _source("m4", "the cache must be bypassed for admin users"),
        },
    ],
    "conflicts": [
        {
            "a_id": "C1",
            "b_id": "cache.admin_bypass",
            "reason": "cache admins vs bypass them",
            "sources": _source("m4", "bypassed for admin users"),
        },
    ],
}


def test_collab_reply_becomes_proposals_with_resolves_and_conflicts():
    llm = ScriptedLLM(REPLY)
    response = run_curate(_request(), llm)

    assert len(llm.calls) == 1
    system, user = llm.calls[0]
    assert "keep every qualifier" in system
    assert "Topic: topic-7" in user
    assert "- [Q1] question payment.refunds: Do refunds need their own endpoint?" in user
    assert "[m1] a (handoff): Handoff" in user
    by_key = {memory.topic_key: memory for memory in response.memories}
    assert by_key["payment.amount_repr"].supersedes_id == "D1"
    assert by_key["payment.refund_endpoint"].resolves_ids == ["Q1"]
    assert by_key["env.sandbox_keys"].kind == "assumption"
    assert by_key["env.sandbox_keys"].resolves_ids == []
    assert response.conflicts is not None
    [conflict] = response.conflicts
    assert (conflict.a_id, conflict.b_id) == ("C1", by_key["cache.admin_bypass"].id)
    assert conflict.sources[0].quote == "bypassed for admin users"
    assert response.diagnostics.final_violations == []


def test_collab_does_not_repropose_declared_entries():
    declared = {
        "id": "A9",
        "kind": "assumption",
        "topic_key": "sandbox",
        "statement": "Sandbox keys stay valid until Friday.",
        "version": 12,
    }
    reply = {"memories": [REPLY["memories"][2]]}
    response = run_curate(_request(active=[*ACTIVE, declared]), ScriptedLLM(reply))
    assert response.memories == []
    assert response.diagnostics.noop_memories == 1


def test_collab_repairs_bad_resolves_and_conflicts():
    bad = {
        "memories": [{**REPLY["memories"][1], "resolves": ["D1"]}],
        "conflicts": [
            {"a_id": "nope", "b_id": "C1", "reason": "x"},
            {
                "a_id": "payment.refund_endpoint",
                "b_id": "payment.refund_endpoint",
                "reason": "self",
            },
        ],
    }
    llm = ScriptedLLM(bad, {"memories": [REPLY["memories"][1]], "conflicts": []})
    response = run_curate(_request(), llm)
    violations = response.diagnostics.initial_violations
    assert any('"resolves" must list ids of active questions' in v for v in violations)
    assert sum("every conflict needs a_id and b_id" in v for v in violations) == 2
    assert "memories, assignments and conflicts, not only the fixes" in llm.calls[1][1]
    assert response.memories[0].resolves_ids == ["Q1"]
    assert response.conflicts == []


def test_collab_rejects_kinds_outside_the_profile():
    reply = {"memories": [{**REPLY["memories"][2], "kind": "fact"}]}
    response = run_curate(_request(max_repairs=0), ScriptedLLM(reply))
    assert response.memories == []
    assert (
        "needs kind decision|convention|assumption|question|lesson"
        in (response.diagnostics.final_violations[0])
    )


def test_conflict_with_a_noop_proposal_points_at_the_active_entry():
    restated = {
        "kind": "convention",
        "topic_key": "cache.admin",
        "statement": "Admin users are cached like everyone else.",
        "sources": _source("m4", "the cache must be bypassed"),
    }
    reply = {
        "memories": [restated, REPLY["memories"][0]],
        "conflicts": [
            {"a_id": "cache.admin", "b_id": "D1", "reason": "unrelated, for the mapping only"}
        ],
    }
    response = run_curate(_request(), ScriptedLLM(reply))
    assert [memory.topic_key for memory in response.memories] == ["payment.amount_repr"]
    [conflict] = response.conflicts or []
    assert (conflict.a_id, conflict.b_id) == ("C1", "D1")


def test_collab_is_deterministic_and_module_output_has_no_collab_fields():
    first = run_curate(_request(), ScriptedLLM(REPLY)).model_dump_json()
    assert first == run_curate(_request(), ScriptedLLM(REPLY)).model_dump_json()

    module = CurateRequest.model_validate(
        {"scope_id": "auth", "window": [{**_msg("m1", 1, "decision", HANDOFF)}]}
    )
    assert "(message): Handoff" in render_request(module)
    reply = {
        "memories": [
            {
                "kind": "decision",
                "topic_key": "pay.repr",
                "statement": "Decimal.",
                "sources": _source("m1", "Amounts are Decimal strings"),
            }
        ]
    }
    dumped = run_curate(module, ScriptedLLM(reply)).model_dump()
    assert "conflicts" not in dumped
    assert "resolves_ids" not in dumped["memories"][0]
    assert dumped["memories"][0]["supersedes_id"] is None


def test_curate_endpoint_collab(tmp_path):
    service = MemoryOSService(
        settings=Settings(data_dir=tmp_path / ".memoryos"), curate_llm=ScriptedLLM(REPLY)
    )
    app.dependency_overrides[get_service] = lambda: service
    try:
        body = _request().model_dump(mode="json", exclude_none=True)
        payload = TestClient(app).post("/curate", json=body).json()
    finally:
        app.dependency_overrides.clear()
    assert payload["schema_version"] == "memoryos_curate/v1"
    assert len(payload["memories"]) == 4
    assert payload["conflicts"][0]["a_id"] == "C1"
    assert payload["memories"][1]["resolves_ids"] == ["Q1"]


def test_malformed_resolves_and_conflict_ids_are_violations_not_errors():
    reply = {
        "memories": [{**REPLY["memories"][1], "resolves": [{"id": "Q1"}]}],
        "conflicts": [{"a_id": {"id": "C1"}, "b_id": ["D1"], "reason": "x"}, "not an object"],
    }
    response = run_curate(_request(max_repairs=0), ScriptedLLM(reply))
    assert response.memories == []
    assert response.conflicts == []
    assert len(response.diagnostics.final_violations) == 3
