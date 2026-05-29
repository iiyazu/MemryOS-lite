"""Agentic Memory Manager — LangGraph multi-agent system.

STATUS: experimental, not wired into engine.py main flow.
Future: to be replaced by a lightweight kernel agent loop that decides
core_memory_append / archival_write / noop after each ingest.

Demonstrates:
- StateGraph with rich TypedDict state
- Conditional edges (intent routing, conflict detection)
- Subgraphs (paging as nested graph)
- Tool-calling agent node
- interrupt_before for human-in-the-loop on conflicts
- Checkpointer for state persistence
- Lineage merge coordination (prevents premature termination)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from memoryos_lite.agent_answer_eval import evaluate_agent_answer
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.observability import (
    current_observability_context,
    log_event,
    observability_context,
    record_core_operation,
    timed_core_operation,
)
from memoryos_lite.schemas import ContextPackage, MessageCreate, Role
from memoryos_lite.tools import create_item_tools, create_memory_tools
from xmuse_core.self_evolution.recovery import RecoveryEvent

logger = logging.getLogger(__name__)


class LineageMergeRecord(TypedDict):
    """Record of a single lineage's contribution to the merged state."""

    lineage_id: str
    intent: str
    observation_summary: str
    conflict_detected: bool
    human_approved: bool
    result: str


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
    memory_decision: MemoryDecision | None
    memory_observation: MemoryObservation | None
    observation_summary: str
    # Lineage tracking fields
    lineage_id: str
    active_lineages: list[str]
    merged_lineages: list[LineageMergeRecord]
    lineage_merge_complete: bool
    pending_lineages: list[str]
    degraded_components: list[str]


class MemoryDecision(TypedDict):
    """Structured output from memory_think_node."""

    action: Literal["memorize", "recall", "patch", "answer_directly", "none"]
    reason_code: Literal[
        "durable_fact",
        "memory_question",
        "correction",
        "sufficient_context",
        "irrelevant",
    ]
    query: str
    content: str
    confidence: float


class MemoryObservation(TypedDict):
    """Result of memory_action_node execution."""

    success: bool
    recalled_item_ids: list[str]
    patched_item_id: str | None
    error: str | None


class LineageCoordinator:
    """Tracks active lineages and coordinates merge before terminal state.

    A lineage represents a single execution path through the agent graph.
    The coordinator ensures that all active lineages are consolidated into
    a merged state record before the graph reaches END, preventing premature
    termination that would leave lineage state unaccounted for.
    """

    def __init__(self) -> None:
        self._active: set[str] = set()
        self._completed: dict[str, LineageMergeRecord] = {}

    def register(self, lineage_id: str) -> None:
        """Register a new active lineage."""
        self._active.add(lineage_id)

    def complete(self, lineage_id: str, record: LineageMergeRecord) -> None:
        """Mark a lineage as completed with its merge record."""
        self._active.discard(lineage_id)
        self._completed[lineage_id] = record

    def all_merged(self) -> bool:
        """Return True when no active lineages remain unmerged."""
        return len(self._active) == 0

    def merged_records(self) -> list[LineageMergeRecord]:
        return list(self._completed.values())

    def pending_count(self) -> int:
        return len(self._active)


class IncompleteLineageMergeError(RuntimeError):
    """Raised when a graph path attempts to terminate with unmerged lineages."""

    def __init__(self, pending_lineages: list[str]) -> None:
        self.pending_lineages = list(pending_lineages)
        super().__init__(
            "graph lineage merge coordination pending: "
            + ", ".join(self.pending_lineages)
        )


def _new_lineage_id() -> str:
    return f"lin_{uuid.uuid4().hex[:12]}"


def _record_agent_recovery_event(
    service: MemoryOSService,
    session_id: str,
    event: RecoveryEvent,
) -> None:
    service.trace(session_id, "agent_recovery_event", event.to_payload())


def _add_degraded_component(state: AgentState, component: str) -> AgentState:
    components = list(state.get("degraded_components", []))
    if component not in components:
        components.append(component)
    return _state_with(state, degraded_components=components)


