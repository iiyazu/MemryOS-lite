"""The curate repair loop as a LangGraph state graph.

::

    START -> extract -> check --(violations, repairs left)--> repair -> check
                          \\--(clean, or no repairs left)--> consolidate -> END

``extract`` asks the LLM for assignments, lessons and memories; ``check``
validates the reply deterministically (quotes are exact substrings, every
failure is accounted for exactly once, lessons exist); ``repair`` sends the
reply and the broken rules back to the LLM; ``consolidate`` turns what is valid
into new memory versions. After the last repair, whatever is still invalid is
dropped and missing failures are reported as ``unaccounted``.

Provider errors (:class:`CuratorLLMError`) propagate to the caller; a reply that
is not JSON counts as a violation and is repaired like any other.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from memoryos_lite.curator.curate import (
    CheckResult,
    CurateActivity,
    CurateRequest,
    CurateResponse,
    check_reply,
    consolidate,
)
from memoryos_lite.curator.llm import CuratorLLM, CuratorSchemaError
from memoryos_lite.curator.prompt import (
    CURATE_COLLAB_SYSTEM_PROMPT,
    CURATE_ROOM_SYSTEM_PROMPT,
    CURATE_SYSTEM_PROMPT,
    build_collab_curate_prompt,
    build_curate_prompt,
    build_repair_prompt,
    build_room_curate_prompt,
    render_activity,
)

SYSTEM_PROMPTS = {
    "module": CURATE_SYSTEM_PROMPT,
    "room": CURATE_ROOM_SYSTEM_PROMPT,
    "collab": CURATE_COLLAB_SYSTEM_PROMPT,
}
#: What a repair reply must repeat in full, per profile.
REPAIR_PARTS = {"collab": "memories, assignments and conflicts"}
#: The violation recorded when a reply is not a JSON object (still present after
#: the last repair means the window produced nothing usable).
REPLY_NOT_JSON = "the reply was not a JSON object"


class CurateState(TypedDict, total=False):
    request: CurateRequest
    prompt: str
    reply: dict[str, Any] | None
    reply_error: str | None
    llm_calls: int
    check: CheckResult
    initial_violations: list[str]
    response: CurateResponse


def _label(request: CurateRequest, activity: CurateActivity) -> str:
    """A collab message shows its xmuse kind (handoff, decision, ...) instead of "message"."""
    if request.profile == "collab" and activity.type == "message" and activity.kind:
        return activity.kind
    return activity.type


def render_request(request: CurateRequest) -> str:
    context = [
        render_activity(a.id, a.speaker, _label(request, a), a.text) for a in request.context
    ]
    window = [render_activity(a.id, a.speaker, _label(request, a), a.text) for a in request.window]
    failure_ids = [activity.id for activity in request.failures]
    if request.profile == "collab":
        return build_collab_curate_prompt(
            scope_id=request.scope_id,
            entries=[
                (memory.id, memory.kind, memory.topic_key, memory.statement)
                for memory in sorted(request.active, key=lambda m: (m.version, m.id))
            ],
            context=context,
            window=window,
            failure_ids=failure_ids,
        )
    if request.profile == "room":
        return build_room_curate_prompt(
            memories=[
                (memory.kind, memory.topic_key, memory.statement)
                for memory in sorted(request.active, key=lambda m: m.version)
            ],
            context=context,
            window=window,
            failure_ids=failure_ids,
        )
    lessons = [
        (memory.topic_key, memory.occurrences, memory.statement)
        for memory in sorted(request.active, key=lambda m: (-m.occurrences, -m.version))
        if memory.kind == "lesson"
    ]
    others = [
        (memory.kind, memory.topic_key, memory.statement)
        for memory in sorted(request.active, key=lambda m: -m.version)
        if memory.kind != "lesson"
    ]
    return build_curate_prompt(
        scope_id=request.scope_id,
        lessons=lessons,
        others=others,
        context=context,
        window=window,
        failure_ids=failure_ids,
    )


def _ask(llm: CuratorLLM, system: str, user: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        reply = llm.complete_json(system, user)
    except CuratorSchemaError:
        return None, REPLY_NOT_JSON
    if not isinstance(reply, dict):
        return None, REPLY_NOT_JSON
    return reply, None


def build_curate_graph(llm: CuratorLLM) -> Any:
    """Compile the curate graph around one LLM client."""

    def extract(state: CurateState) -> CurateState:
        prompt = render_request(state["request"])
        reply, error = _ask(llm, SYSTEM_PROMPTS[state["request"].profile], prompt)
        return {"prompt": prompt, "reply": reply, "reply_error": error, "llm_calls": 1}

    def check(state: CurateState) -> CurateState:
        result = check_reply(state["request"], state.get("reply"), state.get("reply_error"))
        update: CurateState = {"check": result}
        if "initial_violations" not in state:
            update["initial_violations"] = list(result.violations)
        return update

    def route(state: CurateState) -> str:
        repairs_done = state["llm_calls"] - 1
        if state["check"].violations and repairs_done < state["request"].max_repairs:
            return "repair"
        return "consolidate"

    def repair(state: CurateState) -> CurateState:
        previous = state.get("reply")
        previous_text = json.dumps(previous, ensure_ascii=False) if previous is not None else ""
        user = build_repair_prompt(
            state["prompt"],
            previous_text,
            state["check"].violations,
            REPAIR_PARTS.get(state["request"].profile),
        )
        reply, error = _ask(llm, SYSTEM_PROMPTS[state["request"].profile], user)
        return {"reply": reply, "reply_error": error, "llm_calls": state["llm_calls"] + 1}

    def finish(state: CurateState) -> CurateState:
        result = state["check"]
        response = consolidate(state["request"], result)
        response.diagnostics.llm_calls = state["llm_calls"]
        response.diagnostics.repairs = state["llm_calls"] - 1
        response.diagnostics.initial_violations = state.get("initial_violations", [])
        response.diagnostics.final_violations = list(result.violations)
        return {"response": response}

    graph = StateGraph(CurateState)
    graph.add_node("extract", extract)
    graph.add_node("check", check)
    graph.add_node("repair", repair)
    graph.add_node("consolidate", finish)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "check")
    graph.add_conditional_edges("check", route, {"repair": "repair", "consolidate": "consolidate"})
    graph.add_edge("repair", "check")
    graph.add_edge("consolidate", END)
    return graph.compile()


def run_curate(request: CurateRequest, llm: CuratorLLM) -> CurateResponse:
    """Run one curate request through the graph."""

    state = build_curate_graph(llm).invoke({"request": request})
    response: CurateResponse = state["response"]
    return response


__all__ = ["REPLY_NOT_JSON", "CurateState", "build_curate_graph", "render_request", "run_curate"]
