# Phase 3: Answer Eval Baseline + Structured Memory Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish answer accuracy baseline on LongMemEval using existing LLM judge, then implement a structured Think-Act-Observe agent loop with Letta-style memory lifecycle actions (memorize/recall/patch).

**Architecture:** Extend existing LangGraph `agent_graph.py` with three new nodes (memory_think, memory_action, memory_observe) that use deterministic dispatch from a `MemoryDecision` structured output. A separate `build_context_node` handles context assembly for all paths.

**Tech Stack:** LangGraph, langchain_openai (DeepSeek), existing MemoryOSService, existing tool infrastructure.

---

## File Structure

| File | Role |
|------|------|
| `src/memoryos_lite/agent_graph.py` | Add MemoryDecision, think/action/observe/build_context nodes |
| `tests/test_agent.py` | Deterministic tests for new nodes |
| `tests/test_agent_demo.py` | Demo eval cases (memorize/recall/patch lifecycle) |

---

### Task 0: Establish Answer Accuracy Baseline

**Files:** None (run existing infrastructure)

- [ ] **Step 1: Run LongMemEval with LLM answer + LLM judge**

Run:
```bash
uv run memoryos eval public --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite --limit 50 \
  --llm-answer --llm-judge \
  --run-id phase3_answer_baseline
```

- [ ] **Step 2: Record baseline metrics**

Check the report for answer accuracy distribution (pass/fail/error).
This establishes the baseline for future comparison.

- [ ] **Step 3: No commit needed** (data only)

---

### Task 1: MemoryDecision Schema + memory_think_node

**Files:**
- Modify: `src/memoryos_lite/agent_graph.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_agent.py — add at end
def test_memory_think_node_recall_intent():
    """memory_think_node classifies a question as recall."""
    from memoryos_lite.agent_graph import MemoryDecision, memory_think_node_fn

    fake_llm_response = MemoryDecision(
        action="recall",
        reason_code="memory_question",
        query="Where does Alice live?",
        content="",
        confidence=0.9,
    )
    state = {"messages": [HumanMessage(content="Where does Alice live?")]}
    result = memory_think_node_fn(state, fake_decision=fake_llm_response)
    assert result["memory_decision"]["action"] == "recall"
    assert result["memory_decision"]["query"] == "Where does Alice live?"


def test_memory_think_node_memorize_intent():
    """memory_think_node classifies a fact statement as memorize."""
    from memoryos_lite.agent_graph import MemoryDecision, memory_think_node_fn

    fake_llm_response = MemoryDecision(
        action="memorize",
        reason_code="durable_fact",
        query="",
        content="Alice lives in Shanghai",
        confidence=0.95,
    )
    state = {"messages": [HumanMessage(content="I live in Shanghai")]}
    result = memory_think_node_fn(state, fake_decision=fake_llm_response)
    assert result["memory_decision"]["action"] == "memorize"
    assert result["memory_decision"]["content"] == "Alice lives in Shanghai"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent.py::test_memory_think_node_recall_intent -v`
Expected: FAIL — `MemoryDecision` and `memory_think_node_fn` not defined.

- [ ] **Step 3: Implement MemoryDecision and memory_think_node_fn**

Add to `src/memoryos_lite/agent_graph.py` after the `AgentState` class:

```python
from typing import Literal


class MemoryDecision(TypedDict):
    """Structured output from memory_think_node."""

    action: Literal["memorize", "recall", "patch", "answer_directly", "none"]
    reason_code: Literal[
        "durable_fact", "memory_question", "correction",
        "sufficient_context", "irrelevant",
    ]
    query: str
    content: str
    confidence: float
```

Add `memory_decision: MemoryDecision | None` to `AgentState`.

Add the node function:

```python
def memory_think_node_fn(
    state: AgentState,
    fake_decision: MemoryDecision | None = None,
) -> AgentState:
    """Classify user message into a memory lifecycle action."""
    if fake_decision is not None:
        return _state_with(state, memory_decision=fake_decision)
    # LLM path (real mode) — structured output
    messages = state.get("messages", [])
    last_msg = _content_text(messages[-1].content) if messages else ""
    system = SystemMessage(
        content=(
            "Classify this message into a memory action.\n"
            "- memorize: user states a durable fact worth remembering\n"
            "- recall: user asks a question requiring memory lookup\n"
            "- patch: user corrects a previously stored fact\n"
            "- answer_directly: sufficient context already available\n"
            "- none: irrelevant or no memory action needed\n\n"
            "Respond with JSON: {action, reason_code, query, content, confidence}"
        )
    )
    response = llm.invoke([system, HumanMessage(content=last_msg)])
    # Parse structured response
    import json as _json
    try:
        data = _json.loads(_content_text(response.content))
        decision = MemoryDecision(
            action=data.get("action", "none"),
            reason_code=data.get("reason_code", "irrelevant"),
            query=data.get("query", ""),
            content=data.get("content", ""),
            confidence=data.get("confidence", 0.5),
        )
    except (ValueError, KeyError):
        decision = MemoryDecision(
            action="none", reason_code="irrelevant",
            query="", content="", confidence=0.0,
        )
    return _state_with(state, memory_decision=decision)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent.py::test_memory_think_node_recall_intent tests/test_agent.py::test_memory_think_node_memorize_intent -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/agent_graph.py tests/test_agent.py
git commit -m "feat(agent): add MemoryDecision schema + memory_think_node"
```