def _lineage_record_for_state(state: AgentState, lineage_id: str) -> LineageMergeRecord:
    """Build a compact terminal contribution record for a graph lineage."""
    return LineageMergeRecord(
        lineage_id=lineage_id,
        intent=str(state.get("intent", "")),
        observation_summary=str(state.get("observation_summary", "")),
        conflict_detected=bool(state.get("conflict_detected", False)),
        human_approved=bool(state.get("human_approved", False)),
        result=str(state.get("result", "")),
    )


def lineage_merge_node_fn(state: AgentState) -> AgentState:
    """Merge all tracked lineages into state before the graph can terminate.

    LangGraph conditional branches are mutually exclusive in this demo, but
    callers and checkpointers can resume with pre-populated lineage metadata.
    This node is therefore the single terminal coordinator: every active
    lineage ID must have a merge record before END is reachable.
    """
    lineage_id = state.get("lineage_id") or _new_lineage_id()
    active_lineages = list(dict.fromkeys([*state.get("active_lineages", []), lineage_id]))
    merged_by_id: dict[str, LineageMergeRecord] = {
        record["lineage_id"]: record
        for record in state.get("merged_lineages", [])
        if record.get("lineage_id")
    }

    if lineage_id not in merged_by_id:
        merged_by_id[lineage_id] = _lineage_record_for_state(state, lineage_id)

    merged_lineages = list(merged_by_id.values())
    pending = [lineage for lineage in active_lineages if lineage not in merged_by_id]
    return _state_with(
        state,
        lineage_id=lineage_id,
        active_lineages=pending,
        merged_lineages=merged_lineages,
        lineage_merge_complete=not pending,
        pending_lineages=pending,
    )


def assert_lineage_merge_complete(state: AgentState) -> None:
    """Prevent terminalization while active lineage records are still missing."""
    if not state.get("lineage_merge_complete", False):
        raise IncompleteLineageMergeError(list(state.get("pending_lineages", [])))


def memory_think_node_fn(
    state: AgentState,
    fake_decision: MemoryDecision | None = None,
) -> AgentState:
    """Classify user message into a memory lifecycle action."""
    if fake_decision is not None:
        return _state_with(state, memory_decision=fake_decision)
    return _state_with(
        state,
        memory_decision=MemoryDecision(
            action="none",
            reason_code="irrelevant",
            query="",
            content="",
            confidence=0.0,
        ),
    )


def memory_action_node_fn(
    state: AgentState,
    service: MemoryOSService | None = None,
) -> AgentState:
    """Deterministic dispatch based on MemoryDecision."""
    decision = state.get("memory_decision")
    if decision is None or service is None:
        return _state_with(
            state,
            memory_observation=MemoryObservation(
                success=False,
                recalled_item_ids=[],
                patched_item_id=None,
                error="no decision or service",
            ),
        )
    session = state.get("session_id", "")
    action = decision["action"]

    if action == "memorize":
        item = service.create_item(session, decision["content"])
        item_id = item.id if item else ""
        return _state_with(
            state,
            memory_observation=MemoryObservation(
                success=item is not None,
                recalled_item_ids=[item_id] if item_id else [],
                patched_item_id=None,
                error=None if item else "item creation disabled",
            ),
        )
    if action == "recall":
        items = service.store.list_items(session)
        query_lower = decision["query"].lower()
        matched = [it for it in items if query_lower in it.content.lower()]
        if not matched:
            matched = items
        return _state_with(
            state,
            memory_observation=MemoryObservation(
                success=True,
                recalled_item_ids=[it.id for it in matched[:5]],
                patched_item_id=None,
                error=None,
            ),
        )
    if action == "patch":
        items = service.store.list_items(session)
        query_lower = decision["query"].lower()
        matched = [it for it in items if query_lower in it.content.lower()]
        if not matched:
            matched = items
        if not matched:
            return _state_with(
                state,
                memory_observation=MemoryObservation(
                    success=False,
                    recalled_item_ids=[],
                    patched_item_id=None,
                    error="no item found to patch",
                ),
            )
        target = matched[0]
        service.patch_item(session, target.id, decision["content"])
        return _state_with(
            state,
            memory_observation=MemoryObservation(
                success=True,
                recalled_item_ids=[it.id for it in matched],
                patched_item_id=target.id,
                error=None,
            ),
        )
    # answer_directly / none → skip
    return _state_with(
        state,
        memory_observation=MemoryObservation(
            success=True,
            recalled_item_ids=[],
            patched_item_id=None,
            error=None,
        ),
    )


