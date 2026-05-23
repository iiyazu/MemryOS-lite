# phase: phase-12

# Phase 12 Plan: Scoped Tool-Written Archival Memory

Context bundle: `.hermes-loop/work/phase-12/context_bundle.md`.
Brainstorm: `.hermes-loop/work/phase-12/brainstorm.md`.
Dispatch: `.hermes-loop/work/phase-12/god_dispatch.json`.
Spec: `.hermes-loop/work/phase-12/spec.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

This is a PLAN_DRAFT artifact only. Do not edit source code, tests, `.hermes-loop/state.json`, `.hermes-loop/blueprint.md`, or docs outside phase-12 work artifacts in this draft step.

## Execution Rules

- Read `work/phase-12/context_bundle.md` before this plan.
- Require a RED test failure before production changes.
- Use TDD: RED -> GREEN -> REFACTOR -> focused tests -> baseline checks -> review.
- Preserve v3 as default, v1 as explicit fallback, and `MEMORYOS_AGENT_KERNEL=v1` as opt-in.
- Do not add Letta as a dependency.
- Do not claim LongMemEval or LoCoMo improvement from structural archive tests.
- Keep Phase 11 LoCoMo debt visible in `result.md`, `execute_review.md`, `review_verdict.json`, and any ACK.

## File Map

Expected modifications:

- `tests/test_agent_kernel.py`: add the RED test proving approved `archive_write` becomes same-session archival context evidence and legacy retrieved evidence.
- `src/memoryos_lite/agent_kernel.py`: after a successful `archive_write`, create an idempotent session archive attachment using existing store APIs.

Expected verification only:

- `tests/test_archival_store.py`: existing sourceless write, history, attachment, and passage invariant tests must stay green.
- `tests/test_memory_lifecycle.py`: existing update/delete bridged passage sync tests must stay green.
- `tests/test_context_composer.py`: existing attached-scope, no-leakage, archival eligibility, budget-drop, and component accounting tests must stay green.

Avoid changes unless a RED test proves they are necessary:

- `src/memoryos_lite/store.py`
- `src/memoryos_lite/context_composer.py`
- `src/memoryos_lite/engine.py`
- `src/memoryos_lite/public_benchmarks.py`
- `src/memoryos_lite/public_case_diagnostics.py`

## Task 1: RED Test For Tool Write To Archival Context

**Files:**

- Modify: `tests/test_agent_kernel.py`
- Record output: `.hermes-loop/work/phase-12/red_result.md`

- [ ] **Step 1: Add the failing test**

Append this test after `test_kernel_tool_result_message_is_visible_to_later_v3_context`:

```python
def test_kernel_archive_write_becomes_same_session_archival_context_item(tmp_path):
    settings = Settings(data_dir=tmp_path / ".memoryos")
    store = create_store(settings)
    store.reset()
    store.create_session("phase 12 archival test")
    first = _approval_runner(store).run_step(_request(), tool_requests=[_archive_request()])
    approval_id = next(
        event.approval_id for event in first.trace if event.event_type == "approval_pending"
    )
    assert approval_id is not None

    reopened = create_store(settings)
    resumed = _approval_runner(reopened).run_step(
        _request(),
        tool_requests=[_archive_request(approval_id=approval_id)],
    )
    memory_id = next(
        event.payload["result"]["memory_id"]
        for event in resumed.trace
        if event.event_type == "tool_executed"
    )

    v3_package = V3ContextComposer(store=reopened, settings=settings).build(
        ContextComposerRequest(
            session_id="ses_1",
            task="approved archival fact",
            budget=120,
        )
    )
    archival_items = [item for item in v3_package.items if item.layer == "archival"]

    assert [item.text for item in archival_items] == ["approved archival fact"]
    assert archival_items[0].source_refs[0].source_id == "msg_1"
    assert archival_items[0].metadata["archival_memory_id"] == memory_id
    assert archival_items[0].metadata["archive_id"] == "ses_1"
    assert v3_package.metadata["archival_eligibility"]["selected_passage_ids"] == [
        f"apsg_{memory_id}"
    ]
    assert v3_package.metadata["archival_eligibility"]["selected_source_refs"] == [
        {"source_type": "message", "source_id": "msg_1", "session_id": "ses_1"}
    ]

    service = MemoryOSService(settings=settings, store=reopened)
    legacy_package = service.build_context(
        session_id="ses_1",
        task="approved archival fact",
        budget=120,
    )
    archival_evidence = [
        evidence
        for evidence in legacy_package.retrieved_evidence
        if evidence.metadata.get("origin") == "archival"
    ]
    assert [evidence.text for evidence in archival_evidence] == ["approved archival fact"]
    assert archival_evidence[0].message_id == "msg_1"
    assert archival_evidence[0].metadata["v3_item_id"] == f"apsg_{memory_id}"
```

Also add this import at the top of `tests/test_agent_kernel.py`:

```python
from memoryos_lite.engine import MemoryOSService
```

- [ ] **Step 2: Run the RED test**

Run:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_write_becomes_same_session_archival_context_item -q
```

Expected RED:

- Fail before production changes.
- Likely failure: `archival_items` is `[]` or `selected_passage_ids` is `[]` because `archive_write` persists the memory but does not attach the written archive to the same session's eligibility scope.

- [ ] **Step 3: Record RED evidence**

Write `.hermes-loop/work/phase-12/red_result.md` with:

```markdown
# phase: phase-12

# Phase 12 RED Result

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context bundle: `.hermes-loop/work/phase-12/context_bundle.md`.

Command:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_write_becomes_same_session_archival_context_item -q
```

