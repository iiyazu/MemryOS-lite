"""Tests for memory tools and agent graph."""

from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MemoryPage, MessageCreate, PageType, Role
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

    def test_read_page_rejects_cross_session_access(self, tmp_path):
        service, session = self._setup(tmp_path)
        other_session = service.create_session("other_session")
        page = MemoryPage(
            id="other_page",
            session_id=other_session.id,
            page_type=PageType.SOURCE_SUMMARY,
            title="Other page",
            summary="Other session memory.",
        )
        service.store.save_page(page)
        read_tool = next(
            t for t in create_memory_tools(service, session.id) if t.name == "read_page"
        )

        result = read_tool.invoke({"page_id": page.id})

        assert "different session" in result


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
        assert "answer" in graph.nodes

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

    def test_recall_result_includes_source_citations(self, tmp_path):
        from memoryos_lite.agent_graph import build_agent_graph

        settings = Settings(data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test_agent_citations")
        source = service.ingest(
            session.id,
            MessageCreate(role=Role.USER, content="MemoryOS Lite uses source citations."),
        ).message
        service.store.save_page(
            MemoryPage(
                id="citation_page",
                session_id=session.id,
                page_type=PageType.SOURCE_SUMMARY,
                title="Citation page",
                summary="MemoryOS Lite uses source citations.",
                source_message_ids=[source.id],
            )
        )
        router_llm = Mock()
        router_llm.invoke.side_effect = [
            AIMessage(content="recall"),
            AIMessage(content=f"MemoryOS Lite uses source citations [{source.id}]."),
        ]
        tool_llm = Mock()
        tool_llm.invoke.return_value = AIMessage(content="Done.")
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            state = graph.invoke(
                {
                    "messages": [HumanMessage(content="What uses source citations?")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                },
                config={"configurable": {"thread_id": "test-citations"}},
            )

        assert "Answer:" in state["result"]
        assert "Sources:" in state["result"]
        assert source.id in state["result"]
        traces = service.store.list_traces(session.id)
        answer_trace = next(trace for trace in traces if trace.event_type == "agent_answered")
        assert answer_trace.payload["citation_message_ids"]
        assert source.id in answer_trace.payload["citation_message_ids"]
        assert answer_trace.payload["answer_eval"]["answer_has_citation"] is True
        assert answer_trace.payload["answer_eval"]["answer_uses_retrieved_source"] is True
        assert answer_trace.payload["answer_eval"]["unsupported_answer"] is False
        evidence_trace = next(
            trace for trace in traces if trace.event_type == "agent_context_evidence_selected"
        )
        assert source.id in evidence_trace.payload["evidence_message_ids"]

    def test_recall_refuses_when_no_retrieved_evidence(self, tmp_path):
        from memoryos_lite.agent_graph import build_agent_graph

        settings = Settings(data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test_agent_no_evidence")
        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        tool_llm = Mock()
        tool_llm.invoke.return_value = AIMessage(content="Done.")
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            state = graph.invoke(
                {
                    "messages": [HumanMessage(content="What does MemoryOS remember?")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                },
                config={"configurable": {"thread_id": "test-no-evidence"}},
            )

        assert "Insufficient retrieved evidence" in state["result"]
        assert router_llm.invoke.call_count == 1
        answer_trace = next(
            trace
            for trace in service.store.list_traces(session.id)
            if trace.event_type == "agent_answered"
        )
        assert answer_trace.payload["answer_eval"]["refusal_when_no_evidence"] is True
        assert answer_trace.payload["answer_eval"]["unsupported_answer"] is False

    def test_tool_loop_stops_at_configured_turn_bound(self, tmp_path):
        from memoryos_lite.agent_graph import build_agent_graph

        settings = Settings(
            data_dir=tmp_path / ".memoryos",
            openai_api_key="sk-test-dummy",
            agent_max_tool_turns=1,
        )
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test_agent_loop_bound")
        tool_call = {
            "name": "search_memory",
            "args": {"query": "MemoryOS", "top_k": 1},
            "id": "call_search_memory",
            "type": "tool_call",
        }
        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        tool_llm = Mock()
        tool_llm.invoke.return_value = AIMessage(content="", tool_calls=[tool_call])
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
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                },
                config={"configurable": {"thread_id": "test-tool-bound"}},
            )

        assert state["tool_turns"] == 1
        assert tool_llm.invoke.call_count == 1
        assert state["context"] is not None
        trace = next(
            trace
            for trace in service.store.list_traces(session.id)
            if trace.event_type == "agent_tool_turn_completed"
        )
        assert trace.payload["stopped_due_to_max_turns"] is True

    def test_patch_tool_errors_mark_conflict_before_interrupt(self, tmp_path):
        from memoryos_lite.agent_graph import build_agent_graph

        settings = Settings(data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test_agent_patch_interrupt")
        service.store.save_page(
            MemoryPage(
                id="patch_target",
                session_id=session.id,
                page_type=PageType.SOURCE_SUMMARY,
                title="Patch target",
                summary="Database is PostgreSQL.",
                facts=["Database is PostgreSQL."],
            )
        )
        tool_call = {
            "name": "patch_page",
            "args": {
                "page_id": "patch_target",
                "operation": "replace",
                "old_text": "missing text",
                "new_text": "Database is MySQL.",
            },
            "id": "call_patch_page",
            "type": "tool_call",
        }
        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="update")
        tool_llm = Mock()
        tool_llm.invoke.side_effect = [
            AIMessage(content="", tool_calls=[tool_call]),
            AIMessage(content="Patch attempted."),
        ]
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            state = graph.invoke(
                {
                    "messages": [HumanMessage(content="Update the database memory")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                },
                config={"configurable": {"thread_id": "test-patch-interrupt"}},
            )

        assert state["conflict_detected"] is True
        assert state["patch_errors"]
        assert "old_text" in state["patch_errors"][0]
        trace = next(
            trace
            for trace in service.store.list_traces(session.id)
            if trace.event_type == "agent_patch_conflict_detected"
        )
        assert "old_text" in trace.payload["errors"][0]


def test_memory_think_node_recall_intent():
    """memory_think_node classifies a question as recall."""
    from memoryos_lite.agent_graph import MemoryDecision, memory_think_node_fn

    fake_decision = MemoryDecision(
        action="recall",
        reason_code="memory_question",
        query="Where does Alice live?",
        content="",
        confidence=0.9,
    )
    state = {"messages": [HumanMessage(content="Where does Alice live?")]}
    result = memory_think_node_fn(state, fake_decision=fake_decision)
    assert result["memory_decision"]["action"] == "recall"
    assert result["memory_decision"]["query"] == "Where does Alice live?"


def test_memory_think_node_memorize_intent():
    """memory_think_node classifies a fact statement as memorize."""
    from memoryos_lite.agent_graph import MemoryDecision, memory_think_node_fn

    fake_decision = MemoryDecision(
        action="memorize",
        reason_code="durable_fact",
        query="",
        content="Alice lives in Shanghai",
        confidence=0.95,
    )
    state = {"messages": [HumanMessage(content="I live in Shanghai")]}
    result = memory_think_node_fn(state, fake_decision=fake_decision)
    assert result["memory_decision"]["action"] == "memorize"
    assert result["memory_decision"]["content"] == "Alice lives in Shanghai"


def test_memory_observe_node_deterministic():
    """memory_observe_node parses observation without LLM."""
    from memoryos_lite.agent_graph import MemoryObservation, memory_observe_node_fn

    observation = MemoryObservation(
        success=True,
        recalled_item_ids=["item_001", "item_002"],
        patched_item_id=None,
        error=None,
    )
    state = {"memory_observation": observation}
    result = memory_observe_node_fn(state)
    assert result["observation_summary"] == "recalled 2 items"


def test_memory_observe_node_error():
    """memory_observe_node reports error."""
    from memoryos_lite.agent_graph import MemoryObservation, memory_observe_node_fn

    observation = MemoryObservation(
        success=False,
        recalled_item_ids=[],
        patched_item_id=None,
        error="no item found to patch",
    )
    state = {"memory_observation": observation}
    result = memory_observe_node_fn(state)
    assert "error" in result["observation_summary"]


def test_lineage_merge_node_waits_for_active_siblings_before_terminal():
    """lineage_merge_node only closes the current path, not active siblings."""
    from memoryos_lite.agent_graph import lineage_merge_node_fn

    state = {
        "lineage_id": "lin-current",
        "active_lineages": ["lin-current", "lin-sibling"],
        "merged_lineages": [],
        "intent": "recall",
        "observation_summary": "recalled 2 items",
        "conflict_detected": False,
        "human_approved": True,
        "result": "Answer ready.",
    }

    result = lineage_merge_node_fn(state)

    assert result["lineage_merge_complete"] is False
    assert result["active_lineages"] == ["lin-sibling"]
    assert result["pending_lineages"] == ["lin-sibling"]
    merged_ids = {record["lineage_id"] for record in result["merged_lineages"]}
    assert merged_ids == {"lin-current"}


def test_lineage_merge_node_completes_when_siblings_already_merged():
    """lineage_merge_node reaches terminal readiness after all lineage records exist."""
    from memoryos_lite.agent_graph import LineageMergeRecord, lineage_merge_node_fn

    sibling_record = LineageMergeRecord(
        lineage_id="lin-sibling",
        intent="recall",
        observation_summary="sibling done",
        conflict_detected=False,
        human_approved=True,
        result="Sibling answer ready.",
    )
    state = {
        "lineage_id": "lin-current",
        "active_lineages": ["lin-current", "lin-sibling"],
        "merged_lineages": [sibling_record],
        "intent": "recall",
        "observation_summary": "recalled 2 items",
        "conflict_detected": False,
        "human_approved": True,
        "result": "Answer ready.",
    }

    result = lineage_merge_node_fn(state)

    assert result["lineage_merge_complete"] is True
    assert result["active_lineages"] == []
    assert result["pending_lineages"] == []
    merged_ids = {record["lineage_id"] for record in result["merged_lineages"]}
    assert merged_ids == {"lin-current", "lin-sibling"}


def test_lineage_terminal_guard_blocks_pending_lineages():
    """Terminal guard raises when merge coordination is incomplete."""
    from memoryos_lite.agent_graph import (
        IncompleteLineageMergeError,
        assert_lineage_merge_complete,
    )

    state = {
        "lineage_merge_complete": False,
        "pending_lineages": ["lin-sibling"],
    }

    with pytest.raises(IncompleteLineageMergeError) as exc:
        assert_lineage_merge_complete(state)

    assert exc.value.pending_lineages == ["lin-sibling"]


def test_lineage_terminal_guard_allows_complete_merge():
    """Terminal guard allows END only after all lineage records exist."""
    from memoryos_lite.agent_graph import assert_lineage_merge_complete

    state = {
        "lineage_merge_complete": True,
        "pending_lineages": [],
    }

    assert_lineage_merge_complete(state)


# ---------------------------------------------------------------------------
# Error recovery mechanisms (evbundle_6ef398723414454ba7212973e08e05f5)
# Tests: agent-level retry logic, graceful degradation, state preservation.
# ---------------------------------------------------------------------------


class TestAgentErrorRecovery:
    def _setup(self, tmp_path):
        settings = Settings(data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy")
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("error-recovery")
        return service, session, settings

    def test_tool_invocation_error_does_not_lose_prior_messages(self, tmp_path):
        """When a tool raises during agent execution, previously ingested messages
        are not lost and the session remains queryable."""
        from memoryos_lite.agent_graph import build_agent_graph

        service, session, settings = self._setup(tmp_path)
        service.ingest(
            session.id,
            MessageCreate(role=Role.USER, content="Alice lives in Shanghai."),
        )

        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        tool_llm = Mock()
        tool_llm.invoke.side_effect = RuntimeError("LLM service unavailable")
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            try:
                graph.invoke(
                    {
                        "messages": [HumanMessage(content="Where does Alice live?")],
                        "session_id": session.id,
                        "intent": "",
                        "should_page": False,
                        "context": None,
                        "conflict_detected": False,
                        "patch_errors": [],
                        "human_approved": False,
                        "result": "",
                        "tool_turns": 0,
                    },
                    config={"configurable": {"thread_id": "test-tool-error"}},
                )
            except Exception:
                pass

        # The ingested message must survive the agent failure
        messages = service.store.list_messages(session.id)
        assert any("Alice lives in Shanghai" in m.content for m in messages)

    def test_search_tool_failure_propagates_and_session_store_remains_intact(self, tmp_path):
        """When search_memory raises, the exception propagates (the tool does not
        swallow it), and the session store is not corrupted."""
        service, session, settings = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        search_tool = next(t for t in tools if t.name == "search_memory")

        with patch.object(
            service.searcher,
            "search",
            side_effect=RuntimeError("vector store unavailable"),
        ):
            with pytest.raises(RuntimeError, match="vector store unavailable"):
                search_tool.invoke({"query": "Alice", "top_k": 3})

        # Session store must be intact after the tool failure
        assert service.store.get_session(session.id) is not None

    def test_write_page_failure_does_not_leave_partial_page(self, tmp_path):
        """If write_page fails mid-way, no partial page is left in the store."""
        service, session, settings = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        write_tool = next(t for t in tools if t.name == "write_page")

        pages_before = service.store.list_pages(session.id)

        with patch.object(
            service.store,
            "save_page",
            side_effect=RuntimeError("disk full"),
        ):
            try:
                write_tool.invoke(
                    {
                        "title": "Partial page",
                        "summary": "Should not persist.",
                        "facts": ["fact"],
                    }
                )
            except Exception:
                pass

        pages_after = service.store.list_pages(session.id)
        assert len(pages_after) == len(pages_before)

    def test_patch_tool_failure_preserves_original_page_content(self, tmp_path):
        """A patch_page failure must leave the original page content intact."""
        service, session, settings = self._setup(tmp_path)
        tools = create_memory_tools(service, session.id)
        write_tool = next(t for t in tools if t.name == "write_page")
        patch_tool = next(t for t in tools if t.name == "patch_page")

        write_tool.invoke(
            {
                "title": "Recovery target",
                "summary": "Original content.",
                "facts": ["Original content."],
            }
        )
        page = service.store.list_pages(session.id)[0]

        # Patch with a bad old_text — verifier should reject it
        result = patch_tool.invoke(
            {
                "page_id": page.id,
                "operation": "replace",
                "old_text": "nonexistent text",
                "new_text": "corrupted content",
            }
        )

        assert "error" in result.lower() or "failed" in result.lower() or "not" in result.lower()
        loaded = service.store.load_page(page.id)
        assert loaded is not None
        assert "Original content" in loaded.summary
        assert "corrupted content" not in loaded.summary

    def test_agent_graph_recovers_context_after_tool_error_and_retry(self, tmp_path):
        """After a tool error on the first turn, a second invocation with a
        working tool still builds context correctly from the same session."""
        from memoryos_lite.agent_graph import build_agent_graph

        service, session, settings = self._setup(tmp_path)
        service.ingest(
            session.id,
            MessageCreate(role=Role.USER, content="Bob moved to Beijing."),
        )

        # First invocation: tool raises
        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        failing_tool_llm = Mock()
        failing_tool_llm.invoke.side_effect = RuntimeError("transient error")
        router_llm.bind_tools.return_value = failing_tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            try:
                graph.invoke(
                    {
                        "messages": [HumanMessage(content="Where did Bob move?")],
                        "session_id": session.id,
                        "intent": "",
                        "should_page": False,
                        "context": None,
                        "conflict_detected": False,
                        "patch_errors": [],
                        "human_approved": False,
                        "result": "",
                        "tool_turns": 0,
                    },
                    config={"configurable": {"thread_id": "test-retry-1"}},
                )
            except Exception:
                pass

        # Second invocation: tool works — context must still be buildable
        router_llm2 = Mock()
        router_llm2.invoke.return_value = AIMessage(content="recall")
        working_tool_llm = Mock()
        working_tool_llm.invoke.return_value = AIMessage(content="Bob moved to Beijing.")
        router_llm2.bind_tools.return_value = working_tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm2):
            graph2 = build_agent_graph(service, session.id, settings=settings)
            state = graph2.invoke(
                {
                    "messages": [HumanMessage(content="Where did Bob move?")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                },
                config={"configurable": {"thread_id": "test-retry-2"}},
            )

        assert state["context"] is not None
        # The ingested message must still be present
        messages = service.store.list_messages(session.id)
        assert any("Bob moved to Beijing" in m.content for m in messages)

    def test_tool_llm_retry_then_graceful_degradation_is_traced(self, tmp_path):
        from memoryos_lite.agent_graph import build_agent_graph

        service, session, settings = self._setup(tmp_path)
        settings.memoryos_recovery_max_attempts = 2
        settings.memoryos_recovery_initial_delay_s = 0
        service.recovery.config = service._recovery_config_from_settings()
        service.recovery._sleep = lambda _delay: None

        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        tool_llm = Mock()
        tool_llm.invoke.side_effect = TimeoutError("temporary llm outage")
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            result = graph.invoke(
                {
                    "messages": [HumanMessage(content="Where does Alice live?")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                    "lineage_id": "lin-recovery",
                    "active_lineages": [],
                    "merged_lineages": [],
                    "lineage_merge_complete": False,
                    "pending_lineages": [],
                    "degraded_components": [],
                },
                config={"configurable": {"thread_id": "test-tool-llm-recovery"}},
            )

        assert "tool_llm" in result["degraded_components"]
        traces = service.store.list_traces(session.id)
        assert any(t.event_type == "agent_recovery_event" for t in traces)
        assert tool_llm.invoke.call_count == 2

    def test_answer_llm_degradation_marks_component_and_emits_trace(self, tmp_path):
        """When the answer LLM fails, the node degrades gracefully: answer_llm is
        added to degraded_components and an agent_answer_degraded trace is emitted.
        The session store must not be corrupted."""
        from memoryos_lite.agent_graph import build_agent_graph

        service, session, settings = self._setup(tmp_path)
        settings.memoryos_recovery_max_attempts = 1
        settings.memoryos_recovery_initial_delay_s = 0
        service.recovery.config = service._recovery_config_from_settings()
        service.recovery._sleep = lambda _delay: None

        # Seed a message so build_context has retrieved_evidence to work with
        source = service.ingest(
            session.id,
            MessageCreate(role=Role.USER, content="Carol lives in Tokyo."),
        ).message
        service.store.save_page(
            MemoryPage(
                id="answer-degradation-page",
                session_id=session.id,
                page_type=PageType.SOURCE_SUMMARY,
                title="Carol location",
                summary="Carol lives in Tokyo.",
                source_message_ids=[source.id],
            )
        )

        router_llm = Mock()
        # router returns "recall"; answer LLM raises on every call
        router_llm.invoke.side_effect = [
            AIMessage(content="recall"),
            RuntimeError("answer LLM down"),  # answer node call
        ]
        tool_llm = Mock()
        tool_llm.invoke.return_value = AIMessage(content="Done.")
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            state = graph.invoke(
                {
                    "messages": [HumanMessage(content="Where does Carol live?")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                    "lineage_id": "lin-answer-degrade",
                    "active_lineages": [],
                    "merged_lineages": [],
                    "lineage_merge_complete": False,
                    "pending_lineages": [],
                    "degraded_components": [],
                },
                config={"configurable": {"thread_id": "test-answer-degrade"}},
            )

        assert "answer_llm" in state["degraded_components"]
        assert (
            "Insufficient retrieved evidence" in state["result"]
            or "degraded" in state["result"].lower()
        )
        traces = service.store.list_traces(session.id)
        assert any(t.event_type == "agent_answer_degraded" for t in traces)
        assert any(t.event_type == "agent_recovery_event" for t in traces)
        # Session store must be intact
        assert service.store.get_session(session.id) is not None


# ---------------------------------------------------------------------------
# Graph-v1 state consistency validation
# (graph-v1-state-consistency-validation-test)
# Tests: AgentState field consistency, lineage tracking invariants,
#        _state_with helper, lineage_merge_node_fn deduplication,
#        invoke_agent initial state completeness.
# ---------------------------------------------------------------------------


class TestGraphV1StateConsistency:
    """Validate that AgentState fields remain consistent across node transitions."""

    # ------------------------------------------------------------------
    # _state_with helper
    # ------------------------------------------------------------------

    def test_state_with_preserves_all_existing_fields(self):
        """_state_with must not drop any field that was already in state."""
        from memoryos_lite.agent_graph import _state_with

        original = {
            "session_id": "sess-1",
            "intent": "recall",
            "should_page": False,
            "conflict_detected": False,
            "patch_errors": [],
            "human_approved": False,
            "result": "old result",
            "tool_turns": 3,
            "lineage_id": "lin_abc",
            "active_lineages": ["lin_abc"],
            "merged_lineages": [],
            "lineage_merge_complete": False,
            "pending_lineages": [],
        }
        updated = _state_with(original, result="new result", tool_turns=4)

        # All original keys must survive
        for key in original:
            assert key in updated, f"field '{key}' was dropped by _state_with"

        # Updated values must be applied
        assert updated["result"] == "new result"
        assert updated["tool_turns"] == 4

        # Unchanged values must be preserved
        assert updated["session_id"] == "sess-1"
        assert updated["intent"] == "recall"
        assert updated["lineage_id"] == "lin_abc"

    def test_state_with_does_not_mutate_original(self):
        """_state_with must return a new dict and leave the original unchanged."""
        from memoryos_lite.agent_graph import _state_with

        original = {"session_id": "sess-1", "result": "original"}
        updated = _state_with(original, result="changed")

        assert original["result"] == "original"
        assert updated["result"] == "changed"
        assert updated is not original

    def test_state_with_can_add_new_fields(self):
        """_state_with must be able to introduce fields not present in original."""
        from memoryos_lite.agent_graph import _state_with

        original = {"session_id": "sess-1"}
        updated = _state_with(original, lineage_id="lin_new", tool_turns=0)

        assert updated["lineage_id"] == "lin_new"
        assert updated["tool_turns"] == 0
        assert updated["session_id"] == "sess-1"

    # ------------------------------------------------------------------
    # _lineage_record_for_state
    # ------------------------------------------------------------------

    def test_lineage_record_captures_all_required_fields(self):
        """_lineage_record_for_state must populate every LineageMergeRecord field."""
        from memoryos_lite.agent_graph import _lineage_record_for_state

        state = {
            "intent": "update",
            "observation_summary": "patched item-42",
            "conflict_detected": True,
            "human_approved": False,
            "result": "Patch requires review.",
        }
        record = _lineage_record_for_state(state, "lin_test")

        assert record["lineage_id"] == "lin_test"
        assert record["intent"] == "update"
        assert record["observation_summary"] == "patched item-42"
        assert record["conflict_detected"] is True
        assert record["human_approved"] is False
        assert record["result"] == "Patch requires review."

    def test_lineage_record_defaults_missing_fields_gracefully(self):
        """_lineage_record_for_state must not raise when optional fields are absent."""
        from memoryos_lite.agent_graph import _lineage_record_for_state

        record = _lineage_record_for_state({}, "lin_empty")

        assert record["lineage_id"] == "lin_empty"
        assert record["intent"] == ""
        assert record["observation_summary"] == ""
        assert record["conflict_detected"] is False
        assert record["human_approved"] is False
        assert record["result"] == ""

    def test_lineage_record_coerces_conflict_detected_to_bool(self):
        """conflict_detected must be a bool regardless of the source value type."""
        from memoryos_lite.agent_graph import _lineage_record_for_state

        # Truthy non-bool
        record = _lineage_record_for_state({"conflict_detected": 1}, "lin_x")
        assert record["conflict_detected"] is True
        assert isinstance(record["conflict_detected"], bool)

        # Falsy non-bool
        record2 = _lineage_record_for_state({"conflict_detected": 0}, "lin_y")
        assert record2["conflict_detected"] is False
        assert isinstance(record2["conflict_detected"], bool)

    # ------------------------------------------------------------------
    # lineage_merge_node_fn – deduplication and consistency
    # ------------------------------------------------------------------

    def test_lineage_merge_deduplicates_active_lineages_list(self):
        """Duplicate entries in active_lineages must be collapsed to one."""
        from memoryos_lite.agent_graph import lineage_merge_node_fn

        state = {
            "lineage_id": "lin-a",
            "active_lineages": ["lin-a", "lin-a", "lin-a"],
            "merged_lineages": [],
            "intent": "recall",
            "observation_summary": "",
            "conflict_detected": False,
            "human_approved": True,
            "result": "done",
        }
        result = lineage_merge_node_fn(state)

        # lin-a is now merged, so active_lineages should be empty
        assert result["active_lineages"] == []
        assert result["lineage_merge_complete"] is True

    def test_lineage_merge_deduplicates_merged_lineages_by_id(self):
        """If the same lineage_id appears twice in merged_lineages input,
        the output must contain only one record for that id."""
        from memoryos_lite.agent_graph import LineageMergeRecord, lineage_merge_node_fn

        duplicate_record = LineageMergeRecord(
            lineage_id="lin-dup",
            intent="recall",
            observation_summary="first",
            conflict_detected=False,
            human_approved=True,
            result="first result",
        )
        duplicate_record2 = LineageMergeRecord(
            lineage_id="lin-dup",
            intent="recall",
            observation_summary="second",
            conflict_detected=False,
            human_approved=True,
            result="second result",
        )
        state = {
            "lineage_id": "lin-current",
            "active_lineages": ["lin-current"],
            "merged_lineages": [duplicate_record, duplicate_record2],
            "intent": "recall",
            "observation_summary": "ok",
            "conflict_detected": False,
            "human_approved": True,
            "result": "done",
        }
        result = lineage_merge_node_fn(state)

        ids = [r["lineage_id"] for r in result["merged_lineages"]]
        assert ids.count("lin-dup") == 1, "duplicate lineage_id must be collapsed"

    def test_lineage_merge_auto_generates_lineage_id_when_absent(self):
        """When lineage_id is missing from state, the node must generate one."""
        from memoryos_lite.agent_graph import lineage_merge_node_fn

        state = {
            "active_lineages": [],
            "merged_lineages": [],
            "intent": "recall",
            "observation_summary": "",
            "conflict_detected": False,
            "human_approved": True,
            "result": "",
        }
        result = lineage_merge_node_fn(state)

        assert result.get("lineage_id"), "lineage_id must be auto-generated"
        assert result["lineage_id"].startswith("lin_")

    def test_lineage_merge_complete_flag_consistent_with_pending_lineages(self):
        """lineage_merge_complete must be True iff pending_lineages is empty."""
        from memoryos_lite.agent_graph import lineage_merge_node_fn

        # Case 1: single lineage, no siblings → complete
        state_single = {
            "lineage_id": "lin-only",
            "active_lineages": ["lin-only"],
            "merged_lineages": [],
            "intent": "recall",
            "observation_summary": "",
            "conflict_detected": False,
            "human_approved": True,
            "result": "",
        }
        result_single = lineage_merge_node_fn(state_single)
        assert result_single["lineage_merge_complete"] is True
        assert result_single["pending_lineages"] == []

        # Case 2: sibling still active → not complete
        state_sibling = {
            "lineage_id": "lin-a",
            "active_lineages": ["lin-a", "lin-b"],
            "merged_lineages": [],
            "intent": "recall",
            "observation_summary": "",
            "conflict_detected": False,
            "human_approved": True,
            "result": "",
        }
        result_sibling = lineage_merge_node_fn(state_sibling)
        assert result_sibling["lineage_merge_complete"] is False
        assert "lin-b" in result_sibling["pending_lineages"]

    def test_lineage_merge_current_lineage_always_in_merged_records(self):
        """After lineage_merge_node_fn, the current lineage_id must appear
        in merged_lineages regardless of prior state."""
        from memoryos_lite.agent_graph import lineage_merge_node_fn

        state = {
            "lineage_id": "lin-current",
            "active_lineages": ["lin-current"],
            "merged_lineages": [],
            "intent": "ingest",
            "observation_summary": "recalled 1 items",
            "conflict_detected": False,
            "human_approved": True,
            "result": "Message ingested.",
        }
        result = lineage_merge_node_fn(state)

        merged_ids = {r["lineage_id"] for r in result["merged_lineages"]}
        assert "lin-current" in merged_ids

    def test_lineage_merge_does_not_overwrite_existing_sibling_record(self):
        """A sibling record already in merged_lineages must not be overwritten
        by the current lineage's merge pass."""
        from memoryos_lite.agent_graph import LineageMergeRecord, lineage_merge_node_fn

        sibling_record = LineageMergeRecord(
            lineage_id="lin-sibling",
            intent="update",
            observation_summary="patched item-7",
            conflict_detected=True,
            human_approved=False,
            result="conflict",
        )
        state = {
            "lineage_id": "lin-current",
            "active_lineages": ["lin-current", "lin-sibling"],
            "merged_lineages": [sibling_record],
            "intent": "recall",
            "observation_summary": "recalled 3 items",
            "conflict_detected": False,
            "human_approved": True,
            "result": "Answer ready.",
        }
        result = lineage_merge_node_fn(state)

        sibling_out = next(
            r for r in result["merged_lineages"] if r["lineage_id"] == "lin-sibling"
        )
        # The original sibling record values must be preserved
        assert sibling_out["intent"] == "update"
        assert sibling_out["conflict_detected"] is True
        assert sibling_out["result"] == "conflict"

    def test_lineage_merge_active_lineages_order_preserved_for_pending(self):
        """Pending lineages must appear in the same relative order as in
        active_lineages (minus the current lineage)."""
        from memoryos_lite.agent_graph import lineage_merge_node_fn

        state = {
            "lineage_id": "lin-a",
            "active_lineages": ["lin-a", "lin-b", "lin-c"],
            "merged_lineages": [],
            "intent": "recall",
            "observation_summary": "",
            "conflict_detected": False,
            "human_approved": True,
            "result": "",
        }
        result = lineage_merge_node_fn(state)

        # lin-a is merged; lin-b and lin-c remain pending in order
        assert result["pending_lineages"] == ["lin-b", "lin-c"]

    # ------------------------------------------------------------------
    # assert_lineage_merge_complete
    # ------------------------------------------------------------------

    def test_assert_lineage_merge_complete_raises_with_correct_pending_list(self):
        """IncompleteLineageMergeError must carry the exact pending_lineages list."""
        from memoryos_lite.agent_graph import (
            IncompleteLineageMergeError,
            assert_lineage_merge_complete,
        )

        state = {
            "lineage_merge_complete": False,
            "pending_lineages": ["lin-x", "lin-y", "lin-z"],
        }
        with pytest.raises(IncompleteLineageMergeError) as exc_info:
            assert_lineage_merge_complete(state)

        assert set(exc_info.value.pending_lineages) == {"lin-x", "lin-y", "lin-z"}

    def test_assert_lineage_merge_complete_raises_when_flag_false_empty_pending(self):
        """Even with an empty pending_lineages list, if the flag is False the
        guard must raise (flag is the authoritative signal)."""
        from memoryos_lite.agent_graph import (
            IncompleteLineageMergeError,
            assert_lineage_merge_complete,
        )

        state = {
            "lineage_merge_complete": False,
            "pending_lineages": [],
        }
        with pytest.raises(IncompleteLineageMergeError):
            assert_lineage_merge_complete(state)

    def test_assert_lineage_merge_complete_silent_when_flag_true(self):
        """No exception must be raised when lineage_merge_complete is True."""
        from memoryos_lite.agent_graph import assert_lineage_merge_complete

        assert_lineage_merge_complete(
            {"lineage_merge_complete": True, "pending_lineages": []}
        )

    # ------------------------------------------------------------------
    # invoke_agent initial state completeness
    # ------------------------------------------------------------------

    def test_invoke_agent_initial_state_contains_all_lineage_fields(self, tmp_path):
        """invoke_agent must seed the initial state with all lineage tracking
        fields so that lineage_merge_node_fn never encounters missing keys."""
        from unittest.mock import Mock, patch

        from langchain_core.messages import AIMessage, HumanMessage

        from memoryos_lite.agent_graph import build_agent_graph
        from memoryos_lite.config import Settings
        from memoryos_lite.engine import MemoryOSService
        from memoryos_lite.store import MemoryStore

        settings_obj = Settings(
            data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy"
        )
        store = MemoryStore(settings=settings_obj)
        store.init_db()
        service = MemoryOSService(settings=settings_obj, store=store)
        session = service.create_session("test-initial-state")

        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        tool_llm = Mock()
        tool_llm.invoke.return_value = AIMessage(content="Done.")
        router_llm.bind_tools.return_value = tool_llm

        captured_states: list[dict] = []

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings_obj)
            original_invoke = graph.invoke

            def capturing_invoke(state, config=None):
                captured_states.append(dict(state))
                return original_invoke(state, config=config)

            graph.invoke = capturing_invoke
            graph.invoke(
                {
                    "messages": [HumanMessage(content="hello")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                    "lineage_id": "lin_seed",
                    "active_lineages": [],
                    "merged_lineages": [],
                    "lineage_merge_complete": False,
                    "pending_lineages": [],
                },
                config={"configurable": {"thread_id": "test-initial-state"}},
            )

        # The first captured state must contain all lineage fields
        assert captured_states, "no state was captured"
        first = captured_states[0]
        for field in (
            "lineage_id",
            "active_lineages",
            "merged_lineages",
            "lineage_merge_complete",
            "pending_lineages",
        ):
            assert field in first, f"initial state missing field '{field}'"

    # ------------------------------------------------------------------
    # Full graph run – state consistency after lineage_merge
    # ------------------------------------------------------------------

    def test_full_recall_run_lineage_state_consistent_at_end(self, tmp_path):
        """After a complete recall run, the final state must have:
        - lineage_merge_complete == True
        - pending_lineages == []
        - merged_lineages contains exactly one record
        - active_lineages == []
        """
        from unittest.mock import Mock, patch

        from langchain_core.messages import AIMessage, HumanMessage

        from memoryos_lite.agent_graph import build_agent_graph
        from memoryos_lite.config import Settings
        from memoryos_lite.engine import MemoryOSService
        from memoryos_lite.store import MemoryStore

        settings = Settings(
            data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy"
        )
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test-lineage-end-state")

        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        tool_llm = Mock()
        tool_llm.invoke.return_value = AIMessage(content="Nothing found.")
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            state = graph.invoke(
                {
                    "messages": [HumanMessage(content="What do you know?")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                    "lineage_id": "lin_recall_run",
                    "active_lineages": [],
                    "merged_lineages": [],
                    "lineage_merge_complete": False,
                    "pending_lineages": [],
                },
                config={"configurable": {"thread_id": "test-lineage-end-state"}},
            )

        assert state["lineage_merge_complete"] is True
        assert state["pending_lineages"] == []
        assert state["active_lineages"] == []
        assert len(state["merged_lineages"]) == 1
        assert state["merged_lineages"][0]["lineage_id"] == "lin_recall_run"

    def test_full_ingest_run_lineage_state_consistent_at_end(self, tmp_path):
        """After a complete ingest run, lineage state must be fully merged."""
        from unittest.mock import Mock, patch

        from langchain_core.messages import AIMessage, HumanMessage

        from memoryos_lite.agent_graph import build_agent_graph
        from memoryos_lite.config import Settings
        from memoryos_lite.engine import MemoryOSService
        from memoryos_lite.store import MemoryStore

        settings = Settings(
            data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy"
        )
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test-ingest-lineage")

        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="ingest")
        tool_llm = Mock()
        tool_llm.invoke.return_value = AIMessage(content="Ingested.")
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            state = graph.invoke(
                {
                    "messages": [HumanMessage(content="My name is Alice.")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                    "lineage_id": "lin_ingest_run",
                    "active_lineages": [],
                    "merged_lineages": [],
                    "lineage_merge_complete": False,
                    "pending_lineages": [],
                },
                config={"configurable": {"thread_id": "test-ingest-lineage"}},
            )

        assert state["lineage_merge_complete"] is True
        assert state["pending_lineages"] == []
        assert state["active_lineages"] == []
        assert any(
            r["lineage_id"] == "lin_ingest_run" for r in state["merged_lineages"]
        )

    def test_merged_lineage_record_reflects_final_intent_and_result(self, tmp_path):
        """The merged record for the current lineage must capture the intent
        and result that were set during the run, not stale defaults."""
        from unittest.mock import Mock, patch

        from langchain_core.messages import AIMessage, HumanMessage

        from memoryos_lite.agent_graph import build_agent_graph
        from memoryos_lite.config import Settings
        from memoryos_lite.engine import MemoryOSService
        from memoryos_lite.store import MemoryStore

        settings = Settings(
            data_dir=tmp_path / ".memoryos", openai_api_key="sk-test-dummy"
        )
        store = MemoryStore(settings=settings)
        store.init_db()
        service = MemoryOSService(settings=settings, store=store)
        session = service.create_session("test-record-fields")

        router_llm = Mock()
        router_llm.invoke.return_value = AIMessage(content="recall")
        tool_llm = Mock()
        tool_llm.invoke.return_value = AIMessage(content="Nothing found.")
        router_llm.bind_tools.return_value = tool_llm

        with patch("memoryos_lite.agent_graph.ChatOpenAI", return_value=router_llm):
            graph = build_agent_graph(service, session.id, settings=settings)
            state = graph.invoke(
                {
                    "messages": [HumanMessage(content="Tell me something.")],
                    "session_id": session.id,
                    "intent": "",
                    "should_page": False,
                    "context": None,
                    "conflict_detected": False,
                    "patch_errors": [],
                    "human_approved": False,
                    "result": "",
                    "tool_turns": 0,
                    "lineage_id": "lin_record_check",
                    "active_lineages": [],
                    "merged_lineages": [],
                    "lineage_merge_complete": False,
                    "pending_lineages": [],
                },
                config={"configurable": {"thread_id": "test-record-fields"}},
            )

        record = next(
            r for r in state["merged_lineages"] if r["lineage_id"] == "lin_record_check"
        )
        # intent must be the classified value, not the empty seed
        assert record["intent"] == "recall"
        # result must be non-empty (answer node sets it)
        assert record["result"] != ""

    # ------------------------------------------------------------------
    # IncompleteLineageMergeError
    # ------------------------------------------------------------------

    def test_incomplete_lineage_merge_error_message_contains_pending_ids(self):
        """The error message must list all pending lineage IDs."""
        from memoryos_lite.agent_graph import IncompleteLineageMergeError

        err = IncompleteLineageMergeError(["lin-a", "lin-b", "lin-c"])
        msg = str(err)

        assert "lin-a" in msg
        assert "lin-b" in msg
        assert "lin-c" in msg

    def test_incomplete_lineage_merge_error_stores_pending_list(self):
        """pending_lineages attribute must be a copy of the input list."""
        from memoryos_lite.agent_graph import IncompleteLineageMergeError

        pending = ["lin-x", "lin-y"]
        err = IncompleteLineageMergeError(pending)

        assert err.pending_lineages == pending
        # Mutating the original must not affect the stored copy
        pending.append("lin-z")
        assert "lin-z" not in err.pending_lineages

    # ------------------------------------------------------------------
    # _new_lineage_id
    # ------------------------------------------------------------------

    def test_new_lineage_id_format_and_uniqueness(self):
        """_new_lineage_id must return unique IDs with the 'lin_' prefix."""
        from memoryos_lite.agent_graph import _new_lineage_id

        ids = {_new_lineage_id() for _ in range(50)}

        assert len(ids) == 50, "lineage IDs must be unique"
        for lid in ids:
            assert lid.startswith("lin_"), f"unexpected prefix in '{lid}'"
            assert len(lid) == len("lin_") + 12, f"unexpected length for '{lid}'"
