# phase: phase-14

# Blueprint Amendment: Kernel Maintenance Sequence After Phase 13

Context bundle: `.hermes-loop/work/phase-14/context_bundle.md`.

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style
agent memory system for LongMemEval and LoCoMo, without demo-only phase
completion, without hiding case-level regressions, and without enabling the
v3 kernel by default.

## Triggering Evidence

- Phase 13 completed with usable ACK after core-memory lifecycle hardening.
- Manual true full-chain 5-case LLM judge smoke after phase 13:
  - LongMemEval: `5/5`, `answer_mode=llm`, `judge_status=judge_pass`,
    `source_hit=5/5`;
  - LoCoMo: `4/5`, `answer_mode=llm`, `judge_status=judge_pass/judge_fail`,
    `source_hit=2/5`.
- The kernel default remained off in all public benchmark runs.

## Original Hypothesis

The remaining kernel work should be expanded into a broad Letta-style agent
loop with additional tools and more autonomous behavior.

## New Hypothesis

The safest next kernel step is a narrow, auditable memory-action verifier first,
followed by a diagnostic maintenance planner, then a small maintenance tool
surface, and only after that a LoCoMo repair evaluation and benchmark-governed
promotion gate.

## Affected Phases

- Phase 14 remains a narrow opt-in kernel verification phase.
- Phase 15 becomes a diagnostic maintenance planner for kernel memory actions.
- Phase 16 becomes the maintenance tool-surface phase.
- Phase 17 becomes the LoCoMo maintenance repair evaluation phase.
- Phase 18 becomes benchmark governance and promotion.

## Changed Ordering and Scope

1. Keep Phase 14 focused on `archive_write` verification and replay safety.
2. Insert a diagnostic planner phase before broadening the kernel tool surface.
3. Delay benchmark governance until maintenance artifacts have been tested
   through the real v3 context path.

## Next Minimum Verification Command

When Phase 14 executes, begin with the focused kernel tests and public trace
smoke already specified in `work/phase-14/plan_final.md`:

```bash
uv run pytest tests/test_agent_kernel.py -q
uv run pytest tests/test_public_benchmarks.py::test_public_benchmark_kernel_trace_remains_default_off tests/test_public_benchmarks.py::test_public_benchmark_runs_kernel_step_when_v3_kernel_enabled -q
```

## Notes

- This amendment does not enable the kernel by default.
- This amendment does not claim benchmark improvement.
- This amendment preserves the explicit `v1` fallback and `v3` default.

## Additional Eval Isolation Amendment

Triggered by phase-13 reflection evidence.

Parallel public benchmark gates and smokes must use isolated `DATA_DIR`
values per benchmark and run id. Reports from a shared default `.memoryos`
store are invalid for promotion if either parallel process crashes,
cross-contaminates sessions, or cannot prove store isolation. Record each
`DATA_DIR` and report path in the phase result.

## Additional Letta Kernel Boundary Amendment

Triggered by the Phase 14+ review against Letta's kernel/tool execution model.

Letta's relevant design boundary is that the agent emits tool calls, approval is
bound to the pending tool-call message, execution returns a structured
success/error result, and memory changes are routed through managers before the
tool return is persisted. MemoryOS should borrow those semantics without adding
Letta as a dependency.

New hard requirements promoted into the root blueprint:

- approval replay must bind to the pending step/tool-call identity or request
  fingerprint, not only a globally searched `approval_id`;
- `tool_verified` must have both success and failure semantics, and failed
  verification must be durable;
- tool-return messages must carry enough compact verification information for
  replay/idempotency checks;
- benchmark gold fields such as expected answers and expected source ids are
  eval-only sidecars and cannot drive memory writes, tool arguments, source
  refs, archive attachments, passage links, or promotion candidates;
- same-slice LoCoMo repair can be a structural smoke only; quality claims need a
  clean-store or held-out validation gate.

This amendment narrows Phase 15-17 rather than broadening Phase 14. Phase 14
still remains an opt-in kernel verification phase and must not change default
public benchmark behavior.

## Kernel Graduation Spec Promotion

Spec source:
`docs/superpowers/specs/2026-05-24-kernel-agent-graduation-blueprint-design.md`.

The active root blueprint now contains the graduated K0-K5 kernel roadmap:

- K0/K1 are the Phase 14 contract-freeze and audited `archive_write` loop.
- K2 is added to Phase 15 before planner execution: hybrid tool selection is
  default-on inside an enabled kernel, but constrained by deterministic
  candidates and fail-closed policy.
- K3 is Phase 16's graduated tool surface: write-safe, read/search, then
  controlled core edits only after a safety gate.
- K4 is split across Phase 15 planner design and Phase 17 opt-in repair smoke
  plus clean-store or held-out validation.
- K5 is Phase 18 governance and promotion control.

This promotion does not change `.hermes-loop/state.json`, does not enable the
kernel by default, and does not claim benchmark improvement.
