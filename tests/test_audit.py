"""/audit: which messages relied on a statement that was just replaced."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from memoryos_lite.api.app import app, get_service
from memoryos_lite.audit import AuditRequest, Retriever, recent, rule_queries, verify
from memoryos_lite.audit_graph import run_audit
from memoryos_lite.curator.llm import CuratorSchemaError
from memoryos_lite.engine import MemoryOSService

OLD = "Amounts are integer cents: `parse_amount` returns an `int`, `format_amount(cents)` renders."
NEW = "Amounts are decimal strings with two places: `parse_amount('3.5') == '3.50'`; no floats."
DEPENDENT = (
    "Done: parse_amount returns int cents, tests assert parse_amount('3.5') == 350. Review please."
)
PARAPHRASE = "Done: the money parser now gives whole cents as integers; all tests on that pass."
NOISE = [
    f"Standup {i}: CI is green, nothing blocking, next is the report layout." for i in range(30)
]


class ScriptedLLM:
    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _request(**kw: Any) -> AuditRequest:
    items = [{"id": f"m{i}", "text": t, "speaker": "a", "seq": i} for i, t in enumerate(NOISE)]
    items += [
        {"id": "m100", "text": DEPENDENT, "speaker": "impl", "seq": 5},
        {"id": "m101", "text": PARAPHRASE, "speaker": "impl", "seq": 6},
    ]
    return AuditRequest.model_validate(
        {
            "schema": "memoryos_audit/v1",
            "old": {"id": "E7", "text": OLD},
            "new": {"id": "E12", "text": NEW},
            "items": items,
            **kw,
        }
    )


def test_rule_queries_are_code_spans_or_identifiers() -> None:
    assert rule_queries(OLD, NEW) == [
        "parse_amount",
        "int",
        "format_amount(cents)",
        "parse_amount('3.5') == '3.50'",
    ]
    # a decision typed by a person has no backticks: its ASCII names stand in
    assert rule_queries("非法输入时抛 ValueError", "t8util 的函数返回 None") == [
        "ValueError",
        "t8util",
        "None",
    ]


def test_retrieval_puts_the_lexical_dependent_first_without_any_llm() -> None:
    request = _request()
    ranked, dense = Retriever(None).rank(request.items, [OLD, *rule_queries(OLD, NEW)])
    assert ranked[0] == "m100" and dense is False


def test_recent_is_the_newest_by_seq() -> None:
    assert recent(_request().items)[:2] == ["m29", "m28"]


def test_verify_keeps_only_verbatim_quotes_of_candidates() -> None:
    items = _request().items
    flags, dropped = verify(
        items,
        ["m100", "m101", "m3"],
        {
            "m100": {"dep": 1, "quote": "parse_amount returns int cents"},
            "m101": {"dep": 1, "quote": "the parser returns cents"},  # not in the text
            "m3": {"dep": 0, "quote": ""},
            "m50": {"dep": 1, "quote": "x"},
        },
    )  # not a candidate
    assert [f.id for f in flags] == ["m100"] and dropped == 1


def test_graph_expands_judges_and_verifies() -> None:
    llm = ScriptedLLM(
        {
            "queries": [
                "money parser gives whole cents",
                "integer cents tests",
                "cents as int",
                "amount in cents",
            ]
        },
        {
            "verdicts": {
                "m100": {"dep": 1, "quote": "parse_amount returns int cents"},
                "m101": {"dep": 1, "quote": "the money parser now gives whole cents as integers"},
            }
        },
    )
    response = run_audit(_request(k=10), llm, Retriever(None))
    assert [f.id for f in response.flagged] == ["m100", "m101"]
    assert {"m100", "m101"} <= set(response.candidates) and len(response.candidates) == 10
    assert response.diagnostics.expanded == 4 and response.diagnostics.llm_calls == 2
    judged = llm.calls[1][1]
    assert "[m100] impl:" in judged and OLD in judged and NEW in judged


def test_a_failed_expansion_still_audits_by_rules_and_recency() -> None:
    llm = ScriptedLLM(
        CuratorSchemaError("no json"),
        {"verdicts": {"m100": {"dep": 1, "quote": "returns int cents"}}},
    )
    response = run_audit(_request(k=5), llm, Retriever(None))
    assert response.diagnostics.expanded == 0 and [f.id for f in response.flagged] == ["m100"]


def test_expand_false_makes_one_llm_call() -> None:
    llm = ScriptedLLM({"verdicts": {}})
    response = run_audit(_request(expand=False, k=5), llm, Retriever(None))
    assert len(llm.calls) == 1 and response.flagged == [] and response.diagnostics.llm_calls == 1


def test_endpoint_and_health_capability() -> None:
    llm = ScriptedLLM(
        {"queries": []}, {"verdicts": {"m100": {"dep": 1, "quote": "returns int cents"}}}
    )
    service = MemoryOSService(curate_llm=llm, embedding_client=None)
    service.embedding_client = None
    app.dependency_overrides[get_service] = lambda: service
    try:
        client = TestClient(app)
        assert "audit" in client.get("/health").json()["capabilities"]
        body = _request(k=5).model_dump(by_alias=True)
        r = client.post("/audit", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["flagged"] == [{"id": "m100", "quote": "returns int cents"}]
        bad = {**body, "items": body["items"] + body["items"][:1]}
        assert client.post("/audit", json=bad).status_code == 422  # duplicate ids
    finally:
        app.dependency_overrides.clear()
