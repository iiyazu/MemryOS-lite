"""Curator behavior tests. All LLM calls use injectable fakes; no network."""

from __future__ import annotations

from memoryos_eval.memory.schemas import MessageCreate, Role
from memoryos_eval.memory.service import SessionMemoryService
from memoryos_eval.memory.session_curator import Curator
from memoryos_eval.memory.store import create_store
from memoryos_lite.config import Settings
from memoryos_lite.curator import CuratorLLMError, CuratorSchemaError
from memoryos_lite.curator.grounding import repair_quote
from memoryos_lite.curator.prompt import CURATE_ROOM_SYSTEM_PROMPT


class FakeLLM:
    """Scripted curator LLM: returns queued responses, raising exceptions as given."""

    def __init__(self, responses: list[object] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, object]:
        self.calls.append((system, user))
        if not self.responses:
            return {"memories": []}
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, dict)
        return response


def _service(tmp_path, llm, **overrides) -> tuple[SessionMemoryService, Curator]:
    settings = Settings(
        data_dir=tmp_path / "memoryos",
        rot_safe_budget=1_000,
        recent_message_limit=2,
        **overrides,
    )
    store = create_store(settings)
    store.reset()
    curator = Curator(store=store, settings=settings, llm=llm)
    service = SessionMemoryService(store=store, settings=settings)
    return service, curator


def _ingest(service: SessionMemoryService, session_id: str, content: str, **metadata) -> str:
    response = service.ingest(
        session_id,
        MessageCreate(role=Role.USER, content=content, metadata=metadata),
    )
    return response.message.id


def _mem(
    message_id: str,
    statement: str,
    *,
    quote: str | None = None,
    kind: str = "fact",
    topic_key: str = "project.launch_city",
) -> dict[str, object]:
    return {
        "kind": kind,
        "topic_key": topic_key,
        "statement": statement,
        "sources": [{"activity_id": message_id, "quote": quote or statement}],
    }


# -- grounding ---------------------------------------------------------------


def test_repair_quote_whitespace_and_case_normalization() -> None:
    content = "Alice   PREFERS   rail travel."
    assert repair_quote(content, "Alice   PREFERS   rail travel.") == (
        "Alice   PREFERS   rail travel."
    )
    assert repair_quote(content, "alice prefers rail travel") == ("Alice   PREFERS   rail travel")


def test_repair_quote_rejects_short_absent_and_ambiguous_quotes() -> None:
    assert repair_quote("hello short world", "short") is None
    assert repair_quote("hello world", "no such text") is None
    ambiguous = "Alice prefers rail\nALICE prefers  rail"
    assert repair_quote(ambiguous, "alice prefers rail") is None


# -- extraction and grounding ------------------------------------------------


def test_add_writes_grounded_memory(tmp_path):
    statement = "Project Helios launches in Lisbon."
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-add")
    message_id = _ingest(service, session.id, statement)
    fake.responses = [
        {"memories": [_mem(message_id, statement)]},
    ]

    result = curator.run_session(session.id)

    assert result.status == "ok"
    assert (result.windows, result.operations, result.added) == (1, 1, 1)
    rows = service.store.list_active_curated_memories(session.id)
    assert len(rows) == 1
    assert rows[0].kind == "fact"
    assert rows[0].sources == [{"message_id": message_id, "quote": statement}]
    state = service.store.get_curator_state(session.id)
    assert state is not None
    assert (state.last_message_seq, state.runs, state.proposals) == (1, 1, 1)


def test_ungrounded_and_short_quotes_are_rejected_but_window_advances(tmp_path):
    content = "Alice keeps the rollout notes in the shared wiki."
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-grounding")
    message_id = _ingest(service, session.id, content)
    bad_reply = {
        "memories": [
            _mem(message_id, "Hallucinated statement about Lisbon.", quote="not in text"),
            _mem(message_id, "Short quote memory", quote="Alice"),
            # message id from another session is not groundable either.
            _mem("msg_elsewhere", "Foreign message memory", quote=content),
        ]
    }
    # Per-memory problems are repaired inside the loop: repeat the bad reply
    # until repairs are exhausted so the final check still rejects all three.
    fake.responses = [bad_reply, bad_reply, bad_reply]

    result = curator.run_session(session.id)

    assert result.rejected_grounding == 3
    assert result.added == 0
    assert service.store.list_active_curated_memories(session.id) == []
    state = service.store.get_curator_state(session.id)
    assert state is not None
    assert state.last_message_seq == 1
    assert state.rejected_grounding == 3


def test_normalized_quote_is_rewritten_to_exact_original_span(tmp_path):
    content = "Alice   PREFERS   rail travel for launches."
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-normalize")
    message_id = _ingest(service, session.id, content)
    fake.responses = [
        {
            "memories": [
                _mem(
                    message_id,
                    "Alice prefers rail travel for launches.",
                    quote="alice prefers rail travel",
                ),
            ]
        }
    ]

    result = curator.run_session(session.id)

    assert result.added == 1
    rows = service.store.list_active_curated_memories(session.id)
    assert rows[0].sources[0]["quote"] == "Alice   PREFERS   rail travel"
    assert "Alice   PREFERS   rail travel" in content


