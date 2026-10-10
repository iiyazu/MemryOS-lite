# ruff: noqa: E501  (prompt text kept byte-for-byte across renames)
"""Curate prompt text and activity rendering for the three profiles.

``CURATE_SYSTEM_PROMPT`` is the module profile (lesson log with closed-world
failure accounting). ``CURATE_ROOM_SYSTEM_PROMPT`` is the room profile used by
the session curator; its rules for what to store and how to key it are the
earlier room curator prompt, unchanged, with the reply in the curate format.
``CURATE_COLLAB_SYSTEM_PROMPT`` is the collab profile: proposed alignment
entries for one xmuse topic, with answered questions and suspected conflicts.
"""

from __future__ import annotations

from collections.abc import Sequence

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

CURATE_COLLAB_SYSTEM_PROMPT = """You are the alignment curator for one topic in which several \
AI agents and a human collaborate. You read new topic messages and propose the entries the team \
must stay aligned on that are not recorded yet. Everything you return is a proposal: the topic \
owner or the human confirms it. Messages are tagged with their kind: message, handoff, \
review_request, decision, assumption, or question.

Entry kinds:
- decision: a choice that was made and is in force (interfaces, data formats, scope)
- convention: a naming, interface, or process rule the team follows
- assumption: something an agent proceeds on without confirmation
- question: an open question someone must answer; name who should answer if the messages say
- lesson: a mistake or pitfall to avoid

Rules:
- Active entries are already recorded, many declared by the agents themselves. Never propose \
one again, even reworded.
- To replace an active entry whose value changed, reuse its exact topic_key; MemoryOS proposes \
the new entry as superseding it.
- When a message answers an active question, propose the answer (usually a decision) with \
"resolves": [the question ids].
- Keep each statement short, but keep every qualifier: scope, conditions, exceptions, units. \
"Amounts are Decimal strings in the payment API, except ledger totals" must not become \
"Amounts are Decimal strings".
- If two entries seem to contradict each other (two active entries, or an active entry and \
one you propose), report a conflict and do not pick a side. Use active ids; for an entry you \
propose in this reply, use its topic_key.
- Check every review_request and handoff against each active convention and decision. If the \
work it describes breaks one (another format, unit, name, or scope) and no message in this \
window replaced that entry, propose what the message does as an entry quoting it and report a \
conflict between that entry and the active id.
- Do not store who does what (the host tracks assignments), plans, status updates, handoff \
boilerplate, chit-chat, or values no longer in effect.
- Each review_objection or gate_failure listed under "Failures to account for" gets exactly one \
assignment: {"activity_id":"...","lesson":"<topic_key>","quote":"<exact substring of that \
activity>"} with the lesson defined in "lessons" (the mistake and what to do instead), or \
{"activity_id":"...","dismiss":"<short reason>"}. Do not repeat that lesson in "memories".
- Topic keys name the subject, not the value. Copy every quote verbatim from the message it \
cites, 1 to 3 sources per entry. Write statements in the language of the source.

Reply with one JSON object:
{"memories":[{"kind":"decision|convention|assumption|question|lesson","topic_key":"dotted.key",\
"statement":"...","sources":[{"activity_id":"...","quote":"..."}],"resolves":["..."]}],\
"conflicts":[{"a_id":"...","b_id":"...","reason":"...","sources":[{"activity_id":"...",\
"quote":"..."}]}],"assignments":[{"activity_id":"...","lesson":"...","quote":"..."}],\
"lessons":[{"topic_key":"...","statement":"..."}]}"""

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
    return prompt + _failure_block(failure_ids)


def _failure_block(failure_ids: Sequence[str]) -> str:
    if not failure_ids:
        return ""
    return (
        "\n\nFailures to account for (each needs exactly one assignment, as in "
        '{"assignments":[{"activity_id":"...","lesson":"<topic_key>","quote":"..."}]} or '
        '{"activity_id":"...","dismiss":"<reason>"}): ' + ", ".join(failure_ids)
    )


def build_collab_curate_prompt(
    *,
    scope_id: str,
    entries: Sequence[tuple[str, str, str, str]],
    context: Sequence[str],
    window: Sequence[str],
    failure_ids: Sequence[str],
) -> str:
    """Render one collab-profile request; ``entries`` holds ``(id, kind, topic_key, statement)``."""

    entry_block = (
        "\n".join(f"- [{i}] {kind} {key}: {statement}" for i, kind, key, statement in entries)
        or "(none)"
    )
    return (
        f"Topic: {scope_id}\n\n"
        "Active entries (never propose these again; reuse a topic_key to replace one):\n"
        f"{entry_block}\n\n"
        "Earlier context (read-only; you may quote these messages):\n"
        f"{chr(10).join(context) or '(none)'}\n\n"
        "Messages to curate:\n"
        f"{chr(10).join(window)}"
    ) + _failure_block(failure_ids)


def build_repair_prompt(
    prompt: str,
    previous_reply: str,
    violations: list[str],
    parts: str | None = None,
) -> str:
    parts = parts or "assignments, lessons and memories"
    reply = previous_reply[:REPAIR_REPLY_CHARS] or "(no JSON object)"
    rules = "\n".join(f"- {violation}" for violation in violations)
    return (
        f"{prompt}\n\n"
        f"Your previous reply:\n{reply}\n\n"
        f"It broke these rules:\n{rules}\n\n"
        f"Reply again with the complete corrected JSON object: all {parts}, not only the fixes."
    )
