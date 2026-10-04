# ruff: noqa: E501  (prompt text kept byte-for-byte across renames)
"""Curate prompt text and activity rendering for both profiles.

``CURATE_SYSTEM_PROMPT`` is the module profile (lesson log with closed-world
failure accounting). ``CURATE_ROOM_SYSTEM_PROMPT`` is the room profile used by
the session curator; its rules for what to store and how to key it are the
earlier room curator prompt, unchanged, with the reply in the curate format.
"""

from __future__ import annotations

from collections.abc import Sequence

from memoryos_lite.schemas import Message, Role


def speaker_label(message: Message) -> tuple[str, str]:
    """Return ``(label, human|agent)`` for one message.

    xmuse writes ``participant_id`` and an eval harness may write
    ``speaker_name``; otherwise the role stands in for the label.
    """

    speaker_kind = "human" if message.role is Role.USER else "agent"
    for key in ("speaker_name", "participant_id"):
        value = message.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), speaker_kind
    return message.role.value, speaker_kind


#: A gate failure log is shown to the LLM as head + tail; quotes are still
#: grounded against the full stored text.
GATE_LOG_HEAD_CHARS = 1_500
GATE_LOG_TAIL_CHARS = 2_500


def _bounded_gate_log(content: str) -> str:
    if len(content) <= GATE_LOG_HEAD_CHARS + GATE_LOG_TAIL_CHARS:
        return content
    omitted = len(content) - GATE_LOG_HEAD_CHARS - GATE_LOG_TAIL_CHARS
    return (
        f"{content[:GATE_LOG_HEAD_CHARS]}\n[... {omitted} characters of the log omitted ...]\n"
        f"{content[-GATE_LOG_TAIL_CHARS:]}"
    )


CURATE_SYSTEM_PROMPT = """You are the Memory Curator for one software module. You keep the \
module's lesson log and its decisions for the agent that owns the module, so that a restarted \
or replaced owner does not repeat mistakes. You read new module activity; activities are tagged \
message, review_objection, gate_failure, or contract_revision.

1. Account for every failure. Each review_objection and gate_failure listed under "Failures to \
account for" gets exactly one assignment:
- {"activity_id": "...", "lesson": "<topic_key>", "quote": "<exact substring of that activity>"} \
when it shows a concrete mistake in the module's work. Use an active lesson's topic_key when \
the root cause is the same, even if the failing test, tool, or wording differs. Two failures \
share a lesson only if fixing one root cause would have prevented both; related but different \
mistakes get different lessons.
- {"activity_id": "...", "dismiss": "<short reason>"} when it is not a mistake worth \
remembering, for example flaky infrastructure, a question, or an objection that was withdrawn.

2. Lessons. Define every new lesson in "lessons" with a topic_key and a self-contained \
statement: the mistake and what to do instead. You may also give a better statement for an \
active lesson that receives a failure now. Never list a lesson without assigning a failure to it.

3. Decisions and facts. In "memories", record decisions still in force for this module and \
durable facts about it, each quoting 1 to 3 activities. Reuse an active memory's topic_key when \
it is about the same subject, even if the value changed; MemoryOS keeps the newest per \
topic_key. Do not restate active memories unchanged. Do not restate contract text (contracts \
are tracked separately). Do not store plans, status updates, questions, options still under \
discussion, or values that are no longer in effect.

Topic keys name the subject, not the value: "billing.amount_repr", not \
"billing.amount_repr.cents". Every quote must be an exact substring of the activity it cites. \
Write statements in the language of the source.

Reply with one JSON object:
{"assignments":[{"activity_id":"...","lesson":"...","quote":"..."},{"activity_id":"...",\
"dismiss":"..."}],"lessons":[{"topic_key":"...","statement":"..."}],"memories":[{"kind":\
"decision|fact","topic_key":"...","statement":"...","sources":[{"activity_id":"...",\
"quote":"..."}]}]}"""

