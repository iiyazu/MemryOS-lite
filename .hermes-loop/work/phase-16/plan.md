# phase: phase-16

# Kernel Maintenance Tool Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or an equivalent fresh execute-lane Codex task per bounded implementation task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 16's minimal K3 kernel maintenance tool surface for MemoryOS Lite v3 without enabling the kernel by default or making benchmark score targets part of the implementation contract.

**Architecture:** Add a registry for supported kernel maintenance tools, route selection through that registry, move archive writes and attaches into a named archive maintenance service, persist pending core-promotion requests through the lifecycle/store boundary, and keep the existing runner as the replay-safe approval coordinator. Public benchmark behavior stays default-off; opt-in smoke remains structural evidence only.

**Tech Stack:** Python 3.11+, Pydantic v2 models in `v3_contracts.py`, SQLAlchemy/SQLite store in `store.py`, Alembic migrations, pytest, ruff.

Context bundle: `work/phase-16/context_bundle.md`.

Active goal:
Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

God execution choice: subagent-driven execution, because the implementation can be split into independent RED/GREEN slices with review checkpoints. The execute lane must write `execute_goal.md` before touching code.

## File Structure

- Create `src/memoryos_lite/agent_tool_registry.py`: registry metadata and helper functions for Phase 16 kernel maintenance tools.
- Create `src/memoryos_lite/agent_kernel_tools.py`: named archive and promotion maintenance services used by `SimpleToolExecutionManager`.
- Modify `src/memoryos_lite/agent_tool_selection.py`: generate candidates from the registry, with tool-specific argument validation.
- Modify `src/memoryos_lite/agent_kernel.py`: dispatch execution through services, generalize verification and tool result messages, preserve replay checks.
- Modify `src/memoryos_lite/engine.py`: add require-approval policy rules for all opened mutating kernel tools while keeping kernel opt-in.
- Modify `src/memoryos_lite/store.py`: add durable promotion-candidate record and store methods.
- Add `alembic/versions/0008_add_promotion_candidates.py`: SQLite migration for persisted pending candidates.
- Modify `tests/test_agent_kernel.py`: registry, selection, policy, replay, execution, verification, and v3 visibility tests.
- Modify `tests/test_memory_lifecycle.py`: durable pending candidate coverage.
- Modify `tests/test_public_benchmarks.py`: default-off guard remains, opt-in structural report does not imply quality promotion.

## Task 1: RED Tests For Registry, Fail-Closed Selection, And Policy Surface

**Files:**
- Modify: `tests/test_agent_kernel.py`
- Later production: `src/memoryos_lite/agent_tool_registry.py`
- Later production: `src/memoryos_lite/agent_tool_selection.py`
- Later production: `src/memoryos_lite/engine.py`

- [ ] **Step 1: Add failing registry and candidate tests**

Add tests near the existing `ToolSelectionBoundary` tests:

```python
def test_kernel_tool_registry_exposes_only_phase16_level1_tools():
    from memoryos_lite.agent_tool_registry import (
        executable_kernel_tool_names,
        get_kernel_tool_spec,
    )

    assert executable_kernel_tool_names() == {
        "archive_write",
        "archive_attach",
        "core_promotion_request",
    }
    assert get_kernel_tool_spec("archive_attach").mutating is True
    assert get_kernel_tool_spec("core_promotion_request").verification_required is True
    assert get_kernel_tool_spec("core_memory_append") is None


def test_tool_selection_boundary_generates_archive_attach_candidate_without_broad_scope():
    boundary = ToolSelectionBoundary()
    request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_attach",
        arguments={"archive_id": "archive_existing", "scope_type": "session"},
        source_refs=[_source_ref()],
        tool_call_id="toolcall_attach",
    )

    resolution = boundary.resolve(_request(), [request])

    assert resolution.denied is False
    assert resolution.selected_request is not None
    candidate = resolution.candidates[0]
    assert candidate.tool_name == "archive_attach"
    assert candidate.arguments["scope_id"] == "ses_1"
    assert candidate.constraints["requires_session_scope"] is True
    assert candidate.constraints["requires_source_refs_or_approval"] is True


def test_tool_selection_boundary_rejects_archive_attach_non_session_scope():
    boundary = ToolSelectionBoundary()
    request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_attach",
        arguments={"archive_id": "archive_existing", "scope_type": "agent", "scope_id": "agent_1"},
        source_refs=[_source_ref()],
    )

    resolution = boundary.resolve(_request(), [request])

    assert resolution.selected_request is None
    assert resolution.denied is True
    assert "session scope" in resolution.selection_payload["reason"]


def test_tool_selection_boundary_generates_core_promotion_request_candidate():
    boundary = ToolSelectionBoundary()
    request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="core_promotion_request",
        arguments={
            "content": "Alice prefers concise status updates.",
            "reason": "source-backed preference candidate",
            "label": "human",
        },
        source_refs=[_source_ref()],
        tool_call_id="toolcall_promote",
    )

    resolution = boundary.resolve(_request(), [request])

    assert resolution.denied is False
    assert resolution.selected_request is not None
    assert resolution.selected_request.tool_name == "core_promotion_request"
    assert resolution.candidates[0].constraints["applies_core_memory"] is False
```

