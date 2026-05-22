# phase: phase-7

Active goal: Improve MemoryOS Lite v3 into a benchmark-usable Letta-style agent memory system for LongMemEval and LoCoMo, without demo-only phase completion, without hiding case-level regressions, and without enabling the v3 kernel by default.

## Alignment

Phase 7 aligned with the active goal at the kernel/control-plane layer. The implemented work stays on the real v3/public benchmark path while preserving `MEMORYOS_AGENT_KERNEL=v1` as opt-in, keeps default v3 kernel-off behavior, and does not claim LoCoMo improvement by hiding case-level misses. The useful gain is a durable, auditable kernel slice: denied tools do not execute, approval replay crosses a cold boundary, duplicate replay is guarded by persisted trace evidence, successful `archive_write` produces trace and tool-message side effects, and opt-in public benchmark output now carries structured `kernel_trace_events`.

This is benchmark-usable control-plane evidence, not evidence that the kernel improves answer quality. Phase 7 did not change answer projection, and the public benchmark probe remains synthetic rather than a full answer-generating agent loop.

## Advance Decision

Phase 7 should advance.

Reasons:

- Review verdict is `PASS` with no blocking issues.
- ACK level is `usable` and decision is `advance`.
- Focused and full verification passed: kernel tests, public benchmark default-off/opt-in tests, `ruff`, and full `pytest`.
- The phase avoided the main forbidden outcomes: no default kernel enablement, no v1 fallback rewrite, no Letta dependency, no demo-only completion, and no hidden LoCoMo failures.

The advance should be scoped as completion of `kernel-opt-in-usable`, not as completion of the broader Letta-style memory system.

## Case-Level Evidence Limits

The Phase 7 smokes were no-LLM diagnostic runs, so they cannot support fail-to-pass, pass-to-fail, or judged answer-quality claims.

LongMemEval limit 5 showed `1/5` pass with structured kernel traces in `5/5`. Failures remained visible as `evidence_hit_answer_fail` for `e47becba`, `118b2229`, `51a45a95`, and `58bf7951`.

LoCoMo limit 5 showed `0/5` pass with structured kernel traces in `5/5`. Failures remained visible as `retrieval_miss` for `conv-26_qa_002`, `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_005`, and `evidence_hit_answer_fail` for `conv-26_qa_001`.

These runs prove trace plumbing through the public benchmark path when explicitly opted in. They do not prove retrieval improvement, answer improvement, or LoCoMo regression recovery.

## Residual Risks

- Crash-window idempotence still depends on persisting `tool_executed` after archival memory and tool-message side effects; a crash in between could permit duplicate replay.
- The role `tool` message is visible to later v3 context as recent-layer text, but full tool metadata is durable on the message record rather than rendered into `ContextLayerItem.metadata`.
- `kernel_trace_events` changed from event-name strings to structured dictionaries; updated tests cover the intended path, but untested downstream report consumers may still expect strings.
- The benchmark kernel path is still a control-plane probe, not a full Letta-style step loop integrated into answer generation.
- LoCoMo remains the main benchmark risk; Phase 7 preserved its misses instead of addressing them.

## Blueprint Changes

No blueprint change is needed now. The active Phase 7 blueprint already required opt-in kernel behavior, durable traces, approval/tool semantics, context-visible tool results, public benchmark kernel traces, and no default kernel enablement. The implementation and review evidence match that scope.

The blueprint should not be broadened retroactively to claim answer-quality progress. Any future blueprint change should happen in the next phase only if the controller explicitly moves from control-plane usability into answer-path integration or LoCoMo retrieval/source-grounding work.

## Recommended Next Phase Focus

Phase 8 should focus on the benchmark failure surface that Phase 7 intentionally left visible:

- Preserve the opt-in kernel default while deciding whether kernel traces should remain a synthetic probe or become part of a real answer-generation loop.
- Address LoCoMo retrieval misses and evidence-hit-answer-fail cases at case level, with same-case comparisons and no expected-answer leakage.
- Add crash-window/idempotence hardening if the next phase continues kernel mutation work.
- Decide whether structured `kernel_trace_events` needs a compatibility shim or documented schema for downstream consumers.

The next phase should not use kernel trace presence as success by itself; it should require case-level evidence that retrieval, context packaging, or answer behavior improved without regressions.
