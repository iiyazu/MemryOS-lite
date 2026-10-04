"""``memory_ask``: agentic retrieval over a session's history, as a LangGraph graph.

::

    START -> retrieve -> grade --(enough, or no rounds / LLM left)--> finalize -> END
                ^          \\--(not enough)--> rewrite --(new query)--/
                                                  \\--(no new query)--> finalize

``retrieve`` runs one hybrid recall (``build_context`` + ``source_evidence/v2``)
and merges new items. ``grade`` is deterministic: the evidence is enough when
some current (not outdated) item covers at least half of the question's
keywords. ``rewrite`` asks the LLM for one better query. ``finalize`` puts
current items first, outdated ones last with the current statement attached,
within the token budget.

Outdated means the item contains the verbatim quote of a superseded memory
(see :mod:`memoryos_lite.retrieval.supersede`); unlike ``source_evidence/v2``,
the ask response may carry that mark explicitly.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from memoryos_lite.curator.llm import CuratorLLM, CuratorLLMError, CuratorSchemaError
from memoryos_lite.retrieval.lexical import tokenize
from memoryos_lite.retrieval.supersede import SupersededQuote, match_superseded
from memoryos_lite.schemas import SupersededQuotePayload

ASK_SCHEMA = "memoryos_memory_ask/v1"
MAX_ROUNDS = 2
ENOUGH_COVERAGE = 0.5
_STOPWORDS = frozenset(
    "a an and are as at be by did do does for from had has have how i in is it its of on "
    "or our the their them they this to was we were what when where which who why will "
    "with you your now still current currently".split()
)

REWRITE_SYSTEM_PROMPT = """You help an agent search its project's history. Given a question \
and the evidence found so far, write one new search query that is more likely to find the \
missing or current information. Prefer concrete nouns, names, and identifiers that the \
answer would contain. Evidence marked [outdated] states a value that is no longer current; \
search for what replaced it. Reply with one JSON object: {"query": "..."}. Reply with \
{"query": ""} when the evidence already answers the question."""


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    # Task given to the context composer; defaults to the question.
    task: str | None = Field(default=None, max_length=2000)
    budget: int = Field(default=800, ge=1, le=800)
    max_rounds: int = Field(default=MAX_ROUNDS, ge=0, le=MAX_ROUNDS)
    superseded: list[SupersededQuotePayload] = Field(default_factory=list, max_length=64)


class AskItem(BaseModel):
    rank: int
    item_id: str
    layer: str
    text: str
    estimated_tokens: int
    document_id: str | None = None
    source_refs: list[dict[str, str]] = Field(default_factory=list)
    query: str
    outdated: bool = False
    current: str | None = None


class AskDiagnostics(BaseModel):
    retrievals: int = 0
    llm_calls: int = 0
    stopped: str = ""
    omitted: int = 0


class AskResponse(BaseModel):
    schema_version: str = ASK_SCHEMA
    session_id: str
    question: str
    queries: list[str]
    items: list[AskItem]
    diagnostics: AskDiagnostics


Retriever = Callable[[str], list[dict[str, Any]]]


class AskState(TypedDict, total=False):
    question: str
    queries: list[str]
    found: list[dict[str, Any]]
    retrievals: int
    llm_calls: int
    enough: bool
    stopped: str


def keywords(text: str) -> set[str]:
    """Content words: Latin tokens of 3+ letters outside a stopword list, CJK bigrams.

    Latin words are cut to their first five letters, a crude stem so that
    "launch" and "launches" match.
    """

    out: set[str] = set()
    for token in tokenize(text):
        if re.fullmatch(r"[a-z0-9]+", token):
            if len(token) >= 3 and token not in _STOPWORDS:
                out.add(token[:5])
        elif len(token) == 2:
            out.add(token)
    return out


def coverage(question: str, text: str) -> float:
    wanted = keywords(question)
    if not wanted:
        return 1.0
    return len(wanted & keywords(text)) / len(wanted)


def _render_for_rewrite(question: str, found: Sequence[dict[str, Any]]) -> str:
    lines = []
    for index, item in enumerate(found[:12], start=1):
        flag = "[outdated] " if item["outdated"] else ""
        lines.append(f"{index}. {flag}{str(item['text'])[:400]}")
    return f"Question: {question}\n\nEvidence so far:\n" + ("\n".join(lines) or "(none)")