- [ ] **Step 2: Add fail-closed tests for unopened tools**

Extend the existing unsupported memory tool test:

```python
@pytest.mark.parametrize(
    "tool_name",
    [
        "core_memory_append",
        "core_memory_replace",
        "archive_detach",
        "archive_delete",
        "archive_deprecate",
        "recall_search",
        "archive_search",
        "unknown_tool",
    ],
)
def test_kernel_denies_unopened_phase16_tools_before_policy_or_execution(tmp_path, tool_name):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(
        store=store,
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )

    result = runner.run_step(
        _request(),
        tool_requests=[
            ToolExecutionRequest(
                session_id="ses_1",
                tool_name=tool_name,
                arguments={"content": "must not be written"},
                source_refs=[_source_ref()],
            )
        ],
    )

    event_types = [event.event_type for event in result.trace]
    assert "tool_selection_denied" in event_types
    assert "tool_policy_decision" not in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    assert _archival_memory_count(store) == 0
    assert store.list_messages("ses_1") == []
```

- [ ] **Step 3: Run RED command**

Run:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_tool_registry_exposes_only_phase16_level1_tools tests/test_agent_kernel.py::test_tool_selection_boundary_generates_archive_attach_candidate_without_broad_scope tests/test_agent_kernel.py::test_tool_selection_boundary_rejects_archive_attach_non_session_scope tests/test_agent_kernel.py::test_tool_selection_boundary_generates_core_promotion_request_candidate tests/test_agent_kernel.py::test_kernel_denies_unopened_phase16_tools_before_policy_or_execution -q
```

Expected: FAIL because the registry and new candidates do not exist yet.

## Task 2: GREEN Registry And Selection Boundary

**Files:**
- Create: `src/memoryos_lite/agent_tool_registry.py`
- Modify: `src/memoryos_lite/agent_tool_selection.py`
- Modify: `tests/test_agent_kernel.py`

- [ ] **Step 1: Implement registry**

Create `src/memoryos_lite/agent_tool_registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KernelToolSpec:
    name: str
    level: int
    mutating: bool
    requires_policy_check: bool
    requires_source_refs_or_approval: bool
    requires_approval_by_default: bool
    verification_required: bool
    description: str


_PHASE16_KERNEL_TOOLS: dict[str, KernelToolSpec] = {
    "archive_write": KernelToolSpec(
        name="archive_write",
        level=1,
        mutating=True,
        requires_policy_check=True,
        requires_source_refs_or_approval=True,
        requires_approval_by_default=True,
        verification_required=True,
        description="Write source-backed archival memory and attach it to the current session.",
    ),
    "archive_attach": KernelToolSpec(
        name="archive_attach",
        level=1,
        mutating=True,
        requires_policy_check=True,
        requires_source_refs_or_approval=True,
        requires_approval_by_default=True,
        verification_required=True,
        description="Attach an existing archive to the current session scope.",
    ),
    "core_promotion_request": KernelToolSpec(
        name="core_promotion_request",
        level=1,
        mutating=True,
        requires_policy_check=True,
        requires_source_refs_or_approval=True,
        requires_approval_by_default=True,
        verification_required=True,
        description="Create a pending core promotion candidate without applying it.",
    ),
}


def get_kernel_tool_spec(tool_name: str) -> KernelToolSpec | None:
    return _PHASE16_KERNEL_TOOLS.get(tool_name)


def executable_kernel_tool_names() -> set[str]:
    return set(_PHASE16_KERNEL_TOOLS)


__all__ = [
    "KernelToolSpec",
    "executable_kernel_tool_names",
    "get_kernel_tool_spec",
]
```

- [ ] **Step 2: Update selection boundary**

In `src/memoryos_lite/agent_tool_selection.py`, import the registry, keep `ALLOWED_K2_TOOLS` as a compatibility alias, and route validation by tool name:

```python
from memoryos_lite.agent_tool_registry import executable_kernel_tool_names, get_kernel_tool_spec