Result: RED.

Observed failure:

- Paste the failing assertion or traceback summary.

Interpretation:

- Approved `archive_write` persists archival memory, but same-session v3 archival eligibility does not select `apsg_{memory_id}` yet.
```

## Task 2: GREEN Session-Scoped Archive Attachment

**Files:**

- Modify: `src/memoryos_lite/agent_kernel.py`
- Test: `tests/test_agent_kernel.py`

- [ ] **Step 1: Import `ArchiveAttachment`**

Update the v3 contract import block in `src/memoryos_lite/agent_kernel.py`:

```python
from memoryos_lite.v3_contracts import (
    AgentStepRequest,
    AgentStepResult,
    ApprovalState,
    ArchivalMemory,
    ArchiveAttachment,
    KernelTraceEvent,
    SourceRef,
    SourceType,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicyDecision,
    ToolPolicyRule,
    message_to_log_entry,
)
```

- [ ] **Step 2: Attach the written archive to the exact session scope**

In `SimpleToolExecutionManager._archive_write()`, compute the reason once, pass it to `add_archival_memory()`, then create a session attachment only when that archive is not already attached to the same session:

```python
        memory_type = str(request.arguments.get("memory_type") or "fact")
        reason = str(request.arguments.get("reason") or "agent kernel archive_write")
        memory = self.store.add_archival_memory(
            ArchivalMemory(
                id=new_id("amem"),
                archive_id=str(request.arguments.get("archive_id") or request.session_id),
                memory_type=memory_type,  # type: ignore[arg-type]
                content=content,
                source_refs=source_refs,
                metadata={"producer": "agent_kernel", "tool_name": request.tool_name},
            ),
            actor="agent",
            reason=reason,
        )
        attached_archive_ids = {
            attachment.archive_id
            for attachment in self.store.list_archive_attachments(
                scope_type="session",
                scope_id=request.session_id,
            )
        }
        if memory.archive_id is not None and memory.archive_id not in attached_archive_ids:
            self.store.create_archive_attachment(
                ArchiveAttachment(
                    id=new_id("aatt"),
                    archive_id=memory.archive_id,
                    scope_type="session",
                    scope_id=request.session_id,
                    source_refs=source_refs,
                    metadata={
                        "producer": "agent_kernel",
                        "tool_name": request.tool_name,
                        "memory_id": memory.id,
                        "reason": reason,
                    },
                )
            )
```

Do not alter `Settings.resolved_agent_kernel`, environment defaults, or public benchmark scoring.

- [ ] **Step 3: Re-run the RED test for GREEN**

Run:

```bash
uv run pytest tests/test_agent_kernel.py::test_kernel_archive_write_becomes_same_session_archival_context_item -q
```

Expected GREEN:

- The new test passes.
- `archival_items[0].metadata["archival_memory_id"] == memory_id`.
- `selected_passage_ids == [f"apsg_{memory_id}"]`.
- Legacy `retrieved_evidence` has one archival evidence row with `message_id == "msg_1"`.

## Task 3: Focused Regression Suite

**Files:**

- Verify: `tests/test_agent_kernel.py`
- Verify: `tests/test_archival_store.py`
- Verify: `tests/test_memory_lifecycle.py`
- Verify: `tests/test_context_composer.py`

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_agent_kernel.py tests/test_archival_store.py tests/test_memory_lifecycle.py tests/test_context_composer.py -q
```

Expected:

- All focused tests pass.
- Existing update/delete bridged passage tests still pass.
- Existing archival scope no-leakage tests still pass.

- [ ] **Step 2: Run lint**

Run:

```bash
uv run ruff check .
```

Expected: no ruff violations.

- [ ] **Step 3: Run baseline checks**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected:

- Full test suite passes.
- Ruff remains clean.

## Task 4: Phase 12 Result Artifacts

**Files:**

- Create: `.hermes-loop/work/phase-12/result.md`
- Create: `.hermes-loop/work/phase-12/execute_review.md`
- Create: `.hermes-loop/work/phase-12/case_matrix.md`

- [ ] **Step 1: Write `result.md`**

Include:

- first line `# phase: phase-12`;
- active goal;
- context bundle path;
- changed chain: `kernel_loop=changed_opt_in_only`, `store=verified`, `retrieval=verified`, `context_composer=verified`, `public_eval=not_applicable`;
- RED command and failure summary from `red_result.md`;
- focused and baseline verification commands with pass/fail output;
- statement that no LongMemEval/LoCoMo improvement is claimed.

- [ ] **Step 2: Write `execute_review.md`**

Answer:

- What real chain changed?
- What is still demo-only or partial?
- What tests proved the behavior?
- Which benchmark cases moved or regressed?
- Did v1 fallback, v3 default, and kernel opt-in remain intact?

- [ ] **Step 3: Write `case_matrix.md`**

Because this is a structural phase unless public benchmark code is touched, write:

- LongMemEval: `limit=0`, `not_applicable`, no claim;
- LoCoMo: `limit=0`, `not_applicable`, no claim;
- Phase 11 LoCoMo debt still visible: `conv-26_qa_028`, `conv-26_qa_005`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`.

## Conditional Public Smoke

If execution changes `src/memoryos_lite/engine.py`, `src/memoryos_lite/public_benchmarks.py`, or `src/memoryos_lite/public_case_diagnostics.py`, run this structural smoke before review:

```bash
MEMORYOS_MEMORY_ARCH=v3 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge
```

If those files are not changed, do not run or claim milestone full-chain eval for Phase 12.
