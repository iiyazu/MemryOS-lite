"""Tests for memory tools and agent graph."""

from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.store import MemoryStore
from memoryos_lite.tools import create_memory_tools


class TestMemoryTools:
    def _setup(self, tmp_path):
        settings = Settings(data_dir=tmp_path / ".memoryos")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test_tools")
        return service, session

    def test_create_tools(self, tmp_path):
        service, session = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        assert len(tools) == 5
        names = {t.name for t in tools}
        assert "search_memory" in names
        assert "read_page" in names
        assert "write_page" in names
        assert "patch_page" in names
        assert "list_pages" in names

    def test_list_pages_empty(self, tmp_path):
        service, session = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        list_tool = next(t for t in tools if t.name == "list_pages")
        result = list_tool.invoke({})
        assert "No memory pages" in result

    def test_search_memory_empty(self, tmp_path):
        service, session = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        search_tool = next(t for t in tools if t.name == "search_memory")
        result = search_tool.invoke({"query": "test", "top_k": 5})
        assert "No relevant" in result

    def test_write_and_read_page(self, tmp_path):
        service, session = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        write_tool = next(t for t in tools if t.name == "write_page")
        next(t for t in tools if t.name == "read_page")
        list_tool = next(t for t in tools if t.name == "list_pages")

        # Write a page
        result = write_tool.invoke(
            {
                "title": "Test Page",
                "summary": "This is a test summary",
                "facts": ["fact1", "fact2"],
            }
        )
        assert "Created page" in result

        # List should show it
        list_result = list_tool.invoke({})
        assert "Test Page" in list_result

    def test_patch_page_uses_valid_patch_operations(self, tmp_path):
        service, session = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        write_tool = next(t for t in tools if t.name == "write_page")
        patch_tool = next(t for t in tools if t.name == "patch_page")

        write_tool.invoke(
            {
                "title": "Patch Target",
                "summary": "The page contains fact1.",
                "facts": ["fact1"],
            }
        )
        page = service.store.list_pages(session.id)[0]

        result = patch_tool.invoke(
            {
                "page_id": page.id,
                "operation": "replace",
                "old_text": "fact1",
                "new_text": "fact one",
            }
        )

        assert "Patch applied" in result
        assert service.store.list_traces(session.id)[-1].event_type == "patch_verified"
        # Verify patch was actually applied to page content
        updated = service.store.load_page(page.id)
        assert updated is not None
        assert "fact one" in updated.facts
        assert "fact1" not in updated.facts

    def test_read_nonexistent_page(self, tmp_path):
        service, session = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        read_tool = next(t for t in tools if t.name == "read_page")
        result = read_tool.invoke({"page_id": "nonexistent"})
        assert "not found" in result


class TestAgentGraph:
    def test_graph_compiles(self, tmp_path):
        from memoryos_lite.agent_graph import build_agent_graph

        settings = Settings(data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test_agent")
        graph = build_agent_graph(service, session.id)
        assert graph is not None
        # Verify graph has expected nodes
        assert "router" in graph.nodes
        assert "ingest" in graph.nodes
        assert "paging" in graph.nodes
        assert "tool_agent" in graph.nodes
        assert "build_context" in graph.nodes

    def test_tool_loop_preserves_messages(self, tmp_path):
        from memoryos_lite.agent_graph import build_agent_graph

        settings = Settings(data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test_agent_loop")

        tool_call = {
            "name": "search_memory",
            "args": {"query": "MemoryOS", "top_k": 1},
            "id": "call_search_memory",
            "type": "tool_call",
        }
        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        tool_llm = Mock()
        tool_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[tool_call]),
            AIMessage(content="No relevant memory pages found."),
        ]
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            state = graph.invoke(
                {
                    "messages": [HumanMessage(content="Search memory for MemoryOS")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "human_approved": False,
                    "result": "",
                },
                config={"configurable": {"thread_id": "test-tool-loop"}},
            )

        messages = state["messages"]
        assert len(messages) == 4
        assert isinstance(messages[0], HumanMessage)
        assert isinstance(messages[1], AIMessage)
        assert messages[1].tool_calls
        assert isinstance(messages[2], ToolMessage)
        assert isinstance(messages[3], AIMessage)
        assert not messages[3].tool_calls
        assert state["context"] is not None
        assert state["context"].task == "Search memory for MemoryOS"
