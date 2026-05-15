"""Agentic Memory Manager — LangGraph multi-agent system.

Demonstrates:
- StateGraph with rich TypedDict state
- Conditional edges (intent routing, conflict detection)
- Subgraphs (paging as nested graph)
- Tool-calling agent node
- interrupt_before for human-in-the-loop on conflicts
- Checkpointer for state persistence
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import ContextPackage, MessageCreate, Role
from memoryos_lite.tools import create_memory_tools


class AgentState(TypedDict, total=False):
    """State for the agentic memory manager."""

    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    intent: str
    should_page: bool
    context: ContextPackage | None
    conflict_detected: bool
    patch_errors: list[str]
    human_approved: bool
    result: str
    tool_turns: int


def _state_with(state: AgentState, **updates: Any) -> AgentState:
    return cast(AgentState, {**state, **updates})


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def _format_context_citations(context: ContextPackage) -> str:
    if not context.retrieved_evidence:
        return "Citations: none"
    lines = ["Citations:"]
    for index, evidence in enumerate(context.retrieved_evidence, start=1):
        marker = " superseded" if evidence.superseded else ""
        page_ref = f" page={evidence.page_id}" if evidence.page_id else ""
        text = " ".join(evidence.text.split())
        lines.append(f"[{index}] message={evidence.message_id}{page_ref}{marker}: {text}")
    return "\n".join(lines)


def _format_answer_evidence(context: ContextPackage) -> str:
    lines = []
    for index, evidence in enumerate(context.retrieved_evidence, start=1):
        marker = " historical/superseded" if evidence.superseded else ""
        text = " ".join(evidence.text.split())
        lines.append(
            f"[{index}] message_id={evidence.message_id}{marker}\n"
            f"role={evidence.role.value}\n"
            f"text={text}"
        )
    return "\n\n".join(lines)


def _citation_footer(context: ContextPackage) -> str:
    message_ids = [evidence.message_id for evidence in context.retrieved_evidence]
    if not message_ids:
        return "Sources: none"
    return "Sources: " + ", ".join(f"[{message_id}]" for message_id in message_ids)


def _tool_call_summaries(message: BaseMessage | None) -> list[dict[str, Any]]:
    calls = getattr(message, "tool_calls", []) if message is not None else []
    summaries: list[dict[str, Any]] = []
    for call in calls:
        if isinstance(call, dict):
            summaries.append(
                {
                    "name": call.get("name"),
                    "id": call.get("id"),
                    "args": call.get("args", {}),
                }
            )
    return summaries


def _latest_patch_errors(service: MemoryOSService, session_id: str) -> list[str]:
    for trace in reversed(service.store.list_traces(session_id)):
        if trace.event_type not in {"patch_rejected", "patch_verified"}:
            continue
        errors = trace.payload.get("errors", [])
        if isinstance(errors, list):
            return [str(error) for error in errors]
        return [str(errors)] if errors else []
    return []


def build_agent_graph(
    service: MemoryOSService,
    session_id: str,
    settings: Settings | None = None,
    llm: Any | None = None,
):
    """Build the full agentic memory manager graph.

    Architecture:
        entry → Router (LLM intent classification)
          ├→ "ingest" → IngestNode → should_page?
          │                           ├→ yes: PagingNode → BuildContext → END
          │                           └→ no: BuildContext → END
          ├→ "recall" → ToolAgent (search + read) → BuildContext → END
          └→ "update" → ToolAgent (patch) → ConflictCheck
                                              ├→ conflict: interrupt → END
                                              └→ no conflict: END
    """
    settings = settings or service.settings
    api_key = settings.chat_api_key or ""
    base_url = settings.chat_base_url

    kwargs: dict[str, Any] = {}
    if base_url:
        kwargs["base_url"] = base_url

    if llm is None:
        llm = ChatOpenAI(
            model=settings.chat_model,
            api_key=api_key,  # type: ignore[arg-type]
            temperature=0,
            **kwargs,
        )

    tools = create_memory_tools(service, session_id)
    llm_with_tools = llm.bind_tools(tools)

    # --- Node definitions ---

    def router_node(state: AgentState) -> AgentState:
        """Classify user intent: ingest, recall, or update."""
        messages = state.get("messages", [])
        if not messages:
            return _state_with(state, intent="recall")

        last_msg = _content_text(messages[-1].content) if messages else ""
        system = SystemMessage(
            content=(
                "Classify the user's intent into exactly one category:\n"
                "- 'ingest': user is providing new information to remember\n"
                "- 'recall': user is asking a question or requesting information\n"
                "- 'update': user is correcting or updating previously stored information\n"
                "Respond with ONLY the category word."
            )
        )
        response = llm.invoke([system, HumanMessage(content=last_msg)])
        intent = _content_text(response.content).strip().lower()
        if intent not in ("ingest", "recall", "update"):
            intent = "recall"
        session = state.get("session_id", session_id)
        service.trace(
            session,
            "agent_intent_routed",
            {"intent": intent, "message": last_msg},
        )
        return _state_with(state, intent=intent)

    def ingest_node(state: AgentState) -> AgentState:
        """Ingest the user's message into memory."""
        messages = state.get("messages", [])
        last_msg = _content_text(messages[-1].content) if messages else ""
        session = state.get("session_id", session_id)
        response = service.ingest(session, MessageCreate(role=Role.USER, content=last_msg))
        return _state_with(state, should_page=response.should_page, result="Message ingested.")

    def paging_node(state: AgentState) -> AgentState:
        """Run paging to compress messages into memory pages."""
        session = state.get("session_id", session_id)
        page = service.page(session)
        result = f"Paged: {page.title}" if page else "No page created."
        return _state_with(state, result=result)

    def tool_agent_node(state: AgentState) -> AgentState:
        """Agent node that can call memory tools."""
        messages = state.get("messages", [])
        system = SystemMessage(
            content=(
                "You are a memory management agent. Use the available tools to "
                "search, read, write, or patch memory pages as needed. "
                "Be concise and precise in your tool usage."
            )
        )
        response = llm_with_tools.invoke([system, *messages])
        session = state.get("session_id", session_id)
        service.trace(
            session,
            "agent_tool_agent_invoked",
            {
                "tool_turns": state.get("tool_turns", 0),
                "tool_calls": _tool_call_summaries(response),
            },
        )
        return _state_with(state, messages=[response])

    tool_node = ToolNode(tools)

    def tool_executor_node(state: AgentState) -> AgentState:
        """Execute tool calls from the agent."""
        next_state = cast(AgentState, tool_node.invoke(state))
        session = next_state.get("session_id", session_id)
        patch_errors = _latest_patch_errors(service, session)
        tool_turns = state.get("tool_turns", 0) + 1
        service.trace(
            session,
            "agent_tool_turn_completed",
            {
                "tool_turns": tool_turns,
                "patch_errors": patch_errors,
                "stopped_due_to_max_turns": tool_turns >= settings.agent_max_tool_turns,
            },
        )
        if patch_errors:
            service.trace(
                session,
                "agent_patch_conflict_detected",
                {"tool_turns": tool_turns, "errors": patch_errors},
            )
        return _state_with(
            next_state,
            tool_turns=tool_turns,
            patch_errors=patch_errors,
            conflict_detected=bool(patch_errors),
        )

    def build_context_node(state: AgentState) -> AgentState:
        """Build context package for the session."""
        session = state.get("session_id", session_id)
        messages = state.get("messages", [])
        human_messages = [message for message in messages if isinstance(message, HumanMessage)]
        if human_messages:
            task = _content_text(human_messages[-1].content)
        else:
            task = _content_text(messages[-1].content) if messages else ""
        context = service.build_context(session, task=task)
        result = (
            f"Context built: {context.estimated_tokens} tokens\n"
            f"{_format_context_citations(context)}"
        )
        service.trace(
            session,
            "agent_context_evidence_selected",
            {
                "task": task,
                "evidence_message_ids": [
                    evidence.message_id for evidence in context.retrieved_evidence
                ],
                "evidence_page_ids": [evidence.page_id for evidence in context.retrieved_evidence],
                "superseded_evidence": [
                    evidence.message_id
                    for evidence in context.retrieved_evidence
                    if evidence.superseded
                ],
                "tool_turns": state.get("tool_turns", 0),
            },
        )
        return _state_with(state, context=context, result=result)

    def answer_with_citations_node(state: AgentState) -> AgentState:
        """Answer recall requests from retrieved raw evidence only."""
        context = state.get("context")
        if context is None or not context.retrieved_evidence:
            session = state.get("session_id", session_id)
            service.trace(
                session,
                "agent_answered",
                {
                    "insufficient_evidence": True,
                    "citation_message_ids": [],
                },
            )
            return _state_with(
                state,
                result=("Insufficient retrieved evidence to answer with source citations."),
            )

        system = SystemMessage(
            content=(
                "You are an experimental memory QA node. Answer using only the "
                "retrieved raw message evidence below. Do not use page summaries, "
                "recent messages, or outside knowledge. Cite supporting message_id "
                "values in square brackets. If the evidence is insufficient, say so."
            )
        )
        prompt = HumanMessage(
            content=(
                f"Question:\n{context.task}\n\n"
                f"Retrieved evidence:\n{_format_answer_evidence(context)}"
            )
        )
        response = llm.invoke([system, prompt])
        answer = _content_text(response.content).strip()
        insufficient_evidence = not bool(answer)
        if insufficient_evidence:
            answer = "Insufficient retrieved evidence to answer with source citations."
        result = f"Answer:\n{answer}\n\n{_citation_footer(context)}"
        session = state.get("session_id", session_id)
        service.trace(
            session,
            "agent_answered",
            {
                "insufficient_evidence": insufficient_evidence,
                "citation_message_ids": [
                    evidence.message_id for evidence in context.retrieved_evidence
                ],
                "superseded_citation_ids": [
                    evidence.message_id
                    for evidence in context.retrieved_evidence
                    if evidence.superseded
                ],
            },
        )
        return _state_with(state, result=result)

    def conflict_check_node(state: AgentState) -> AgentState:
        """Check if the update introduces conflicts."""
        patch_errors = state.get("patch_errors", [])
        if patch_errors:
            return _state_with(
                state,
                conflict_detected=True,
                human_approved=False,
                result="Patch requires review: " + "; ".join(patch_errors),
            )
        return _state_with(state, conflict_detected=False, human_approved=True)

    # --- Routing functions ---

    def route_by_intent(state: AgentState) -> str:
        intent = state.get("intent", "recall")
        if intent == "ingest":
            return "ingest"
        elif intent == "update":
            return "tool_agent"
        else:
            return "tool_agent"

    def route_after_ingest(state: AgentState) -> str:
        return "paging" if state.get("should_page") else "build_context"

    def route_after_tool_agent(state: AgentState) -> str:
        """Check if agent wants to call tools or is done."""
        messages = state.get("messages", [])
        if state.get("tool_turns", 0) >= settings.agent_max_tool_turns:
            return "build_context"
        if messages and hasattr(messages[-1], "tool_calls") and messages[-1].tool_calls:
            return "tool_executor"
        return "build_context"

    def route_after_tool_executor(state: AgentState) -> str:
        if state.get("tool_turns", 0) >= settings.agent_max_tool_turns:
            return "build_context"
        return "tool_agent"

    def route_after_build_context(state: AgentState) -> str:
        if state.get("intent") == "update" and state.get("conflict_detected"):
            return "conflict_check"
        if state.get("intent") == "recall":
            return "answer"
        return END

    # --- Build graph ---

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("router", router_node)
    graph.add_node("ingest", ingest_node)
    graph.add_node("paging", paging_node)
    graph.add_node("tool_agent", tool_agent_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("build_context", build_context_node)
    graph.add_node("answer", answer_with_citations_node)
    graph.add_node("conflict_check", conflict_check_node)

    # Set entry point
    graph.set_entry_point("router")

    # Add edges
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {"ingest": "ingest", "tool_agent": "tool_agent"},
    )
    graph.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {"paging": "paging", "build_context": "build_context"},
    )
    graph.add_edge("paging", "build_context")
    graph.add_conditional_edges(
        "tool_agent",
        route_after_tool_agent,
        {"tool_executor": "tool_executor", "build_context": "build_context"},
    )
    graph.add_conditional_edges(
        "tool_executor",
        route_after_tool_executor,
        {"tool_agent": "tool_agent", "build_context": "build_context"},
    )
    graph.add_conditional_edges(
        "build_context",
        route_after_build_context,
        {"answer": "answer", "conflict_check": "conflict_check", END: END},
    )
    graph.add_edge("answer", END)
    graph.add_edge("conflict_check", END)

    # Compile with checkpointer for state persistence
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer, interrupt_before=["conflict_check"])


def invoke_agent(
    service: MemoryOSService,
    session_id: str,
    user_message: str,
    thread_id: str | None = None,
) -> dict:
    """Convenience function to invoke the agent graph.

    Args:
        service: The MemoryOS service instance.
        session_id: Session to operate on.
        user_message: The user's input message.
        thread_id: Thread ID for state persistence (defaults to session_id).

    Returns:
        Final agent state dict.
    """
    graph = build_agent_graph(service, session_id)
    config = {"configurable": {"thread_id": thread_id or session_id}}
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "session_id": session_id,
        "intent": "",
        "should_page": False,
        "context": None,
        "conflict_detected": False,
        "patch_errors": [],
        "human_approved": False,
        "result": "",
        "tool_turns": 0,
    }
    return graph.invoke(initial_state, config=config)
