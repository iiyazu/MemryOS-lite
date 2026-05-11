from typing import TypedDict

from langgraph.graph import END, StateGraph

from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import ContextPackage, MemoryPage, MessageCreate


class MemoryGraphState(TypedDict, total=False):
    session_id: str
    message: MessageCreate
    task: str
    budget: int
    should_page: bool
    page: MemoryPage | None
    context: ContextPackage


def build_memory_graph(service: MemoryOSService):
    graph = StateGraph(MemoryGraphState)

    def ingest_node(state: MemoryGraphState) -> MemoryGraphState:
        response = service.ingest(state["session_id"], state["message"])
        return {**state, "should_page": response.should_page}

    def page_node(state: MemoryGraphState) -> MemoryGraphState:
        return {**state, "page": service.page(state["session_id"])}

    def build_context_node(state: MemoryGraphState) -> MemoryGraphState:
        return {
            **state,
            "context": service.build_context(
                state["session_id"],
                task=state.get("task", ""),
                budget=state.get("budget", service.settings.rot_safe_budget),
            ),
        }

    def route_after_ingest(state: MemoryGraphState) -> str:
        return "page" if state.get("should_page") else "build_context"

    graph.add_node("ingest", ingest_node)
    graph.add_node("page", page_node)
    graph.add_node("build_context", build_context_node)
    graph.set_entry_point("ingest")
    graph.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {"page": "page", "build_context": "build_context"},
    )
    graph.add_edge("page", "build_context")
    graph.add_edge("build_context", END)
    return graph.compile()