def test_memory_schema_violations_are_rejected(tmp_path):
    content = "Rollout notes live in the shared wiki for the Helios project."
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-schema")
    message_id = _ingest(service, session.id, content)
    bad_reply = {
        "memories": [
            _mem(message_id, "x" * 601),
            _mem(message_id, "Valid statement but bad kind.", kind="vibe"),
            {
                "kind": "fact",
                "topic_key": "too.many",
                "statement": "Four sources are too many for one memory.",
                "sources": [
                    {"activity_id": message_id, "quote": content},
                ]
                * 4,
            },
        ]
    }
    fake.responses = [bad_reply, bad_reply, bad_reply]

    result = curator.run_session(session.id)

    assert result.rejected_grounding == 3
    assert result.rejected_schema == 0
    assert result.added == 0
    assert service.store.get_curator_state(session.id).last_message_seq == 1


# -- consolidation -----------------------------------------------------------


def test_update_supersedes_in_one_transaction(tmp_path):
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-supersede")
    first_content = "The launch city is Lisbon."
    first_id = _ingest(service, session.id, first_content)
    fake.responses = [{"memories": [_mem(first_id, first_content)]}]
    assert curator.run_session(session.id).added == 1
    old = service.store.list_active_curated_memories(session.id)[0]

    new_content = "The launch city changed to Porto."
    new_id = _ingest(service, session.id, new_content)
    fake.responses = [
        {
            "memories": [
                _mem(
                    new_id,
                    new_content,
                    quote=new_content,
                )
            ]
        }
    ]
    result = curator.run_session(session.id)

    assert (result.added, result.superseded) == (0, 1)
    active = service.store.list_active_curated_memories(session.id)
    assert len(active) == 1
    new_row = active[0]
    assert new_row.id != old.id
    assert new_row.supersedes_id == old.id
    assert new_row.superseded_by_id is None
    # The old memory is flipped to superseded in the same transaction as the
    # watermark advance, and points at the row that replaced it.
    superseded = service.store.get_curated_memory(old.id)
    assert superseded is not None
    assert superseded.status == "superseded"
    assert superseded.superseded_by_id == new_row.id
    all_rows = service.store.list_curated_memories(session.id, limit=32)
    assert [row.id for row in all_rows] == [old.id, new_row.id]


def test_one_window_supersedes_a_memory_once_and_drops_duplicate_writes(tmp_path):
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=2)
    session = service.create_session("curator-window-conflicts")
    first_content = "The launch city is Lisbon."
    first_id = _ingest(service, session.id, first_content)
    fake.responses = [{"memories": [_mem(first_id, first_content)]}]
    assert curator.run_session(session.id, force=True).added == 1
    old = service.store.list_active_curated_memories(session.id)[0]

    porto = "The launch city changed to Porto."
    madrid = "The afterparty venue is in Madrid."
    porto_id = _ingest(service, session.id, porto)
    madrid_id = _ingest(service, session.id, madrid)
    fake.responses = [
        {
            "memories": [
                _mem(porto_id, porto),
                _mem(porto_id, porto),
                _mem(madrid_id, madrid, topic_key="project.afterparty_venue"),
            ]
        }
    ]
    result = curator.run_session(session.id, force=True)

    assert (result.superseded, result.added, result.noop) == (1, 1, 1)
    active = service.store.list_active_curated_memories(session.id)
    assert sorted(row.statement for row in active) == [madrid, porto]
    assert [row.supersedes_id for row in active].count(old.id) == 1
    superseded = service.store.get_curated_memory(old.id)
    assert superseded is not None and superseded.status == "superseded"


def test_restatements_become_noop_without_writes(tmp_path):
    content = "Rollout happens on Fridays after the sync."
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-noop")
    first_id = _ingest(service, session.id, content)
    fake.responses = [{"memories": [_mem(first_id, content)]}]
    assert curator.run_session(session.id).added == 1

    # Same statement modulo whitespace/case: groundable, but a restatement.
    second_content = "ROLLOUT   HAPPENS on Fridays after the sync."
    second_id = _ingest(service, session.id, second_content)
    third_content = "Rollout  happens  ON Fridays after the sync."
    third_id = _ingest(service, session.id, third_content)
    fake.responses = [
        {"memories": [_mem(second_id, content, quote=second_content)]},
        {"memories": [_mem(third_id, content, quote=third_content)]},
    ]
    result = curator.run_session(session.id, force=True)

    assert result.windows == 2
    assert result.noop == 2
    assert result.added == 0
    assert len(service.store.list_active_curated_memories(session.id)) == 1


# -- watermark, retry, skip --------------------------------------------------