ALLOWED_K2_TOOLS = executable_kernel_tool_names()
```

Replace the hard-coded `archive_write` branch in `generate_candidates()` with helper methods:

```python
spec = get_kernel_tool_spec(request.tool_name)
if spec is None:
    rejected_inputs.append({"tool_name": request.tool_name, "reason": "unsupported tool for kernel maintenance selection"})
    continue
try:
    candidate = self._candidate_for_request(request, spec)
except ValueError as exc:
    rejected_inputs.append({"tool_name": request.tool_name, "reason": str(exc)})
    continue
candidates.append(candidate)
```

Add tool-specific candidate builders:

```python
@staticmethod
def _candidate_for_request(request: ToolExecutionRequest, spec) -> ToolCandidate:
    arguments = dict(request.arguments)
    if request.tool_name == "archive_write":
        content = str(arguments.get("content") or "").strip()
        if not content:
            raise ValueError("archive_write candidate requires non-empty content")
        arguments["content"] = content
        constraints = {
            "allowed_tool": "archive_write",
            "requires_source_refs_or_approval": True,
            "requires_non_empty_content": True,
            "requires_policy_check": True,
        }
    elif request.tool_name == "archive_attach":
        archive_id = str(arguments.get("archive_id") or "").strip()
        if not archive_id:
            raise ValueError("archive_attach candidate requires archive_id")
        scope_type = str(arguments.get("scope_type") or "session")
        scope_id = str(arguments.get("scope_id") or request.session_id)
        if scope_type != "session" or scope_id != request.session_id:
            raise ValueError("archive_attach candidate requires current session scope")
        arguments.update({"archive_id": archive_id, "scope_type": "session", "scope_id": request.session_id})
        constraints = {
            "allowed_tool": "archive_attach",
            "requires_source_refs_or_approval": True,
            "requires_existing_archive": True,
            "requires_session_scope": True,
            "requires_policy_check": True,
        }
    elif request.tool_name == "core_promotion_request":
        content = str(arguments.get("content") or "").strip()
        if not content:
            raise ValueError("core_promotion_request candidate requires non-empty content")
        arguments["content"] = content
        arguments.setdefault("target_layer", "core")
        arguments.setdefault("operation", "promote")
        arguments.setdefault("write_source", "explicit_instruction")
        constraints = {
            "allowed_tool": "core_promotion_request",
            "requires_source_refs_or_approval": True,
            "applies_core_memory": False,
            "requires_policy_check": True,
        }
    else:
        raise ValueError(f"unsupported tool for kernel maintenance selection: {request.tool_name}")
    return ToolCandidate(
        tool_call_id=request.tool_call_id or new_id("toolcall"),
        session_id=request.session_id,
        tool_name=request.tool_name,
        arguments=arguments,
        source_refs=list(request.source_refs),
        approval_id=request.approval_id,
        candidate_reason=f"{request.tool_name} candidate requiring policy and provenance",
        constraints=constraints,
    )
```

- [ ] **Step 3: Run Task 1 focused tests**

Run the Task 1 command again.

Expected: PASS for registry/selection tests; later execution tests are not part of this task.

## Task 3: RED Tests For Archive Maintenance Service And V3 Visibility

**Files:**
- Modify: `tests/test_agent_kernel.py`
- Later production: `src/memoryos_lite/agent_kernel_tools.py`
- Later production: `src/memoryos_lite/agent_kernel.py`

- [ ] **Step 1: Add an archive fixture helper**

Add to `tests/test_agent_kernel.py`:

```python
from memoryos_lite.v3_contracts import ArchivalMemory
from memoryos_lite.schemas import new_id


def _seed_archival_memory(store, *, archive_id: str, content: str, session_id: str = "ses_1") -> str:
    memory = store.add_archival_memory(
        ArchivalMemory(
            id=new_id("amem"),
            archive_id=archive_id,
            memory_type="fact",
            content=content,
            source_refs=[_source_ref(session_id)],
            metadata={"test": "phase16_archive_attach"},
        ),
        actor="agent",
        reason="test seed archival memory",
    )
    return memory.id
