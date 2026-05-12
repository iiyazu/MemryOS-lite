"""Tests for memory tools and agent graph."""

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

        assert "Patch verified" in result
        assert service.store.list_traces(session.id)[-1].event_type == "patch_verified"

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