CURATE_ROOM_SYSTEM_PROMPT = """You are the Memory Curator for MemoryOS. You read a window of \
session messages and extract durable, source-grounded memories that are in effect now.

Store only durable knowledge:
- fact: an established fact about the user, project, people, or environment
- decision: a choice that was made and still stands
- rule: a project/team rule or standing instruction
- preference: a user preference that should shape future behavior
- lesson: a learned constraint, pitfall, or mistake to avoid

Do NOT store:
- questions, chit-chat, greetings, or small talk
- hypotheticals, options still under discussion, or rejected proposals
- tentative statements that were not confirmed
- plan steps, task lists, or status updates
- the wrapper text of instructions addressed to an agent; store only the rule or fact inside
- old, previous, replaced, or abandoned values. When a message mentions a value that is no \
longer in effect ("we used to use X", "X was dropped", "before we moved off X"), do not \
store that value; store the current value only if the message itself states it.

Topic keys:
- "topic_key" names the subject, not the value: "project.launch_city", not \
"project.launch_city.porto".
- When a statement is about the same subject as an active memory, reuse that memory's \
exact topic_key, even if the value changed. MemoryOS keeps the newest statement per \
topic_key; you never decide which memory is outdated.
- Leave out memories that only restate an active memory.

Rules:
- Write one self-contained statement per memory, in the language of the source.
- Copy "quote" verbatim from the message text; every quote must be an exact substring of \
the message it cites.
- Provide 1 to 3 sources per memory; every activity_id must be one of the rendered ids.

Reply with one JSON object:
{"memories":[{"kind":"fact|decision|rule|preference|lesson","topic_key":"dotted.key",\
"statement":"...","sources":[{"activity_id":"...","quote":"..."}]}]}"""

#: Previous replies are echoed into a repair prompt up to this many characters.
REPAIR_REPLY_CHARS = 6_000


def render_activity(activity_id: str, speaker: str, activity_type: str, text: str) -> str:
    body = _bounded_gate_log(text) if activity_type == "gate_failure" else text
    return f"[{activity_id}] {speaker or 'unknown'} ({activity_type}): {body}"


def build_curate_prompt(
    *,
    scope_id: str,
    lessons: Sequence[tuple[str, int, str]],
    others: Sequence[tuple[str, str, str]],
    context: Sequence[str],
    window: Sequence[str],
    failure_ids: Sequence[str],
) -> str:
    """Render one module-profile curate request.

    ``lessons`` holds ``(topic_key, occurrences, statement)``, ``others`` holds
    ``(kind, topic_key, statement)``, and ``context``/``window`` are rendered
    activities (see :func:`render_activity`).
    """

    lesson_block = (
        "\n".join(
            f"- {key} (failed {count} time{'s' if count != 1 else ''}): {statement}"
            for key, count, statement in lessons
        )
        or "(none)"
    )
    other_block = (
        "\n".join(f"- {kind} {key}: {statement}" for kind, key, statement in others) or "(none)"
    )
    return (
        f"Module: {scope_id}\n\n"
        "Active lessons (reuse a topic_key when a failure has the same root cause):\n"
        f"{lesson_block}\n\n"
        "Active decisions and facts (reuse a topic_key for the same subject):\n"
        f"{other_block}\n\n"
        "Earlier activity (read-only; memories may quote it):\n"
        f"{chr(10).join(context) or '(none)'}\n\n"
        "Activities to curate:\n"
        f"{chr(10).join(window)}\n\n"
        "Failures to account for (each needs exactly one assignment): "
        f"{', '.join(failure_ids) or '(none)'}"
    )


def build_room_curate_prompt(
    *,
    memories: Sequence[tuple[str, str, str]],
    context: Sequence[str],
    window: Sequence[str],
    failure_ids: Sequence[str],
) -> str:
    """Render one room-profile curate request; ``memories`` holds ``(kind, topic_key, statement)``."""

    memory_block = (
        "\n".join(f"- {kind} {key}: {statement}" for kind, key, statement in memories) or "(none)"
    )
    prompt = (
        "Active memories (reuse a topic_key from this list for the same subject):\n"
        f"{memory_block}\n\n"
        "Earlier context (read-only; you may quote these messages):\n"
        f"{chr(10).join(context) or '(none)'}\n\n"
        "Messages to curate:\n"
        f"{chr(10).join(window)}"
    )
    if failure_ids:
        prompt += (
            "\n\nFailures to account for (each needs exactly one assignment, as in "
            '{"assignments":[{"activity_id":"...","lesson":"<topic_key>","quote":"..."}]} or '
            '{"activity_id":"...","dismiss":"<reason>"}): ' + ", ".join(failure_ids)
        )
    return prompt


def build_repair_prompt(prompt: str, previous_reply: str, violations: list[str]) -> str:
    reply = previous_reply[:REPAIR_REPLY_CHARS] or "(no JSON object)"
    rules = "\n".join(f"- {violation}" for violation in violations)
    return (
        f"{prompt}\n\n"
        f"Your previous reply:\n{reply}\n\n"
        f"It broke these rules:\n{rules}\n\n"
        "Reply again with the complete corrected JSON object: all assignments, lessons and "
        "memories, not only the fixes."
    )