def memory_observe_node_fn(state: AgentState) -> AgentState:
    """Deterministic summary of memory action results."""
    obs = state.get("memory_observation")
    if obs is None:
        return _state_with(state, observation_summary="no observation")
    if not obs["success"]:
        return _state_with(
            state, observation_summary=f"error: {obs['error']}"
        )
    parts: list[str] = []
    if obs["recalled_item_ids"]:
        parts.append(f"recalled {len(obs['recalled_item_ids'])} items")
    if obs["patched_item_id"]:
        parts.append(f"patched {obs['patched_item_id']}")
    if not parts:
        parts.append("no memory action taken")
    return _state_with(state, observation_summary="; ".join(parts))


def _state_with(state: AgentState, **updates: Any) -> AgentState:
    return cast(AgentState, {**state, **updates})


def _instrument_agent_node(
    node_name: str,
    func: Any,
    *,
    default_session_id: str,
) -> Any:
    def wrapper(state: AgentState) -> AgentState:
        session_id = str(state.get("session_id", default_session_id))
        lineage_id = state.get("lineage_id")
        with observability_context(
            session_id=session_id,
            lane_id=str(lineage_id) if lineage_id else None,
        ):
            start = time.perf_counter()
            try:
                result = func(state)
            except Exception as exc:
                elapsed_s = time.perf_counter() - start
                record_core_operation(
                    component="agent_graph",
                    operation=node_name,
                    elapsed_s=elapsed_s,
                    status="error",
                    error_type=type(exc).__name__,
                )
                log_event(
                    logger,
                    logging.ERROR,
                    "agent_graph_node_failed",
                    component="agent_graph",
                    operation=node_name,
                    session_id=session_id,
                    latency_ms=round(elapsed_s * 1000, 3),
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                raise
            elapsed_s = time.perf_counter() - start
            record_core_operation(
                component="agent_graph",
                operation=node_name,
                elapsed_s=elapsed_s,
                status="ok",
            )
            log_event(
                logger,
                logging.DEBUG,
                "agent_graph_node_completed",
                component="agent_graph",
                operation=node_name,
                session_id=session_id,
                latency_ms=round(elapsed_s * 1000, 3),
            )
            return result

    return wrapper


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
          │                           ├→ yes: PagingNode → ToolAgent → MemoryThink
          │                           └→ no:              ToolAgent → MemoryThink
          │                                                              ↓
          ├→ "recall" → ToolAgent → MemoryThink → MemoryAction → MemoryObserve
          │                                                              ↓
          └→ "update" → ToolAgent → MemoryThink → MemoryAction → MemoryObserve
                                                                        ↓
                                                               BuildContext
                                                                 ├→ answer (recall)
                                                                 ├→ conflict_check (update+conflict)
                                                                 └→ lineage_merge (all paths)
                                                                        ↓
                                                                       END

    Lineage merge coordination:
        All execution paths converge at lineage_merge before END.
        The LineageCoordinator ensures no lineage terminates without
        recording its contribution to the merged state. This prevents
        premature termination that would leave lineage state unaccounted.
    """
    with observability_context(session_id=session_id), timed_core_operation(
        component="agent_graph",
        operation="build_agent_graph",
        logger=logger,
        session_id=session_id,
    ):
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
                timeout=settings.memoryos_llm_timeout_s,
                **kwargs,
            )

        tools = create_memory_tools(service, session_id)
        tools.extend(create_item_tools(service, session_id))
        llm_with_tools = llm.bind_tools(tools)

    # --- Node definitions ---

    def router_node(state: AgentState) -> AgentState:
        """Classify user intent: ingest, recall, or update."""
        lineage_id = state.get("lineage_id") or _new_lineage_id()
        active_lineages = list(dict.fromkeys([*state.get("active_lineages", []), lineage_id]))
        state = _state_with(
            state,
            lineage_id=lineage_id,
            active_lineages=active_lineages,
            lineage_merge_complete=False,
        )
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
        session = state.get("session_id", session_id)
        response = service.recovery.execute(
            "agent_graph.router_llm",
            "invoke",
            lambda: llm.invoke([system, HumanMessage(content=last_msg)]),
            critical=True,
            observer=lambda event: _record_agent_recovery_event(service, session, event),
        )
        intent = _content_text(response.content).strip().lower()
        if intent not in ("ingest", "recall", "update"):
            intent = "recall"
        service.trace(
            session,
            "agent_intent_routed",
            {
                **current_observability_context(),
                "lineage_id": lineage_id,
                "intent": intent,
                "message": last_msg,
            },
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
                "search, read, write, or patch memory pages as needed.\n\n"
                "Item-level tools:\n"
                "- memorize_item: when the user states a durable fact, preference, "
                "or decision worth remembering long-term.\n"
                "- recall_items: before answering questions about past conversations "
                "or user preferences.\n"
                "- patch_item: when correcting a previously memorized atomic fact.\n\n"
                "Be concise and precise in your tool usage."
            )
        )
        session = state.get("session_id", session_id)
        response = service.recovery.execute(
            "agent_graph.tool_llm",
            "invoke",
            lambda: llm_with_tools.invoke([system, *messages]),
            fallback=lambda exc: HumanMessage(
                content=f"Tool agent degraded: {type(exc).__name__}: {exc}"
            ),
            critical=False,
            observer=lambda event: _record_agent_recovery_event(service, session, event),
        )
        degraded = isinstance(response, HumanMessage)
        service.trace(
            session,
            "agent_tool_agent_invoked",
            {
                **current_observability_context(),
                "tool_turns": state.get("tool_turns", 0),
                "tool_calls": _tool_call_summaries(response),
                "degraded": degraded,
            },
        )
        next_state = _state_with(state, messages=[response])
        return _add_degraded_component(next_state, "tool_llm") if degraded else next_state

    tool_node = ToolNode(tools)

    def tool_executor_node(state: AgentState) -> AgentState:
        """Execute tool calls from the agent."""
        session = state.get("session_id", session_id)

        def _tool_fallback(exc: BaseException) -> AgentState:
            return _state_with(
                state,
                patch_errors=[f"tool execution degraded: {type(exc).__name__}: {exc}"],
                conflict_detected=True,
            )

        next_state = cast(
            AgentState,
            service.recovery.execute(
                "agent_graph.tool_executor",
                "invoke",
                lambda: tool_node.invoke(state),
                fallback=_tool_fallback,
                critical=False,
                observer=lambda event: _record_agent_recovery_event(service, session, event),
            ),
        )
        session = next_state.get("session_id", session_id)
        patch_errors = _latest_patch_errors(service, session)
        if next_state.get("patch_errors"):
            patch_errors = [*next_state.get("patch_errors", []), *patch_errors]
        tool_turns = state.get("tool_turns", 0) + 1
        service.trace(
            session,
            "agent_tool_turn_completed",
            {
                **current_observability_context(),
                "tool_turns": tool_turns,
                "patch_errors": patch_errors,
                "stopped_due_to_max_turns": tool_turns >= settings.agent_max_tool_turns,
            },
        )
        if patch_errors:
            service.trace(
                session,
                "agent_patch_conflict_detected",
                {
                    **current_observability_context(),
                    "tool_turns": tool_turns,
                    "errors": patch_errors,
                },
            )
        return _state_with(
            _add_degraded_component(next_state, "tool_executor")
            if next_state.get("patch_errors")
            else next_state,
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
                **current_observability_context(),
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
            refusal = "Insufficient retrieved evidence to answer with source citations."
            answer_eval = evaluate_agent_answer(refusal, [])
            session = state.get("session_id", session_id)
            service.trace(
                session,
                "agent_answered",
                {
                    **current_observability_context(),
                    "insufficient_evidence": True,
                    "citation_message_ids": [],
                    "answer_eval": answer_eval.to_report(),
                },
            )
            return _state_with(
                state,
                result=refusal,
            )

        session = state.get("session_id", session_id)
        system = SystemMessage(
            content=(
                "You are an experimental memory QA node. Answer using only the "
                "retrieved raw message evidence below. Do not use page summaries, "
                "recent messages, or outside knowledge. Cite supporting message_id "
                "values in square brackets. For temporal-reasoning questions, use "
                "the timestamps in the retrieved evidence to determine order or "
                "duration. If the evidence is insufficient, say so."
            )
        )
        prompt = HumanMessage(
            content=(
                f"Question:\n{context.task}\n\n"
                f"Retrieved evidence:\n{_format_answer_evidence(context)}"
            )
        )
        response = service.recovery.execute(
            "agent_graph.answer_llm",
            "invoke",
            lambda: llm.invoke([system, prompt]),
            fallback=lambda exc: HumanMessage(
                content=(
                    "Insufficient retrieved evidence to answer with source citations. "
                    f"Answer generation degraded after {type(exc).__name__}."
                )
            ),
            critical=False,
            observer=lambda event: _record_agent_recovery_event(service, session, event),
        )
        if isinstance(response, HumanMessage):
            state = _add_degraded_component(state, "answer_llm")
            service.trace(
                session,
                "agent_answer_degraded",
                {
                    **current_observability_context(),
                    "reason": "answer_llm_unavailable",
                },
            )
        answer = _content_text(response.content).strip()
        insufficient_evidence = not bool(answer)
        if insufficient_evidence:
            answer = "Insufficient retrieved evidence to answer with source citations."
        result = f"Answer:\n{answer}\n\n{_citation_footer(context)}"
        answer_eval = evaluate_agent_answer(result, context.retrieved_evidence)
        service.trace(
            session,
            "agent_answered",
            {
                **current_observability_context(),
                "insufficient_evidence": insufficient_evidence,
                "citation_message_ids": [
                    evidence.message_id for evidence in context.retrieved_evidence
                ],
                "superseded_citation_ids": [
                    evidence.message_id
                    for evidence in context.retrieved_evidence
                    if evidence.superseded
                ],
                "answer_eval": answer_eval.to_report(),
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

    def lineage_merge_node(state: AgentState) -> AgentState:
        """Consolidate all lineages before graph termination."""
        result = lineage_merge_node_fn(state)
        assert_lineage_merge_complete(result)
        session = result.get("session_id", session_id)
        service.trace(
            session,
            "agent_lineage_merged",
            {
                **current_observability_context(),
                "lineage_id": result.get("lineage_id"),
                "active_lineages": result.get("active_lineages", []),
                "pending_lineages": result.get("pending_lineages", []),
                "merged_lineage_ids": [
                    record["lineage_id"]
                    for record in result.get("merged_lineages", [])
                ],
                "lineage_merge_complete": result.get("lineage_merge_complete", False),
            },
        )
        return result

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
        return "paging" if state.get("should_page") else "tool_agent"

    def route_after_tool_agent(state: AgentState) -> str:
        """Check if agent wants to call tools or is done."""
        messages = state.get("messages", [])
        if state.get("tool_turns", 0) >= settings.agent_max_tool_turns:
            return "memory_think"
        if messages and hasattr(messages[-1], "tool_calls") and messages[-1].tool_calls:
            return "tool_executor"
        return "memory_think"

    def route_after_tool_executor(state: AgentState) -> str:
        if state.get("tool_turns", 0) >= settings.agent_max_tool_turns:
            return "memory_think"
        return "tool_agent"

    def route_after_build_context(state: AgentState) -> str:
        if state.get("intent") == "update" and state.get("conflict_detected"):
            return "conflict_check"
        if state.get("intent") == "recall":
            return "answer"
        return "lineage_merge"

    # --- Build graph ---

    def _memory_think_wrapper(state: AgentState) -> AgentState:
        """Graph-node wrapper for memory_think_node_fn."""
        session = state.get("session_id", session_id)
        result = memory_think_node_fn(state)
        decision = result.get("memory_decision")
        service.trace(
            session,
            "memory_thought",
            {
                **current_observability_context(),
                "action": decision["action"] if decision else "none",
                "reason_code": decision["reason_code"] if decision else "irrelevant",
                "confidence": decision["confidence"] if decision else 0.0,
            },
        )
        return result

    def _memory_action_wrapper(state: AgentState) -> AgentState:
        """Graph-node wrapper for memory_action_node_fn."""
        session = state.get("session_id", session_id)
        result = memory_action_node_fn(state, service=service)
        obs = result.get("memory_observation")
        service.trace(
            session,
            "memory_action",
            {
                **current_observability_context(),
                "success": obs["success"] if obs else False,
                "recalled_item_ids": obs["recalled_item_ids"] if obs else [],
                "patched_item_id": obs["patched_item_id"] if obs else None,
                "error": obs["error"] if obs else None,
            },
        )
        return result

    def _memory_observe_wrapper(state: AgentState) -> AgentState:
        """Graph-node wrapper for memory_observe_node_fn."""
        session = state.get("session_id", session_id)
        result = memory_observe_node_fn(state)
        service.trace(
            session,
            "memory_observation",
            {
                **current_observability_context(),
                "summary": result.get("observation_summary", ""),
            },
        )
        return result

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node(
        "router",
        _instrument_agent_node("router", router_node, default_session_id=session_id),
    )
    graph.add_node(
        "ingest",
        _instrument_agent_node("ingest", ingest_node, default_session_id=session_id),
    )
    graph.add_node(
        "paging",
        _instrument_agent_node("paging", paging_node, default_session_id=session_id),
    )
    graph.add_node(
        "tool_agent",
        _instrument_agent_node("tool_agent", tool_agent_node, default_session_id=session_id),
    )
    graph.add_node(
        "tool_executor",
        _instrument_agent_node("tool_executor", tool_executor_node, default_session_id=session_id),
    )
    graph.add_node(
        "memory_think",
        _instrument_agent_node(
            "memory_think",
            _memory_think_wrapper,
            default_session_id=session_id,
        ),
    )
    graph.add_node(
        "memory_action",
        _instrument_agent_node(
            "memory_action",
            _memory_action_wrapper,
            default_session_id=session_id,
        ),
    )
    graph.add_node(
        "memory_observe",
        _instrument_agent_node(
            "memory_observe",
            _memory_observe_wrapper,
            default_session_id=session_id,
        ),
    )
    graph.add_node(
        "build_context",
        _instrument_agent_node(
            "build_context",
            build_context_node,
            default_session_id=session_id,
        ),
    )
    graph.add_node(
        "answer",
        _instrument_agent_node(
            "answer",
            answer_with_citations_node,
            default_session_id=session_id,
        ),
    )
    graph.add_node(
        "conflict_check",
        _instrument_agent_node(
            "conflict_check",
            conflict_check_node,
            default_session_id=session_id,
        ),
    )
    graph.add_node(
        "lineage_merge",
        _instrument_agent_node(
            "lineage_merge",
            lineage_merge_node,
            default_session_id=session_id,
        ),
    )

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
        {"paging": "paging", "tool_agent": "tool_agent"},
    )
    graph.add_edge("paging", "tool_agent")
    graph.add_conditional_edges(
        "tool_agent",
        route_after_tool_agent,
        {"tool_executor": "tool_executor", "memory_think": "memory_think"},
    )
    graph.add_conditional_edges(
        "tool_executor",
        route_after_tool_executor,
        {"tool_agent": "tool_agent", "memory_think": "memory_think"},
    )
    graph.add_edge("memory_think", "memory_action")
    graph.add_edge("memory_action", "memory_observe")
    graph.add_edge("memory_observe", "build_context")
    graph.add_conditional_edges(
        "build_context",
        route_after_build_context,
        {
            "answer": "answer",
            "conflict_check": "conflict_check",
            "lineage_merge": "lineage_merge",
        },
    )
    graph.add_edge("answer", "lineage_merge")
    graph.add_edge("conflict_check", "lineage_merge")
    graph.add_edge("lineage_merge", END)

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
    with observability_context(session_id=session_id), timed_core_operation(
        component="agent_graph",
        operation="invoke_agent",
        logger=logger,
        session_id=session_id,
    ):
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
            "lineage_id": _new_lineage_id(),
            "active_lineages": [],
            "merged_lineages": [],
            "lineage_merge_complete": False,
            "pending_lineages": [],
            "degraded_components": [],
        }
        return graph.invoke(initial_state, config=config)
