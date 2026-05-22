# phase: phase-7

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context source: `work/phase-7/context_bundle.md` was the controlling bundle for this execution result, together with `work/phase-7/god_dispatch.json` and `work/phase-7/plan_final.md`.

## Result

Phase 7 implemented an opt-in v3 kernel control-plane slice in the real MemoryOS v3/public benchmark path.

Changed chain components:

- `kernel_loop`: changed. Denied tools now emit `tool_denied`; approval replay validates persisted pending trace evidence by approval id, session id, tool name, and requested action; replay executes exactly once; duplicate replay emits `tool_replay_skipped`.
- `store`: changed/verified. Successful `archive_write` stores archival memory with approval ids on source refs and persists one role `tool` message.
- `context_composer`: verified. The persisted role `tool` message is visible through the normal v3 recent-message layer.
- `public_eval`: changed. Opt-in public benchmark reports now preserve JSON-safe, payload-bearing `kernel_trace_events` instead of event-name-only strings.
- `ingest`, `retrieval`, `answer_projection`: verified/not changed for Phase 7.

Kernel default remains unchanged: `MEMORYOS_AGENT_KERNEL=v1` is still required to enter the kernel path.

## RED Evidence

- `uv run pytest tests/test_agent_kernel.py -q` before kernel implementation: `5 failed, 2 passed`.
  - Missing `tool_denied`.
  - Pending approval payload lacked policy/replay metadata.
  - Arbitrary or mismatched approval ids still granted/executed.
  - Successful tool execution did not persist a role `tool` message visible to later v3 context.
- Public benchmark RED after test update:
  - Command: `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q`
  - Result: `1 failed, 1 passed`.
  - Failure: `TypeError: string indices must be integers, not 'str'`, proving opt-in `kernel_trace_events` still lost payloads as `list[str]`.

## Verification

- `uv run pytest tests/test_agent_kernel.py -q` -> `7 passed in 8.49s`.
- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q` -> `2 passed in 5.49s`.
- `git diff --check -- src/memoryos_lite/agent_kernel.py src/memoryos_lite/evals.py src/memoryos_lite/public_benchmarks.py src/memoryos_lite/public_case_diagnostics.py tests/test_agent_kernel.py tests/test_public_benchmarks.py` -> exit 0.
- `uv run ruff check .` -> `All checks passed!`.
- `uv run pytest -q` -> `400 passed, 1 warning in 562.67s`.

The `uv` commands printed the existing `VIRTUAL_ENV=/home/iiyatu/.hermes/hermes-agent/venv` mismatch warning and then used the project environment.

## Kernel Smokes

Both final smoke commands were run in parallel with explicit run ids to avoid the default timestamp run-id collision seen in an earlier parallel attempt.

LongMemEval:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark longmemeval \
  --data-path benchmarks/longmemeval/longmemeval.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase7_kernel_lme5_20260522
```

Report: `.memoryos/evals/phase7_kernel_lme5_20260522_longmemeval.json`.

- Pass/fail: `1/5`.
- `kernel_trace_events`: non-empty structured trace in `5/5`; each case had 9 events:
  `kernel_step_started -> tool_policy_decision -> approval_pending -> kernel_step_completed -> kernel_step_started -> tool_policy_decision -> approval_granted -> tool_executed -> kernel_step_completed`.
- Failures:
  - `evidence_hit_answer_fail`: `e47becba`, `118b2229`, `51a45a95`, `58bf7951`.
- Supported pass:
  - `supported_cited_answer`: `1e043500`.
- No broad answer-quality claim: no LLM answer/judge was run, and movement baseline was `new_case_no_baseline`.

LoCoMo:

```bash
MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1 uv run memoryos eval public \
  --benchmark locomo \
  --data-path benchmarks/locomo/locomo10.json \
  --baseline memoryos_lite \
  --limit 5 \
  --no-llm-answer \
  --no-llm-judge \
  --run-id phase7_kernel_locomo5_20260522
```

Report: `.memoryos/evals/phase7_kernel_locomo5_20260522_locomo.json`.

- Pass/fail: `0/5`.
- `kernel_trace_events`: non-empty structured trace in `5/5`; each case had the same 9-event approval/tool sequence as LongMemEval.
- Failures:
  - `evidence_hit_answer_fail`: `conv-26_qa_001`.
  - `retrieval_miss`: `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`.
- No broad answer-quality claim: no LLM answer/judge was run, and LoCoMo residual failures remain visible.

## Collision Note

An initial parallel smoke attempt without explicit `--run-id` caused the LoCoMo process to fail with `ValueError: session not found: ses_13c075de70cb`, consistent with both benchmark processes sharing the default second-resolution run id and one isolated run resetting the other's store. This was not treated as benchmark evidence. The final paired run used distinct explicit run ids and completed.