def build_ask_graph(
    retrieve: Retriever,
    marks: Sequence[SupersededQuote],
    llm: CuratorLLM | None,
    *,
    max_rounds: int,
) -> Any:
    """Compile the ask graph around a retriever, superseded marks and an optional LLM.

    LangGraph ships in the ``remote`` extra; it is imported here so the request and
    response models stay importable without it.
    """

    from langgraph.graph import END, START, StateGraph

    def retrieve_node(state: AskState) -> AskState:
        query = state["queries"][-1]
        found = list(state.get("found", []))
        seen = {item["item_id"] for item in found}
        for item in retrieve(query):
            if item["item_id"] in seen:
                continue
            seen.add(item["item_id"])
            mark = match_superseded(str(item.get("text", "")), marks)
            found.append(
                {
                    **item,
                    "query": query,
                    "outdated": mark is not None,
                    "current": mark.current if mark is not None else None,
                }
            )
        return {"found": found, "retrievals": state.get("retrievals", 0) + 1}

    def grade(state: AskState) -> AskState:
        best = max(
            (
                coverage(state["question"], str(item["text"]))
                for item in state["found"]
                if not item["outdated"]
            ),
            default=0.0,
        )
        return {"enough": best >= ENOUGH_COVERAGE}

    def after_grade(state: AskState) -> str:
        if state["enough"]:
            return "enough"
        if llm is None:
            return "no_llm"
        if state["retrievals"] > max_rounds:
            return "no_rounds"
        return "rewrite"

    def rewrite(state: AskState) -> AskState:
        assert llm is not None
        calls = state.get("llm_calls", 0) + 1
        try:
            reply = llm.complete_json(
                REWRITE_SYSTEM_PROMPT, _render_for_rewrite(state["question"], state["found"])
            )
        except (CuratorSchemaError, CuratorLLMError):
            return {"llm_calls": calls, "stopped": "rewrite_failed"}
        query = reply.get("query") if isinstance(reply, dict) else None
        query = query.strip()[:500] if isinstance(query, str) else ""
        if not query or query in state["queries"]:
            return {"llm_calls": calls, "stopped": "no_new_query"}
        return {"llm_calls": calls, "queries": [*state["queries"], query]}

    def after_rewrite(state: AskState) -> str:
        return "finalize" if state.get("stopped") else "retrieve"

    def finalize(state: AskState) -> AskState:
        if state.get("stopped"):
            return {}
        if state.get("enough"):
            return {"stopped": "enough"}
        return {"stopped": "no_llm" if llm is None else "no_rounds"}

    graph = StateGraph(AskState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("grade", grade)
    graph.add_node("rewrite", rewrite)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges(
        "grade",
        after_grade,
        {"enough": "finalize", "no_llm": "finalize", "no_rounds": "finalize", "rewrite": "rewrite"},
    )
    graph.add_conditional_edges(
        "rewrite", after_rewrite, {"retrieve": "retrieve", "finalize": "finalize"}
    )
    graph.add_edge("finalize", END)
    return graph.compile()


def run_ask(
    *,
    session_id: str,
    request: AskRequest,
    retrieve: Retriever,
    marks: Sequence[SupersededQuote],
    llm: CuratorLLM | None,
) -> AskResponse:
    """Run one ask through the graph and select current items first within the budget."""

    state = build_ask_graph(retrieve, marks, llm, max_rounds=request.max_rounds).invoke(
        {"question": request.question, "queries": [request.question]}
    )
    found: list[dict[str, Any]] = state.get("found", [])
    ordered = [item for item in found if not item["outdated"]] + [
        item for item in found if item["outdated"]
    ]
    items: list[AskItem] = []
    spent = 0
    omitted = 0
    for item in ordered:
        tokens = int(item.get("estimated_tokens", 0))
        if spent + tokens > request.budget:
            omitted += 1
            continue
        spent += tokens
        items.append(
            AskItem(
                rank=len(items) + 1,
                item_id=str(item["item_id"]),
                layer=str(item.get("layer", "")),
                text=str(item.get("text", "")),
                estimated_tokens=tokens,
                document_id=item.get("document_id"),
                source_refs=[
                    {k: str(v) for k, v in ref.items()} for ref in item.get("source_refs", [])
                ],
                query=str(item["query"]),
                outdated=bool(item["outdated"]),
                current=item.get("current"),
            )
        )
    return AskResponse(
        session_id=session_id,
        question=request.question,
        queries=list(state["queries"]),
        items=items,
        diagnostics=AskDiagnostics(
            retrievals=int(state.get("retrievals", 0)),
            llm_calls=int(state.get("llm_calls", 0)),
            stopped=str(state.get("stopped", "")),
            omitted=omitted,
        ),
    )


def render_ask_item(item: AskItem) -> str:
    """How a host may show an item to its agent: outdated items carry the current value."""

    if not item.outdated:
        return item.text
    note = f"[outdated; current: {item.current}] " if item.current else "[outdated] "
    return note + item.text


__all__ = [
    "ASK_SCHEMA",
    "AskItem",
    "AskRequest",
    "AskResponse",
    "build_ask_graph",
    "coverage",
    "keywords",
    "render_ask_item",
    "run_ask",
]