---

### Task 2: memory_action_node (deterministic dispatch)

**Files:**
- Modify: `src/memoryos_lite/agent_graph.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_agent.py — add at end
def test_memory_action_node_memorize(tmp_path):
    """memory_action_node dispatches memorize → memorize_item."""
    from memoryos_lite.agent_graph import MemoryDecision, memory_action_node_fn
    from memoryos_lite.config import Settings
    from memoryos_lite.engine import MemoryOSService
    from memoryos_lite.store import create_store

    settings = Settings(data_dir=str(tmp_path))
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("test")

    decision = MemoryDecision(
        action="memorize",
        reason_code="durable_fact",
        query="",
        content="Alice lives in Shanghai",
        confidence=0.9,
    )
    state = {"session_id": session.id, "memory_decision": decision}
    result = memory_action_node_fn(state, service=service)
    assert result["memory_observation"]["success"] is True
    items = store.list_items(session.id)
    assert any("Shanghai" in item.content for item in items)


def test_memory_action_node_recall(tmp_path):
    """memory_action_node dispatches recall → recall_items."""
    from memoryos_lite.agent_graph import MemoryDecision, memory_action_node_fn
    from memoryos_lite.config import Settings
    from memoryos_lite.engine import MemoryOSService
    from memoryos_lite.store import create_store

    settings = Settings(data_dir=str(tmp_path))
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("test")
    service.ingest(session.id, MessageCreate(role=Role.USER, content="I live in Shanghai"))
    service.page(session.id)

    decision = MemoryDecision(
        action="recall",
        reason_code="memory_question",
        query="Where does Alice live?",
        content="",
        confidence=0.9,
    )
    state = {"session_id": session.id, "memory_decision": decision}
    result = memory_action_node_fn(state, service=service)
    assert result["memory_observation"]["success"] is True
    assert len(result["memory_observation"]["recalled_item_ids"]) >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent.py::test_memory_action_node_memorize -v`
Expected: FAIL — `memory_action_node_fn` not defined.

- [ ] **Step 3: Implement memory_action_node_fn and MemoryObservation**

Add to `src/memoryos_lite/agent_graph.py`:

```python
class MemoryObservation(TypedDict):
    """Result of memory_action_node execution."""

    success: bool
    recalled_item_ids: list[str]
    patched_item_id: str | None
    error: str | None


def memory_action_node_fn(
    state: AgentState,
    service: MemoryOSService | None = None,
) -> AgentState:
    """Deterministic dispatch based on MemoryDecision."""
    decision = state.get("memory_decision")
    if decision is None:
        return _state_with(
            state,
            memory_observation=MemoryObservation(
                success=False, recalled_item_ids=[],
                patched_item_id=None, error="no decision",
            ),
        )
    session = state.get("session_id", "")
    action = decision["action"]

    if action == "memorize":
        item = service.memorize_item(session, decision["content"])
        return _state_with(
            state,
            memory_observation=MemoryObservation(
                success=True, recalled_item_ids=[item.id],
                patched_item_id=None, error=None,
            ),
        )
    if action == "recall":
        items = service.recall_items(session, decision["query"])
        return _state_with(
            state,
            memory_observation=MemoryObservation(
                success=True,
                recalled_item_ids=[item.id for item in items],
                patched_item_id=None, error=None,
            ),
        )
    if action == "patch":
        items = service.recall_items(session, decision["query"])
        if not items:
            return _state_with(
                state,
                memory_observation=MemoryObservation(
                    success=False, recalled_item_ids=[],
                    patched_item_id=None,
                    error="no item found to patch",
                ),
            )
        target = items[0]
        service.patch_item(session, target.id, decision["content"])
        return _state_with(
            state,
            memory_observation=MemoryObservation(
                success=True,
                recalled_item_ids=[item.id for item in items],
                patched_item_id=target.id, error=None,
            ),
        )
    # answer_directly / none → skip
    return _state_with(
        state,
        memory_observation=MemoryObservation(
            success=True, recalled_item_ids=[],
            patched_item_id=None, error=None,
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent.py::test_memory_action_node_memorize tests/test_agent.py::test_memory_action_node_recall -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/agent_graph.py tests/test_agent.py
git commit -m "feat(agent): add memory_action_node with deterministic dispatch"
```

