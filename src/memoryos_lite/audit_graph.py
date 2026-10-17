"""The dependency audit as a LangGraph state graph.

::

    START -> expand -> retrieve -> judge -> verify -> END

``expand`` asks the LLM for a few queries describing the old behaviour (skipped when the request
says so; a reply that is not usable JSON only means no expansion); ``retrieve`` fuses the
rule-expanded, LLM-expanded and recency rankings and keeps the top ``k``; ``judge`` asks the LLM
which of them depend on the old statement; ``verify`` keeps the flags whose quote is an exact
substring. Provider errors (:class:`CuratorLLMError`) propagate to the caller.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from memoryos_lite.audit import (
    EXPAND_SYSTEM,
    EXPANSIONS,
    JUDGE_SYSTEM,
    AuditDiagnostics,
    AuditRequest,
    AuditResponse,
    AuditUsage,
    Retriever,
    expand_prompt,
    judge_prompt,
    recent,
    rrf,
    rule_queries,
    verify,
)
from memoryos_lite.curator.llm import CuratorLLM, CuratorSchemaError, record_attempts


class AuditState(TypedDict, total=False):
    request: AuditRequest
    expansions: list[str]
    candidates: list[str]
    queries: int
    dense: bool
    verdicts: Any
    llm_calls: int
    response: AuditResponse


def build_audit_graph(llm: CuratorLLM, retriever: Retriever) -> Any:
    def expand(state: AuditState) -> AuditState:
        request = state["request"]
        if not request.expand or not request.items:
            return {"expansions": [], "llm_calls": 0}
        try:
            reply = llm.complete_json(
                EXPAND_SYSTEM, expand_prompt(request.old.text, request.new.text)
            )
        except CuratorSchemaError:
            return {"expansions": [], "llm_calls": 1}
        qs = reply.get("queries") if isinstance(reply, dict) else None
        qs = (
            [q.strip() for q in qs if isinstance(q, str) and q.strip()]
            if isinstance(qs, list)
            else []
        )
        return {"expansions": qs[:EXPANSIONS], "llm_calls": 1}

    def retrieve(state: AuditState) -> AuditState:
        request = state["request"]
        old, new = request.old.text, request.new.text
        rules = [old, *rule_queries(old, new)]
        by_rules, dense = retriever.rank(request.items, rules)
        lists = [by_rules, recent(request.items)]
        if state["expansions"]:
            by_llm, _ = retriever.rank(request.items, [old + "\n" + new, *state["expansions"]])
            lists.insert(1, by_llm)
        return {
            "candidates": rrf(*lists)[: request.k],
            "queries": len(rules) + len(state["expansions"]),
            "dense": dense,
        }

    def judge(state: AuditState) -> AuditState:
        request, ids = state["request"], set(state["candidates"])
        if not ids:
            return {"verdicts": {}}
        items = [item for item in request.items if item.id in ids]
        try:
            reply = llm.complete_json(
                JUDGE_SYSTEM, judge_prompt(request.old.text, request.new.text, items)
            )
        except CuratorSchemaError:
            reply = {}
        return {
            "verdicts": reply.get("verdicts") if isinstance(reply, dict) else {},
            "llm_calls": state["llm_calls"] + 1,
        }

    def finish(state: AuditState) -> AuditState:
        request = state["request"]
        flags, dropped = verify(request.items, state["candidates"], state.get("verdicts"))
        return {
            "response": AuditResponse(
                flagged=flags,
                candidates=state["candidates"],
                diagnostics=AuditDiagnostics(
                    queries=state["queries"],
                    expanded=len(state["expansions"]),
                    dense=state["dense"],
                    judged=len(state["candidates"]),
                    dropped_quotes=dropped,
                    llm_calls=state["llm_calls"],
                ),
            )
        }

    graph = StateGraph(AuditState)
    graph.add_node("expand", expand)
    graph.add_node("retrieve", retrieve)
    graph.add_node("judge", judge)
    graph.add_node("verify", finish)
    graph.add_edge(START, "expand")
    graph.add_edge("expand", "retrieve")
    graph.add_edge("retrieve", "judge")
    graph.add_edge("judge", "verify")
    graph.add_edge("verify", END)
    return graph.compile()


def run_audit(request: AuditRequest, llm: CuratorLLM, retriever: Retriever) -> AuditResponse:
    """Run one audit request through the graph; the response sums the provider usage."""

    with record_attempts() as attempts:
        state = build_audit_graph(llm, retriever).invoke({"request": request})
    response: AuditResponse = state["response"]
    usages = [a.usage for a in attempts if a.usage]
    if usages:
        response.diagnostics.usage = AuditUsage(
            **{
                k: sum(u.get(k) or 0 for u in usages)
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
        )
    return response


__all__ = ["AuditState", "build_audit_graph", "run_audit"]
