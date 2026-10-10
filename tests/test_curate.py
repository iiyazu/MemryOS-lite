"""Stateless module curation: closed-world lesson accounting and the repair graph."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from memoryos_lite.api.app import app, get_service
from memoryos_lite.config import Settings
from memoryos_lite.curator.curate import (
    CurateRequest,
    check_reply,
    consolidate,
)
from memoryos_lite.curator.graph import build_curate_graph, run_curate
from memoryos_lite.curator.llm import CuratorLLMError, CuratorSchemaError
from memoryos_lite.engine import MemoryOSService

GATE = "FAILED tests/test_refresh.py::test_concurrent_refresh - token written twice"
REVIEW = "Objection: refresh again ran without taking the per-user lock."
FLAKY = "FAILED install: npm registry timed out (ETIMEDOUT)"
DECISION = "Owner: we will store amounts as integer cents from now on."


class ScriptedLLM:
    """Returns queued replies; an Exception instance in the queue is raised."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _activity(activity_id: str, seq: int, kind: str, text: str) -> dict[str, Any]:
    return {"id": activity_id, "seq": seq, "type": kind, "speaker": "ci", "text": text}


def _request(**overrides: Any) -> CurateRequest:
    payload: dict[str, Any] = {
        "scope_id": "auth",
        "window": [
            _activity("a10", 10, "gate_failure", GATE),
            _activity("a11", 11, "message", DECISION),
            _activity("a12", 12, "gate_failure", FLAKY),
        ],
    }
    payload.update(overrides)
    return CurateRequest.model_validate(payload)


CLEAN_REPLY = {
    "assignments": [
        {"activity_id": "a10", "lesson": "auth.refresh_lock", "quote": "token written twice"},
        {"activity_id": "a12", "dismiss": "registry timeout, infrastructure"},
    ],
    "lessons": [
        {
            "topic_key": "auth.refresh_lock",
            "statement": "Take the per-user lock before refreshing a token.",
        }
    ],
    "memories": [
        {
            "kind": "decision",
            "topic_key": "billing.amount_repr",
            "statement": "Amounts are stored as integer cents.",
            "sources": [{"activity_id": "a11", "quote": "store amounts as integer cents"}],
        }
    ],
}


def test_clean_reply_needs_one_call_and_accounts_for_every_failure():
    llm = ScriptedLLM(CLEAN_REPLY)

    response = run_curate(_request(), llm)

    assert len(llm.calls) == 1
    assert (
        "Failures to account for (each needs exactly one assignment): a10, a12" in (llm.calls[0][1])
    )
    assert response.unaccounted == []
    assert response.diagnostics.repairs == 0
    assert [(a.activity_id, a.lesson, a.dismiss) for a in response.assignments] == [
        ("a10", "auth.refresh_lock", None),
        ("a12", None, "registry timeout, infrastructure"),
    ]
    lesson, decision = response.memories
    assert (lesson.kind, lesson.topic_key, lesson.occurrences, lesson.version) == (
        "lesson",
        "auth.refresh_lock",
        1,
        10,
    )
    assert [s.activity_id for s in lesson.sources] == ["a10"]
    assert (decision.kind, decision.version, decision.supersedes_id) == ("decision", 11, None)
    # Ids are content-derived, so a replay yields the same ids.
    assert run_curate(_request(), ScriptedLLM(CLEAN_REPLY)).memories[0].id == lesson.id


def test_repeat_failure_adds_an_occurrence_to_the_active_lesson():
    prior = {
        "id": "mem_prior",
        "kind": "lesson",
        "topic_key": "auth.refresh_lock",
        "statement": "Take the per-user lock before refreshing a token.",
        "version": 4,
        "occurrences": 2,
        "sources": [
            {"activity_id": "a03", "quote": "token written twice"},
            {"activity_id": "a04", "quote": "without the lock"},
        ],
    }
    request = _request(active=[prior], window=[_activity("a20", 20, "review_objection", REVIEW)])
    reply = {
        "assignments": [
            {"activity_id": "a20", "lesson": "auth.refresh_lock", "quote": "without taking"}
        ]
    }

    response = consolidate(request, check_reply(request, reply))

    (lesson,) = response.memories
    assert lesson.occurrences == 3
    assert lesson.version == 20
    assert lesson.supersedes_id == "mem_prior"
    assert lesson.statement == prior["statement"]
    assert [s.activity_id for s in lesson.sources] == ["a03", "a04", "a20"]

    # Replaying a failure the lesson already cites changes nothing.
    replay = _request(
        active=[{**prior, "sources": [*prior["sources"], {"activity_id": "a20", "quote": "x"}]}],
        window=[_activity("a20", 20, "review_objection", REVIEW)],
    )
    assert consolidate(replay, check_reply(replay, reply)).memories == []


def test_repair_loop_fixes_a_missing_failure_and_a_bad_quote():
    broken = {
        "assignments": [
            {"activity_id": "a10", "lesson": "auth.refresh_lock", "quote": "not in the log"}
        ],
        "lessons": CLEAN_REPLY["lessons"],
    }
    llm = ScriptedLLM(broken, CLEAN_REPLY)

    response = run_curate(_request(), llm)

    assert len(llm.calls) == 2
    repair_prompt = llm.calls[1][1]
    assert "Your previous reply:" in repair_prompt
    assert "the quote for a10 must be an exact substring of a10" in repair_prompt
    assert "a12 (gate_failure) has no assignment" in repair_prompt
    assert response.diagnostics.repairs == 1
    assert len(response.diagnostics.initial_violations) >= 2
    assert response.diagnostics.final_violations == []
    assert response.unaccounted == []