---

### Task 3: memory_observe_node + build_context_node

**Files:**
- Modify: `src/memoryos_lite/agent_graph.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_agent.py — add at end
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent.py::test_memory_observe_node_deterministic -v`
Expected: FAIL — `memory_observe_node_fn` not defined.

- [ ] **Step 3: Implement memory_observe_node_fn**

Add to `src/memoryos_lite/agent_graph.py`:

```python
def memory_observe_node_fn(state: AgentState) -> AgentState:
    """Deterministic summary of memory action results."""
    obs = state.get("memory_observation")
    if obs is None:
        return _state_with(state, observation_summary="no observation")
    if not obs["success"]:
        return _state_with(
            state, observation_summary=f"error: {obs['error']}"
        )
    parts = []
    if obs["recalled_item_ids"]:
        parts.append(f"recalled {len(obs['recalled_item_ids'])} items")
    if obs["patched_item_id"]:
        parts.append(f"patched {obs['patched_item_id']}")
    if not parts:
        parts.append("no memory action taken")
    return _state_with(state, observation_summary="; ".join(parts))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent.py::test_memory_observe_node_deterministic tests/test_agent.py::test_memory_observe_node_error -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memoryos_lite/agent_graph.py tests/test_agent.py
git commit -m "feat(agent): add memory_observe_node (deterministic)"
```

---

### Task 4: Wire Nodes into LangGraph + Demo Eval Cases

**Files:**
- Modify: `src/memoryos_lite/agent_graph.py`
- Create: `tests/test_agent_demo.py`

- [ ] **Step 1: Write demo eval test**

```python
# tests/test_agent_demo.py
"""Demo eval: end-to-end memory lifecycle through structured agent."""
from langchain_core.messages import HumanMessage

from memoryos_lite.agent_graph import MemoryDecision, memory_action_node_fn, memory_think_node_fn, memory_observe_node_fn
from memoryos_lite.config import Settings
from memoryos_lite.engine import MemoryOSService
from memoryos_lite.schemas import MessageCreate, Role
from memoryos_lite.store import create_store


def test_demo_memorize_then_recall(tmp_path):
    """User states fact → memorize → later recall → correct answer."""
    settings = Settings(data_dir=str(tmp_path))
    store = create_store(settings)
    service = MemoryOSService(store=store, settings=settings)
    session = service.create_session("demo")

    # Step 1: Memorize
    think_state = memory_think_node_fn(
        {"messages": [HumanMessage(content="I live in Shanghai")], "session_id": session.id},
        fake_decision=MemoryDecision(
            action="memorize", reason_code="durable_fact",
            query="", content="User lives in Shanghai", confidence=0.95,
        ),
    )
    action_state = memory_action_node_fn({**think_state, "session_id": session.id}, service=service)
    assert action_state["memory_observation"]["success"]

    # Step 2: Recall
    think_state2 = memory_think_node_fn(
        {"messages": [HumanMessage(content="Where do I live?")], "session_id": session.id},
        fake_decision=MemoryDecision(
            action="recall", reason_code="memory_question",
            query="Where does user live?", content="", confidence=0.9,
        ),
    )
    action_state2 = memory_action_node_fn({**think_state2, "session_id": session.id}, service=service)
    assert action_state2["memory_observation"]["success"]
    assert len(action_state2["memory_observation"]["recalled_item_ids"]) >= 1


def test_demo_patch_corrects_fact(tmp_path):
    """User corrects fact → patch → recall returns updated value."""
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
            query="User lives", content="User lives in Beijing", confidence=0.9,
        )},
        service=service,
    )
    assert action_state["memory_observation"]["success"]
    assert action_state["memory_observation"]["patched_item_id"] is not None

    # Verify patched content
    items = store.list_items(session.id)
    assert any("Beijing" in item.content for item in items)


def test_demo_none_skips_tools(tmp_path):
    """Irrelevant input → none → no memory action."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_demo.py -v`
Expected: FAIL (depends on Task 1-3 implementations)

- [ ] **Step 3: Verify all tests pass after Tasks 1-3**

Run: `uv run pytest tests/test_agent_demo.py tests/test_agent.py -v`
Expected: PASS (all demo + unit tests)

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -q -p no:cacheprovider`
Expected: All pass (270+)

- [ ] **Step 5: Commit**

```bash
git add tests/test_agent_demo.py
git commit -m "test(agent): add demo eval cases for memory lifecycle"
```
