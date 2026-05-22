# phase: phase-7

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context source: `work/phase-7/context_bundle.md` was the controlling bundle for this execute self-review, together with `work/phase-7/god_dispatch.json`, `work/phase-7/plan_final.md`, and `work/phase-7/result.md`.

## Chain Changes

- `kernel_loop`: real opt-in path changed. The kernel now emits denial, pending approval, approval replay, execution, replay-skip, and completion traces with payloads.
- `store`: real SQLite-backed store path changed/verified through trace persistence, archival memory history, and persisted role `tool` messages.
- `context_composer`: verified through a later v3 context build that includes the role `tool` result message in the recent layer.
- `public_eval`: real public benchmark path changed to preserve structured `kernel_trace_events` when `MEMORYOS_AGENT_KERNEL=v1` is explicitly set.
- `answer_projection`: not changed. Phase 7 does not claim answer-quality improvement.

## Demo-Only Check

No blocking demo-only item remains for the Phase 7 scope:

- Denial is tested against real `archive_write` and unknown-tool requests.
- Approval replay crosses a cold store boundary.
- Duplicate approval replay is idempotent.
- Tool execution writes real archival memory and a real stored role `tool` message.
- Public benchmark trace output is tested through `run_public_benchmark`, not a direct kernel-only stub.

## Tests Proving Behavior

- Kernel RED before implementation: `5 failed, 2 passed`.
- Kernel GREEN: `uv run pytest tests/test_agent_kernel.py -q` -> `7 passed`.
- Public benchmark RED: opt-in trace test failed on string-only events.
- Public benchmark GREEN: focused default-off/opt-in tests -> `2 passed`.
- Full verification: `uv run pytest -q` -> `400 passed, 1 warning`; `uv run ruff check .` -> `All checks passed!`.

## Case-Level Movement

Final smokes are diagnostic no-LLM runs, so movement is `new_case_no_baseline`; there is no fail-to-pass or pass-to-fail claim.

LongMemEval limit 5:

- Pass/fail: `1/5`.
- `kernel_trace_events` non-empty structured traces: `5/5`.
- `evidence_hit_answer_fail`: `e47becba`, `118b2229`, `51a45a95`, `58bf7951`.
- `supported_cited_answer`: `1e043500`.

LoCoMo limit 5:

- Pass/fail: `0/5`.
- `kernel_trace_events` non-empty structured traces: `5/5`.
- `retrieval_miss`: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.
- `evidence_hit_answer_fail`: `conv-26_qa_001`.

## Constraints

- `MEMORYOS_AGENT_KERNEL=v1` remains opt-in and was only used explicitly in kernel smoke commands.
- Default v3 remains kernel-off.
- `MEMORYOS_MEMORY_ARCH=v1` fallback was not edited.
- No Letta runtime dependency was added.
- LoCoMo failures are not hidden; they remain the main residual benchmark risk.
