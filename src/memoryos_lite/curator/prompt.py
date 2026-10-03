# ruff: noqa: E501  (prompt text kept byte-for-byte across renames)
"""Curator prompt text and message rendering.

``CURATOR_SYSTEM_PROMPT`` (deterministic consolidation) is the constant to
iterate on.  ``CURATOR_SYSTEM_PROMPT_LLM_SUPERSEDE`` is the earlier prompt in
which the LLM picks supersede targets; it is kept verbatim so the
``llm`` consolidation mode stays reproducible for comparisons.
"""

from __future__ import annotations

from memoryos_lite.schemas import Message, Role
from memoryos_lite.store_curator import CuratedMemoryRow

CURATOR_SYSTEM_PROMPT = """You are the Memory Curator for MemoryOS. You read a window of \
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
- Use "noop" when the messages only restate an active memory.

Rules:
- Write one self-contained statement per memory, in the language of the source.
- Copy "quote" verbatim from the message text; every quote must be an exact substring of \
the message it cites.
- Provide 1 to 3 sources per memory; every message_id must be one of the rendered ids.
- A noop operation carries no other fields.

Reply with one JSON object:
{"operations":[{"op":"add|noop","kind":"fact|decision|rule|preference|lesson",\
"topic_key":"dotted.key","statement":"...","sources":[{"message_id":"...","quote":"..."}]}]}"""

# Kept byte-for-byte (cached curator replies are keyed on this text).
CURATOR_SYSTEM_PROMPT_LLM_SUPERSEDE = """You are the Memory Curator for MemoryOS. You read a window of \
session messages and extract durable, source-grounded memories, then reconcile them with \
the active memories already stored for this session.

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

Reconciliation:
- Prefer "update" with "supersedes" when a new statement changes the value of an active \
memory; the newer statement may come from a different speaker than the original.
- Use "noop" when the messages only restate an active memory.
- Otherwise use "add" for a genuinely new memory.

Rules:
- Write one self-contained statement per memory, in the language of the source.
- Copy "quote" verbatim from the message text; every quote must be an exact substring of \
the message it cites.
- Provide 1 to 3 sources per memory; every message_id must be one of the rendered ids.
- "topic_key" is a stable dotted key such as "project.launch_city".
- A noop operation carries no other fields.

Reply with one JSON object:
{"operations":[{"op":"add|update|noop","kind":"fact|decision|rule|preference|lesson",\
"topic_key":"dotted.key","statement":"...","sources":[{"message_id":"...","quote":"..."}],\
"supersedes":"<active memory id>|null"}]}"""


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


def render_message(message: Message) -> str:
    label, speaker_kind = speaker_label(message)
    activity_type = message.metadata.get("activity_type")
    if not isinstance(activity_type, str):
        # Untyped messages render exactly as before (prompt caches stay valid).
        return f"[{message.id}] {label} ({speaker_kind}): {message.content}"
    content = (
        _bounded_gate_log(message.content) if activity_type == "gate_failure" else message.content
    )
    return f"[{message.id}] {label} ({speaker_kind}, {activity_type}): {content}"


def render_active_memories(memories: list[CuratedMemoryRow]) -> str:
    if not memories:
        return "(none)"
    return "\n".join(
        f"- [{memory.id}] {memory.kind} {memory.topic_key}: {memory.statement}"
        for memory in memories
    )


ACTIVE_HEADER_LLM_SUPERSEDE = (
    'Active memories (reconcile against these; "supersedes" must use an id from this list):'
)
MODULE_NOTICE = (
    "This session is the long-term memory of module {module_id}, kept for the agent that "
    "owns it. Messages are tagged with their activity type. Record decisions still in force "
    "for this module, and lessons: a lesson is a concrete mistake to avoid and must quote at "
    "least one review_objection or gate_failure message. Contract revisions are tracked "
    "separately; do not restate contract text as memories."
)
ACTIVE_HEADER_DETERMINISTIC = (
    "Active memories (reuse a topic_key from this list for the same subject):"
)


def build_user_prompt(
    *,
    context_messages: list[Message],
    window_messages: list[Message],
    active_memories: list[CuratedMemoryRow],
    active_header: str = ACTIVE_HEADER_LLM_SUPERSEDE,
    module_id: str | None = None,
) -> str:
    context_block = (
        "\n".join(render_message(message) for message in context_messages)
        if context_messages
        else "(none)"
    )
    window_block = "\n".join(render_message(message) for message in window_messages)
    module_block = (
        MODULE_NOTICE.format(module_id=module_id) + "\n\n" if module_id is not None else ""
    )
    return (
        f"{module_block}{active_header}\n"
        f"{render_active_memories(active_memories)}\n\n"
        "Earlier context (read-only; you may quote these messages):\n"
        f"{context_block}\n\n"
        "Messages to curate:\n"
        f"{window_block}"
    )