def test_watermark_advances_only_on_accepted_output(tmp_path):
    fake = FakeLLM(
        [
            CuratorSchemaError("unparseable"),
            CuratorSchemaError("unparseable"),
            CuratorSchemaError("unparseable"),
            {"memories": []},
        ]
    )
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-watermark")
    _ingest(service, session.id, "A durable fact that will wait for a schema fix.")

    first = curator.run_session(session.id)

    assert first.windows == 0
    assert first.rejected_schema == 1
    assert first.status == "failed"
    assert len(fake.calls) == 3
    assert service.store.get_curator_state(session.id).last_message_seq == 0

    second = curator.run_session(session.id)

    assert second.windows == 1
    assert service.store.get_curator_state(session.id).last_message_seq == 1
    trace_types = [trace.event_type for trace in service.store.list_traces(session.id)]
    assert "curator_schema_error" in trace_types


def test_schema_failure_retries_inside_one_run_then_succeeds(tmp_path):
    content = "The design review moved to Thursday."
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-retry")
    message_id = _ingest(service, session.id, content)
    fake.responses = [
        CuratorSchemaError("unparseable"),
        {"memories": [_mem(message_id, content)]},
    ]

    result = curator.run_session(session.id)

    assert result.windows == 1
    assert result.added == 1
    assert result.rejected_schema == 0
    assert len(fake.calls) == 2


def test_window_is_skipped_after_three_consecutive_failures(tmp_path):
    fake = FakeLLM([CuratorLLMError("provider down")] * 6)
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-skip")
    _ingest(service, session.id, "A fact that never gets curated due to provider errors.")

    first = curator.run_session(session.id)
    second = curator.run_session(session.id)
    third = curator.run_session(session.id)

    assert (first.status, second.status) == ("failed", "failed")
    assert third.status == "skipped"
    assert first.llm_errors + second.llm_errors + third.llm_errors == 3
    state = service.store.get_curator_state(session.id)
    assert state is not None
    assert state.last_message_seq == 1
    assert state.llm_errors == 3
    trace_types = [trace.event_type for trace in service.store.list_traces(session.id)]
    assert "curator_window_skipped" in trace_types
    assert curator.run_session(session.id).status == "no_messages"


def test_idle_gate_flushes_partial_window_only_when_due(tmp_path):
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(
        tmp_path,
        fake,
        memoryos_curator_window_messages=3,
        memoryos_curator_idle_flush_s=3_600.0,
    )
    session = service.create_session("curator-idle")
    _ingest(service, session.id, "One message is below the window size.")

    idle = curator.run_session(session.id)

    assert idle.status == "idle"
    assert idle.windows == 0
    assert service.store.get_curator_state(session.id) is None

    forced = curator.run_session(session.id, force=True)

    assert forced.windows == 1
    assert forced.status == "ok"
    assert service.store.get_curator_state(session.id).last_message_seq == 1


def test_idle_gate_flushes_when_oldest_message_waited_long_enough(tmp_path):
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(
        tmp_path,
        fake,
        memoryos_curator_window_messages=3,
        memoryos_curator_idle_flush_s=0.0,
    )
    session = service.create_session("curator-idle-due")
    _ingest(service, session.id, "Oldest message waited long enough to flush.")

    result = curator.run_session(session.id)

    assert result.windows == 1
    assert result.status == "ok"


# -- prompt rendering --------------------------------------------------------


def test_prompt_renders_ids_speakers_and_bounded_context(tmp_path):
    fake = FakeLLM([{"memories": []}])
    service, curator = _service(tmp_path, fake, memoryos_curator_window_messages=1)
    session = service.create_session("curator-prompt")
    first_id = _ingest(service, session.id, "Alice notes the launch plan.", speaker_name="Alice")
    second = service.ingest(
        session.id,
        MessageCreate(
            role=Role.ASSISTANT,
            content="Bob records the launch decision.",
            metadata={"participant_id": "agent-7"},
        ),
    ).message
    third_id = _ingest(service, session.id, "Carol confirms the timeline.")

    curator.run_session(session.id, force=True)

    assert len(fake.calls) == 3
    system, first_user = fake.calls[0]
    assert system == CURATE_ROOM_SYSTEM_PROMPT
    assert "Do NOT store" in system
    assert "verbatim" in system
    assert f"[{first_id}] Alice, human (message): Alice notes the launch plan." in first_user
    assert "Active memories (reuse a topic_key" in first_user
    assert "- fact project.launch_city:" in first_user or "(none)" in first_user
    _, third_user = fake.calls[2]
    context_section = third_user.split("Messages to curate:", 1)[0]
    assert f"[{first_id}] Alice, human (message):" in context_section
    assert f"[{second.id}] agent-7, agent (message):" in context_section
    assert "Earlier context" in context_section
    assert f"[{third_id}] user, human (message): Carol confirms the timeline." in third_user


# -- missing LLM -------------------------------------------------------------


def test_missing_llm_leaves_the_watermark_unchanged(tmp_path):
    service, curator = _service(tmp_path, None)
    session = service.create_session("curator-no-key")
    _ingest(service, session.id, "Pending until a key is configured.")

    result = curator.run_session(session.id)

    assert result.status == "llm_unavailable"
    assert result.error_code == "curator_llm_key_missing"
    assert service.store.get_curator_state(session.id) is None
