# phase: phase-7

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Context used: `.hermes-loop/work/phase-7/context_bundle.md`, `.hermes-loop/work/phase-7/god_dispatch.json`, `.hermes-loop/work/phase-7/plan_final.md`, `.hermes-loop/work/phase-7/result.md`, `.hermes-loop/work/phase-7/execute_review.md`, `.hermes-loop/work/phase-7/reviews/codex-review-current.md` prior FAIL, and the current Phase 7 git diff.

## Lineage Gate

PASS. The prior blocking issue is fixed: `.hermes-loop/work/phase-7/execute_review.md:5` now explicitly cites `work/phase-7/context_bundle.md` as the controlling bundle. This satisfies the context-bundle lineage requirement from `.hermes-loop/work/phase-7/context_bundle.md:253`-`.hermes-loop/work/phase-7/context_bundle.md:255` and `.hermes-loop/work/phase-7/god_dispatch.json:105`-`.hermes-loop/work/phase-7/god_dispatch.json:108`.

## Code Gates

- Kernel opt-in is preserved. `Settings.memoryos_agent_kernel` still defaults to `"off"` in `src/memoryos_lite/config.py:29`-`src/memoryos_lite/config.py:30`, and `MemoryOSService.agent_kernel` is only constructed when `settings.resolved_agent_kernel == "v1"` in `src/memoryos_lite/engine.py:1490`-`src/memoryos_lite/engine.py:1507`.
- Default v3 public benchmark behavior remains kernel-off. The benchmark kernel probe only runs when `service.agent_kernel is not None`, the context has v3 metadata, and `settings.resolved_memory_arch == "v3"` in `src/memoryos_lite/evals.py:741`-`src/memoryos_lite/evals.py:747`; the default-off regression test asserts empty trace output in `tests/test_public_benchmarks.py:1897`-`tests/test_public_benchmarks.py:1913`.
- Denied tools do not execute or write memory in the inspected path. `decision.effect == "deny"` emits `tool_denied` and continues before execution in `src/memoryos_lite/agent_kernel.py:198`-`src/memoryos_lite/agent_kernel.py:221`; tests assert no `tool_executed`, no tool message, and no archival write in `tests/test_agent_kernel.py:108`-`tests/test_agent_kernel.py:170`.
- Approval replay no longer grants arbitrary or mismatched ids. Replay validates pending trace evidence by approval id, session id, tool name, and requested action in `src/memoryos_lite/agent_kernel.py:349`-`src/memoryos_lite/agent_kernel.py:368`; tests cover missing, session-mismatched, tool-mismatched, and tampered requests in `tests/test_agent_kernel.py:281`-`tests/test_agent_kernel.py:319`.
- Duplicate replay is guarded. Prior `tool_executed` traces are detected in `src/memoryos_lite/agent_kernel.py:392`-`src/memoryos_lite/agent_kernel.py:412`, and duplicate replay emits `tool_replay_skipped` without another archival memory or tool message in `tests/test_agent_kernel.py:266`-`tests/test_agent_kernel.py:278`.
- Successful tool execution is durable and later-context-visible at the current Phase 7 scope. `archive_write` persists archival memory in `src/memoryos_lite/agent_kernel.py:118`-`src/memoryos_lite/agent_kernel.py:135`, the runner persists a role `tool` message on successful execution in `src/memoryos_lite/agent_kernel.py:315`-`src/memoryos_lite/agent_kernel.py:322`, and the v3 composer includes stored messages in the recent layer in `src/memoryos_lite/context_composer.py:429`-`src/memoryos_lite/context_composer.py:442`. The test proves a later v3 context includes the tool result item in `tests/test_agent_kernel.py:322`-`tests/test_agent_kernel.py:361`.
- Public benchmark trace payloads are real structured events, not misleading event-name-only strings. `evals.py` now carries `event.model_dump(mode="json")` for both pending and resumed kernel steps in `src/memoryos_lite/evals.py:770`-`src/memoryos_lite/evals.py:797`, and the opt-in benchmark test asserts payload fields, approval id continuity, and executed result ids in `tests/test_public_benchmarks.py:1960`-`tests/test_public_benchmarks.py:2014`.
- Source grounding and LoCoMo failures are not hidden. `public_case_diagnostics.py` still derives failure class from retrieval/context/answer support status and only uses kernel traces for `kernel_trace_present` in `src/memoryos_lite/public_case_diagnostics.py:50`-`src/memoryos_lite/public_case_diagnostics.py:104`. The inspected smoke reports keep LongMemEval and LoCoMo separate: LongMemEval limit 5 has 1/5 pass with 5/5 non-empty traces; LoCoMo limit 5 has 0/5 pass with 5/5 non-empty traces and visible `retrieval_miss`/`evidence_hit_answer_fail` classes.
- I did not find expected-answer or case-id leakage in the Phase 7 kernel path. The public benchmark probe writes a generic `"Benchmark question reviewed: {case.question}"` trace payload in `src/memoryos_lite/evals.py:749`-`src/memoryos_lite/evals.py:757`; it does not consume expected answers or case ids for kernel decisions.

## Verification

Fresh review-lane commands:

- `uv run pytest tests/test_agent_kernel.py -q` -> `7 passed in 7.47s`.
- `uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q` -> `2 passed in 4.67s`.
- `uv run ruff check .` -> `All checks passed!`.
- `git diff --check -- src/memoryos_lite/agent_kernel.py src/memoryos_lite/evals.py src/memoryos_lite/public_benchmarks.py src/memoryos_lite/public_case_diagnostics.py tests/test_agent_kernel.py tests/test_public_benchmarks.py` -> exit 0.
- `uv run pytest -q` -> `400 passed, 1 warning in 622.02s`.

Smoke report inspection, without creating new benchmark artifacts:

- `.memoryos/evals/phase7_kernel_lme5_20260522_longmemeval.json`: 5 cases, 5/5 non-empty `kernel_trace_events`, 1 pass, failure classes `evidence_hit_answer_fail` x4 and `supported_cited_answer` x1.
- `.memoryos/evals/phase7_kernel_locomo5_20260522_locomo.json`: 5 cases, 5/5 non-empty `kernel_trace_events`, 0 passes, failure classes `retrieval_miss` x4 and `evidence_hit_answer_fail` x1.

## Residual Risks

- Idempotence depends on a persisted `tool_executed` trace. Because archival memory/message side effects happen before trace persistence in `src/memoryos_lite/agent_kernel.py:298`-`src/memoryos_lite/agent_kernel.py:340`, a crash between those operations could still allow duplicate replay.
- The role `tool` message is visible in v3 context as compact recent-layer text. Its full stored metadata is durable on the message record, but `ContextLayerItem.metadata` currently preserves only role/reason in `src/memoryos_lite/context_composer.py:433`-`src/memoryos_lite/context_composer.py:442`.
- The public benchmark kernel step is still a synthetic control-plane probe inside the benchmark path, not a full answer-generating agent loop. It should remain framed as kernel/control-plane usability evidence, not answer-quality improvement.
- Changing `kernel_trace_events` from `list[str]` to `list[dict]` is covered by updated tests, but any untested downstream report consumer expecting strings may need migration.

Verdict: PASS
