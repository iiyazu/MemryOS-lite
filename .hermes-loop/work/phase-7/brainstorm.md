# phase: phase-7

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context used: `work/phase-7/context_bundle.md` was read first and is the controlling bundle for this brainstorm. I also used `work/phase-7/god_dispatch.json`, the Phase 7 blueprint section, current kernel/public-eval tests, `agent_kernel.py`, `evals.py`, `store.py`, `v3_contracts.py`, and focused Letta reference semantics for approval, denials-as-tool-returns, tool execution results, memory rendering, and context accounting.

## Options

### Option A: Minimal trace hardening

Add tests and small kernel changes so denied tools emit durable denial trace detail, approvals can pause/resume, and public benchmark opt-in still reports trace events.

Trade-offs:
- Lowest implementation risk and least chance of changing benchmark answers.
- Still weak as a Letta-style memory system because tool results may not become later-context-visible messages.
- Could pass direct kernel tests while remaining demo-like in the public benchmark path.

### Option B: Durable control-plane slice

Keep the kernel opt-in, but make one real end-to-end contract durable: policy decision -> approval pending/granted or denial -> exactly-once tool execution -> tool result trace -> tool result message/log entry visible to a later v3 context build where relevant -> public benchmark kernel trace fields.

Trade-offs:
- Best fit for Phase 7 because it borrows Letta semantics without porting Letta internals.
- Requires touching kernel, store/message visibility, v3 context path, and public eval tests, so regression risk is higher than Option A.
- Gives concrete anti-demo evidence: denied, pending, resumed, executed, traced, and later visible.

### Option C: Broader Letta-style loop expansion

Introduce richer tool routing, more memory mutation tools, continuation/stop-reason modeling, and fuller message persistence around assistant/tool events.

Trade-offs:
- Most aligned with Letta long-term shape.
- Too broad for this phase and likely to blur kernel work with answer behavior or benchmark tuning.
- Higher risk of default-path or LoCoMo regressions and harder to verify without large eval cost.

## Chosen Route

Choose Option B.

Phase 7 should implement a narrow durable control-plane contract, not a new autonomous agent. The route should preserve `MEMORYOS_AGENT_KERNEL=off` as default, keep `MEMORYOS_MEMORY_ARCH=v1` behavior untouched, and only exercise kernel behavior when `MEMORYOS_AGENT_KERNEL=v1` and v3 context are explicit.

Operational shape:
- Add RED tests first for denial non-execution, approval pause/resume replayability, exactly-once resumed execution, tool result trace detail, later-context-visible tool result message/log entry, and public benchmark default-off versus opt-in trace behavior.
- Represent denied tools as trace/control-plane results and never execute or write archival/core memory on denial.
- Persist enough approval state in trace/message payloads to replay the pause/resume boundary used by benchmark smoke.
- On successful `archive_write`, emit a durable `tool_executed` result and a bounded tool result message/log entry with source refs and metadata that the v3 context path can include or explicitly diagnose as not applicable.
- Keep public benchmark case-level records separate for LongMemEval and LoCoMo; claim kernel usability only from opt-in kernel smoke plus focused tests, not from aggregate score movement.

## RED Evidence Required Before Implementation

- `tests/test_agent_kernel.py`: denied `archive_write` and unknown tools produce denial trace/result and do not create archival memory.
- `tests/test_agent_kernel.py`: approval pause emits a replayable approval id/state; resume with that id executes exactly once; repeated resume does not duplicate writes.
- `tests/test_agent_kernel.py` or `tests/test_context_composer.py`: successful `archive_write` creates a durable tool result message/log entry visible to a later v3 context build, or records a precise diagnostic if current scope makes visibility intentionally unavailable.
- `tests/test_public_benchmarks.py`: public benchmark without `MEMORYOS_AGENT_KERNEL=v1` has empty `kernel_trace_events`.
- `tests/test_public_benchmarks.py`: public benchmark with `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1` has non-empty `kernel_trace_events` with meaningful approval/tool result events.
- Existing v1 fallback and v3 default-off tests remain green.

## Verification Gate

Focused:
- `uv run pytest tests/test_agent_kernel.py -q`
- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_present_when_opted_in -q`

Baseline:
- `uv run pytest -q`
- `uv run ruff check .`

Opt-in kernel smoke, no LLM answer/judge:
- LongMemEval limit 5 with `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1`
- LoCoMo limit 5 with `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1`

Run 30-case full-chain LLM judge only if implementation changes answer/context behavior beyond tool-result visibility. If run, report LongMemEval and LoCoMo separately with case-level pass/fail, retrieval miss, evidence-hit-answer-fail, and kernel trace presence.

## Risks

- Approval replay may duplicate archival writes unless the approval/tool execution pair has an idempotence key or trace-backed duplicate guard.
- Denial handling could accidentally write memory if policy decision and execution are not separated cleanly.
- Tool result messages could pollute normal v3 benchmark context if kernel-off paths are not explicitly tested.
- Public benchmark trace fields could become event-name-only and misleading unless trace payloads preserve decision/result details.
- LoCoMo residual failures could be hidden by saying kernel traces exist; Phase 7 must not claim answer-quality improvement from control-plane instrumentation.
- Adding broad tools or Letta dependencies would exceed phase scope and make regression attribution harder.

## Demo-Only Would Mean

- Kernel behavior is proven only through direct unit tests, not through the real v3 public benchmark path.
- `kernel_trace_events` is non-empty but lacks durable denial/approval/tool result details.
- Approval pause/resume works only within one in-memory call stack and cannot cross the benchmark smoke boundary.
- A denied tool merely skips execution silently, or denial is not represented as a result the loop can reason about.
- Tool execution writes archival memory but leaves no later-context-visible result or explicit non-visibility diagnostic.
- Success is reported as aggregate benchmark movement without case-level LongMemEval and LoCoMo records.
- The kernel is enabled by default, v1 fallback changes, or answer prompt tuning is used to mask kernel incompleteness.