```

- [ ] **Step 2: Add archive_attach approval, verification, and v3 visibility test**

```python
def test_kernel_archive_attach_is_approval_bound_verified_and_visible_to_v3(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    archive_id = "archive_phase16"
    memory_id = _seed_archival_memory(
        store,
        archive_id=archive_id,
        content="Alice wants the blue notebook remembered.",
    )
    before = V3ContextComposer(store=store, settings=settings).build(
        ContextComposerRequest(session_id="ses_1", task="blue notebook", budget=120)
    )
    assert [item for item in before.items if item.layer == "archival"] == []

    runner = SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="archive_attach_requires_approval",
                    tool_name="archive_attach",
                    effect="require_approval",
                    reason="archive attachments require approval",
                )
            ]
        ),
        approval_gate=ApprovalGateV1(),
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )
    tool_request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_attach",
        arguments={"archive_id": archive_id, "scope_type": "session"},
        source_refs=[_source_ref()],
    )

    first = runner.run_step(_request(), tool_requests=[tool_request])
    approval_id = next(event.approval_id for event in first.trace if event.event_type == "approval_pending")
    tool_call_id = _pending_tool_call_id(first.trace)
    resumed = runner.run_step(
        _request(),
        tool_requests=[
            tool_request.model_copy(update={"approval_id": approval_id, "tool_call_id": tool_call_id})
        ],
    )

    event_types = [event.event_type for event in resumed.trace]
    assert "tool_executed" in event_types
    assert "tool_verified" in event_types
    verified = next(event for event in resumed.trace if event.event_type == "tool_verified")
    assert verified.payload["tool_name"] == "archive_attach"
    assert verified.payload["ok"] is True
    assert verified.payload["verification"]["status"] == "verified"
    assert verified.payload["verification"]["attachment_found"] is True
    assert f"apsg_{memory_id}" in verified.payload["verification"]["eligible_passage_ids"]
    attachments = store.list_archive_attachments(scope_type="session", scope_id="ses_1")
    assert [attachment.archive_id for attachment in attachments] == [archive_id]

    after = V3ContextComposer(store=store, settings=settings).build(
        ContextComposerRequest(session_id="ses_1", task="blue notebook", budget=120)
    )
    archival_items = [item for item in after.items if item.layer == "archival"]
    assert [item.text for item in archival_items] == ["Alice wants the blue notebook remembered."]
