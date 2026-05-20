"""Demo eval: end-to-end memory lifecycle through structured agent."""
from langchain_core.messages import HumanMessage

from memoryos_lite.agent_graph import (
    MemoryDecision,
    memory_action_node_fn,
    memory_observe_node_fn,
    memory_think_node_fn,
)
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.store import create_store


def test_demo_memorize_then_recall(tmp_path):
    """User states fact -> memorize -> later recall -> correct answer."""
    settings = Settings(data_dir=str(tmp_path))
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("demo")

    # Step 1: Memorize
    think_state = memory_think_node_fn(
        {"messages": [HumanMessage(content="I live in Shanghai")],
         "session_id": session.id},
        fake_decision=MemoryDecision(
            action="memorize", reason_code="durable_fact",
            query="", content="User lives in Shanghai", confidence=0.95,
        ),
    )
    action_state = memory_action_node_fn(
        {**think_state, "session_id": session.id}, service=service
    )
    assert action_state["memory_observation"]["success"]

    # Step 2: Recall
    think_state2 = memory_think_node_fn(
        {"messages": [HumanMessage(content="Where do I live?")],
         "session_id": session.id},
        fake_decision=MemoryDecision(
            action="recall", reason_code="memory_question",
            query="Where does user live?", content="", confidence=0.9,
        ),
    )
    action_state2 = memory_action_node_fn(
        {**think_state2, "session_id": session.id}, service=service
    )
    assert action_state2["memory_observation"]["success"]
    assert len(action_state2["memory_observation"]["recalled_item_ids"]) >= 1


def test_demo_patch_corrects_fact(tmp_path):
    """User corrects fact -> patch -> recall returns updated value."""
    settings = Settings(data_dir=str(tmp_path))
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("demo")

    # Memorize original
    memory_action_node_fn(
        {"session_id": session.id, "memory_decision": MemoryDecision(
            action="memorize", reason_code="durable_fact",
            query="", content="User lives in Shanghai", confidence=0.95,
        )},
        service=service,
    )

    # Patch
    action_state = memory_action_node_fn(
        {"session_id": session.id, "memory_decision": MemoryDecision(
            action="patch", reason_code="correction",
            query="User lives", content="User lives in Beijing",
            confidence=0.9,
        )},
        service=service,
    )
    assert action_state["memory_observation"]["success"]
    assert action_state["memory_observation"]["patched_item_id"] is not None

    # Verify patched content
    items = store.list_items(session.id)
    assert any("Beijing" in item.content for item in items)


def test_demo_none_skips_tools(tmp_path):
    """Irrelevant input -> none -> no memory action."""
    settings = Settings(data_dir=str(tmp_path))
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("demo")

    action_state = memory_action_node_fn(
        {"session_id": session.id, "memory_decision": MemoryDecision(
            action="none", reason_code="irrelevant",
            query="", content="", confidence=0.1,
        )},
        service=service,
    )
    assert action_state["memory_observation"]["success"]
    assert action_state["memory_observation"]["recalled_item_ids"] == []
    assert store.list_items(session.id) == []


def test_demo_observe_after_recall(tmp_path):
    """Observe node produces summary after recall."""
    settings = Settings(data_dir=str(tmp_path))
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("demo")

    # Memorize first
    memory_action_node_fn(
        {"session_id": session.id, "memory_decision": MemoryDecision(
            action="memorize", reason_code="durable_fact",
            query="", content="User likes TypeScript", confidence=0.9,
        )},
        service=service,
    )

    # Recall
    action_state = memory_action_node_fn(
        {"session_id": session.id, "memory_decision": MemoryDecision(
            action="recall", reason_code="memory_question",
            query="TypeScript", content="", confidence=0.9,
        )},
        service=service,
    )

    # Observe
    obs_state = memory_observe_node_fn(action_state)
    assert "recalled" in obs_state["observation_summary"]