def test_exhausted_repairs_keep_valid_parts_and_report_unaccounted_failures():
    partial = {
        "assignments": [
            {"activity_id": "a10", "lesson": "auth.refresh_lock", "quote": "token written twice"}
        ],
        "lessons": CLEAN_REPLY["lessons"],
    }
    llm = ScriptedLLM(partial, partial, partial)

    response = run_curate(_request(), llm)

    assert len(llm.calls) == 3  # one extraction + max_repairs (2)
    assert response.unaccounted == ["a12"]
    assert response.diagnostics.final_violations == ["a12 (gate_failure) has no assignment"]
    assert [m.topic_key for m in response.memories] == ["auth.refresh_lock"]


def test_non_json_reply_is_repaired_and_provider_errors_propagate():
    llm = ScriptedLLM(CuratorSchemaError("no json"), CLEAN_REPLY)
    response = run_curate(_request(), llm)
    assert response.diagnostics.repairs == 1
    assert "the reply was not a JSON object" in response.diagnostics.initial_violations
    assert "(no JSON object)" in llm.calls[1][1]

    with pytest.raises(CuratorLLMError):
        run_curate(_request(), ScriptedLLM(CuratorLLMError("provider call failed")))


def test_no_repairs_requested_means_a_single_call():
    llm = ScriptedLLM({"assignments": []})
    response = run_curate(_request(max_repairs=0), llm)
    assert len(llm.calls) == 1
    assert response.unaccounted == ["a10", "a12"]


@pytest.mark.parametrize(
    ("reply", "violation"),
    [
        (
            {"assignments": [{"activity_id": "a11", "dismiss": "chat"}]},
            "a11 is not a review_objection or gate_failure to curate",
        ),
        (
            {"assignments": [{"activity_id": "a10", "dismiss": " "}]},
            "a10: a dismissal needs a reason",
        ),
        (
            {"assignments": [{"activity_id": "a10", "lesson": "auth.unknown", "quote": GATE}]},
            "neither an active lesson nor defined",
        ),
        (
            {"lessons": [{"topic_key": "auth.orphan", "statement": "Never do this."}]},
            "lesson auth.orphan has no failure assigned",
        ),
        (
            {
                "memories": [
                    {
                        "kind": "lesson",
                        "topic_key": "x.y",
                        "statement": "s",
                        "sources": [{"activity_id": "a10", "quote": GATE}],
                    }
                ]
            },
            "lessons are recorded through assignments",
        ),
        (
            {
                "assignments": [
                    {"activity_id": "a10", "dismiss": "flaky"},
                    {"activity_id": "a10", "dismiss": "again"},
                ]
            },
            "a10 has more than one assignment",
        ),
    ],
)
def test_rule_violations_are_named(reply, violation):
    result = check_reply(_request(), reply)
    assert any(violation in item for item in result.violations), result.violations


def test_decisions_keep_the_newest_and_ignore_restatements_and_stale_values():
    prior = {
        "id": "mem_old",
        "kind": "decision",
        "topic_key": "billing.amount_repr",
        "statement": "Amounts are stored as float dollars.",
        "version": 5,
        "sources": [{"activity_id": "a05", "quote": "float dollars"}],
    }
    request = _request(active=[prior])
    response = consolidate(request, check_reply(request, CLEAN_REPLY))
    decision = next(m for m in response.memories if m.kind == "decision")
    assert decision.supersedes_id == "mem_old"

    same = _request(active=[{**prior, "statement": "Amounts are stored as integer cents."}])
    response = consolidate(same, check_reply(same, CLEAN_REPLY))
    assert all(m.kind != "decision" for m in response.memories)
    assert response.diagnostics.noop_memories == 1

    newer = _request(active=[{**prior, "version": 30}])
    response = consolidate(newer, check_reply(newer, CLEAN_REPLY))
    assert all(m.kind != "decision" for m in response.memories)
    assert response.diagnostics.stale_memories == 1


def test_request_rejects_duplicate_activity_ids():
    with pytest.raises(ValidationError):
        _request(context=[_activity("a10", 9, "message", "dup")])


def test_graph_has_the_repair_loop():
    mermaid = build_curate_graph(ScriptedLLM()).get_graph().draw_mermaid()
    for node in ("extract", "check", "repair", "consolidate"):
        assert node in mermaid


def _service(tmp_path, **kwargs: Any) -> MemoryOSService:
    settings = Settings(
        data_dir=tmp_path / ".memoryos",
        openai_api_key=None,
        deepseek_api_key=None,
        opencode_api_key=None,
    )
    return MemoryOSService(settings=settings, **kwargs)


def test_curate_endpoint(tmp_path):
    payload = _request().model_dump()
    client = TestClient(app)
    try:
        app.dependency_overrides[get_service] = lambda: _service(
            tmp_path / "ok", curate_llm=ScriptedLLM(CLEAN_REPLY)
        )
        response = client.post("/curate", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "memoryos_curate/v1"
        assert body["unaccounted"] == []
        assert len(body["memories"]) == 2

        app.dependency_overrides[get_service] = lambda: _service(tmp_path / "nokey")
        response = client.post("/curate", json=payload)
        assert (response.status_code, response.json()["detail"]) == (
            503,
            "curator_llm_key_missing",
        )

        app.dependency_overrides[get_service] = lambda: _service(
            tmp_path / "down", curate_llm=ScriptedLLM(CuratorLLMError("boom secret"))
        )
        response = client.post("/curate", json=payload)
        assert (response.status_code, response.json()["detail"]) == (502, "curator_llm_error")
        assert client.get("/health").json()["capability_details"]["curate"] == "memoryos_curate/v1"
    finally:
        app.dependency_overrides.clear()