```

- [ ] **Step 3: Add replay tamper denial test for archive_attach**

```python
def test_kernel_archive_attach_replay_tamper_denies_before_execution(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    _seed_archival_memory(store, archive_id="archive_phase16", content="attach me")
    runner = _approval_runner(store)
    runner.tool_policy_engine = SimpleToolPolicyEngine(
        rules=[
            ToolPolicyRule(
                id="archive_attach_requires_approval",
                tool_name="archive_attach",
                effect="require_approval",
                reason="archive attachments require approval",
            )
        ]
    )
    tool_request = ToolExecutionRequest(
        session_id="ses_1",
        tool_name="archive_attach",
        arguments={"archive_id": "archive_phase16", "scope_type": "session"},
        source_refs=[_source_ref()],
    )
    first = runner.run_step(_request(), tool_requests=[tool_request])
    approval_id = next(event.approval_id for event in first.trace if event.event_type == "approval_pending")
    tool_call_id = _pending_tool_call_id(first.trace)

    tampered = tool_request.model_copy(
        update={
            "approval_id": approval_id,
            "tool_call_id": tool_call_id,
            "arguments": {"archive_id": "archive_other", "scope_type": "session"},
        }
    )
    result = runner.run_step(_request(), tool_requests=[tampered])

    event_types = [event.event_type for event in result.trace]
    assert "approval_replay_denied" in event_types
    assert "tool_executed" not in event_types
    assert "tool_verified" not in event_types
    assert store.list_archive_attachments(scope_type="session", scope_id="ses_1") == []
```

- [ ] **Step 4: Run RED command**

Run:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_attach_is_approval_bound_verified_and_visible_to_v3 tests/test_agent_kernel.py::test_kernel_archive_attach_replay_tamper_denies_before_execution -q
```

Expected: FAIL because `archive_attach` execution is unsupported.

## Task 4: GREEN Archive Maintenance Service

**Files:**
- Create: `src/memoryos_lite/agent_kernel_tools.py`
- Modify: `src/memoryos_lite/agent_kernel.py`

- [ ] **Step 1: Add source provenance helper and archive service**

Create `src/memoryos_lite/agent_kernel_tools.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from memoryos_lite.schemas import new_id, utc_now
from memoryos_lite.store import MemoryStore
from memoryos_lite.v3_contracts import (
    ArchivalMemory,
    ArchiveAttachment,
    ArchiveEligibilityScope,
    SourceRef,
    SourceType,
    ToolExecutionRequest,
    ToolExecutionResult,
)


def source_refs_for_tool_request(request: ToolExecutionRequest) -> list[SourceRef]:
    refs = list(request.source_refs)
    if refs and request.approval_id:
        return [ref.model_copy(update={"approval_id": request.approval_id}) for ref in refs]
    if refs:
        return refs
    if request.approval_id:
        return [
            SourceRef(
                source_type=SourceType.MANUAL,
                source_id=request.approval_id,
                approval_id=request.approval_id,
            )
        ]
    return []


@dataclass
class ArchiveMaintenanceService:
    store: MemoryStore

    def write(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        content = str(request.arguments.get("content") or "").strip()
        if not content:
            return ToolExecutionResult(tool_name=request.tool_name, ok=False, error="archive_write requires content")
        source_refs = source_refs_for_tool_request(request)
        if not source_refs:
            return ToolExecutionResult(tool_name=request.tool_name, ok=False, error="archive_write requires source_refs or approval_id")
        memory = self.store.add_archival_memory(
            ArchivalMemory(
                id=new_id("amem"),
                archive_id=str(request.arguments.get("archive_id") or request.session_id),
                memory_type=str(request.arguments.get("memory_type") or "fact"),
                content=content,
                source_refs=source_refs,
                metadata={"producer": "agent_kernel", "tool_name": request.tool_name},
            ),
            actor="agent",
            reason=str(request.arguments.get("reason") or "agent kernel archive_write"),
        )
        self._ensure_session(request.session_id)
        self._create_attachment_if_missing(
            archive_id=memory.archive_id or request.session_id,
            scope_id=request.session_id,
            source_refs=source_refs,
            metadata={"producer": "agent_kernel", "tool_name": request.tool_name, "memory_id": memory.id},
        )
        verification = self.verify_archive_write(request, memory_id=memory.id, archive_id=memory.archive_id)
        return ToolExecutionResult(
            tool_name=request.tool_name,
            ok=True,
            result={"memory_id": memory.id, "archive_id": memory.archive_id},
            source_refs=source_refs,
            verification=verification,
        )

    def attach(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        archive_id = str(request.arguments.get("archive_id") or "").strip()
        if not archive_id:
            return ToolExecutionResult(tool_name=request.tool_name, ok=False, error="archive_attach requires archive_id")
        scope_type = str(request.arguments.get("scope_type") or "session")
        scope_id = str(request.arguments.get("scope_id") or request.session_id)
        if scope_type != "session" or scope_id != request.session_id:
            return ToolExecutionResult(tool_name=request.tool_name, ok=False, error="archive_attach requires current session scope")
        source_refs = source_refs_for_tool_request(request)
        if not source_refs:
            return ToolExecutionResult(tool_name=request.tool_name, ok=False, error="archive_attach requires source_refs or approval_id")
        if not self.store.list_archival_passages(archive_id=archive_id):
            return ToolExecutionResult(tool_name=request.tool_name, ok=False, error="archive_attach requires existing archive passages")
        self._ensure_session(request.session_id)
        attachment = self._create_attachment_if_missing(
            archive_id=archive_id,
            scope_id=request.session_id,
            source_refs=source_refs,
            metadata={"producer": "agent_kernel", "tool_name": request.tool_name},
        )
        verification = self.verify_archive_attach(request, archive_id=archive_id)
        return ToolExecutionResult(
            tool_name=request.tool_name,
            ok=verification["status"] == "verified",
            result={"archive_id": archive_id, "attachment_id": attachment.id},
            source_refs=source_refs,
            verification=verification,
        )
```

Continue the service with `_ensure_session()`, `_create_attachment_if_missing()`, `verify_archive_write()`, and `verify_archive_attach()` by moving the current inline archive-write verification logic out of `SimpleToolExecutionManager`. `verify_archive_attach()` must return `attachment_found`, `eligible_archive_found`, `eligible_passage_ids`, and `status`.

- [ ] **Step 2: Route SimpleToolExecutionManager through service**

Update `SimpleToolExecutionManager`:

```python
@dataclass
class SimpleToolExecutionManager:
    store: MemoryStore
    archive_service: ArchiveMaintenanceService | None = None

    def __post_init__(self) -> None:
        if self.archive_service is None:
            self.archive_service = ArchiveMaintenanceService(self.store)

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        if request.tool_name == "archive_write":
            return self.archive_service.write(request)
        if request.tool_name == "archive_attach":
            return self.archive_service.attach(request)
        return ToolExecutionResult(tool_name=request.tool_name, ok=False, error=f"unsupported tool: {request.tool_name}")

    def verify(self, request: ToolExecutionRequest, **kwargs: Any) -> dict[str, Any]:
        if request.tool_name == "archive_write":
            return self.archive_service.verify_archive_write(request, **kwargs)
        if request.tool_name == "archive_attach":
            return self.archive_service.verify_archive_attach(request, archive_id=kwargs.get("archive_id"))
        return {}
```

- [ ] **Step 3: Generalize runner verification fallback**

Replace the `tool_name == "archive_write"` special case with:

```python
if not verification and hasattr(self.tool_execution_manager, "verify"):
    verification = self.tool_execution_manager.verify(
        tool_request,
        memory_id=tool_result.result.get("memory_id"),
        archive_id=tool_result.result.get("archive_id"),
        candidate_id=tool_result.result.get("candidate_id"),
    )
```

- [ ] **Step 4: Generalize tool result message**

Update `_tool_result_message()` content to:

```python
result_id = result.result.get("memory_id") or result.result.get("attachment_id") or result.result.get("candidate_id")
content = f"tool {request.tool_name} executed"
if result_id:
    content = f"{content}: result_id={result_id}"
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_attach_is_approval_bound_verified_and_visible_to_v3 tests/test_agent_kernel.py::test_kernel_archive_attach_replay_tamper_denies_before_execution tests/test_agent_kernel.py::test_kernel_replays_persisted_approval_after_cold_boundary_once tests/test_agent_kernel.py::test_kernel_archive_write_becomes_same_session_archival_context_item -q
```

Expected: PASS.

## Task 5: RED Tests For Durable Core Promotion Request

**Files:**
- Modify: `tests/test_memory_lifecycle.py`
- Modify: `tests/test_agent_kernel.py`
- Later production: `src/memoryos_lite/store.py`
- Later production: `src/memoryos_lite/memory_lifecycle.py`
- Later production: `src/memoryos_lite/agent_kernel_tools.py`
- Later production: `alembic/versions/0008_add_promotion_candidates.py`

- [ ] **Step 1: Add lifecycle persistence test**

In `tests/test_memory_lifecycle.py`:

```python
def test_lifecycle_create_candidate_persists_pending_candidate(tmp_path):
    store = create_store(Settings(data_dir=tmp_path / ".memoryos"))
    store.reset()
    service = MemoryLifecycleService(store)

    candidate = service.create_candidate(
        source_layer="archival",
        target_layer="core",
        operation="promote",
        content="Alice prefers concise status updates.",
        source_refs=[_source_ref()],
        identity_scope=None,
        reason="source-backed candidate",
        confidence=0.8,
        write_source="explicit_instruction",
        metadata={"label": "human", "limit_tokens": 200},
    )

    persisted = store.get_promotion_candidate(candidate.id)
    assert persisted is not None
    assert persisted.id == candidate.id
    assert persisted.status == "pending"
    assert persisted.metadata["label"] == "human"
```

- [ ] **Step 2: Add kernel core_promotion_request test**

In `tests/test_agent_kernel.py`:

```python
def _core_memory_history_count(store) -> int:
    with store.db() as db:
        return int(db.scalar(text("select count(*) from core_memory_history")))


def test_kernel_core_promotion_request_persists_pending_candidate_without_core_mutation(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    runner = SimpleAgentStepRunner(
        store=store,
        tool_policy_engine=SimpleToolPolicyEngine(
            rules=[
                ToolPolicyRule(
                    id="allow_core_promotion_request",
                    tool_name="core_promotion_request",
                    effect="allow",
                    reason="allowed for pending request test",
                )
            ]
        ),
        tool_execution_manager=SimpleToolExecutionManager(store=store),
    )

    result = runner.run_step(
        _request(),
        tool_requests=[
            ToolExecutionRequest(
                session_id="ses_1",
                tool_name="core_promotion_request",
                arguments={
                    "content": "Alice prefers concise status updates.",
                    "reason": "source-backed preference candidate",
                    "label": "human",
                },
                source_refs=[_source_ref()],
            )
        ],
    )

    event_types = [event.event_type for event in result.trace]
    assert "tool_executed" in event_types
    assert "tool_verified" in event_types
    executed = next(event for event in result.trace if event.event_type == "tool_executed")
    candidate_id = executed.payload["result"]["candidate_id"]
    persisted = store.get_promotion_candidate(candidate_id)
    assert persisted is not None
    assert persisted.status == "pending"
    assert store.list_core_memory_blocks() == []
    assert _core_memory_history_count(store) == 0
    package = V3ContextComposer(store=store, settings=settings).build(
        ContextComposerRequest(session_id="ses_1", task="concise status", budget=120)
    )
    assert [item for item in package.items if item.layer == "core"] == []
```

- [ ] **Step 3: Run RED command**

Run:

```bash
uv run pytest tests/test_memory_lifecycle.py::test_lifecycle_create_candidate_persists_pending_candidate tests/test_agent_kernel.py::test_kernel_core_promotion_request_persists_pending_candidate_without_core_mutation -q
```

Expected: FAIL because promotion candidates are not persisted and the tool is unsupported.

## Task 6: GREEN Durable Promotion Candidate Store And Tool Execution

**Files:**
- Modify: `src/memoryos_lite/store.py`
- Modify: `src/memoryos_lite/memory_lifecycle.py`
- Modify: `src/memoryos_lite/agent_kernel_tools.py`
- Modify: `src/memoryos_lite/agent_kernel.py`
- Add: `alembic/versions/0008_add_promotion_candidates.py`

- [ ] **Step 1: Add SQLAlchemy record and conversion helpers**

In `store.py`, add `PromotionCandidateRecord` with JSON columns for `source_refs`, `identity_scope`, and `metadata`, plus conversion helpers using existing `_dump_source_refs`, `_load_source_refs`, `_dump_json`, and `_load_json` patterns.

- [ ] **Step 2: Add store methods**

Implement:

```python
def create_promotion_candidate(self, candidate: PromotionCandidate) -> PromotionCandidate: ...
def get_promotion_candidate(self, candidate_id: str) -> PromotionCandidate | None: ...
def list_promotion_candidates(self, status: str | None = None) -> list[PromotionCandidate]: ...
```

`create_promotion_candidate()` must preserve `status="pending"` and raise on duplicate ids through the database constraint.

- [ ] **Step 3: Add Alembic migration**

Add `alembic/versions/0008_add_promotion_candidates.py` with `down_revision = "0007_add_core_block_read_only_tags"` and a `promotion_candidates` table matching the SQLAlchemy record.

- [ ] **Step 4: Persist candidates in lifecycle service**

In `MemoryLifecycleService.create_candidate()`, after constructing the candidate, call `self.store.create_promotion_candidate(candidate)` and return the persisted object. Keep `recall_to_archival_candidate()` and `archival_to_core_candidate()` as pure factory helpers.

- [ ] **Step 5: Add promotion service execution**

Extend `agent_kernel_tools.py`:

```python
@dataclass
class PromotionMaintenanceService:
    store: MemoryStore
    lifecycle: MemoryLifecycleService | None = None

    def __post_init__(self) -> None:
        if self.lifecycle is None:
            self.lifecycle = MemoryLifecycleService(self.store)

    def request_core_promotion(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        source_refs = source_refs_for_tool_request(request)
        if not source_refs:
            return ToolExecutionResult(tool_name=request.tool_name, ok=False, error="core_promotion_request requires source_refs or approval_id")
        content = str(request.arguments.get("content") or "").strip()
        if not content:
            return ToolExecutionResult(tool_name=request.tool_name, ok=False, error="core_promotion_request requires content")
        before_blocks = len(self.store.list_core_memory_blocks())
        candidate = self.lifecycle.create_candidate(
            source_layer=str(request.arguments.get("source_layer") or "archival"),
            target_layer="core",
            operation="promote",
            content=content,
            source_refs=source_refs,
            identity_scope=None,
            reason=str(request.arguments.get("reason") or "agent kernel core promotion request"),
            confidence=float(request.arguments.get("confidence") or 0.5),
            write_source=str(request.arguments.get("write_source") or "explicit_instruction"),
            metadata={
                "label": str(request.arguments.get("label") or "promotion"),
                "limit_tokens": int(request.arguments.get("limit_tokens") or 200),
                "producer": "agent_kernel",
                "tool_name": request.tool_name,
            },
        )
        verification = self.verify_core_promotion_request(
            request,
            candidate_id=candidate.id,
            before_blocks=before_blocks,
        )
        return ToolExecutionResult(
            tool_name=request.tool_name,
            ok=verification["status"] == "verified",
            result={"candidate_id": candidate.id},
            source_refs=source_refs,
            verification=verification,
        )
```

`verify_core_promotion_request()` must check persisted candidate existence, pending status, and unchanged core block/history counts.

- [ ] **Step 6: Route new service in execution manager**

Add `promotion_service` to `SimpleToolExecutionManager` and route `core_promotion_request` to it. Extend `verify()` for `core_promotion_request`.

- [ ] **Step 7: Run focused tests**

Run:

```bash
uv run pytest tests/test_memory_lifecycle.py::test_lifecycle_create_candidate_persists_pending_candidate tests/test_agent_kernel.py::test_kernel_core_promotion_request_persists_pending_candidate_without_core_mutation -q
```

Expected: PASS.

## Task 7: Policy Integration, Public Benchmark Guards, And Regression Tests

**Files:**
- Modify: `src/memoryos_lite/engine.py`
- Modify: `tests/test_agent_kernel.py`
- Modify: `tests/test_public_benchmarks.py`

- [ ] **Step 1: Add policy rules for opened mutating tools**

In `MemoryOSService.__init__`, add require-approval rules for `archive_attach` and `core_promotion_request` next to the existing `archive_write` rule:

```python
ToolPolicyRule(
    id="kernel_archive_attach_requires_approval",
    tool_name="archive_attach",
    effect="require_approval",
    reason="archive attachments require explicit approval",
),
ToolPolicyRule(
    id="kernel_core_promotion_request_requires_approval",
    tool_name="core_promotion_request",
    effect="require_approval",
    reason="core promotion requests require explicit approval",
),
```

Keep the surrounding `if self.settings.resolved_agent_kernel == "v1"` unchanged.

- [ ] **Step 2: Add public default-off and opt-in trace guard assertions**

Keep `test_public_benchmark_kernel_trace_remains_default_off` unchanged except for stronger assertions:

```python
assert settings.resolved_agent_kernel != "v1"
assert report["kernel_trace_events"] == []
```

In `test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled`, assert the opt-in probe still uses only `archive_write`:

```python
executed_tool_names = {
    event["payload"]["tool_name"]
    for event in kernel_trace_events
    if event["event_type"] in {"tool_selected", "tool_policy_decision", "approval_pending", "approval_granted", "tool_executed", "tool_verified"}
    and "tool_name" in event["payload"]
}
assert executed_tool_names == {"archive_write"}
```

- [ ] **Step 3: Run focused public tests**

Run:

```bash
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

Expected: PASS.

## Task 8: Refactor, Full Verification, And Structural Smoke

**Files:**
- Modify: `.hermes-loop/work/phase-16/result.md`
- Modify: `.hermes-loop/work/phase-16/execute_review.md`

- [ ] **Step 1: Run focused kernel suites**

Run:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_memory_lifecycle.py tests/test_core_memory_service.py tests/test_archival_store.py tests/test_context_composer.py -q
uv run pytest tests/test_public_benchmarks.py -q
```

Expected: PASS.

- [ ] **Step 2: Run baseline checks**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 3: Run default-off public guard**

Run:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase16_locomo5_kernel_default_off_guard
```

Expected: `kernel_trace_events == []` for every row. This is a guard, not promotion evidence.

- [ ] **Step 4: Run opt-in structural smoke**

Run:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase16_locomo5_kernel_tools_structural
```

Expected: structural trace events only under opt-in kernel. Record case-level rows in `result.md`; do not claim benchmark-quality improvement.

- [ ] **Step 5: Write execution artifacts**

Write `.hermes-loop/work/phase-16/result.md` and `.hermes-loop/work/phase-16/execute_review.md` with first line `# phase: phase-16`. Both files must cite `work/phase-16/context_bundle.md`, the active goal, changed real chain components, focused tests, full checks, structural smoke case-level findings, v1 fallback, v3 default, and kernel opt-in status.

## Anti-Demo Gate

Do not ACK Phase 16 if any of these are true:

- tool names exist only in a registry without policy, execution, verification, and tests;
- `archive_attach` reports success without a real `ArchiveAttachment` row and v3 eligibility evidence;
- `core_promotion_request` creates only an in-memory object or applies core memory;
- replay tampering reaches `tool_executed`;
- public benchmark reports kernel events when `MEMORYOS_AGENT_KERNEL` is not set to `v1`;
- result language claims LongMemEval or LoCoMo quality improvement from structural smoke.

## Review Routing

The review lane must inspect:

- `work/phase-16/context_bundle.md`;
- `work/phase-16/god_dispatch.json`;
- `work/phase-16/brainstorm.md`;
- `work/phase-16/spec.md`;
- `work/phase-16/plan.md`;
- `work/phase-16/result.md`;
- `work/phase-16/execute_review.md`;
- `git diff`.

Review eval decision should be `smoke` for Phase 16 unless the implementation changes default retrieval, context composition, answer projection, or scoring. Promotion gate is `not_applicable` for benchmark-quality milestone evidence because this phase is structural.
