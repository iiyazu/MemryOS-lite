# phase: phase-7

Final plan summary for Phase 7, based on `work/phase-7/context_bundle.md` and the active goal: improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

Proceed with the durable opt-in control-plane slice from `work/phase-7/plan.md`.

Implementation order:

1. Add RED tests in `tests/test_agent_kernel.py` for denied `archive_write`, unknown-tool denial, cold-boundary approval replay from persisted pending evidence, invalid/mismatched approval replay denial, exactly-once approved execution, replay skip, and role `tool` result message visibility in later v3 context.
2. Add/update public benchmark RED tests so kernel traces remain empty by default and become non-empty, payload-bearing events only with `MEMORYOS_MEMORY_ARCH=v3 MEMORYOS_AGENT_KERNEL=v1`.
3. Implement denial result traces in `agent_kernel.py` without executing denied tools or writing memory.
4. Implement persisted approval replay validation from durable pending evidence, checking `session_id`, `approval_id`, `tool_name`, and requested action before execution.
5. Implement idempotence for approved replay so repeated approvals emit `tool_replay_skipped` and do not duplicate archival memory or tool messages.
6. Persist successful tool-result messages as role `tool` entries with tool metadata, approval id, result payload, and source refs so later v3 context can see the result through the normal recent-message path.
7. Preserve full payload-bearing kernel trace events through `evals.py`, `public_benchmarks.py`, and diagnostics without changing failure classification or answer-quality semantics.
8. Verify with focused kernel/public benchmark tests, full pytest, ruff, and separate LongMemEval and LoCoMo limit-5 opt-in kernel smokes.

Guardrails:

- Do not make `MEMORYOS_AGENT_KERNEL=v1` default.
- Do not change `MEMORYOS_MEMORY_ARCH=v3` default behavior into a kernel path.
- Do not change `MEMORYOS_MEMORY_ARCH=v1` fallback behavior.
- Do not add Letta as a runtime dependency.
- Do not tune answer prompts or use expected answers/case ids as kernel inputs.
- Do not hide LoCoMo residual failures behind trace presence or LongMemEval-only success.
