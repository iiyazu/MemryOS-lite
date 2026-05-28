from __future__ import annotations

import json
from pathlib import Path

from xmuse_core.chat.driver import ChatDriver
from xmuse_core.chat.store import ChatStore


def _make_driver(
    tmp_path: Path,
    monkeypatch,
    claude_outputs: list[str],
) -> tuple[ChatDriver, list[dict]]:
    """Build a ChatDriver whose Claude subprocess returns canned outputs.

    Returns the driver plus a list that records each call's prompt for assertions.
    """
    db = tmp_path / "chat.db"
    driver = ChatDriver(chat_db_path=db, runtime="claude", model="haiku", timeout_s=5.0)
    calls: list[dict] = []
    queue = list(claude_outputs)

    def fake_run(cmd, input, capture_output, text, timeout, check):  # noqa: ARG001
        if not queue:
            raise AssertionError("claude called more times than canned outputs")
        out = queue.pop(0)
        calls.append({"input": input, "cmd": cmd})
        envelope = json.dumps({"result": out})
        return _Stub(stdout=envelope, stderr="", returncode=0)

    monkeypatch.setattr("xmuse_core.chat.driver.subprocess.run", fake_run)
    return driver, calls


class _Stub:
    def __init__(self, stdout: str, stderr: str, returncode: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_driver_routes_default_to_architect(tmp_path: Path, monkeypatch) -> None:
    driver, calls = _make_driver(
        tmp_path,
        monkeypatch,
        [json.dumps({"type": "message", "text": "I'll think about it."})],
    )
    store = ChatStore(tmp_path / "chat.db")
    conv = store.create_conversation(title="t1")
    # Seed an old human message and prime cursor by ticking once
    store.add_message(conv.id, "Operator", "human", "old message")
    driver.tick()  # primes cursor, no claude call expected to consume queue
    assert len(calls) == 0
    # Now post a new human message
    store.add_message(conv.id, "Operator", "human", "what should we build next?")

    outcomes = driver.tick()

    assert len(outcomes) == 1
    out = outcomes[0]
    assert out.god_role == "architect"
    assert out.envelope_type == "message"
    assert out.reply_message_id is not None
    msgs = store.list_messages(conv.id)
    assert msgs[-1].author == "architect-god"
    assert msgs[-1].role == "assistant"
    assert "think about it" in msgs[-1].content


def test_driver_routes_review_mention(tmp_path: Path, monkeypatch) -> None:
    driver, calls = _make_driver(
        tmp_path,
        monkeypatch,
        [json.dumps({"type": "verdict", "decision": "approve", "rationale": "looks fine"})],
    )
    store = ChatStore(tmp_path / "chat.db")
    conv = store.create_conversation(title="t2")
    store.add_message(conv.id, "Operator", "human", "seed")
    driver.tick()
    store.add_message(conv.id, "Operator", "human", "@review-god please verify the proposal")

    outcomes = driver.tick()

    assert len(outcomes) == 1
    assert outcomes[0].god_role == "review"
    assert outcomes[0].envelope_type == "verdict"
    msgs = store.list_messages(conv.id)
    assert msgs[-1].author == "review-god"
    assert "[verdict: approve]" in msgs[-1].content


def test_driver_falls_back_to_plain_text(tmp_path: Path, monkeypatch) -> None:
    driver, _ = _make_driver(
        tmp_path,
        monkeypatch,
        ["this is not json"],
    )
    store = ChatStore(tmp_path / "chat.db")
    conv = store.create_conversation(title="t3")
    store.add_message(conv.id, "Operator", "human", "seed")
    driver.tick()
    store.add_message(conv.id, "Operator", "human", "anything")

    outcomes = driver.tick()

    assert len(outcomes) == 1
    assert outcomes[0].envelope_type is None
    msgs = store.list_messages(conv.id)
    assert msgs[-1].content == "this is not json"


def test_driver_does_not_double_process(tmp_path: Path, monkeypatch) -> None:
    driver, _ = _make_driver(
        tmp_path,
        monkeypatch,
        [json.dumps({"type": "message", "text": "hi"})],
    )
    store = ChatStore(tmp_path / "chat.db")
    conv = store.create_conversation(title="t4")
    store.add_message(conv.id, "Operator", "human", "seed")
    driver.tick()
    store.add_message(conv.id, "Operator", "human", "real")

    first = driver.tick()
    second = driver.tick()

    assert len(first) == 1
    assert len(second) == 0


def test_driver_skips_assistant_role_messages(tmp_path: Path, monkeypatch) -> None:
    driver, _ = _make_driver(tmp_path, monkeypatch, [])
    store = ChatStore(tmp_path / "chat.db")
    conv = store.create_conversation(title="t5")
    store.add_message(conv.id, "system", "system", "spam")
    driver.tick()
    store.add_message(conv.id, "architect-god", "assistant", "i'm a god replying")

    outcomes = driver.tick()

    # No human message → driver should produce no outcomes for the assistant
    # message (it should be skipped without spawning Claude).
    assert outcomes == []


def test_driver_handles_proposal_envelope(tmp_path: Path, monkeypatch) -> None:
    proposal_envelope = {
        "type": "proposal",
        "summary": "Add a thing",
        "lanes": [
            {"feature_id": "thing-impl", "prompt": "do it", "depends_on": []},
            {"feature_id": "thing-test", "prompt": "test it", "depends_on": ["thing-impl"]},
        ],
    }
    driver, _ = _make_driver(
        tmp_path,
        monkeypatch,
        [json.dumps(proposal_envelope)],
    )
    store = ChatStore(tmp_path / "chat.db")
    conv = store.create_conversation(title="t6")
    store.add_message(conv.id, "Operator", "human", "seed")
    driver.tick()
    store.add_message(conv.id, "Operator", "human", "draft a plan for adding a thing")

    outcomes = driver.tick()

    assert len(outcomes) == 1
    assert outcomes[0].envelope_type == "proposal"
    msgs = store.list_messages(conv.id)
    assert "[proposal]" in msgs[-1].content
    assert "2 lanes" in msgs[-1].content
